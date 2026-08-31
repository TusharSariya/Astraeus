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
    from ingest.store import QuotaExceeded, StoreUnavailable  # noqa: PLC0415

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
        self._progress: dict[str, dict[str, Any]] = {
            config.source_id: {"cadence_seconds": config.cadence_seconds, "last_success": None, "last_state": "pending", "last_detail": ""}
            for _, config in self._pairs
        }

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

    def cycle(self, *, force: bool = False, heartbeat: Callable[[], None] | None = None) -> list[SourceOutcome]:
        reference = datetime.now(UTC)
        outcomes: list[SourceOutcome] = []
        for adapter, config in self.due_now(force=force):
            # Beat before each source, not only between cycles: a serial cycle
            # over many sources outlives the healthcheck window otherwise.
            if heartbeat is not None:
                heartbeat()
            outcome = run_source(adapter, config, self._store, reference=reference, heartbeat=heartbeat)
            self._record_progress(outcome)
            # Reschedule on cadence regardless of outcome: a failing source must
            # not spin, and must not be dropped from the rotation either.
            self._due[config.source_id] = time.monotonic() + config.cadence_seconds
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

    def drain_jobs(self, *, heartbeat: Callable[[], None] | None = None) -> None:
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
    if store is not None:
        try:
            store.restart()
        except Exception as error:
            log(f"could not clear abandoned staging: {error!r}")

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
    last_prune = 0.0
    while not stopping:
        beat()
        try:
            scheduler.cycle(heartbeat=beat)
            scheduler.drain_jobs(heartbeat=beat)
            # Derived display-support artifacts (cloud motion) follow the runs
            # that produced their inputs. Cheap when nothing changed: one
            # current_artifacts read and a revision comparison per source.
            if store is not None:
                try:
                    from ingest.derive.cloud_motion import cloud_motion_cycle  # noqa: PLC0415

                    for line in cloud_motion_cycle(store):
                        log(line)
                except Exception as error:
                    log(f"cloud-motion derive pass failed: {error!r}")
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
