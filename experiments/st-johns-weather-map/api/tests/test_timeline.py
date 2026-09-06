"""`/timeline` over the sliding window: 361 hours, correct locally, honest when empty."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import sys as _sys

from weather_api.app import PREFIX, app
from weather_api.config import WINDOW_STEPS, sliding_window
from weather_api.fixtures import now, timeline
from weather_api.store import StoreUnavailable

# ``weather_api.app`` the attribute is the FastAPI instance; the module is what
# has to be patched.
api_module = _sys.modules["weather_api.app"]

client = TestClient(app)
NEWFOUNDLAND = ZoneInfo("America/St_Johns")
NST = timedelta(hours=-3, minutes=-30)
NDT = timedelta(hours=-2, minutes=-30)


class EmptyStore:
    """A live store that is reachable and holds nothing."""

    skipped: list[Any] = []
    unmodelled: list[Any] = []

    def published_products(self) -> dict[str, set[datetime]]:
        return {}

    def source_activity(self) -> dict[str, datetime]:
        return {}

    def current(self) -> list[Any]:
        return []


@dataclass(frozen=True)
class Retained:
    """A retained revision, shaped exactly as ``ingest.store.RetainedArtifact``.

    ``run_time`` is the ``model_runs`` column - the retrieval-time fallback -
    and is deliberately different from the adapter's declared run time in
    ``provenance``, so a test that confused the two would fail.
    """

    source_id: str
    provider_run_id: str
    provenance: dict[str, Any]
    valid_time_start: datetime | None = None
    valid_time_end: datetime | None = None
    logical_name: str = "surface"
    revision_id: str = "rev"
    state: str = "published"
    published_at: datetime | None = None
    retrieval_run_time: datetime | None = None


def run_of(source_id, run_time, *, first_lead_hours=0, last_lead_hours=24, provider_run_id=None, declare_run_time=True):
    """One retained run publishing an hourly span of frames from its run time."""
    provenance: dict[str, Any] = {
        "valid_times": [
            (run_time + timedelta(hours=lead)).isoformat()
            for lead in range(first_lead_hours, last_lead_hours + 1)
        ]
    }
    if declare_run_time:
        provenance["run_time"] = run_time.isoformat()
    return Retained(
        source_id=source_id,
        provider_run_id=provider_run_id or f"{source_id}:{run_time.isoformat()}",
        provenance=provenance,
        retrieval_run_time=run_time + timedelta(hours=5),
    )


class RetainingStore(EmptyStore):
    """A reachable store holding the runs it is given."""

    def __init__(self, runs, *, published=None):
        self._runs = list(runs)
        self._published = published or {}

    def retained_artifacts(self):
        return list(self._runs)

    def published_products(self):
        return dict(self._published)


def use_live_store(monkeypatch, data_mode, store) -> None:
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)


@pytest.fixture(autouse=True)
def no_last_valid_time_record(monkeypatch):
    """Default: the store holds no record, so every absence is ``null``.

    Stated rather than inherited. A test that forgets it would be asserting
    against whatever the real query does against a store that is not there.
    """
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {})


# --- 361 hourly items ----------------------------------------------------

def test_the_timeline_returns_361_hourly_items_across_the_whole_window():
    payload = client.get(f"{PREFIX}/timeline").json()
    start = datetime.fromisoformat(payload["start"])
    end = datetime.fromisoformat(payload["end"])

    assert len(payload["items"]) == 361 == WINDOW_STEPS
    assert end - start == timedelta(days=15)
    stamps = [datetime.fromisoformat(item["valid_time_utc"]) for item in payload["items"]]
    assert stamps[0] == start and stamps[-1] == end
    assert all(later - earlier == timedelta(hours=1) for earlier, later in zip(stamps, stamps[1:]))


def test_361_items_are_still_returned_when_the_store_holds_nothing(monkeypatch, data_mode):
    """An unavailable timeline is a full window of empty hours, not a short one."""
    use_live_store(monkeypatch, data_mode, EmptyStore())
    payload = client.get(f"{PREFIX}/timeline").json()

    assert payload["data_mode"] == "unavailable"
    assert len(payload["items"]) == 361
    assert all(item["available_products"] == [] for item in payload["items"])
    assert payload["notices"]


# --- local time comes from the zone database, on both sides of a DST change

def test_local_times_are_zone_derived_across_a_dst_transition():
    """A 15-day window can straddle a transition, so a fixed offset is wrong.

    Newfoundland leaves DST on 2026-11-01. A window opened on 2026-10-25 holds
    hours on both sides of it, and every one of them has to carry the offset
    the zone database gives, not one offset for the whole response.
    """
    reference = datetime(2026, 10, 25, 12, tzinfo=UTC)
    items = timeline(reference)

    assert len(items) == 361
    offsets = {item.valid_time_newfoundland.utcoffset() for item in items}
    assert offsets == {NDT, NST}, "the window straddles the transition and must show both"
    assert all(
        item.valid_time_newfoundland == item.valid_time_utc.astimezone(NEWFOUNDLAND)
        for item in items
    )


def test_every_item_carries_the_same_instant_in_both_zones():
    payload = client.get(f"{PREFIX}/timeline").json()
    for item in payload["items"]:
        utc = datetime.fromisoformat(item["valid_time_utc"])
        local = datetime.fromisoformat(item["valid_time_newfoundland"])
        assert local == utc.astimezone(NEWFOUNDLAND)
        assert local.utcoffset() in {NDT, NST}


# --- the boundaries themselves -------------------------------------------

def test_the_boundary_instants_are_accepted_and_outside_ones_are_422():
    reference = now()
    start, end = sliding_window(reference)

    assert client.get(f"{PREFIX}/point", params={"valid_time": start.isoformat()}).status_code == 200
    assert client.get(f"{PREFIX}/point", params={"valid_time": end.isoformat()}).status_code == 200

    before = client.get(f"{PREFIX}/point", params={"valid_time": (start - timedelta(minutes=1)).isoformat()})
    after = client.get(f"{PREFIX}/point", params={"valid_time": (end + timedelta(minutes=1)).isoformat()})
    assert before.status_code == after.status_code == 422
    assert "window" in before.json()["detail"] and "window" in after.json()["detail"]


def test_a_naive_boundary_instant_is_still_refused():
    reference = now()
    start, _ = sliding_window(reference)
    response = client.get(f"{PREFIX}/point", params={"valid_time": start.replace(tzinfo=None).isoformat()})
    assert response.status_code == 422
    assert "UTC offset" in response.json()["detail"]


# --- an emptied hour names why -------------------------------------------

def test_an_hour_emptied_by_the_purge_names_its_aged_out_sources(monkeypatch, data_mode):
    """An hour with nothing must not read like an hour nothing ever covered."""
    held = datetime(2026, 9, 1, 6, tzinfo=UTC)
    use_live_store(monkeypatch, data_mode, EmptyStore())
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {"eccc-hrdps": held})

    payload = client.get(f"{PREFIX}/timeline").json()

    assert payload["data_mode"] == "unavailable"
    assert all(item["available_products"] == [] for item in payload["items"])
    named = payload["items"][0]["aged_out_sources"]
    assert set(named) == {"eccc-hrdps"}
    assert datetime.fromisoformat(named["eccc-hrdps"]) == held


def test_an_hour_that_holds_a_product_is_not_reported_aged_out(monkeypatch, data_mode):
    covered = now()

    class OneHour(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {covered}}

    use_live_store(monkeypatch, data_mode, OneHour())
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {"eccc-hrdps": covered})

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}

    assert at_hour[covered]["available_products"] == ["eccc-hrdps"]
    assert at_hour[covered]["aged_out_sources"] == {}
    # A source that is still serving is not aged out in any hour, including the
    # empty ones: the record is a high-water mark, not a claim about now.
    assert all(item["aged_out_sources"] == {} for item in payload["items"])


def test_an_unreadable_store_says_neither_held_nor_aged_out(monkeypatch, data_mode):
    """No hour holds a product AND no hour has aged out: both would be guesses."""

    class Raising(EmptyStore):
        def published_products(self):
            raise StoreUnavailable("postgres is gone")

    use_live_store(monkeypatch, data_mode, Raising())
    payload = client.get(f"{PREFIX}/timeline").json()

    assert payload["data_mode"] == "unavailable"
    assert len(payload["items"]) == 361
    assert all(item["available_products"] == [] for item in payload["items"])
    assert all(item["aged_out_sources"] == {} for item in payload["items"])
    assert any("raised" in notice for notice in payload["notices"])


def test_an_unreadable_last_valid_time_record_reports_no_absence_state(monkeypatch, data_mode):
    def raising(store):
        raise StoreUnavailable("the last valid time table is unreachable")

    use_live_store(monkeypatch, data_mode, EmptyStore())
    monkeypatch.setattr(api_module, "last_valid_times", raising)

    payload = client.get(f"{PREFIX}/timeline").json()
    assert all(item["aged_out_sources"] == {} for item in payload["items"])
    assert any("aged out" in notice for notice in payload["notices"])


# --- the two tiers, as ranges --------------------------------------------

def test_the_timeline_serves_both_tier_ranges_and_the_boundary_between_them():
    """Two ranges, meeting at the boundary and covering the window exactly."""
    payload = client.get(f"{PREFIX}/timeline").json()
    reference = now()

    core, planning = payload["tiers"]
    assert core["id"] == "core" and planning["id"] == "planning"
    assert datetime.fromisoformat(core["start"]) == reference - timedelta(hours=24)
    assert datetime.fromisoformat(core["end"]) == reference + timedelta(hours=24)
    assert datetime.fromisoformat(planning["start"]) == reference + timedelta(hours=24)
    assert datetime.fromisoformat(planning["end"]) == reference + timedelta(days=14)
    # The boundary is the join, and the two ranges are the whole window.
    assert datetime.fromisoformat(payload["boundary"]) == datetime.fromisoformat(core["end"])
    assert core["start"] == payload["start"] and planning["end"] == payload["end"]


def test_no_tier_names_a_source():
    """A tier is a valid-time range; a source list in one would be the defect."""
    payload = client.get(f"{PREFIX}/timeline").json()
    assert all(set(tier) == {"id", "start", "end"} for tier in payload["tiers"])


def test_every_item_carries_the_tier_its_own_instant_falls_in():
    payload = client.get(f"{PREFIX}/timeline").json()
    boundary = datetime.fromisoformat(payload["boundary"])
    for item in payload["items"]:
        valid_time = datetime.fromisoformat(item["valid_time_utc"])
        assert item["tier"] == ("core" if valid_time <= boundary else "planning")
    assert {item["tier"] for item in payload["items"]} == {"core", "planning"}


def test_an_instant_in_neither_tier_is_refused_naming_both_tier_ranges():
    reference = now()
    start, end = sliding_window(reference)
    for outside in (start - timedelta(minutes=1), end + timedelta(minutes=1)):
        response = client.get(f"{PREFIX}/point", params={"valid_time": outside.isoformat()})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "core tier" in detail and "planning tier" in detail
        # Both ranges are named in full, so the refusal says where the two are.
        for stamp in (start, reference + timedelta(hours=24), end):
            assert stamp.isoformat() in detail


def test_the_boundary_instant_itself_is_in_the_core_tier_and_is_served():
    reference = now()
    boundary = reference + timedelta(hours=24)
    assert client.get(f"{PREFIX}/point", params={"valid_time": boundary.isoformat()}).status_code == 200
    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    assert at_hour[boundary]["tier"] == "core"


# --- coverage from declared reach against runs actually retrieved --------

def test_coverage_lists_every_retained_run_reaching_the_instant(monkeypatch, data_mode):
    """Three runs cover one instant; all three are listed, none is primary."""
    reference = now()
    hour = reference + timedelta(hours=12)
    runs = [
        run_of("eccc-hrdps", reference - timedelta(hours=2), last_lead_hours=48),
        run_of("noaa-gfs", reference - timedelta(hours=5), last_lead_hours=120),
        run_of("ecmwf-ifs", reference - timedelta(hours=7), last_lead_hours=240),
    ]
    use_live_store(monkeypatch, data_mode, RetainingStore(runs, published={"eccc-hrdps": {hour}}))

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    covering = at_hour[hour]["coverage"]

    assert [entry["source_id"] for entry in covering] == ["eccc-hrdps", "ecmwf-ifs", "noaa-gfs"]
    assert at_hour[hour]["coverage_notice"] is None
    for entry, run in zip(covering, sorted(runs, key=lambda item: item.source_id)):
        assert datetime.fromisoformat(entry["run_time"]) == datetime.fromisoformat(run.provenance["run_time"])
        assert entry["provider_run_id"] == run.provider_run_id


def test_coverage_omits_a_declared_reach_with_no_retrieved_run(monkeypatch, data_mode):
    """HRDPS declares a 48 h reach; with nothing retrieved it covers nothing."""
    reference = now()
    hour = reference + timedelta(hours=6)
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("noaa-gfs", reference - timedelta(hours=5), last_lead_hours=120)], published={"noaa-gfs": {hour}}),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    assert [entry["source_id"] for entry in at_hour[hour]["coverage"]] == ["noaa-gfs"]


def test_coverage_stops_where_the_run_stopped_publishing_frames(monkeypatch, data_mode):
    """GFS reaches 384 h; a run that published to +11 h covers only to +11 h."""
    reference = now()
    run_time = reference - timedelta(hours=5)
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("noaa-gfs", run_time, last_lead_hours=11)], published={"noaa-gfs": {reference}}),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    covered = {
        datetime.fromisoformat(item["valid_time_utc"])
        for item in payload["items"] if item["coverage"]
    }
    assert max(covered) == run_time + timedelta(hours=11)
    assert reference + timedelta(hours=12) not in covered


def test_coverage_is_empty_with_a_notice_when_nothing_covers_the_instant(monkeypatch, data_mode):
    reference = now()
    run_time = reference - timedelta(hours=5)
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("noaa-gfs", run_time, last_lead_hours=11)], published={"noaa-gfs": {reference}}),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    far = at_hour[reference + timedelta(days=10)]

    assert far["coverage"] == []
    assert far["coverage_notice"] == "nothing covers this instant"
    # The neighbouring covered hour's list is not borrowed.
    assert at_hour[reference]["coverage"] and at_hour[reference]["coverage_notice"] is None


def test_no_coverage_is_claimed_when_the_store_cannot_report_retained_runs(monkeypatch, data_mode):
    """Unresolvable coverage is neither covered nor uncovered - it is unknown."""

    class Raising(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {now()}}

        def retained_artifacts(self):
            raise StoreUnavailable("postgres is gone")

    use_live_store(monkeypatch, data_mode, Raising())
    payload = client.get(f"{PREFIX}/timeline").json()

    assert all(item["coverage"] == [] for item in payload["items"])
    assert all(item["coverage_notice"] is None for item in payload["items"])
    assert any("coverage could not be resolved" in notice for notice in payload["notices"])


def test_coverage_flags_a_run_older_than_twice_its_cadence_as_run_stale(monkeypatch, data_mode):
    """HRDPS is six-hourly, so a thirteen-hour-old run is two cycles behind."""
    reference = now()
    run_time = reference - timedelta(hours=13)
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("eccc-hrdps", run_time, last_lead_hours=48)], published={"eccc-hrdps": {reference}}),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    entry = at_hour[reference]["coverage"][0]

    assert entry["run_cadence_seconds"] == 21600
    assert entry["run_age_seconds"] == 13 * 3600
    assert entry["run_stale"] is True and entry["run_stale_reason"] is None
    # Flagged, never withheld: the hour it feeds still lists it.
    assert at_hour[reference]["coverage_notice"] is None


def test_coverage_reports_a_fresh_run_as_not_stale(monkeypatch, data_mode):
    reference = now()
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("eccc-hrdps", reference - timedelta(hours=2), last_lead_hours=48)], published={"eccc-hrdps": {reference}}),
    )
    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    assert at_hour[reference]["coverage"][0]["run_stale"] is False


def test_coverage_never_reads_a_retrieval_time_as_a_run_time(monkeypatch, data_mode):
    """An undeclared run time is null, with run_stale null and the reason."""
    reference = now()
    run_time = reference - timedelta(hours=3)
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore(
            [run_of("eccc-hrdps", run_time, last_lead_hours=48, declare_run_time=False)],
            published={"eccc-hrdps": {reference}},
        ),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    entry = at_hour[reference]["coverage"][0]

    assert entry["run_time"] is None
    assert entry["run_age_seconds"] is None
    assert entry["run_stale"] is None
    assert "no run time" in entry["run_stale_reason"]


def test_coverage_crosses_the_tier_boundary_without_being_filtered(monkeypatch, data_mode):
    """One GFS run covering hour 3 and day 10 is listed in both tiers."""
    reference = now()
    run_time = reference - timedelta(hours=5)
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("noaa-gfs", run_time, last_lead_hours=360)], published={"noaa-gfs": {reference}}),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    at_hour = {datetime.fromisoformat(item["valid_time_utc"]): item for item in payload["items"]}
    near, far = at_hour[reference + timedelta(hours=3)], at_hour[reference + timedelta(days=10)]

    assert near["tier"] == "core" and far["tier"] == "planning"
    assert [entry["source_id"] for entry in near["coverage"]] == ["noaa-gfs"]
    assert [entry["source_id"] for entry in far["coverage"]] == ["noaa-gfs"]


def test_coverage_honours_the_per_cycle_reach_of_a_short_cycle(monkeypatch, data_mode):
    """IFS at 06z reaches 144 h, so nothing past that is credited to it."""
    reference = now()
    run_time = reference.replace(hour=6) - timedelta(days=1)
    # The run published far more frames than its cycle reaches; the declared
    # reach is the promise and caps what the delivery may be credited with.
    use_live_store(
        monkeypatch, data_mode,
        RetainingStore([run_of("ecmwf-ifs", run_time, last_lead_hours=360)], published={"ecmwf-ifs": {reference}}),
    )

    payload = client.get(f"{PREFIX}/timeline").json()
    covered = {
        datetime.fromisoformat(item["valid_time_utc"])
        for item in payload["items"] if item["coverage"]
    }
    assert max(covered) <= run_time + timedelta(hours=144)
