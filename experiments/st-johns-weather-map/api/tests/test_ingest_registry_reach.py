"""The declared horizon, as the scheduler sees it through ``IngestConfig``.

``registry/tests/test_reach.py`` proves the registry records are well formed.
This module proves the scheduler-facing view carries them: the reach of a run
depends on that run's own cycle, an observation is scheduled against a native
cadence and no run cadence, and a record that declares no reach is not
schedulable at all.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from ingest.registry import PublicationLatency, Reach, get_config

UTC = timezone.utc


def test_hrdps_carries_reach_run_cadence_and_a_datamart_fallback() -> None:
    config = get_config("eccc-hrdps")
    assert config.reach == Reach(earliest_hours=0.0, latest_hours=48.0, per_cycle={})
    assert config.run_cadence_seconds == 21600
    assert config.native_cadence_seconds is None
    assert config.datamart_fallback_path == (
        "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/{HH}/{FFF}/"
    )
    assert config.ingestible


def test_ifs_reach_is_per_cycle_and_a_06z_run_reaches_144_hours() -> None:
    config = get_config("ecmwf-ifs")
    assert config.reach is not None
    long_run = datetime(2026, 9, 2, 0, tzinfo=UTC)
    short_run = datetime(2026, 9, 2, 6, tzinfo=UTC)

    assert config.reach.latest_hours_for(long_run) == 360.0
    assert config.reach.latest_hours_for(short_run) == 144.0
    assert config.reach.span(short_run) == (short_run, datetime(2026, 9, 8, 6, tzinfo=UTC))
    # Day 10 is inside the 00z run and nine days beyond the 06z one.
    day_ten = datetime(2026, 9, 12, 0, tzinfo=UTC)
    assert config.reach.covers(long_run, day_ten)
    assert not config.reach.covers(short_run, day_ten)


def test_ifs_latency_is_a_seed_and_says_so() -> None:
    latency = get_config("ecmwf-ifs").publication_latency
    assert isinstance(latency, PublicationLatency)
    assert latency.estimate_seconds == 27360
    assert latency.measured is False
    assert latency.observation_count == 0
    assert latency.last_observed is None
    assert "planning-horizon-matrix" in latency.basis


def test_radar_is_scheduled_on_a_native_cadence_with_no_run_cadence() -> None:
    config = get_config("eccc-radar")
    assert config.native_cadence_seconds == 360
    assert config.run_cadence_seconds is None
    assert config.publication_latency is None
    assert config.reach == Reach(earliest_hours=0.0, latest_hours=0.0, per_cycle={})
    assert config.ingestible


def test_poll_and_cycle_seconds_are_untouched_by_the_declared_horizon() -> None:
    """The declared numbers sit beside the derived ones, they do not replace them."""
    config = get_config("eccc-hrdps")
    assert config.cycle_seconds == 21600
    assert config.cadence_seconds > 0


def test_a_record_with_no_reach_is_not_ingestible() -> None:
    config = get_config("eccc-hrdps")
    assert dataclasses.replace(config, reach=None).ingestible is False


def test_a_record_with_neither_cadence_is_not_ingestible() -> None:
    config = get_config("eccc-hrdps")
    stripped = dataclasses.replace(config, run_cadence_seconds=None, native_cadence_seconds=None)
    assert stripped.ingestible is False


def test_a_catalogued_record_with_no_adapter_horizon_stays_unschedulable() -> None:
    """Most records declare no horizon at all, and none of them may be scheduled."""
    config = get_config("eccc-rdwps")
    assert config.reach is None
    assert config.ingestible is False
