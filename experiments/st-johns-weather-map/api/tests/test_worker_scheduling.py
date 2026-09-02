"""When each source is next attempted.

`ingestion-worker-scheduling` requires a forecast source's first attempt for a
run to be at that run's nominal time plus its *measured* publication latency,
and - where nothing has been measured and no seed exists - at the run time
itself, never offset by a guessed value. Observation and nowcast sources are
scheduled at their own native cadence instead: radar every 6 minutes, lightning
and GOES every 10, METAR and SWOB hourly, the SWPC solar wind every minute.

The decisions are pure functions in ``ingest/scheduler.py``, so they are
exercised here against the real registry records without a live PostgreSQL,
MinIO or any array machinery. The last two tests check that
``worker/runtime.py``'s ``Scheduler`` actually schedules on them.

Tasks 2.2 (the bounded ten-minute poll and the Datamart fallback) and 2.3 (the
heartbeat latency write) are deliberately not covered here.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from ingest.registry import PublicationLatency, get_config
from ingest.scheduler import (
    POLL_INTERVAL_SECONDS,
    first_attempt,
    latest_run_time,
    next_due,
    next_run_time,
)

UTC = timezone.utc
# A 00z run, and an instant a few minutes into the cycle that follows it.
RUN_00Z = datetime(2026, 9, 2, 0, tzinfo=UTC)
INSIDE_00Z = datetime(2026, 9, 2, 3, 17, tzinfo=UTC)


# --- forecast: run time plus measured latency ----------------------------

def test_latency_seeded_estimate_moves_the_first_attempt_off_the_run_time() -> None:
    """GFS at 00z with a 5 h 18 m estimate is first asked for at 05:18Z."""
    config = get_config("noaa-gfs")
    assert config.publication_latency is not None
    assert config.publication_latency.estimate_seconds == 19080

    assert first_attempt(RUN_00Z, config.publication_latency) == datetime(2026, 9, 2, 5, 18, tzinfo=UTC)

    plan = next_due(config, now=INSIDE_00Z)
    assert plan.kind == "forecast"
    assert plan.run_time == RUN_00Z
    assert plan.due == datetime(2026, 9, 2, 5, 18, tzinfo=UTC)
    # The whole point: not 00:00Z, where a systematically early fetch finds
    # nothing and manufactures a cancellation that looks like an upstream fault.
    assert plan.due != RUN_00Z


@pytest.mark.parametrize(
    ("source_id", "estimate_seconds"),
    [("dwd-icon-global", 12600), ("noaa-gfs", 19080), ("noaa-gefs", 19080),
     ("ecmwf-ifs", 27360), ("ecmwf-ens", 27360), ("ecmwf-aifs-single", 27360),
     ("ecmwf-aifs-ens", 27360)],
)
def test_latency_seeds_are_carried_into_the_schedule(source_id: str, estimate_seconds: int) -> None:
    config = get_config(source_id)
    plan = next_due(config, now=INSIDE_00Z)
    assert plan.due == plan.run_time + timedelta(seconds=estimate_seconds)


@pytest.mark.parametrize("source_id", ["eccc-gdps", "eccc-geps", "eccc-reps", "eccc-hrdps", "eccc-rdps"])
def test_unmeasured_latency_attempts_at_the_run_time_exactly(source_id: str) -> None:
    """No seed and no observation means the run time itself, not a borrowed offset."""
    config = get_config(source_id)
    assert config.publication_latency is not None
    assert config.publication_latency.estimate_seconds is None

    plan = next_due(config, now=INSIDE_00Z)
    assert plan.due == plan.run_time
    assert plan.latency_measured is False
    assert "no latency is measured" in plan.reason


def test_missing_latency_block_attempts_at_the_run_time_exactly() -> None:
    """A record carrying no latency block at all is treated the same way."""
    config = dataclasses.replace(get_config("noaa-gfs"), publication_latency=None)
    assert first_attempt(RUN_00Z, None) == RUN_00Z
    assert next_due(config, now=INSIDE_00Z).due == RUN_00Z


def test_latency_measured_is_recorded_and_is_false_for_a_seed() -> None:
    """A researched seed is never presented as this deployment's measurement."""
    seeded = get_config("noaa-gfs")
    assert next_due(seeded, now=INSIDE_00Z).latency_measured is False

    observed = dataclasses.replace(
        seeded,
        publication_latency=PublicationLatency(
            estimate_seconds=17400, observation_count=3,
            last_observed=datetime(2026, 9, 1, 4, 50, tzinfo=UTC), measured=True,
            basis="observed by this deployment",
        ),
    )
    plan = next_due(observed, now=INSIDE_00Z)
    assert plan.latency_measured is True
    assert plan.due == RUN_00Z + timedelta(seconds=17400)


def test_latency_offset_survives_the_walk_to_the_next_run() -> None:
    """Having just attempted a run, the next attempt is the next run's, not a poll."""
    config = get_config("noaa-gfs")
    attempted_at = datetime(2026, 9, 2, 5, 18, tzinfo=UTC)
    plan = next_due(config, now=attempted_at, after=attempted_at)
    assert plan.run_time == datetime(2026, 9, 2, 6, tzinfo=UTC)
    assert plan.due == datetime(2026, 9, 2, 11, 18, tzinfo=UTC)
    # The ten-minute poll is task 2.2's, and is not what the schedule advances by.
    assert plan.delay_seconds(attempted_at) > POLL_INTERVAL_SECONDS


def test_latency_run_anchors_are_the_producer_cycles() -> None:
    six_hourly = 21600
    assert latest_run_time(six_hourly, INSIDE_00Z) == RUN_00Z
    assert next_run_time(six_hourly, INSIDE_00Z) == datetime(2026, 9, 2, 6, tzinfo=UTC)
    twelve_hourly = 43200
    assert latest_run_time(twelve_hourly, datetime(2026, 9, 2, 13, tzinfo=UTC)) == datetime(2026, 9, 2, 12, tzinfo=UTC)
    with pytest.raises(ValueError):
        latest_run_time(0, INSIDE_00Z)


# --- observations and nowcasts: native cadence ---------------------------

@pytest.mark.parametrize(
    ("source_id", "seconds"),
    [("eccc-radar", 360), ("eccc-lightning", 600), ("noaa-goes-east", 600),
     ("awc-metar-speci", 3600), ("eccc-swob", 3600), ("noaa-swpc-rtsw", 60)],
)
def test_native_cadence_is_the_declared_interval(source_id: str, seconds: int) -> None:
    """Radar 6 min, lightning 10, GOES 10, METAR and SWOB hourly, SWPC 1 min."""
    config = get_config(source_id)
    assert config.native_cadence_seconds == seconds
    assert config.run_cadence_seconds is None

    plan = next_due(config, now=INSIDE_00Z, after=INSIDE_00Z)
    assert plan.kind == "native"
    assert plan.cadence_seconds == seconds
    assert plan.due == INSIDE_00Z + timedelta(seconds=seconds)


@pytest.mark.parametrize("source_id", ["eccc-radar", "noaa-swpc-rtsw", "awc-metar-speci"])
def test_native_cadence_is_not_clamped_to_the_old_poll_floor(source_id: str) -> None:
    """The derived 300-1800 s poll window no longer decides these sources.

    It folded six-minute radar onto a five-minute rotation, asked the
    one-minute solar wind five times too slowly, and hit hourly METAR twice an
    hour. The declared interval is now the schedule.
    """
    config = get_config(source_id)
    plan = next_due(config, now=INSIDE_00Z, after=INSIDE_00Z)
    assert plan.delay_seconds(INSIDE_00Z) == config.native_cadence_seconds
    assert plan.delay_seconds(INSIDE_00Z) != config.cadence_seconds


def test_native_cadence_first_attempt_is_immediate() -> None:
    """With no attempt behind it, an observation source is due now, not one
    interval from now: a restart must not blind the map for an hour."""
    plan = next_due(get_config("eccc-swob"), now=INSIDE_00Z)
    assert plan.due == INSIDE_00Z
    assert plan.delay_seconds(INSIDE_00Z) == 0


def test_a_record_with_neither_run_nor_native_cadence_is_unscheduled() -> None:
    config = dataclasses.replace(
        get_config("eccc-radar"), native_cadence_seconds=None, run_cadence_seconds=None,
    )
    plan = next_due(config, now=INSIDE_00Z)
    assert plan.kind == "unscheduled"
    assert plan.due is None
    assert plan.scheduled is False
    assert "run_cadence_seconds" in plan.reason and "native_cadence_seconds" in plan.reason
    with pytest.raises(ValueError):
        plan.delay_seconds(INSIDE_00Z)


def test_no_declared_reach_is_unscheduled_whatever_the_native_cadence() -> None:
    config = dataclasses.replace(get_config("eccc-radar"), reach=None)
    plan = next_due(config, now=INSIDE_00Z)
    assert plan.kind == "unscheduled"
    assert "reach" in plan.reason


# --- the worker schedules on those decisions -----------------------------

@pytest.fixture()
def scheduler_over(monkeypatch: pytest.MonkeyPatch):
    """A ``Scheduler`` over chosen registry records and no adapters or store."""
    from worker.runtime import Scheduler
    import ingest.registry as registry

    def build(*source_ids: str) -> Scheduler:
        pairs = [(object(), get_config(source_id)) for source_id in source_ids]
        monkeypatch.setattr(registry, "load_adapters", lambda *a, **k: [])
        monkeypatch.setattr(registry, "scheduled", lambda: iter(pairs))
        return Scheduler(None)

    return build


def test_scheduler_reschedules_a_source_on_its_native_cadence(scheduler_over) -> None:
    scheduler = scheduler_over("eccc-radar", "noaa-swpc-rtsw")
    now = INSIDE_00Z
    import time as _time

    before = _time.monotonic()
    scheduler._reschedule(get_config("eccc-radar"), now)
    scheduler._reschedule(get_config("noaa-swpc-rtsw"), now)
    assert scheduler._due["eccc-radar"] - before == pytest.approx(360, abs=2)
    assert scheduler._due["noaa-swpc-rtsw"] - before == pytest.approx(60, abs=2)
    # The nominal cadence the stall check counts is the declared one now.
    assert scheduler.progress["eccc-radar"]["cadence_seconds"] == 360
    assert scheduler.progress["eccc-radar"]["schedule_kind"] == "native"


def test_scheduler_progress_carries_latency_measured(scheduler_over) -> None:
    scheduler = scheduler_over("noaa-gfs", "eccc-reps")
    for source_id in ("noaa-gfs", "eccc-reps"):
        assert scheduler.progress[source_id]["latency_measured"] is False
        assert scheduler.progress[source_id]["cadence_seconds"] == 21600
        assert scheduler.progress[source_id]["schedule_kind"] == "forecast"

    scheduler._reschedule(get_config("eccc-reps"), INSIDE_00Z)
    state = scheduler.progress["eccc-reps"]
    assert state["latency_measured"] is False
    # Attempted inside the 00z cycle, so the next attempt is the 06z run time
    # itself - REPS has no measured latency and borrows nobody else's.
    assert state["next_due"] == datetime(2026, 9, 2, 6, tzinfo=UTC).isoformat()
