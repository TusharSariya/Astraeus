"""`/timeline` over the sliding window: 361 hours, correct locally, honest when empty."""

from __future__ import annotations

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
