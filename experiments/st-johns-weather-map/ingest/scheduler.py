"""Restart reconciliation and the idempotency check, on the ingest side.

`ingestion-worker-scheduling` requires a restart to *resume* the window rather
than refill it: sweep abandoned staging, purge what left the window, then fetch
only what is missing. `artifact-ingestion` requires the missing set to be
decided by asking the store which `(source_id, provider_run_id, valid_time)`
keys it already holds, and requires the source to fail rather than read an
unreadable store as an empty one.

Everything here is a decision, not an effect: the functions take a store and
return what the worker should do, so the rules can be exercised without a live
PostgreSQL or MinIO. ``worker/runtime.py`` is the one caller.

The store side is a small protocol, recorded in the change's ``design.md``
under "Seam" so the storage owner can match it:

    present_keys(source_id, provider_run_id) -> set[int]   # valid times, ns
    sweep_abandoned_staging() -> int
    purge_outside_window(now) -> int
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Protocol, Sequence

from .validate import to_nanoseconds
from .window import sliding_window

if TYPE_CHECKING:  # pragma: no cover - typing only, and keeps this module registry-free
    from .registry import IngestConfig, PublicationLatency

UTC = timezone.utc

#: How often a forecast run is polled for once its first attempt has passed.
#: ``next_due`` reads the bound from the same run cadence, so the two agree on
#: one number.
POLL_INTERVAL_SECONDS = 600

#: The quantile the latency estimator converges on, and the two step sizes that
#: produce it. ``design.md`` left the statistic open between a rolling median
#: and a high quantile; this is the high-quantile answer, written as asymmetric
#: exponential smoothing so the whole estimator's state is the estimate and its
#: count - which is exactly what ``PublicationLatency`` carries and what the
#: heartbeat can hold across a restart. A step up four times the step down
#: converges on the 0.8 quantile: a run that publishes late raises the estimate
#: quickly, and a run that publishes early lowers it slowly, so the schedule
#: gives up a little horizon rather than fetching an absent run half the time.
LATENCY_STEP_UP = 0.4
LATENCY_STEP_DOWN = 0.1
LATENCY_QUANTILE = LATENCY_STEP_UP / (LATENCY_STEP_UP + LATENCY_STEP_DOWN)

#: The reason an idempotent no-op states. `ingestion-worker-scheduling`
#: requires the outcome to be `succeeded` with zero artifacts and a reason
#: naming the satisfied window, so an idempotent no-op is never mistaken for an
#: upstream failure.
SATISFIED_REASON = "the retained window already holds every frame of this provider run; nothing fetched"

#: Absence states a derived artifact's input can be in, worst last. `null` is
#: ranked worse than `aged_out` because an aged-out input names a last valid
#: time the reader can act on, while a null input says nothing was ever held
#: here at all - so a derived artifact reporting its worst input reports the
#: less informative state, never the more flattering one.
ABSENCE_RANK = {"present": 0, "aged_out": 1, "null": 2}

__all__ = [
    "ABSENCE_RANK",
    "BEYOND_BOTH",
    "JOIN_EPSILON",
    "LATENCY_QUANTILE",
    "LATENCY_STEP_DOWN",
    "LATENCY_STEP_UP",
    "NO_PREVIOUS_RUN",
    "POLL_INTERVAL_SECONDS",
    "SATISFIED_REASON",
    "DerivedPlan",
    "FetchPlan",
    "InputState",
    "PollDecision",
    "PollState",
    "Reconciliation",
    "RestartCache",
    "RetainedRun",
    "Schedule",
    "ServedRange",
    "ShortCyclePlan",
    "candidate_valid_times",
    "derived_plan",
    "first_attempt",
    "latest_run_time",
    "latency_heartbeat_block",
    "next_due",
    "next_run_time",
    "observe_latency",
    "plan_fetch",
    "poll_decision",
    "reconcile_on_start",
    "retained_runs",
    "short_cycle_plan",
    "worst_absence",
]


# --- when a source is next attempted -------------------------------------

def latest_run_time(run_cadence_seconds: int, now: datetime) -> datetime:
    """The most recent nominal run instant at or before ``now``.

    Cycles are anchored on the UTC epoch, which is a midnight, so a 6 h cadence
    lands on 00/06/12/18Z and an hourly one on the hour. Nothing here consults
    what a provider has actually published: this is the *nominal* run time, and
    the gap between it and the publication is exactly what ``first_attempt``
    exists to carry.
    """
    if run_cadence_seconds <= 0:
        raise ValueError("run cadence must be a positive number of seconds")
    moment = now if now.tzinfo else now.replace(tzinfo=UTC)
    epoch_seconds = moment.timestamp()
    floored = (epoch_seconds // run_cadence_seconds) * run_cadence_seconds
    return datetime.fromtimestamp(floored, UTC)


def next_run_time(run_cadence_seconds: int, now: datetime) -> datetime:
    """The next nominal run instant strictly after ``now``.

    This is the bound task 2.2's poll stops at: past it the missing run is
    superseded rather than late.
    """
    return latest_run_time(run_cadence_seconds, now) + timedelta(seconds=run_cadence_seconds)


def first_attempt(run_time: datetime, latency: "PublicationLatency | None") -> datetime:
    """When a forecast run is first asked for.

    ``run_time + estimate_seconds`` where an estimate exists, and the run time
    *exactly* where none does. The second half matters as much as the first: a
    record with no measured latency and no seed (REPS, GDPS, WeatherNext 2)
    must not borrow another source's offset, because a guessed offset is
    indistinguishable downstream from a measured one.
    """
    moment = run_time if run_time.tzinfo else run_time.replace(tzinfo=UTC)
    estimate = getattr(latency, "estimate_seconds", None) if latency is not None else None
    if estimate is None:
        return moment
    return moment + timedelta(seconds=int(estimate))


def observe_latency(
    previous: "PublicationLatency | None",
    *,
    run_time: datetime,
    observed_at: datetime,
) -> "PublicationLatency":
    """Fold one *observed* publication into a source's latency estimate.

    ``observed_at`` is the instant this deployment actually saw the run of
    ``run_time`` present - the successful attempt, not the estimate that
    predicted it and not a producer's promise. The result always carries
    ``measured: True``, an observation count one higher than before, and a
    ``basis`` naming this deployment's own observations, so nothing downstream
    can read a seed as a measurement or a measurement as a seed.

    The estimator is asymmetric exponential smoothing, which converges on the
    ``LATENCY_QUANTILE`` quantile of the observed latencies while keeping only
    the estimate and the count as state (see the constants above for why a high
    quantile rather than a median). The first observation of an unseeded source
    *is* the estimate: there is nothing yet to move away from, and inventing a
    smoothed value there would publish a number no run ever produced.

    Only ever called from an observed publication: a bounded-out poll writes
    nothing, which is what leaves the previous estimate and its count intact.
    """
    run_moment = run_time if run_time.tzinfo else run_time.replace(tzinfo=UTC)
    seen_moment = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=UTC)
    # A run seen at or before its own nominal time is a zero-second latency, not
    # a negative one: the schedule cannot ask for a run before it exists.
    observed_seconds = max(0.0, (seen_moment - run_moment).total_seconds())

    prior = getattr(previous, "estimate_seconds", None) if previous is not None else None
    count = int(getattr(previous, "observation_count", 0) or 0) if previous is not None else 0
    if prior is None:
        estimate = observed_seconds
    else:
        step = LATENCY_STEP_UP if observed_seconds > float(prior) else LATENCY_STEP_DOWN
        estimate = float(prior) + step * (observed_seconds - float(prior))
    count += 1

    fields = {
        "estimate_seconds": int(round(estimate)),
        "observation_count": count,
        "last_observed": seen_moment,
        "measured": True,
        "basis": (
            f"measured here: {count} observed publication(s) by this deployment, "
            f"asymmetric quantile p={LATENCY_QUANTILE:.2f}"
        ),
    }
    if previous is not None:
        from dataclasses import replace  # noqa: PLC0415 - local, keeps the module registry-free

        return replace(previous, **fields)
    from .registry import PublicationLatency  # noqa: PLC0415 - only when there is no previous block

    return PublicationLatency(**fields)


def latency_heartbeat_block(latency: "PublicationLatency | None") -> dict[str, Any]:
    """The heartbeat's ``publication_latency`` block, exactly as the seam names it.

    ``latency_measured`` rather than ``measured``: the heartbeat's reader is the
    healthcheck and the operator, and the question they are asking of a number
    on a liveness document is whether *the latency* was measured.
    """
    last_observed = getattr(latency, "last_observed", None) if latency is not None else None
    return {
        "estimate_seconds": getattr(latency, "estimate_seconds", None) if latency is not None else None,
        "observation_count": int(getattr(latency, "observation_count", 0) or 0) if latency is not None else 0,
        "last_observed": last_observed.isoformat() if isinstance(last_observed, datetime) else None,
        "latency_measured": bool(getattr(latency, "measured", False)) if latency is not None else False,
        "basis": str(getattr(latency, "basis", "none")) if latency is not None else "none",
    }


@dataclass(frozen=True)
class Schedule:
    """When one source is next attempted, and on what grounds.

    ``kind`` is ``forecast`` (scheduled against a producer run), ``native``
    (scheduled against a publication interval) or ``unscheduled``. An
    unscheduled decision carries ``due=None`` and a ``reason`` naming the field
    that is missing, so a source is never silently dropped from the rotation.
    """

    source_id: str
    kind: str
    due: datetime | None = None
    run_time: datetime | None = None
    cadence_seconds: int | None = None
    latency_measured: bool = False
    reason: str = ""

    @property
    def scheduled(self) -> bool:
        return self.due is not None

    def delay_seconds(self, now: datetime) -> float:
        """Seconds from ``now`` until the attempt, never negative."""
        if self.due is None:
            raise ValueError(f"{self.source_id} is not scheduled: {self.reason}")
        return max(0.0, (self.due - now).total_seconds())


def next_due(
    config: "IngestConfig",
    *,
    now: datetime,
    after: datetime | None = None,
    latency: "PublicationLatency | None" = None,
) -> Schedule:
    """Decide when ``config``'s source is attempted next.

    A forecast source is attempted at its run's first-attempt instant: the
    latest nominal run plus the measured latency, or the run time itself where
    nothing is measured. An observation or nowcast source is attempted every
    ``native_cadence_seconds`` - its own publication interval, never rounded up
    onto a shared poll floor, which is what folded six-minute radar onto a
    five-minute rotation and hourly METAR onto the same one.

    ``after`` is the instant a scheduled attempt has just been made at; the
    result is then the *next* attempt strictly after it.

    ``latency`` overrides the record's block with the *live* one the worker
    holds: once this deployment has observed a publication, the next first
    attempt is placed on the re-measured estimate rather than back on the seed.
    Passing nothing keeps the record's own block, which is what a caller with
    no live state (and every pure test of the record) wants.
    """
    source_id = str(getattr(config, "source_id", "") or "")
    moment = now if now.tzinfo else now.replace(tzinfo=UTC)
    if latency is None:
        latency = getattr(config, "publication_latency", None)
    measured = bool(getattr(latency, "measured", False)) if latency is not None else False

    if getattr(config, "reach", None) is None:
        return Schedule(
            source_id, "unscheduled", latency_measured=measured,
            reason="the record declares no reach; an unbounded source cannot be said to cover any instant",
        )

    run_cadence = getattr(config, "run_cadence_seconds", None)
    native_cadence = getattr(config, "native_cadence_seconds", None)

    if run_cadence:
        run = latest_run_time(int(run_cadence), moment)
        due = first_attempt(run, latency)
        # Walk forward a whole run at a time rather than adding a poll: the
        # next attempt for a forecast source belongs to the next *run*.
        while after is not None and due <= after:
            run = run + timedelta(seconds=int(run_cadence))
            due = first_attempt(run, latency)
        offset = int(getattr(latency, "estimate_seconds", None) or 0)
        reason = (
            f"run {run.isoformat()} plus a measured latency of {offset}s" if offset
            else f"run {run.isoformat()} exactly; no latency is measured for this source"
        )
        return Schedule(source_id, "forecast", due=due, run_time=run, cadence_seconds=int(run_cadence),
                        latency_measured=measured, reason=reason)

    if native_cadence:
        base = after if after is not None else moment
        due = base + timedelta(seconds=int(native_cadence)) if after is not None else base
        return Schedule(source_id, "native", due=due, cadence_seconds=int(native_cadence),
                        latency_measured=measured,
                        reason=f"native cadence of {int(native_cadence)}s")

    return Schedule(
        source_id, "unscheduled", latency_measured=measured,
        reason="the record declares neither run_cadence_seconds nor native_cadence_seconds; nothing to schedule against",
    )


# --- polling for a run that has not appeared yet -------------------------

@dataclass(frozen=True)
class PollState:
    """One source's open poll: which run it is waiting for, and since when.

    Held per source by ``worker/runtime.py`` and carried into the heartbeat, so
    a run that appears late can be reported with the instant it was actually
    first seen at (task 2.3) rather than with the estimate that missed it.
    """

    run_time: datetime
    since: datetime
    attempts: int = 0
    provider_run_id: str | None = None

    def as_progress(self) -> dict[str, Any]:
        return {
            "run_time": self.run_time.isoformat(),
            "since": self.since.isoformat(),
            "attempts": int(self.attempts),
        }


@dataclass(frozen=True)
class PollDecision:
    """Poll again, or stop because the missing run has been superseded.

    ``exhausted`` is the only state that reports anything: every poll before
    the bound is an absence, not a failure, because the run being late is
    exactly what the poll exists to absorb. At the bound the next run of the
    same source is due, so the missing one is superseded rather than late, and
    the outcome is a ``cancelled`` that names the run and how long it was
    waited for. Nothing is fetched in its place, and the previous run stays
    visible because nothing here touches it.
    """

    state: PollState
    bound: datetime
    due: datetime | None
    exhausted: bool
    polled_seconds: float
    detail: str

    @property
    def polled_minutes(self) -> int:
        return int(round(self.polled_seconds / 60.0))


def poll_decision(
    state: PollState,
    *,
    run_cadence_seconds: int,
    now: datetime,
    interval_seconds: int = POLL_INTERVAL_SECONDS,
) -> PollDecision:
    """Whether to poll ``state``'s run again, and when.

    The bound is the next nominal run time for that source: past it the run
    being waited for is superseded, not late, and a poll that carried on would
    spin for as long as the upstream stayed broken. The final poll lands
    exactly on the bound, so the window is closed by an attempt rather than by
    a clock the source never got to answer.
    """
    if run_cadence_seconds <= 0:
        raise ValueError("run cadence must be a positive number of seconds")
    moment = now if now.tzinfo else now.replace(tzinfo=UTC)
    bound = state.run_time + timedelta(seconds=int(run_cadence_seconds))
    polled = max(0.0, (moment - state.since).total_seconds())
    named = state.provider_run_id or state.run_time.isoformat()
    if moment >= bound:
        minutes = int(round(polled / 60.0))
        return PollDecision(
            state, bound, None, True, polled,
            f"run {named} did not appear after polling {minutes} min; previous run stays visible",
        )
    due = min(moment + timedelta(seconds=int(interval_seconds)), bound)
    return PollDecision(
        state, bound, due, False, polled,
        f"polling for run {state.run_time.isoformat()}; attempt {state.attempts} found nothing, "
        f"next poll at {due.isoformat()}, bounded by {bound.isoformat()}",
    )


# --- a short cycle: two runs, two labelled ranges -------------------------

@dataclass(frozen=True)
class RetainedRun:
    """One run this deployment still holds, and how far it can serve.

    ``reach_end`` is the declared reach of *this run's cycle*
    (``Reach.span(run_time)[1]``), which is the whole reason a short cycle
    exists: IFS reaches 360 h from 00z and 12z and 144 h from 06z and 18z, so
    the newest run of a source can reach less far than the one before it.

    ``published_start``/``published_end`` are the valid times this run
    *actually* published, where they are known. They only ever narrow the
    range: a run that promised 360 h and delivered 120 h serves 120 h, and a
    run that delivered more than it promised is still held to the promise.
    Passing neither leaves the run on its declared reach alone.
    """

    source_id: str
    provider_run_id: str
    run_time: datetime
    reach_end: datetime
    published_start: datetime | None = None
    published_end: datetime | None = None

    @property
    def serves_from(self) -> datetime:
        """The first valid time this run can serve on its own."""
        return self.published_start if self.published_start is not None else self.run_time

    @property
    def serves_to(self) -> datetime:
        """The last valid time this run can serve: reach, narrowed by delivery."""
        if self.published_end is None:
            return self.reach_end
        return min(self.reach_end, self.published_end)


#: The join between the two runs is exclusive on the newer run's last instant:
#: an instant the newer run serves is never also claimed by the older one. The
#: previous run's range therefore opens one second later. Every source here
#: publishes leads on whole-hour (or coarser) steps, so a second cannot hide a
#: frame between the two ranges, and it keeps both ends of the join printable
#: as distinct instants rather than as one instant with a footnote.
JOIN_EPSILON = timedelta(seconds=1)

NO_PREVIOUS_RUN = "no previous run was retained"
BEYOND_BOTH = "beyond both runs' reach"


@dataclass(frozen=True)
class ServedRange:
    """One run serving one contiguous span of valid times, under its own label.

    ``role`` is ``newest`` or ``previous``. Both carry ``run_time`` because the
    requirement is that both runs are labelled with their own run time wherever
    they are served or drawn - a range that lost its run time is exactly the
    blended series the requirement refuses.
    """

    role: str
    provider_run_id: str
    run_time: datetime
    start: datetime
    end: datetime
    start_exclusive: bool = False

    def covers(self, instant: datetime) -> bool:
        after_start = self.start < instant if self.start_exclusive else self.start <= instant
        return after_start and instant <= self.end


@dataclass(frozen=True)
class ShortCyclePlan:
    """Which run serves which leads, once the newest run reaches less far.

    Two labelled pieces of evidence, never one series: ``newest`` serves up to
    its own end and ``previous`` serves *only* beyond it, so the two ranges
    cannot overlap and nothing is averaged, interpolated or extrapolated across
    the join. Past ``covered_to`` the source is uncovered, with
    ``uncovered_reason`` saying whether that is because no previous run was
    retained or because neither run reaches that far.

    Nothing here deletes, refetches or shortens anything: it is a reading of
    what retention already holds. The two-run ceiling in
    ``003_retention_window.sql`` is what keeps the previous run available, and
    this plan only says what to do with it.
    """

    source_id: str
    newest: ServedRange
    previous: ServedRange | None
    covered_to: datetime
    uncovered_reason: str
    retained_previous_run_time: datetime | None = None

    @property
    def short_cycle(self) -> bool:
        """True when a retained previous run is serving leads the newest lacks."""
        return self.previous is not None

    @property
    def ranges(self) -> list[ServedRange]:
        """The labelled ranges, newest first. Never fewer than one."""
        return [self.newest] if self.previous is None else [self.newest, self.previous]

    def serving(self, instant: datetime) -> ServedRange | None:
        """The one range that serves ``instant``, or ``None`` if it is uncovered."""
        for served in self.ranges:
            if served.covers(instant):
                return served
        return None

    @property
    def detail(self) -> str:
        if self.previous is None:
            return (
                f"run {self.newest.run_time.isoformat()} serves to "
                f"{self.newest.end.isoformat()}; beyond that {self.uncovered_reason}"
            )
        return (
            f"short cycle: run {self.newest.run_time.isoformat()} serves to "
            f"{self.newest.end.isoformat()}, retained run {self.previous.run_time.isoformat()} "
            f"serves {self.previous.start.isoformat()} to {self.previous.end.isoformat()}; "
            f"beyond that {self.uncovered_reason}"
        )

    def as_progress(self) -> dict[str, Any]:
        """The heartbeat's ``short_cycle`` block, exactly as the seam names it."""
        retained = self.retained_previous_run_time
        return {
            "newest_run_time": self.newest.run_time.isoformat(),
            "newest_serves_to": self.newest.end.isoformat(),
            "previous_run_time": retained.isoformat() if retained is not None else None,
            "previous_serves_from": self.previous.start.isoformat() if self.previous else None,
            "previous_serves_to": self.previous.end.isoformat() if self.previous else None,
        }


def short_cycle_plan(previous: RetainedRun | None, newest: RetainedRun) -> ShortCyclePlan:
    """Which leads each retained run serves when the newest reaches less far.

    The newest run always serves first and serves everything it reaches. The
    previous run is called on *only* beyond the newest run's end, and only
    where it actually reaches further - a previous run that reaches no further
    serves nothing, because there is no lead for it to add. Where the previous
    run is absent, or where both runs stop, the source is uncovered and says
    which of the two it is: nothing is extrapolated from a final lead.

    Pure: no store, no clock, no registry lookup. ``worker/runtime.py`` builds
    the two ``RetainedRun`` values from what the store still holds and records
    the result; the API serves the ranges (tasks 3.1 and 3.2).
    """
    newest_range = ServedRange(
        "newest", newest.provider_run_id, newest.run_time, newest.serves_from, newest.serves_to,
    )
    if previous is None:
        return ShortCyclePlan(newest.source_id, newest_range, None, newest_range.end, NO_PREVIOUS_RUN)

    if previous.source_id != newest.source_id:
        raise ValueError(
            f"two runs of different sources cannot serve one span: "
            f"{previous.source_id!r} and {newest.source_id!r}"
        )
    if previous.run_time >= newest.run_time:
        raise ValueError(
            f"{newest.source_id}: the previous run {previous.run_time.isoformat()} is not older "
            f"than the newest run {newest.run_time.isoformat()}"
        )

    if previous.serves_to <= newest_range.end:
        # Not a short cycle: the newest run reaches at least as far, so the
        # retained run adds no lead. It is still retained - nothing here drops
        # it - it simply serves nothing.
        return ShortCyclePlan(
            newest.source_id, newest_range, None, newest_range.end, BEYOND_BOTH,
            retained_previous_run_time=previous.run_time,
        )

    previous_range = ServedRange(
        "previous", previous.provider_run_id, previous.run_time,
        newest_range.end + JOIN_EPSILON, previous.serves_to, start_exclusive=True,
    )
    return ShortCyclePlan(
        newest.source_id, newest_range, previous_range, previous_range.end, BEYOND_BOTH,
        retained_previous_run_time=previous.run_time,
    )


def retained_runs(config: "IngestConfig", artifacts: Iterable[Any]) -> list[RetainedRun]:
    """Group retained revisions into runs, newest run first.

    ``artifacts`` are ``ingest.store.RetainedArtifact`` values - anything with
    ``provider_run_id``, ``provenance``, ``valid_time_start`` and
    ``valid_time_end`` will do, which is what keeps this testable without a
    live store.

    A run is keyed by its adapter-declared ``provenance["run_time"]``. A run
    that declared none is skipped: a reach is stated relative to a run time, so
    there is nothing to measure one against, and the ``model_runs`` retrieval
    stamp is not a run-time claim (``design.md``, "Where the code lives").
    """
    reach = getattr(config, "reach", None)
    if reach is None:
        return []
    source_id = str(getattr(config, "source_id", "") or "")
    grouped: dict[tuple[str, datetime], dict[str, Any]] = {}
    for artifact in artifacts:
        run_time = _instant(getattr(artifact, "provenance", None) or {})
        if run_time is None:
            continue
        key = (str(getattr(artifact, "provider_run_id", "") or ""), run_time)
        entry = grouped.setdefault(key, {"start": None, "end": None})
        for name, bound in (("start", getattr(artifact, "valid_time_start", None)),
                            ("end", getattr(artifact, "valid_time_end", None))):
            if not isinstance(bound, datetime):
                continue
            moment = bound if bound.tzinfo else bound.replace(tzinfo=UTC)
            current = entry[name]
            if current is None:
                entry[name] = moment
            else:
                entry[name] = min(current, moment) if name == "start" else max(current, moment)
    runs = [
        RetainedRun(
            source_id=source_id, provider_run_id=run_id, run_time=run_time,
            reach_end=reach.span(run_time)[1],
            published_start=entry["start"], published_end=entry["end"],
        )
        for (run_id, run_time), entry in grouped.items()
    ]
    runs.sort(key=lambda run: run.run_time, reverse=True)
    return runs


def _instant(provenance: Mapping[str, Any]) -> datetime | None:
    """The adapter-declared run time of a revision, or ``None``."""
    value = provenance.get("run_time")
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class RestartCache(Protocol):
    """What the ingest side needs of the store to resume a window."""

    def present_keys(self, source_id: str, provider_run_id: str) -> set[int]:
        """Valid times in nanoseconds already published under this run key."""

    def sweep_abandoned_staging(self) -> int:
        """Discard staged rows and objects left by an interrupted run."""

    def purge_outside_window(self, now: datetime) -> int:
        """Purge retained frames whose valid time left the sliding window."""


# --- restart reconciliation ---------------------------------------------

@dataclass(frozen=True)
class Reconciliation:
    """The result of the three start-up steps, in the order they must run."""

    healthy: bool
    swept: int = 0
    purged: int = 0
    detail: str = ""

    @property
    def may_fetch(self) -> bool:
        """A worker that could not read the store must not fetch: it would
        refetch everything, which is how a restart becomes an outage on the
        constraint that actually binds."""
        return self.healthy


def reconcile_on_start(store: Any, *, now: datetime | None = None) -> Reconciliation:
    """Sweep abandoned staging, purge outside the window, then allow fetching.

    The store is never cleared on start and no frame inside the window is
    removed. A store that cannot be read yields an unhealthy reconciliation
    that schedules nothing, rather than an empty one that refetches the world.
    """
    moment = now or datetime.now(UTC)
    if store is None:
        return Reconciliation(False, detail="no artifact store is available; the window cannot be read")
    try:
        swept = int(store.sweep_abandoned_staging())
    except Exception as error:
        return Reconciliation(False, detail=f"abandoned staging could not be swept: {error!r}")
    try:
        purged = int(store.purge_outside_window(moment))
    except Exception as error:
        return Reconciliation(False, swept=swept, detail=f"the window could not be purged: {error!r}")
    return Reconciliation(
        True,
        swept=swept,
        purged=purged,
        detail=f"swept {swept} abandoned staged revision(s), purged {purged} frame(s) outside the window",
    )


# --- the idempotency check ----------------------------------------------

def candidate_valid_times(candidate: Any) -> tuple[datetime, ...]:
    """The instants a discovered candidate says it carries.

    Discovery states these in ``RunCandidate.detail['valid_times']``. A
    candidate that states none is not treated as covering nothing: the worker
    fetches it, because a run whose frames the store cannot be asked about is
    exactly the case where assuming would drop evidence.
    """
    stamps: list[datetime] = []
    for raw in (getattr(candidate, "detail", None) or {}).get("valid_times") or ():
        if isinstance(raw, datetime):
            stamps.append(raw)
            continue
        try:
            stamps.append(datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00")))
        except ValueError:
            continue
    return tuple(sorted({moment if moment.tzinfo else moment.replace(tzinfo=UTC) for moment in stamps}))


@dataclass(frozen=True)
class FetchPlan:
    """What a restart should do about one discovered candidate."""

    satisfied: bool
    reason: str
    wanted: tuple[int, ...] = ()
    present: tuple[int, ...] = ()
    missing: tuple[int, ...] = ()

    @property
    def should_fetch(self) -> bool:
        return not self.satisfied


def plan_fetch(store: Any, *, source_id: str, candidate: Any, window: Any) -> FetchPlan:
    """Ask the store what is present, and fetch only the answers that are no.

    Raises whatever the store raises when it cannot be asked - the caller
    turns that into a failed source, because an unknown cache state is not an
    empty one.
    """
    provider_run_id = str(getattr(candidate, "provider_run_id", "") or "")
    declared = candidate_valid_times(candidate)
    wanted = tuple(
        to_nanoseconds(moment)
        for moment in declared
        if window is None or window.covers(moment)
    )
    if not wanted:
        return FetchPlan(
            False,
            "the candidate declares no valid time inside the window; fetching rather than assuming",
        )

    present = store.present_keys(source_id, provider_run_id)
    present_ns = tuple(sorted(int(value) for value in present))
    missing = tuple(value for value in sorted(set(wanted)) if value not in set(present_ns))
    if not missing:
        return FetchPlan(True, SATISFIED_REASON, wanted=tuple(sorted(set(wanted))), present=present_ns)
    return FetchPlan(
        False,
        f"{len(missing)} of {len(set(wanted))} frame(s) of run {provider_run_id} are missing from the window",
        wanted=tuple(sorted(set(wanted))),
        present=present_ns,
        missing=missing,
    )


# --- derived artifacts ---------------------------------------------------

@dataclass(frozen=True)
class InputState:
    """One retained input of a derived artifact, as the store reports it."""

    name: str
    present: bool = False
    last_valid_time: datetime | None = None

    @property
    def absence(self) -> str:
        """`present` when retained; `aged_out` when the store once held it and
        recorded a last valid time; `null` when nothing was ever held."""
        if self.present:
            return "present"
        return "aged_out" if self.last_valid_time is not None else "null"


def worst_absence(states: Iterable[str]) -> str:
    """The state a derived artifact reports, given its inputs' states."""
    return max(states, key=lambda name: ABSENCE_RANK.get(name, 0), default="present")


@dataclass(frozen=True)
class DerivedPlan:
    """Recompute from retained inputs, or be absent and say which input failed."""

    recompute: bool
    absence: str | None = None
    last_valid_time: datetime | None = None
    detail: str = ""
    blocking: tuple[str, ...] = field(default_factory=tuple)


def derived_plan(inputs: Sequence[InputState] | Mapping[str, InputState]) -> DerivedPlan:
    """Decide a derived artifact's fate without reaching upstream.

    A derived-here or display-derived artifact has no upstream of its own; its
    inputs do. So a missing derived artifact is recomputed from the retained
    inputs and never causes them to be fetched again. Where an input is not
    retained the artifact is absent and reports that input's state, because a
    derivation whose input is gone must not reach for a substitute or compute
    from a shorter input set.
    """
    items = list(inputs.values()) if isinstance(inputs, Mapping) else list(inputs)
    if not items:
        return DerivedPlan(False, absence="null", detail="the derivation declares no inputs")
    absent = [item for item in items if not item.present]
    if not absent:
        return DerivedPlan(True, detail=f"recomputing from {len(items)} retained input(s); no upstream request is made")
    state = worst_absence(item.absence for item in absent)
    blocking = tuple(item.name for item in absent if item.absence == state)
    stamps = [item.last_valid_time for item in absent if item.absence == state and item.last_valid_time is not None]
    last = max(stamps) if stamps else None
    if state == "aged_out":
        detail = f"aged out at {last.isoformat()} naming {', '.join(blocking)}" if last else f"aged out naming {', '.join(blocking)}"
    else:
        detail = f"null naming {', '.join(blocking)}"
    return DerivedPlan(False, absence=state, last_valid_time=last, detail=detail, blocking=blocking)
