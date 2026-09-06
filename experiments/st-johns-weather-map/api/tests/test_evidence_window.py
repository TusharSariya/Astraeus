"""The evidence window is defined once and every consumer reads that one place.

Four things used to state the window: request validation, the timeline, the
ingestion ``FetchWindow`` and the manifest QC gate. They drifted apart, and a
forecast frame the API served failed the gate that was supposed to protect it.
These tests assert the definition and that nothing restates it as a literal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from weather_api import config
from weather_api.app import PREFIX, app
from weather_api.fixtures import BACK_HOURS, FORWARD_HOURS, now, window_end, window_start

client = TestClient(app)


def test_the_sliding_window_is_twenty_four_hours_back_and_fourteen_days_forward():
    assert config.WINDOW_BACK == timedelta(hours=24)
    assert config.WINDOW_FORWARD == timedelta(days=14)
    assert config.WINDOW_STEPS == 361


def test_sliding_window_returns_utc_aware_bounds_around_the_instant_given():
    reference = datetime(2026, 9, 2, 15, 30, tzinfo=UTC)
    start, end = config.sliding_window(reference)
    assert start == reference - timedelta(hours=24)
    assert end == reference + timedelta(days=14)
    assert start.tzinfo is not None and end.tzinfo is not None
    assert start.utcoffset() == timedelta(0) and end.utcoffset() == timedelta(0)


def test_the_window_slides_with_the_clock_rather_than_being_pinned():
    """A window pinned to a run would answer differently for the same instant."""
    first = config.sliding_window(datetime(2026, 9, 2, 15, tzinfo=UTC))
    later = config.sliding_window(datetime(2026, 9, 2, 16, tzinfo=UTC))
    assert later[0] - first[0] == timedelta(hours=1)
    assert later[1] - first[1] == timedelta(hours=1)


def test_a_naive_instant_is_refused_rather_than_assumed_to_be_utc():
    """Guessing an offset is how a window ends up 3.5 hours wrong here."""
    with pytest.raises(ValueError, match="offset"):
        config.sliding_window(datetime(2026, 9, 2, 15))


def test_a_non_utc_instant_is_normalised_rather_than_taken_at_face_value():
    from zoneinfo import ZoneInfo

    local = datetime(2026, 9, 2, 15, tzinfo=ZoneInfo("America/St_Johns"))
    start, end = config.sliding_window(local)
    assert start == local.astimezone(UTC) - timedelta(hours=24)
    assert end == local.astimezone(UTC) + timedelta(days=14)


def test_in_window_includes_both_boundaries():
    reference = datetime(2026, 9, 2, 15, tzinfo=UTC)
    start, end = config.sliding_window(reference)
    assert config.in_window(start, reference)
    assert config.in_window(end, reference)
    assert not config.in_window(start - timedelta(seconds=1), reference)
    assert not config.in_window(end + timedelta(seconds=1), reference)


# --- one definition, not four --------------------------------------------

def test_the_api_window_helpers_are_the_single_source_not_a_second_pair():
    reference = now()
    assert (window_start(reference), window_end(reference)) == config.sliding_window(reference)
    assert BACK_HOURS == 24 and FORWARD_HOURS == 336


def test_the_ingestion_fetch_window_reads_the_single_source():
    """The worker's window and the API's window are the same two numbers.

    They are separate objects - the FetchWindow carries hours because adapters
    speak in leads - so what is asserted is that they agree, not that one is
    the other.
    """
    from ingest.contract import FetchWindow

    reference = datetime(2026, 9, 2, 15, tzinfo=UTC)
    window = FetchWindow(now=reference)
    assert (window.start, window.end) == config.sliding_window(reference)


def test_request_validation_reads_the_single_source_at_both_boundaries():
    reference = now()
    start, end = config.sliding_window(reference)
    assert client.get(f"{PREFIX}/point", params={"valid_time": start.isoformat()}).status_code == 200
    assert client.get(f"{PREFIX}/point", params={"valid_time": end.isoformat()}).status_code == 200

    outside = client.get(f"{PREFIX}/point", params={"valid_time": (start - timedelta(hours=1)).isoformat()})
    assert outside.status_code == 422
    assert start.isoformat() in outside.json()["detail"]

    beyond = client.get(f"{PREFIX}/point", params={"valid_time": (end + timedelta(hours=1)).isoformat()})
    assert beyond.status_code == 422
    assert end.isoformat() in beyond.json()["detail"]


def test_an_instant_outside_the_window_is_refused_and_never_answered_aged_out():
    """Outside the window is not an absence state; it is outside what is served."""
    reference = now()
    start, _ = config.sliding_window(reference)
    response = client.get(f"{PREFIX}/point", params={"valid_time": (start - timedelta(days=2)).isoformat()})
    assert response.status_code == 422
    assert "aged" not in response.json()["detail"].lower()


def test_the_storage_cap_and_retention_ceiling_live_beside_the_window():
    """One module, so a change to retention cannot miss the quota that sizes it."""
    assert config.STORAGE_CAP == "64GiB"
    assert config.STORAGE_CAP_BYTES == 64 * 1024**3
    assert config.KEEP_COMPLETE_RUNS == 2
    assert config.OBSERVATION_RETENTION == config.WINDOW_BACK
    assert config.COLD_TIER is None
