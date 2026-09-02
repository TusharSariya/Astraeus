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
#: Owned by task 2.2; named here because ``next_due`` is where the bound will
#: be read from and the two must agree on one number.
POLL_INTERVAL_SECONDS = 600

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
    "POLL_INTERVAL_SECONDS",
    "SATISFIED_REASON",
    "DerivedPlan",
    "FetchPlan",
    "InputState",
    "Reconciliation",
    "RestartCache",
    "Schedule",
    "candidate_valid_times",
    "derived_plan",
    "first_attempt",
    "latest_run_time",
    "next_due",
    "next_run_time",
    "plan_fetch",
    "reconcile_on_start",
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


def next_due(config: "IngestConfig", *, now: datetime, after: datetime | None = None) -> Schedule:
    """Decide when ``config``'s source is attempted next.

    A forecast source is attempted at its run's first-attempt instant: the
    latest nominal run plus the measured latency, or the run time itself where
    nothing is measured. An observation or nowcast source is attempted every
    ``native_cadence_seconds`` - its own publication interval, never rounded up
    onto a shared poll floor, which is what folded six-minute radar onto a
    five-minute rotation and hourly METAR onto the same one.

    ``after`` is the instant a scheduled attempt has just been made at; the
    result is then the *next* attempt strictly after it.
    """
    source_id = str(getattr(config, "source_id", "") or "")
    moment = now if now.tzinfo else now.replace(tzinfo=UTC)
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
