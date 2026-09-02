"""Live readiness is judged against the sliding window, and names aged out.

The original lie was ``ready: true`` with ``live_store: false``. The lie this
file guards against now is subtler: a deployment whose evidence has all aged
out reporting the same "not ready" as one that never ingested anything. They
are different operational facts and the reader is told which.
"""

from __future__ import annotations

import sys as _sys
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from weather_api.app import PREFIX, app
from weather_api.config import sliding_window
from weather_api.fixtures import now
from weather_api.store import StoreUnavailable

api_module = _sys.modules["weather_api.app"]
client = TestClient(app)


class EmptyStore:
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
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {})


# --- readiness is judged against the sliding window ----------------------

def test_a_frame_inside_the_sliding_window_makes_the_boundary_true(monkeypatch, data_mode):
    """A frame 20 hours old counts now; under the old 3 h window it did not."""
    covered = now() - timedelta(hours=20)

    class Covered(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {covered}}

    use_live_store(monkeypatch, data_mode, Covered())
    payload = client.get(f"{PREFIX}/ready").json()

    assert payload["ready"] is True
    assert payload["checks"]["evidence_boundary"] is True
    assert payload["data_mode"] == "live"


def test_a_frame_ten_days_ahead_is_inside_the_window(monkeypatch, data_mode):
    """The planning tier is served, so readiness must not stop at 24 h ahead."""
    covered = now() + timedelta(days=10)

    class Covered(EmptyStore):
        def published_products(self):
            return {"noaa-gfs": {covered}}

    use_live_store(monkeypatch, data_mode, Covered())
    assert client.get(f"{PREFIX}/ready").json()["ready"] is True


def test_a_frame_outside_the_window_does_not_make_the_deployment_ready(monkeypatch, data_mode):
    reference = now()
    start, end = sliding_window(reference)

    class Outside(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {start - timedelta(hours=1), end + timedelta(hours=1)}}

    use_live_store(monkeypatch, data_mode, Outside())
    payload = client.get(f"{PREFIX}/ready").json()

    assert payload["ready"] is False
    assert payload["checks"]["evidence_boundary"] is False
    assert payload["data_mode"] == "unavailable"


# --- and it names aged out where a last valid time exists ----------------

def test_a_store_holding_only_aged_out_frames_says_so_rather_than_never_retrieved(monkeypatch, data_mode):
    held = datetime(2026, 9, 1, 6, tzinfo=UTC)
    use_live_store(monkeypatch, data_mode, EmptyStore())
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {"eccc-hrdps": held})

    payload = client.get(f"{PREFIX}/ready").json()

    assert payload["ready"] is False
    assert payload["checks"]["evidence_boundary"] is False
    assert payload["data_mode"] == "unavailable"
    assert datetime.fromisoformat(payload["aged_out_sources"]["eccc-hrdps"]) == held


def test_a_deployment_that_never_ingested_reports_no_aged_out_source(monkeypatch, data_mode):
    """No record means never held, and never held is ``null``, not aged out."""
    use_live_store(monkeypatch, data_mode, EmptyStore())
    payload = client.get(f"{PREFIX}/ready").json()

    assert payload["ready"] is False
    assert payload["aged_out_sources"] == {}
    assert payload["notices"] == []


def test_a_ready_deployment_names_no_aged_out_source(monkeypatch, data_mode):
    """A warning beside evidence that is currently being served is noise."""
    covered = now()

    class Covered(EmptyStore):
        def published_products(self):
            return {"eccc-hrdps": {covered}}

    use_live_store(monkeypatch, data_mode, Covered())
    monkeypatch.setattr(api_module, "last_valid_times", lambda store: {"eccc-hrdps": covered})

    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is True
    assert payload["aged_out_sources"] == {}


def test_an_unreadable_last_valid_time_record_names_the_failure_not_an_absence(monkeypatch, data_mode):
    def raising(store):
        raise StoreUnavailable("the last valid time table is unreachable")

    use_live_store(monkeypatch, data_mode, EmptyStore())
    monkeypatch.setattr(api_module, "last_valid_times", raising)

    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is False
    assert payload["aged_out_sources"] == {}
    assert any("aged out" in notice for notice in payload["notices"])


# --- the modes that are not live -----------------------------------------

def test_a_fixture_deployment_is_ready_but_never_claims_a_live_store():
    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is True
    assert payload["data_mode"] == "fixture"
    assert payload["checks"]["live_store"] is False
    assert payload["aged_out_sources"] == {}


def test_an_unconfigured_deployment_is_not_ready(data_mode):
    data_mode(None)
    payload = client.get(f"{PREFIX}/ready").json()
    assert payload["ready"] is False
    assert payload["checks"]["data_mode_configured"] is False
    assert payload["aged_out_sources"] == {}


def test_no_reachable_store_is_not_ready_and_names_no_absence(monkeypatch, data_mode):
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: None)
    payload = client.get(f"{PREFIX}/ready").json()

    assert payload["ready"] is False
    assert payload["checks"]["live_store"] is False
    assert payload["checks"]["evidence_boundary"] is False
    assert payload["aged_out_sources"] == {}, "with no store there is nothing to have aged out of"
