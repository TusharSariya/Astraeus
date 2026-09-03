"""The astronomy capability: pinned-kernel verification, geometry, endpoint.

Tests that need the real DE442 kernel skip cleanly when it has not been
fetched (``uv run python scripts/fetch_ephemeris.py``); the fail-closed
scenarios run everywhere because they need only a wrong or absent file.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weather_api import astronomy
from weather_api.app import app
from weather_api.ephemeris import EPHEMERIS_SHA256, ephemeris_path, verify_ephemeris

UTC = timezone.utc
PREFIX = "/api/experiments/weather/v0"

KERNEL_PRESENT = ephemeris_path().is_file()
needs_kernel = pytest.mark.skipif(not KERNEL_PRESENT, reason="DE442 kernel not fetched; run scripts/fetch_ephemeris.py")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def broken_kernel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point the capability at a file that hashes wrong, and clean up the cache."""
    bogus = tmp_path / "de442.bsp"
    bogus.write_bytes(b"not an ephemeris")
    monkeypatch.setenv("WEATHER_EPHEMERIS_PATH", str(bogus))
    astronomy.reset_cache()
    yield bogus
    astronomy.reset_cache()


@pytest.fixture()
def missing_kernel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("WEATHER_EPHEMERIS_PATH", str(tmp_path / "absent.bsp"))
    astronomy.reset_cache()
    yield
    astronomy.reset_cache()


# --- fail-closed kernel handling -----------------------------------------


def test_missing_kernel_is_refused(missing_kernel):
    with pytest.raises(FileNotFoundError):
        verify_ephemeris()


def test_checksum_mismatch_is_refused(broken_kernel):
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_ephemeris()


def test_endpoint_fails_closed_without_a_kernel(client, missing_kernel):
    response = client.get(f"{PREFIX}/astronomy")
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "unavailable"
    assert body["provenance"] is None
    assert body["twilight_bands"] == []
    assert any("missing" in notice for notice in body["notices"])
    assert any("nothing is substituted" in notice.lower() for notice in body["notices"])


def test_endpoint_fails_closed_on_checksum_mismatch(client, broken_kernel):
    body = client.get(f"{PREFIX}/astronomy").json()
    assert body["data_mode"] == "unavailable"
    assert any("checksum mismatch" in notice for notice in body["notices"])
    assert body["provenance"] is None


def test_no_in_process_download_is_attempted(client, missing_kernel, monkeypatch):
    """The kernel being absent must never trigger a fetch from a handler."""
    import urllib.request

    def forbidden(*args, **kwargs):  # pragma: no cover - the point is it never runs
        raise AssertionError("the API attempted a network fetch of the kernel")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    for _ in range(3):
        assert client.get(f"{PREFIX}/astronomy").json()["data_mode"] == "unavailable"


# --- request validation ---------------------------------------------------


def test_outside_window_is_422(client):
    response = client.get(f"{PREFIX}/astronomy", params={"valid_time": "2020-01-01T00:00:00Z"})
    assert response.status_code == 422


def test_outside_core_bounds_is_422(client):
    response = client.get(f"{PREFIX}/astronomy", params={"latitude": 10.0, "longitude": 10.0})
    assert response.status_code == 422


# --- geometry against the real kernel ------------------------------------


@needs_kernel
def test_known_answer_the_2024_total_eclipse_is_a_new_moon():
    """Known answer pinned to an external fact: the 2024-04-08 total solar
    eclipse (totality over eastern North America ~18:20-19:30 UTC) is by
    definition a new moon. The illuminated fraction must be ~0 and the moon
    within a degree of the sun."""
    at = datetime(2024, 4, 8, 18, 30, tzinfo=UTC)
    geometry = astronomy.sky_geometry(47.5615, -52.7126, at - timedelta(hours=1), at + timedelta(hours=1), at)
    assert geometry.moon.illuminated_fraction < 0.01
    assert abs(geometry.moon_altitude_deg - geometry.sun_altitude_deg) < 1.5


@needs_kernel
def test_twilight_bands_tile_the_window_in_order():
    start = datetime(2026, 8, 30, 19, 0, tzinfo=UTC)
    end = start + timedelta(hours=27)
    geometry = astronomy.sky_geometry(47.5615, -52.7126, start, end, start)
    bands = geometry.twilight_bands
    assert bands[0].start == start and bands[-1].end == end
    for previous, current in zip(bands, bands[1:]):
        assert previous.end == current.start, "bands must tile without gap or overlap"
        assert previous.kind != current.kind
    kinds = {band.kind for band in bands}
    assert kinds <= {"day", "civil_twilight", "nautical_twilight", "astronomical_twilight", "night"}
    assert "night" in kinds  # a 27 h window at 47.6 N always contains night


@needs_kernel
def test_core_window_requires_all_three_conditions():
    """Late August 2026 has a bright waning gibbous moon up all night at
    St. John's: the geometric core window must be empty even though the core
    is above 5 degrees during astronomical night - the moon veto is real."""
    start = datetime(2026, 8, 30, 19, 0, tzinfo=UTC)
    end = start + timedelta(hours=27)
    geometry = astronomy.sky_geometry(47.5615, -52.7126, start, end, start)
    assert geometry.moon.illuminated_fraction > 0.85
    assert geometry.core.windows == []
    assert geometry.core.max_altitude_deg > 5.0


@needs_kernel
def test_core_max_altitude_is_low_at_this_latitude():
    """The honesty number: at 47.56 N the galactic core never rises far. The
    served maximum must stay in the low teens, never a fabricated high arc."""
    start = datetime(2026, 7, 15, 21, 0, tzinfo=UTC)
    geometry = astronomy.sky_geometry(47.5615, -52.7126, start, start + timedelta(hours=27), start)
    assert 8.0 < geometry.core.max_altitude_deg < 16.0


@needs_kernel
def test_endpoint_serves_bands_moon_and_disclosed_provenance(client):
    body = client.get(f"{PREFIX}/astronomy").json()
    assert body["data_mode"] == "live"
    assert body["operational"] is False
    assert len(body["twilight_bands"]) >= 3
    assert 0.0 <= body["moon"]["illuminated_fraction"] <= 1.0
    provenance = body["provenance"]
    assert provenance["source_id"] == "nasa-jpl-de442"
    assert provenance["kernel_sha256"] == EPHEMERIS_SHA256
    assert "skyfield" in provenance["derivation"]
    assert "DE442" in provenance["derivation"]
    assert provenance["derivation_version"] == "astronomy-de442-v1"
    core = body["milky_way_core"]
    assert "light pollution" in core["caption"]
    assert isinstance(core["max_altitude_deg"], float)


# --- registry -------------------------------------------------------------


def test_registry_entry_exists_and_is_never_scheduled():
    from ingest.registry import get_config, ingest_configs, parse_cadence_seconds

    config = get_config("nasa-jpl-de442")
    assert config.registry_status == "catalogued"
    # The cadence prose must not parse and the freshness is "not applicable":
    # either alone keeps ``ingestible`` false, so the worker never schedules
    # the kernel as though it were a feed.
    assert parse_cadence_seconds("static kernel; pinned release") is None
    assert config.freshness_threshold_seconds is None
    assert config.ingestible is False
    assert "nasa-jpl-de442" in ingest_configs()


@pytest.mark.live_smoke
@pytest.mark.skipif(__import__("os").environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to contact NAIF")
def test_live_ephemeris_pin_still_matches_naif():
    """HEAD the pinned NAIF URL: still served, still the pinned byte size. A
    changed size means the release moved under the pin and the checksum would
    fail a re-fetch - better to hear it from the smoke test."""
    import httpx

    from weather_api.ephemeris import EPHEMERIS_BYTES, EPHEMERIS_URL

    response = httpx.head(EPHEMERIS_URL, timeout=30, follow_redirects=True)
    assert response.status_code == 200
    assert int(response.headers["content-length"]) == EPHEMERIS_BYTES
