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

Task 2.2's bounded ten-minute poll and the declared ECCC Datamart fallback are
covered here too. Task 2.3 (the heartbeat latency write) is deliberately not.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ingest.registry import PublicationLatency, get_config
from ingest.scheduler import (
    POLL_INTERVAL_SECONDS,
    PollState,
    first_attempt,
    latest_run_time,
    next_due,
    next_run_time,
    poll_decision,
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


@pytest.fixture()
def scheduler_over_adapters(monkeypatch: pytest.MonkeyPatch):
    """A ``Scheduler`` over given ``(adapter, config)`` pairs and no store."""
    from worker.runtime import Scheduler
    import ingest.registry as registry

    def build(*pairs):
        monkeypatch.setattr(registry, "load_adapters", lambda *a, **k: [])
        monkeypatch.setattr(registry, "scheduled", lambda: iter(list(pairs)))
        return Scheduler(None)

    return build


# --- the bounded ten-minute poll -----------------------------------------

SIX_HOURLY = 21600


def test_poll_repeats_every_ten_minutes_until_the_bound() -> None:
    """Absence is polled through, not reported: every attempt before the bound
    asks again ten minutes later and nothing is fetched in the run's place."""
    started = RUN_00Z
    state = PollState(run_time=RUN_00Z, since=started, attempts=1)
    decision = poll_decision(state, run_cadence_seconds=SIX_HOURLY, now=started)
    assert decision.exhausted is False
    assert decision.due == started + timedelta(seconds=POLL_INTERVAL_SECONDS)
    assert decision.bound == datetime(2026, 9, 2, 6, tzinfo=UTC)
    assert "polling for run" in decision.detail

    later = poll_decision(
        dataclasses.replace(state, attempts=4),
        run_cadence_seconds=SIX_HOURLY,
        now=started + timedelta(minutes=30),
    )
    assert later.exhausted is False
    assert later.due == started + timedelta(minutes=40)
    assert later.polled_minutes == 30


def test_poll_stops_at_the_next_run_time_and_names_the_run_and_duration() -> None:
    """At the bound the missing run is superseded, not late."""
    state = PollState(run_time=RUN_00Z, since=RUN_00Z, attempts=36)
    bound = datetime(2026, 9, 2, 6, tzinfo=UTC)
    decision = poll_decision(state, run_cadence_seconds=SIX_HOURLY, now=bound)
    assert decision.exhausted is True
    assert decision.due is None
    assert decision.bound == bound
    assert decision.detail == (
        f"run {RUN_00Z.isoformat()} did not appear after polling 360 min; previous run stays visible"
    )


def test_poll_names_the_provider_run_id_where_the_candidate_gave_one() -> None:
    state = PollState(run_time=RUN_00Z, since=RUN_00Z, attempts=2, provider_run_id="2026090200")
    decision = poll_decision(
        state, run_cadence_seconds=SIX_HOURLY, now=RUN_00Z + timedelta(hours=6),
    )
    assert decision.detail.startswith("run 2026090200 did not appear after polling 360 min")


def test_poll_last_attempt_lands_exactly_on_the_bound() -> None:
    """The window closes on an attempt, not on a clock the source never answered."""
    state = PollState(run_time=RUN_00Z, since=RUN_00Z, attempts=35)
    almost = datetime(2026, 9, 2, 5, 55, tzinfo=UTC)
    decision = poll_decision(state, run_cadence_seconds=SIX_HOURLY, now=almost)
    assert decision.due == datetime(2026, 9, 2, 6, tzinfo=UTC)
    assert decision.due == decision.bound


def test_poll_refuses_a_cadence_that_is_not_a_positive_number_of_seconds() -> None:
    with pytest.raises(ValueError):
        poll_decision(PollState(run_time=RUN_00Z, since=RUN_00Z), run_cadence_seconds=0, now=RUN_00Z)


# --- the worker polls on those decisions ---------------------------------

def _cancelled(source_id: str):
    from worker.runtime import SourceOutcome

    return SourceOutcome(source_id, "cancelled", "nothing usable upstream: no populated run cycle")


def test_scheduler_poll_opens_on_a_cancelled_forecast_attempt(scheduler_over) -> None:
    """A forecast run that is not there yet is polled for, and the poll state
    is recorded so task 2.3 can write the publication instant when it lands."""
    scheduler = scheduler_over("eccc-gdps")
    config = get_config("eccc-gdps")
    now = datetime(2026, 9, 2, 0, 5, tzinfo=UTC)

    outcome, due = scheduler._poll(config, _cancelled("eccc-gdps"), now)
    assert outcome.state == "cancelled"
    assert due == now + timedelta(seconds=POLL_INTERVAL_SECONDS)
    polling = scheduler.progress["eccc-gdps"]["polling"]
    assert polling == {"run_time": RUN_00Z.isoformat(), "since": now.isoformat(), "attempts": 1}
    assert scheduler.progress["eccc-gdps"]["poll_bound"] == datetime(2026, 9, 2, 12, tzinfo=UTC).isoformat()


def test_scheduler_poll_counts_attempts_and_keeps_the_run_it_waits_for(scheduler_over) -> None:
    scheduler = scheduler_over("eccc-gdps")
    config = get_config("eccc-gdps")
    started = datetime(2026, 9, 2, 0, 5, tzinfo=UTC)
    for index in range(3):
        outcome, due = scheduler._poll(config, _cancelled("eccc-gdps"), started + timedelta(minutes=10 * index))
        assert outcome.state == "cancelled"
        assert due is not None
    polling = scheduler.progress["eccc-gdps"]["polling"]
    assert polling["attempts"] == 3
    assert polling["since"] == started.isoformat()
    assert polling["run_time"] == RUN_00Z.isoformat()


def test_scheduler_poll_at_the_bound_reports_the_declared_cancellation(scheduler_over) -> None:
    scheduler = scheduler_over("eccc-gdps")
    config = get_config("eccc-gdps")
    started = datetime(2026, 9, 2, 0, tzinfo=UTC)
    scheduler._poll(config, _cancelled("eccc-gdps"), started)

    bound = datetime(2026, 9, 2, 12, tzinfo=UTC)
    outcome, due = scheduler._poll(config, _cancelled("eccc-gdps"), bound)
    assert outcome.state == "cancelled"
    assert outcome.detail == (
        f"run {RUN_00Z.isoformat()} did not appear after polling 720 min; previous run stays visible"
    )
    # The source goes back on its normal schedule, and nothing was written
    # about a publication that never happened.
    assert due is None
    assert "polling" not in scheduler.progress["eccc-gdps"]
    assert "observed_publication" not in scheduler.progress["eccc-gdps"]


def test_scheduler_poll_records_the_publication_instant_when_the_run_appears(scheduler_over) -> None:
    """The late run is fetched and the instant it was first seen is recorded;
    no earlier poll was reported as a failure."""
    from worker.runtime import SourceOutcome

    scheduler = scheduler_over("eccc-gdps")
    config = get_config("eccc-gdps")
    started = datetime(2026, 9, 2, 0, tzinfo=UTC)
    for index in range(3):
        outcome, _ = scheduler._poll(config, _cancelled("eccc-gdps"), started + timedelta(minutes=10 * index))
        assert outcome.state != "failed"

    appeared = started + timedelta(minutes=40)
    outcome, due = scheduler._poll(
        config, SourceOutcome("eccc-gdps", "succeeded", "published 1 artifact(s)", 1), appeared,
    )
    assert outcome.state == "succeeded"
    assert due is None
    state = scheduler.progress["eccc-gdps"]
    assert state["observed_publication"] == appeared.isoformat()
    assert state["observed_publication_run_time"] == RUN_00Z.isoformat()
    assert "polling" not in state


def test_scheduler_poll_is_not_opened_for_an_observation_source(scheduler_over) -> None:
    """Only a forecast run is polled for: an observation source has no run to
    wait for and goes straight back onto its native cadence."""
    scheduler = scheduler_over("eccc-radar")
    outcome, due = scheduler._poll(get_config("eccc-radar"), _cancelled("eccc-radar"), INSIDE_00Z)
    assert due is None
    assert outcome.detail.startswith("nothing usable upstream")
    assert "polling" not in scheduler.progress["eccc-radar"]


def test_scheduler_poll_leaves_a_failed_attempt_alone(scheduler_over) -> None:
    """A failure is a failure; polling absorbs absence, not error."""
    from worker.runtime import SourceOutcome

    scheduler = scheduler_over("eccc-gdps")
    config = get_config("eccc-gdps")
    outcome, due = scheduler._poll(
        config, SourceOutcome("eccc-gdps", "failed", "discovery failed: TimeoutError()"), INSIDE_00Z,
    )
    assert outcome.state == "failed"
    assert due is None
    assert "polling" not in scheduler.progress["eccc-gdps"]


def test_scheduler_poll_cycle_puts_the_source_back_at_its_next_poll(scheduler_over_adapters) -> None:
    """One full cycle over an adapter with nothing upstream: the outcome is a
    cancelled that names the poll, and the next attempt is the poll, not the
    next run."""
    from ingest.contract import AdapterUnavailable

    class Empty:
        source_id = "eccc-gdps"
        adapter_version = "test"

        def discover(self, window):
            raise AdapterUnavailable("no populated run cycle")

    scheduler = scheduler_over_adapters((Empty(), get_config("eccc-gdps")))
    outcomes = scheduler.cycle(force=True)
    assert [item.state for item in outcomes] == ["cancelled"]
    assert "polling for run" in outcomes[0].detail
    state = scheduler.progress["eccc-gdps"]
    assert state["polling"]["attempts"] == 1
    assert state["next_due"] <= state["poll_bound"]
    assert "polling every 600s" in state["schedule_reason"]


# --- the declared dated WXO-DD Datamart fallback -------------------------

FALLBACK_TEMPLATE = (
    "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/{HH}/{FFF}/"
)
DISCOVERY_NOW = datetime(2026, 8, 29, 15, tzinfo=UTC)


def _listing(items: list[str]) -> str:
    return "<html><body>" + "".join(f'<a href="{item}">{item}</a><br>' for item in items) + "</body></html>"


def _populated_tree(prefix: str) -> dict[str, str]:
    stamped = [
        f"20260829T12Z_MSC_HRDPS_{var}_AGL-2m_RLatLon0.0225_PT000H.grib2" for var in ("TMP", "DPT")
    ]
    return {
        prefix: _listing(["12/"]),
        f"{prefix}12/": _listing(["000/", "001/"]),
        f"{prefix}12/000/": _listing(stamped),
    }


def _datamart_adapter(url_map: dict[str, str], **kwargs):
    """An HRDPS adapter over a mocked directory tree. No network, no store."""
    pytest.importorskip("numpy")
    from ingest.adapters.eccc_datamart import HRDPS_VARS, ECCCDataMartAdapter
    from ingest.http import PoliteClient, USER_AGENT

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        for pattern, html in sorted(url_map.items(), key=lambda item: len(item[0]), reverse=True):
            if pattern in url_str:
                return httpx.Response(200, text=html)
        return httpx.Response(404)

    client = PoliteClient(min_host_interval_seconds=0.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return ECCCDataMartAdapter(
        source_id="eccc-hrdps",
        model_subpath="model_hrdps/continental/2.5km",
        grid_token="RLatLon0.0225",
        var_map=HRDPS_VARS,
        client=client,
        fallback_days=0,
        **kwargs,
    )


def test_datamart_fallback_path_is_declared_on_every_eccc_model_record() -> None:
    """The path the adapter may fall back to is the record's, not the code's."""
    for source_id in ("eccc-hrdps", "eccc-rdps", "eccc-gdps"):
        declared = get_config(source_id).datamart_fallback_path
        assert declared and declared.startswith("https://dd.weather.gc.ca/")
        assert "{YYYYMMDD}" in declared and "WXO-DD" in declared


def test_datamart_fallback_answers_when_the_primary_path_is_empty() -> None:
    """A primary directory that answers with nothing usable sends discovery to
    the declared dated WXO-DD path, and the answering path is recorded."""
    from ingest.contract import FetchWindow

    url_map = {"https://primary.example/20260829/WXO-DD/model_hrdps/continental/2.5km/": _listing(["doc/"])}
    url_map.update(_populated_tree("https://dd.weather.gc.ca/20260829/WXO-DD/model_hrdps/continental/2.5km/"))
    adapter = _datamart_adapter(
        url_map, base_url="https://primary.example", datamart_fallback_path=FALLBACK_TEMPLATE,
    )

    candidates = adapter.discover(FetchWindow(now=DISCOVERY_NOW))
    assert candidates
    assert candidates[0].provider_run_id == "2026082912"
    assert candidates[0].detail["datamart_path"] == (
        "https://dd.weather.gc.ca/20260829/WXO-DD/model_hrdps/continental/2.5km/"
    )


def test_datamart_fallback_is_not_tried_when_the_primary_answers() -> None:
    from ingest.contract import FetchWindow

    url_map = _populated_tree("https://primary.example/20260829/WXO-DD/model_hrdps/continental/2.5km/")
    adapter = _datamart_adapter(
        url_map, base_url="https://primary.example", datamart_fallback_path=FALLBACK_TEMPLATE,
    )
    candidates = adapter.discover(FetchWindow(now=DISCOVERY_NOW))
    assert candidates[0].detail["datamart_path"] == (
        "https://primary.example/20260829/WXO-DD/model_hrdps/continental/2.5km/"
    )


def test_datamart_fallback_that_is_not_declared_is_never_inferred() -> None:
    """A record with no declared fallback names its primary path only."""
    from ingest.contract import AdapterUnavailable, FetchWindow

    adapter = _datamart_adapter({}, base_url="https://primary.example", datamart_fallback_path="")
    with pytest.raises(AdapterUnavailable) as error:
        adapter.discover(FetchWindow(now=DISCOVERY_NOW))
    message = str(error.value)
    assert "primary.example" in message
    assert "declares no fallback path" in message
    assert "dd.weather.gc.ca" not in message


def test_datamart_fallback_exhausted_names_both_paths() -> None:
    from ingest.contract import AdapterUnavailable, FetchWindow

    adapter = _datamart_adapter({}, base_url="https://primary.example", datamart_fallback_path=FALLBACK_TEMPLATE)
    with pytest.raises(AdapterUnavailable) as error:
        adapter.discover(FetchWindow(now=DISCOVERY_NOW))
    message = str(error.value)
    assert "https://primary.example/" in message
    assert FALLBACK_TEMPLATE in message


def test_datamart_fallback_root_fills_only_the_date() -> None:
    """`{HH}` and `{FFF}` stay for the cycle and lead walk that follows."""
    adapter = _datamart_adapter({}, datamart_fallback_path=FALLBACK_TEMPLATE)
    assert adapter.fallback_root("20260829") == (
        "https://dd.weather.gc.ca/20260829/WXO-DD/model_hrdps/continental/2.5km/"
    )
    assert _datamart_adapter({}, datamart_fallback_path="").fallback_root("20260829") is None
