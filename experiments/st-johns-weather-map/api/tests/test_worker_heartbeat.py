"""Worker liveness must distinguish a live process from advancing ingestion.

The old heartbeat was a bare mtime written only between cycles: a long serial
cycle read as death, and a process that had silently stopped publishing read as
health. Both directions are tested here.

Task 2.3's latency re-measurement is here too, because the heartbeat is where
the observed publication instant and the re-measured estimate are published.
The rule under test is one-directional: only a publication this deployment
actually observed writes anything, so a bounded-out poll and a source with no
run to wait for leave the block exactly as the registry seeded it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from worker.runtime import (
    HEARTBEAT_MAX_AGE_SECONDS,
    STALL_CADENCE_MULTIPLIER,
    check_heartbeat,
    read_heartbeat,
    stalled_sources,
    write_heartbeat,
)

UTC = timezone.utc
RUN_00Z = datetime(2026, 9, 2, 0, tzinfo=UTC)


def test_write_heartbeat_is_atomic_and_carries_source_progress(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    write_heartbeat(path, {"awc-metar-speci": {"cadence_seconds": 900, "last_success": None, "last_state": "pending"}})

    document = read_heartbeat(path)
    assert document is not None
    assert "beat" in document
    assert document["sources"]["awc-metar-speci"]["cadence_seconds"] == 900
    assert not list(tmp_path.glob("*.tmp")), "the temporary file must be renamed, never left behind"


def test_missing_or_corrupt_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    assert check_heartbeat(tmp_path / "absent") == 1
    corrupt = tmp_path / "corrupt"
    corrupt.write_text("not json", encoding="utf-8")
    assert read_heartbeat(corrupt) is None
    assert check_heartbeat(corrupt) == 1


def test_fresh_beat_with_no_source_history_is_healthy(tmp_path: Path) -> None:
    """A source that has never succeeded is reported, not fatal.

    A 404 endpoint is an ingestion fact for the API's source status. Failing
    liveness on it would restart-loop the container without fixing anything.
    """
    path = tmp_path / "beat"
    write_heartbeat(path, {"ecmwf-ifs": {"cadence_seconds": 300, "last_success": None, "last_state": "failed"}})
    assert check_heartbeat(path) == 0


def test_stale_beat_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    stale = datetime.now(UTC) - timedelta(seconds=HEARTBEAT_MAX_AGE_SECONDS + 60)
    path.write_text(json.dumps({"beat": stale.isoformat(), "sources": {}}), encoding="utf-8")
    assert check_heartbeat(path) == 1


def test_source_that_stopped_succeeding_is_a_stall(tmp_path: Path) -> None:
    cadence = 900
    reference = datetime.now(UTC)
    recent = (reference - timedelta(seconds=cadence)).isoformat()
    lapsed = (reference - timedelta(seconds=cadence * STALL_CADENCE_MULTIPLIER + 60)).isoformat()

    document = {
        "beat": reference.isoformat(),
        "sources": {
            "eccc-hrdps": {"cadence_seconds": cadence, "last_success": recent},
            "awc-metar-speci": {"cadence_seconds": cadence, "last_success": lapsed},
        },
    }
    assert stalled_sources(document, reference=reference) == ["awc-metar-speci"]

    path = tmp_path / "beat"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert check_heartbeat(path) == 1, "a live process that stopped publishing is not healthy"


def test_unparseable_last_success_does_not_crash_the_healthcheck(tmp_path: Path) -> None:
    document = {"beat": datetime.now(UTC).isoformat(), "sources": {"x": {"cadence_seconds": 300, "last_success": "yesterday"}}}
    assert stalled_sources(document) == []


# --- the re-measured publication latency (task 2.3) ----------------------

BLOCK_KEYS = {"estimate_seconds", "observation_count", "last_observed", "latency_measured", "basis"}


def test_latency_estimate_moves_toward_an_observed_publication() -> None:
    """The scenario as written: a run first seen at T+4 h 50 m against a
    T+5 h 18 m estimate moves the estimate toward the observation."""
    from ingest.registry import get_config
    from ingest.scheduler import observe_latency

    seed = get_config("noaa-gfs").publication_latency
    assert seed is not None and seed.estimate_seconds == 19080 and seed.measured is False

    observed_at = RUN_00Z + timedelta(hours=4, minutes=50)
    updated = observe_latency(seed, run_time=RUN_00Z, observed_at=observed_at)

    assert 17400 <= updated.estimate_seconds < 19080, "the estimate moves toward the observation"
    assert updated.observation_count == seed.observation_count + 1
    assert updated.last_observed == observed_at
    assert updated.measured is True
    assert "this deployment" in updated.basis, "the basis names whose observations these are"
    # The seed is not mutated: the registry record keeps saying what it said.
    assert seed.estimate_seconds == 19080 and seed.measured is False


def test_latency_estimate_rises_faster_than_it_falls() -> None:
    """The recorded estimator choice: a high quantile, not a median. A late
    publication is absorbed quickly; an early one gives up horizon slowly."""
    from ingest.scheduler import LATENCY_QUANTILE, observe_latency
    from ingest.registry import PublicationLatency

    seed = PublicationLatency(
        estimate_seconds=19080, observation_count=0, last_observed=None, measured=False, basis="seed",
    )
    late = observe_latency(seed, run_time=RUN_00Z, observed_at=RUN_00Z + timedelta(seconds=19080 + 3600))
    early = observe_latency(seed, run_time=RUN_00Z, observed_at=RUN_00Z + timedelta(seconds=19080 - 3600))

    assert LATENCY_QUANTILE > 0.5
    assert late.estimate_seconds - 19080 > 19080 - early.estimate_seconds


def test_latency_repeated_observations_converge_on_the_observed_value() -> None:
    from ingest.scheduler import observe_latency
    from ingest.registry import PublicationLatency

    latency = PublicationLatency(
        estimate_seconds=19080, observation_count=0, last_observed=None, measured=False, basis="seed",
    )
    for index in range(40):
        run_time = RUN_00Z + timedelta(hours=6 * index)
        latency = observe_latency(latency, run_time=run_time, observed_at=run_time + timedelta(seconds=17400))
    assert latency.observation_count == 40
    assert abs(latency.estimate_seconds - 17400) < 60


def test_latency_first_observation_of_an_unseeded_source_is_the_observation() -> None:
    """GDPS has no seed. The first measurement is the measurement itself; a
    smoothed value there would publish a number no run produced."""
    from ingest.registry import get_config
    from ingest.scheduler import observe_latency

    seed = get_config("eccc-gdps").publication_latency
    assert seed is not None and seed.estimate_seconds is None

    updated = observe_latency(seed, run_time=RUN_00Z, observed_at=RUN_00Z + timedelta(hours=2))
    assert updated.estimate_seconds == 7200
    assert updated.observation_count == 1
    assert updated.measured is True


def test_latency_observation_before_the_run_time_is_zero_not_negative() -> None:
    from ingest.registry import PublicationLatency
    from ingest.scheduler import observe_latency

    seed = PublicationLatency(
        estimate_seconds=None, observation_count=0, last_observed=None, measured=False, basis="none",
    )
    updated = observe_latency(seed, run_time=RUN_00Z, observed_at=RUN_00Z - timedelta(minutes=5))
    assert updated.estimate_seconds == 0


@pytest.fixture()
def scheduler_over(monkeypatch: pytest.MonkeyPatch):
    """A ``Scheduler`` over chosen registry records, with no adapter or store."""
    from ingest.registry import get_config
    from worker.runtime import Scheduler
    import ingest.registry as registry

    def build(*source_ids: str, restore=None) -> Scheduler:
        pairs = [(object(), get_config(source_id)) for source_id in source_ids]
        monkeypatch.setattr(registry, "load_adapters", lambda *a, **k: [])
        monkeypatch.setattr(registry, "scheduled", lambda: iter(pairs))
        return Scheduler(None, restore=restore)

    return build


def _outcome(source_id: str, state: str):
    from worker.runtime import SourceOutcome

    detail = "published 1 artifact(s)" if state == "succeeded" else "nothing usable upstream: no populated run cycle"
    return SourceOutcome(source_id, state, detail, 1 if state == "succeeded" else 0)


def test_latency_seed_block_is_published_before_any_observation(scheduler_over) -> None:
    """The reader sees the seed and that it is a seed, not an absence."""
    scheduler = scheduler_over("noaa-gfs", "eccc-gdps")
    gfs = scheduler.progress["noaa-gfs"]
    assert set(gfs["publication_latency"]) == BLOCK_KEYS
    assert gfs["publication_latency"]["estimate_seconds"] == 19080
    assert gfs["publication_latency"]["latency_measured"] is False
    assert gfs["publication_latency"]["observation_count"] == 0
    assert gfs["publication_latency"]["last_observed"] is None
    assert "seed" in gfs["publication_latency"]["basis"]
    assert gfs["last_observed_publication"] is None
    assert scheduler.progress["eccc-gdps"]["publication_latency"]["estimate_seconds"] is None


def test_latency_is_re_measured_in_the_heartbeat_when_the_run_appears(scheduler_over) -> None:
    """Scenario "Latency is re-measured from an observed publication"."""
    from ingest.registry import get_config

    scheduler = scheduler_over("noaa-gfs")
    config = get_config("noaa-gfs")
    appeared = RUN_00Z + timedelta(hours=4, minutes=50)

    scheduler._poll(config, _outcome("noaa-gfs", "cancelled"), RUN_00Z + timedelta(hours=4, minutes=40))
    outcome, due = scheduler._poll(config, _outcome("noaa-gfs", "succeeded"), appeared)

    assert outcome.state == "succeeded" and due is None
    state = scheduler.progress["noaa-gfs"]
    block = state["publication_latency"]
    assert set(block) == BLOCK_KEYS
    assert block["latency_measured"] is True
    assert block["observation_count"] == 1
    assert block["last_observed"] == appeared.isoformat()
    assert 17400 <= block["estimate_seconds"] < 19080
    assert "this deployment" in block["basis"]
    assert state["last_observed_publication"] == appeared.isoformat()
    assert state["latency_measured"] is True


def test_latency_is_re_measured_without_an_open_poll(scheduler_over) -> None:
    """A run that is there on the first attempt is still an observation."""
    from ingest.registry import get_config

    scheduler = scheduler_over("noaa-gfs")
    appeared = RUN_00Z + timedelta(hours=5, minutes=18)
    scheduler._poll(get_config("noaa-gfs"), _outcome("noaa-gfs", "succeeded"), appeared)

    block = scheduler.progress["noaa-gfs"]["publication_latency"]
    assert block["latency_measured"] is True
    assert block["observation_count"] == 1
    assert scheduler.progress["noaa-gfs"]["observed_publication_run_time"] == RUN_00Z.isoformat()


def test_latency_writes_nothing_when_the_run_never_appeared(scheduler_over) -> None:
    """Scenario "A run that never appeared": the estimate and its count are
    unchanged and the absence is a cancelled attempt naming the run."""
    from ingest.registry import get_config

    scheduler = scheduler_over("noaa-gfs")
    config = get_config("noaa-gfs")
    before = dict(scheduler.progress["noaa-gfs"]["publication_latency"])

    scheduler._poll(config, _outcome("noaa-gfs", "cancelled"), RUN_00Z + timedelta(hours=1))
    outcome, due = scheduler._poll(config, _outcome("noaa-gfs", "cancelled"), RUN_00Z + timedelta(hours=6))

    assert due is None and outcome.state == "cancelled"
    assert "did not appear after polling" in outcome.detail and RUN_00Z.isoformat() in outcome.detail
    state = scheduler.progress["noaa-gfs"]
    assert state["publication_latency"] == before
    assert state["publication_latency"]["observation_count"] == 0
    assert state["publication_latency"]["latency_measured"] is False
    assert state["last_observed_publication"] is None
    assert "observed_publication" not in state


def test_latency_block_is_untouched_for_a_non_forecast_source(scheduler_over) -> None:
    """Radar has no run to wait for, so nothing measures a latency for it."""
    from ingest.registry import get_config

    scheduler = scheduler_over("eccc-radar")
    assert "publication_latency" not in scheduler.progress["eccc-radar"]

    scheduler._poll(get_config("eccc-radar"), _outcome("eccc-radar", "succeeded"), RUN_00Z + timedelta(minutes=6))
    state = scheduler.progress["eccc-radar"]
    assert "publication_latency" not in state
    assert "last_observed_publication" not in state
    assert state.get("latency_measured") is False


def test_latency_measurement_moves_the_next_first_attempt(scheduler_over) -> None:
    """The live estimate, not the seed, places the next run's first attempt."""
    from ingest.registry import get_config

    scheduler = scheduler_over("noaa-gfs")
    config = get_config("noaa-gfs")
    appeared = RUN_00Z + timedelta(hours=4, minutes=50)
    scheduler._poll(config, _outcome("noaa-gfs", "succeeded"), appeared)
    measured = scheduler.progress["noaa-gfs"]["publication_latency"]["estimate_seconds"]

    # Past the 00z first attempt, so the next attempt belongs to the 06z run.
    scheduler._reschedule(config, appeared + timedelta(hours=1))
    state = scheduler.progress["noaa-gfs"]
    assert state["latency_measured"] is True
    expected = datetime(2026, 9, 2, 6, tzinfo=UTC) + timedelta(seconds=measured)
    assert state["next_due"] == expected.isoformat()


def test_latency_measurement_survives_a_restart(scheduler_over, tmp_path: Path) -> None:
    """A restart that forgot its measurements would go back to the seed."""
    from ingest.registry import get_config

    first = scheduler_over("noaa-gfs")
    appeared = RUN_00Z + timedelta(hours=4, minutes=50)
    first._poll(get_config("noaa-gfs"), _outcome("noaa-gfs", "succeeded"), appeared)
    measured = first.progress["noaa-gfs"]["publication_latency"]

    path = tmp_path / "beat"
    write_heartbeat(path, first.progress)
    document = read_heartbeat(path)
    assert document is not None

    restarted = scheduler_over("noaa-gfs", restore=document)
    assert restarted.progress["noaa-gfs"]["publication_latency"] == measured
    assert restarted.progress["noaa-gfs"]["last_observed_publication"] == appeared.isoformat()

    # And a second observation continues the count rather than restarting it.
    restarted._poll(get_config("noaa-gfs"), _outcome("noaa-gfs", "succeeded"), appeared + timedelta(hours=6))
    assert restarted.progress["noaa-gfs"]["publication_latency"]["observation_count"] == 2


@pytest.mark.parametrize(
    "block",
    [
        None,
        {"estimate_seconds": 19080, "observation_count": 0, "last_observed": None, "latency_measured": False, "basis": "seed"},
        {"estimate_seconds": 1, "observation_count": 1, "last_observed": "yesterday", "latency_measured": True, "basis": "x"},
        {"estimate_seconds": None, "observation_count": 3, "last_observed": None, "latency_measured": True, "basis": "x"},
        "not a block",
    ],
)
def test_latency_restore_refuses_anything_that_is_not_a_measurement(scheduler_over, block) -> None:
    document = {"beat": datetime.now(UTC).isoformat(), "sources": {"noaa-gfs": {"publication_latency": block}}}
    scheduler = scheduler_over("noaa-gfs", restore=document)
    restored = scheduler.progress["noaa-gfs"]["publication_latency"]
    assert restored["latency_measured"] is False
    assert restored["estimate_seconds"] == 19080, "the registry seed governs when there is no measurement"


def test_latency_block_round_trips_through_the_heartbeat_document(scheduler_over, tmp_path: Path) -> None:
    from ingest.registry import get_config

    scheduler = scheduler_over("noaa-gfs")
    appeared = RUN_00Z + timedelta(hours=5)
    scheduler._poll(get_config("noaa-gfs"), _outcome("noaa-gfs", "succeeded"), appeared)

    path = tmp_path / "beat"
    write_heartbeat(path, scheduler.progress)
    document = read_heartbeat(path)
    assert document is not None
    block = document["sources"]["noaa-gfs"]["publication_latency"]
    assert set(block) == BLOCK_KEYS
    assert block["last_observed"] == appeared.isoformat()
    assert document["sources"]["noaa-gfs"]["last_observed_publication"] == appeared.isoformat()
    # The document a healthcheck reads is still a healthy one.
    assert check_heartbeat(path) == 0
