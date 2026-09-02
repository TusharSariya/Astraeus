"""The single ingestion worker: heartbeat, scheduler, publication.

One process on purpose. Sources are scheduled on their registry cadence and
isolated from each other: an adapter that fails, or an upstream that has
nothing, must never stop the loop or take the container down with it.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

# Tolerates one whole source fetch. A GFS byte-range sweep or an HRDPS lead
# walk runs for minutes, and killing the worker mid-download would leave
# staging to clean up on every restart.
HEARTBEAT_MAX_AGE_SECONDS = 300
LOOP_SLEEP_SECONDS = 10
# A source that has succeeded before and then goes this many nominal cadences
# without another success is treated as stalled ingestion, not merely late.
STALL_CADENCE_MULTIPLIER = 3
UTC = timezone.utc


def heartbeat_path() -> Path:
    return Path(os.environ.get("WEATHER_WORKER_HEARTBEAT", "/tmp/weather-worker-heartbeat"))


def write_heartbeat(path: Path, sources: Mapping[str, dict[str, Any]] | None = None) -> None:
    """Publish liveness and per-source ingestion progress atomically.

    The file carries more than a timestamp because a live process is not the
    same claim as advancing ingestion: ``check_heartbeat`` needs both to answer
    honestly, and a bare mtime cannot express the second one.
    """
    document = {"beat": datetime.now(UTC).isoformat(), "sources": dict(sources or {})}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document), encoding="utf-8")
    temporary.replace(path)


def read_heartbeat(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def stalled_sources(document: Mapping[str, Any], *, reference: datetime | None = None) -> list[str]:
    """Sources that used to succeed and have now stopped.

    A source that has *never* succeeded is not counted: an endpoint that is 404
    or a product this experiment cannot yet decode is an ingestion fact to
    report through the API's source status, not a reason to kill the container
    and restart-loop. Only a regression from working to not-working is a stall.
    """
    moment = reference or datetime.now(UTC)
    stalled: list[str] = []
    for source_id, state in (document.get("sources") or {}).items():
        last_success = state.get("last_success")
        cadence = state.get("cadence_seconds")
        if not last_success or not cadence:
            continue
        try:
            succeeded_at = datetime.fromisoformat(str(last_success))
        except ValueError:
            continue
        if (moment - succeeded_at).total_seconds() > int(cadence) * STALL_CADENCE_MULTIPLIER:
            stalled.append(source_id)
    return sorted(stalled)


def check_heartbeat(path: Path) -> int:
    """Exit status for the container healthcheck: 0 healthy, 1 unhealthy."""
    document = read_heartbeat(path)
    if document is None:
        return 1
    try:
        beat = datetime.fromisoformat(str(document["beat"]))
    except (KeyError, ValueError):
        return 1
    age = (datetime.now(UTC) - beat).total_seconds()
    if not 0 <= age <= HEARTBEAT_MAX_AGE_SECONDS:
        print(f"heartbeat is {age:.0f}s old", flush=True)
        return 1
    stalled = stalled_sources(document)
    if stalled:
        print(f"ingestion stalled for: {', '.join(stalled)}", flush=True)
        return 1
    return 0


def log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


@dataclass(frozen=True)
class SourceOutcome:
    """What one source did this cycle. ``state`` maps onto the jobs enum."""

    source_id: str
    state: str
    detail: str
    published: int = 0


def _store():
    """Return the artifact store, or ``None`` when the stack is not up yet."""
    from ingest.store import StoreUnavailable, store_from_env  # noqa: PLC0415

    try:
        return store_from_env()
    except StoreUnavailable as error:
        log(f"store unavailable: {error}")
        return None


def run_source(adapter, config, store, *, reference: datetime, heartbeat: Callable[[], None] | None = None) -> SourceOutcome:
    """Discover, fetch, stage and publish one source. Never raises."""
    from ingest.contract import AdapterUnavailable, FetchWindow  # noqa: PLC0415
    from ingest.scheduler import plan_fetch  # noqa: PLC0415
    from ingest.store import QuotaExceeded, RunIdentityConflict, StoreUnavailable  # noqa: PLC0415

    window = FetchWindow(now=reference)
    try:
        candidates = adapter.discover(window)
    except AdapterUnavailable as error:
        return SourceOutcome(config.source_id, "cancelled", f"nothing usable upstream: {error}")
    except Exception as error:
        return SourceOutcome(config.source_id, "failed", f"discovery failed: {error!r}")
    if not candidates:
        return SourceOutcome(config.source_id, "cancelled", "discovery returned no candidate run")

    candidate = candidates[0]
    # Ask the store what is present before fetching. A restart whose window is
    # already satisfied issues no bulk request at all; a store that cannot be
    # asked fails the source, because refetching everything on an unreadable
    # store is how a restart becomes an outage on the constraint that binds.
    if store is not None:
        try:
            plan = plan_fetch(store, source_id=config.source_id, candidate=candidate, window=window)
        except Exception as error:
            return SourceOutcome(config.source_id, "failed", f"the store could not be asked what is present: {error!r}")
        if plan.satisfied:
            return SourceOutcome(config.source_id, "succeeded", plan.reason, 0)
    if heartbeat is not None:
        heartbeat()
    with tempfile.TemporaryDirectory(prefix=f"{config.source_id}-") as workdir:
        try:
            result = adapter.fetch(candidate, window, Path(workdir))
        except AdapterUnavailable as error:
            return SourceOutcome(config.source_id, "cancelled", f"candidate unusable: {error}")
        except Exception as error:
            return SourceOutcome(config.source_id, "failed", f"fetch failed: {error!r}")

        if store is None:
            return SourceOutcome(config.source_id, "failed", "fetched but no artifact store is available")
        if heartbeat is not None:
            heartbeat()
        try:
            store.upsert_source(
                source_id=config.source_id, producer=config.producer, product=config.product,
                registry_status=config.registry_status,
                adapter_version=str(getattr(adapter, "adapter_version", "unversioned")),
                metadata={"bounds": dict(config.bounds), "variables": list(config.variables)},
            )
            published = store.stage_and_publish(result)
        except RunIdentityConflict as error:
            # The published artifact stays visible; this is never a silent
            # replacement of evidence a reader may already have cited.
            return SourceOutcome(config.source_id, "failed", str(error))
        except QuotaExceeded as error:
            return SourceOutcome(config.source_id, "failed", f"storage cap reached: {error}")
        except StoreUnavailable as error:
            return SourceOutcome(config.source_id, "failed", f"store unavailable: {error}")
        except Exception as error:
            return SourceOutcome(config.source_id, "failed", f"publication failed: {error!r}")

    if not (result.complete and result.qc_passed):
        # The validator already worked out exactly which fields were missing,
        # empty or wrongly-united and recorded them on the artifact. Reporting
        # only "incomplete or QC-failed" throws that away and leaves the reader
        # with nothing to act on, so the flags travel into the outcome.
        flags: list[str] = []
        for artifact in result.artifacts:
            quality = artifact.provenance.get("quality") or {}
            flags.extend(str(flag) for flag in quality.get("flags") or ())
        detail = f" [{', '.join(dict.fromkeys(flags))}]" if flags else ""
        return SourceOutcome(
            config.source_id, "failed",
            f"run staged but incomplete or QC-failed; previous revision stays visible{detail}", 0,
        )
    return SourceOutcome(config.source_id, "succeeded", f"published {len(published)} artifact(s)", len(published))


class Scheduler:
    """Tracks per-source due times and runs one cycle at a time."""

    def __init__(self, store, *, source_ids: tuple[str, ...] | None = None) -> None:
        from ingest.registry import load_adapters, scheduled  # noqa: PLC0415

        load_adapters()
        self._store = store
        self._pairs = [(adapter, config) for adapter, config in scheduled() if source_ids is None or config.source_id in source_ids]
        self._due: dict[str, float] = {config.source_id: 0.0 for _, config in self._pairs}
        # Seeded with cadence but no last_success: a source that has never
        # worked is reported, not counted as a stall. See ``stalled_sources``.
        #
        # ``cadence_seconds`` here is the *declared* cadence the source is now
        # scheduled on - the producer's run cadence, or the native publication
        # interval - not how often this deployment happens to look. The stall
        # check counts three of these, and counting three poll intervals would
        # report a six-hourly model stalled forty-five minutes after a run.
        self._progress: dict[str, dict[str, Any]] = {}
        for _, config in self._pairs:
            plan = self._plan(config, datetime.now(UTC))
            self._progress[config.source_id] = {
                "cadence_seconds": plan.cadence_seconds or config.cadence_seconds,
                "schedule_kind": plan.kind,
                "latency_measured": plan.latency_measured,
                "last_success": None,
                "last_state": "pending",
                "last_detail": "",
            }
            if not plan.scheduled:
                # Never silently dropped: the source stays in the rotation's
                # bookkeeping with the missing field named.
                self._progress[config.source_id]["last_state"] = "unscheduled"
                self._progress[config.source_id]["last_detail"] = plan.reason[:200]

    @staticmethod
    def _plan(config, now: datetime, *, after: datetime | None = None):
        from ingest.scheduler import next_due  # noqa: PLC0415

        return next_due(config, now=now, after=after)

    def _reschedule(self, config, now: datetime) -> None:
        """Put a source back in the rotation on its own declared cadence.

        A forecast source lands on its next run's first-attempt instant; an
        observation or nowcast source one native interval on. A source that
        declares neither is not rescheduled at all - it is pushed out of reach
        rather than run on a number nobody declared.
        """
        plan = self._plan(config, now, after=now)
        state = self._progress.setdefault(config.source_id, {})
        state["schedule_kind"] = plan.kind
        state["latency_measured"] = plan.latency_measured
        if plan.cadence_seconds:
            state["cadence_seconds"] = plan.cadence_seconds
        if not plan.scheduled:
            state["next_due"] = None
            state["schedule_reason"] = plan.reason[:200]
            self._due[config.source_id] = float("inf")
            log(f"{config.source_id}: not scheduled - {plan.reason}")
            return
        state["next_due"] = plan.due.isoformat()
        state["schedule_reason"] = plan.reason[:200]
        self._due[config.source_id] = time.monotonic() + plan.delay_seconds(now)

    def _schedule_poll(self, source_id: str, due: datetime, now: datetime) -> None:
        """Put a polling source back at its next poll, not at its next run."""
        from ingest.scheduler import POLL_INTERVAL_SECONDS  # noqa: PLC0415

        state = self._progress.setdefault(source_id, {})
        state["next_due"] = due.isoformat()
        state["schedule_reason"] = f"polling every {POLL_INTERVAL_SECONDS}s for a run that has not appeared"
        self._due[source_id] = time.monotonic() + max(0.0, (due - now).total_seconds())

    def _poll(self, config, outcome: SourceOutcome, now: datetime) -> tuple[SourceOutcome, datetime | None]:
        """Keep, open or close a poll for a forecast run that has not appeared.

        Returns the outcome to report and, where the source stays on the poll,
        the instant of its next attempt. A ``cancelled`` outcome from a
        forecast source means the upstream had nothing usable *yet*: that is
        what polling is for, so it is not reported as a failure and no
        neighbouring run, fixture or other value is put in the missing run's
        place. The poll is bounded by the next run time of the same source; at
        the bound the run is superseded rather than late and the outcome names
        it and the poll duration. The previous run is untouched throughout, so
        it stays visible and keeps serving.
        """
        from ingest.scheduler import PollState, latest_run_time, poll_decision  # noqa: PLC0415

        run_cadence = getattr(config, "run_cadence_seconds", None)
        state = self._progress.setdefault(config.source_id, {})
        open_poll = state.get("polling")
        if not run_cadence:
            state.pop("polling", None)
            return outcome, None

        if outcome.state != "cancelled":
            if open_poll and outcome.state == "succeeded":
                # The run appeared. Record when this deployment first saw it;
                # task 2.3 turns that into the re-measured latency.
                state["observed_publication"] = now.isoformat()
                state["observed_publication_run_time"] = open_poll.get("run_time")
            state.pop("polling", None)
            return outcome, None

        run_time = latest_run_time(int(run_cadence), now)
        if open_poll and open_poll.get("run_time"):
            try:
                run_time = datetime.fromisoformat(str(open_poll["run_time"]))
            except ValueError:
                open_poll = None
        since = now
        attempts = 1
        if open_poll:
            try:
                since = datetime.fromisoformat(str(open_poll.get("since")))
            except (TypeError, ValueError):
                since = now
            attempts = int(open_poll.get("attempts", 0)) + 1
        poll = PollState(run_time=run_time, since=since, attempts=attempts)
        decision = poll_decision(poll, run_cadence_seconds=int(run_cadence), now=now)
        if decision.exhausted:
            state.pop("polling", None)
            # Nothing is written about latency here: a run that never appeared
            # is not an observation of one.
            return SourceOutcome(outcome.source_id, "cancelled", decision.detail), None
        state["polling"] = poll.as_progress()
        state["poll_bound"] = decision.bound.isoformat()
        return SourceOutcome(outcome.source_id, "cancelled", decision.detail), decision.due

    @property
    def source_ids(self) -> list[str]:
        return [config.source_id for _, config in self._pairs]

    @property
    def progress(self) -> dict[str, dict[str, Any]]:
        return {source_id: dict(state) for source_id, state in self._progress.items()}

    def _record_progress(self, outcome: SourceOutcome) -> None:
        state = self._progress.setdefault(outcome.source_id, {"cadence_seconds": None, "last_success": None})
        state["last_state"] = outcome.state
        state["last_detail"] = outcome.detail[:200]
        if outcome.state == "succeeded":
            state["last_success"] = datetime.now(UTC).isoformat()

    def due_now(self, *, force: bool = False) -> list[tuple[object, object]]:
        moment = time.monotonic()
        return [pair for pair in self._pairs if force or self._due.get(pair[1].source_id, 0.0) <= moment]

    def cycle(
        self,
        *,
        force: bool = False,
        heartbeat: Callable[[], None] | None = None,
        after_publish: Callable[[], None] | None = None,
    ) -> list[SourceOutcome]:
        reference = datetime.now(UTC)
        outcomes: list[SourceOutcome] = []
        for adapter, config in self.due_now(force=force):
            # Beat before each source, not only between cycles: a serial cycle
            # over many sources outlives the healthcheck window otherwise.
            if heartbeat is not None:
                heartbeat()
            outcome = run_source(adapter, config, self._store, reference=reference, heartbeat=heartbeat)
            # A forecast run that is not there yet is polled for rather than
            # reported: the outcome and the next attempt both come from the
            # bounded poll, and only its bound reports the absence.
            outcome, poll_due = self._poll(config, outcome, datetime.now(UTC))
            self._record_progress(outcome)
            # Derived artifacts follow the run that produced their inputs, not
            # the end of the cycle. A cycle is a serial pass over every due
            # source and outlives any one of them, so waiting for it to finish
            # left a source that republished early with motion pinned to its
            # previous revision - which /flow refuses - until the slowest or
            # most broken adapter in the rotation was done. Only a publish can
            # invalidate derived motion, so only a publish triggers this.
            if after_publish is not None and outcome.state == "succeeded":
                after_publish()
            # Reschedule on cadence regardless of outcome: a failing source must
            # not spin, and must not be dropped from the rotation either. A
            # source on an open poll is put back at its next poll instead,
            # which is bounded, so it cannot spin either.
            if poll_due is not None:
                self._schedule_poll(config.source_id, poll_due, datetime.now(UTC))
            else:
                self._reschedule(config, datetime.now(UTC))
            outcomes.append(outcome)
            log(f"{outcome.source_id}: {outcome.state} - {outcome.detail}")
            # Success is already recorded in model_runs; only the states that
            # would otherwise vanish need a durable row.
            if self._store is not None and outcome.state != "succeeded":
                try:
                    self._store.record_outcome(config.source_id, state=outcome.state, detail=outcome.detail)
                except Exception as error:
                    log(f"could not record outcome for {config.source_id}: {error!r}")
        return outcomes

    def drain_jobs(
        self,
        *,
        heartbeat: Callable[[], None] | None = None,
        after_publish: Callable[[], None] | None = None,
    ) -> None:
        """Serve API refresh requests. Failures here never stop the loop."""
        if self._store is None:
            return
        try:
            job = self._store.claim_job()
        except Exception as error:
            log(f"could not claim a job: {error!r}")
            return
        if job is None:
            return
        requested = set(job["source_ids"]) or set(self.source_ids)
        reference = datetime.now(UTC)
        outcomes: list[SourceOutcome] = []
        for adapter, config in self._pairs:
            if config.source_id not in requested:
                continue
            if heartbeat is not None:
                heartbeat()
            outcome = run_source(adapter, config, self._store, reference=reference, heartbeat=heartbeat)
            self._record_progress(outcome)
            outcomes.append(outcome)
            # Same rule as `cycle`: an on-demand refresh that republishes a
            # source invalidates that source's derived motion immediately.
            if after_publish is not None and outcome.state == "succeeded":
                after_publish()
        # A job that matched no schedulable adapter did not succeed; reporting
        # it as succeeded is exactly the dishonesty this experiment forbids.
        if not outcomes:
            unmatched = ", ".join(sorted(requested)) or "(none)"
            self._finish(job, "failed", f"no registered schedulable adapter matched: {unmatched}")
            return
        states = {item.state for item in outcomes}
        if "failed" in states:
            state = "failed"
        elif "succeeded" in states:
            state = "succeeded"
        else:
            state = "cancelled"
        detail = "; ".join(f"{item.source_id}: {item.state} - {item.detail}" for item in outcomes)
        self._finish(job, state, detail)

    def _finish(self, job: dict[str, Any], state: str, detail: str) -> None:
        log(f"job {job['id']}: {state} - {detail}")
        try:
            self._store.finish_job(job["id"], state=state, detail=detail[:2000])
        except Exception as error:
            log(f"could not finish job {job['id']}: {error!r}")


def run(*, once: bool = False, source_ids: tuple[str, ...] | None = None) -> int:
    path = heartbeat_path()
    write_heartbeat(path)
    store = _store()
    # Reconcile the retained window before scheduling anything: sweep
    # abandoned staging, purge what left the window, then let the sources ask
    # what is missing. The store is never cleared on start.
    from ingest.scheduler import reconcile_on_start  # noqa: PLC0415

    reconciliation = reconcile_on_start(store)
    log(f"restart reconciliation: {reconciliation.detail}")
    if store is not None and not reconciliation.may_fetch:
        # A worker that cannot see the cache would refetch everything, so it
        # reports unhealthy and schedules nothing instead.
        log("the store could not be reconciled; scheduling no fetch and reporting unhealthy")
        return 1

    scheduler = Scheduler(store, source_ids=source_ids)
    if not scheduler.source_ids:
        log("no registered adapter is schedulable; the worker will idle and stay healthy")
    else:
        log(f"scheduling {len(scheduler.source_ids)} source(s): {', '.join(scheduler.source_ids)}")

    def beat() -> None:
        write_heartbeat(path, scheduler.progress)

    beat()
    if once:
        outcomes = scheduler.cycle(force=True, heartbeat=beat)
        if store is not None:
            try:
                # Before the motion pass, because the WEonG layer is one of
                # the artifacts that pass derives motion FOR.
                from ingest.derive.weong_layer import weong_cycle  # noqa: PLC0415

                for line in weong_cycle(store):
                    log(line)
            except Exception as error:
                log(f"weong low-cloud derive pass failed: {error!r}")
            try:
                from ingest.derive.cloud_motion import cloud_motion_cycle  # noqa: PLC0415

                for line in cloud_motion_cycle(store):
                    log(line)
            except Exception as error:
                log(f"cloud-motion derive pass failed: {error!r}")
            try:
                store.prune()
            except Exception as error:
                log(f"retention pass failed: {error!r}")
        beat()
        return 0 if all(item.state != "failed" for item in outcomes) else 1

    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    def derive() -> None:
        """Bring derived display-support artifacts up to the current revisions.

        Cheap when nothing changed: one `current_artifacts` read and a revision
        comparison per source. Called after every publish rather than once per
        cycle, because a cycle is a serial pass over every due source and a
        source that republishes at the start of one would otherwise have motion
        pinned to its previous revision - which `/flow` refuses outright, so the
        map falls back to a plain cross-dissolve - for as long as the rest of
        the rotation takes, including any adapter that is slow or failing.
        """
        if store is None:
            return
        try:
            # The WEonG low-cloud layer is derived first: it publishes an
            # artifact the motion pass below then derives motion for, so the
            # order is a dependency and not a preference. One pass late means
            # the derived layer draws a plain crossfade for a whole cycle.
            from ingest.derive.weong_layer import weong_cycle  # noqa: PLC0415

            for line in weong_cycle(store):
                log(line)
        except Exception as error:
            log(f"weong low-cloud derive pass failed: {error!r}")
        try:
            from ingest.derive.cloud_motion import cloud_motion_cycle  # noqa: PLC0415

            for line in cloud_motion_cycle(store):
                log(line)
        except Exception as error:
            log(f"cloud-motion derive pass failed: {error!r}")
        # The derive can outlast the healthcheck window on its own, so the
        # liveness signal is refreshed on the way out as well as on the way in.
        beat()

    last_prune = 0.0
    while not stopping:
        beat()
        try:
            scheduler.cycle(heartbeat=beat, after_publish=derive)
            scheduler.drain_jobs(heartbeat=beat, after_publish=derive)
            # A final pass catches anything the per-publish hook could not: a
            # derive whose own inputs were published earlier in this same cycle
            # by a different source.
            derive()
            if store is not None and time.monotonic() - last_prune > 3600:
                store.prune()
                last_prune = time.monotonic()
        except Exception:  # the loop is the last line of defence
            log("unexpected scheduler error:\n" + traceback.format_exc())
        time.sleep(LOOP_SLEEP_SECONDS)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-heartbeat", action="store_true")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--source", action="append", default=None, help="restrict to one registry source id; repeatable")
    args = parser.parse_args()
    if args.check_heartbeat:
        return check_heartbeat(heartbeat_path())
    return run(once=args.once, source_ids=tuple(args.source) if args.source else None)


if __name__ == "__main__":
    sys.exit(main())
