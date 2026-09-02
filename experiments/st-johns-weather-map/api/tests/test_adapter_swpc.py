"""Unit tests for the NOAA SWPC space-weather adapters."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy
import pytest
import xarray
import zarr

from ingest.adapters.swpc import (
    KP_FORECAST_URL,
    KP_OBSERVED_URL,
    OVATION_URL,
    RTSW_MAG_URL,
    SWPCKpAdapter,
    SWPCOvationAdapter,
    SWPCSolarWindAdapter,
)
from ingest.contract import ATLANTIC_CONTEXT_BOUNDS, AdapterUnavailable, FetchWindow
from ingest.http import USER_AGENT, PoliteClient

UTC = timezone.utc
NOW = datetime(2026, 8, 31, 2, 0, tzinfo=UTC)
WINDOW = FetchWindow(now=NOW)

KP_OBSERVED = [
    {"time_tag": "2026-08-30T18:00:00", "Kp": 2.33, "a_running": 9, "station_count": 8},
    {"time_tag": "2026-08-30T21:00:00", "Kp": 3.67, "a_running": 15, "station_count": 8},
    {"time_tag": "2026-08-31T00:00:00", "Kp": 4.33, "a_running": 22, "station_count": 8},
]
KP_FORECAST = [
    {"time_tag": "2026-08-31T00:00:00", "kp": 4.33, "observed": "observed", "noaa_scale": None},
    {"time_tag": "2026-08-31T03:00:00", "kp": 4.0, "observed": "estimated", "noaa_scale": None},
    {"time_tag": "2026-08-31T06:00:00", "kp": 5.0, "observed": "predicted", "noaa_scale": "G1"},
]
RTSW = [
    {"time_tag": "2026-08-31T01:58:00", "source": "SOLAR1", "bz_gsm": -3.89, "bt": 4.24},
    {"time_tag": "2026-08-31T01:59:00", "source": "SOLAR1", "bz_gsm": -4.1, "bt": 4.3},
    {"time_tag": "2026-08-31T02:00:00", "source": "SOLAR1", "bz_gsm": None, "bt": 4.2},
]


def ovation_payload(**overrides):
    coordinates = []
    # A global-ish grid: inside-box cells (lat 40..55, lon 290..320 East ->
    # -70..-40) and far-away cells that the crop must drop.
    for lon_east in range(288, 322, 2):
        for lat in range(38, 58, 2):
            coordinates.append([lon_east, lat, 12 if lat >= 50 else 3])
    coordinates.append([10, 65, 55])   # Norway: outside the box
    coordinates.append([200, -80, 40])  # southern oval: outside the box
    payload = {
        "Observation Time": "2026-08-31T01:49:00Z",
        "Forecast Time": "2026-08-31T02:50:00Z",
        "Data Format": "[Longitude, Latitude, Aurora]",
        "coordinates": coordinates,
    }
    payload.update(overrides)
    return payload


def make_mock_client(url_bodies: dict[str, object]) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for pattern, body in url_bodies.items():
            if pattern in url:
                if body is None:
                    return httpx.Response(503, text="unavailable")
                return httpx.Response(200, text=json.dumps(body))
        return httpx.Response(404)

    client = PoliteClient(min_host_interval_seconds=0.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return client


def open_artifact(artifact) -> xarray.Dataset:
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    return xarray.open_zarr(store, consolidated=False)


# --- Kp -------------------------------------------------------------------


def test_kp_publishes_observed_and_forecast_separately(tmp_path: Path):
    adapter = SWPCKpAdapter(client=make_mock_client({"k-index-forecast": KP_FORECAST, "k-index": KP_OBSERVED}))
    candidate = adapter.discover(WINDOW)[0]
    assert candidate.run_time == datetime(2026, 8, 31, 0, 0, tzinfo=UTC)

    result = adapter.fetch(candidate, WINDOW, tmp_path)
    names = [a.logical_name for a in result.artifacts]
    assert all(a.provenance["evidence_classes"] == ["retrieved"] for a in result.artifacts)
    assert names == ["kp_observed", "kp_forecast"]
    assert result.complete is True

    observed = open_artifact(result.artifacts[0])
    assert list(observed.dims) == ["valid_time"]
    assert "latitude" not in observed.coords and "longitude" not in observed.coords
    assert float(observed["kp_index"].values[-1]) == 4.33

    forecast = open_artifact(result.artifacts[1])
    status = forecast["kp_status"]
    assert status.attrs["flag_meanings"] == "observed estimated predicted"
    assert [int(v) for v in status.values] == [0, 1, 2]
    assert float(forecast["kp_index"].values[-1]) == 5.0
    # No lead hours anywhere: the outlook is served with the provider's own
    # status, never re-indexed as a model run.
    assert "lead_hours" not in forecast.attrs
    assert "lead_hours" not in result.artifacts[1].provenance


def test_kp_forecast_outage_keeps_the_observed_series(tmp_path: Path):
    adapter = SWPCKpAdapter(client=make_mock_client({"k-index-forecast": None, "k-index": KP_OBSERVED}))
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert [a.logical_name for a in result.artifacts] == ["kp_observed"]
    assert result.complete is False
    assert "no kp_forecast artifact" in result.notes


def test_kp_empty_feed_is_unavailable():
    adapter = SWPCKpAdapter(client=make_mock_client({"k-index-forecast": [], "k-index": []}))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(WINDOW)


def test_kp_header_row_form_is_accepted(tmp_path: Path):
    rows = [["time_tag", "Kp", "a_running", "station_count"]] + [[r["time_tag"], r["Kp"], r["a_running"], r["station_count"]] for r in KP_OBSERVED]
    adapter = SWPCKpAdapter(client=make_mock_client({"k-index-forecast": [], "k-index": rows}))
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    observed = open_artifact(result.artifacts[0])
    assert float(observed["kp_index"].values[-1]) == 4.33


# --- solar wind -----------------------------------------------------------


def test_rtsw_series_has_no_coordinates_and_keeps_gaps(tmp_path: Path):
    adapter = SWPCSolarWindAdapter(client=make_mock_client({"rtsw_mag_1m": RTSW}))
    candidate = adapter.discover(WINDOW)[0]
    assert candidate.run_time == datetime(2026, 8, 31, 2, 0, tzinfo=UTC)

    result = adapter.fetch(candidate, WINDOW, tmp_path)
    dataset = open_artifact(result.artifacts[0])
    assert result.artifacts[0].logical_name == "solar_wind"
    assert list(dataset.dims) == ["valid_time"]
    assert "latitude" not in dataset.coords and "longitude" not in dataset.coords
    assert float(dataset["bz_gsm"].values[1]) == -4.1
    # A missing reading stays a gap, never zero.
    assert numpy.isnan(dataset["bz_gsm"].values[2])
    # The spacecraft name is whatever the feed declared, recorded verbatim.
    assert result.artifacts[0].provenance["feed_declared_spacecraft"] == "SOLAR1"
    assert "DSCOVR" not in json.dumps(result.artifacts[0].provenance)


def test_rtsw_empty_feed_is_unavailable():
    adapter = SWPCSolarWindAdapter(client=make_mock_client({"rtsw_mag_1m": []}))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(WINDOW)


# --- OVATION --------------------------------------------------------------


def test_ovation_grid_is_cropped_and_timestamped_by_the_payload(tmp_path: Path):
    adapter = SWPCOvationAdapter(client=make_mock_client({"ovation_aurora_latest": ovation_payload()}))
    candidate = adapter.discover(WINDOW)[0]
    assert candidate.run_time == datetime(2026, 8, 31, 1, 49, tzinfo=UTC)

    result = adapter.fetch(candidate, WINDOW, tmp_path)
    artifact = result.artifacts[0]
    assert artifact.logical_name == "aurora_grid"
    dataset = open_artifact(artifact)
    # Valid at the file's own Forecast Time, not the wall clock.
    stamp = dataset["valid_time"].values[0]
    assert numpy.datetime64("2026-08-31T02:50:00") == stamp.astype("datetime64[s]")
    lats = dataset["latitude"].values
    lons = dataset["longitude"].values
    assert lats.min() >= ATLANTIC_CONTEXT_BOUNDS["south"] and lats.max() <= ATLANTIC_CONTEXT_BOUNDS["north"]
    assert lons.min() >= ATLANTIC_CONTEXT_BOUNDS["west"] and lons.max() <= ATLANTIC_CONTEXT_BOUNDS["east"]
    # East-longitude cells landed at their converted western values.
    values = dataset["aurora_probability"].sel(latitude=54, longitude=-60, method="nearest").values
    assert float(values[0]) == 12.0
    assert dataset["aurora_probability"].attrs["units"] == "percent"
    assert "nowcast" in dataset.attrs["model_disclosure"]


def test_ovation_without_its_timestamps_is_refused():
    payload = ovation_payload()
    del payload["Forecast Time"]
    adapter = SWPCOvationAdapter(client=make_mock_client({"ovation_aurora_latest": payload}))
    with pytest.raises(AdapterUnavailable, match="refused rather than wall-clock stamped"):
        adapter.discover(WINDOW)


def test_ovation_with_no_cell_in_the_box_is_unavailable(tmp_path: Path):
    payload = ovation_payload(coordinates=[[10, 65, 55]])
    adapter = SWPCOvationAdapter(client=make_mock_client({"ovation_aurora_latest": payload}))
    candidate = adapter.discover(WINDOW)[0]
    with pytest.raises(AdapterUnavailable, match="no cell inside the context box"):
        adapter.fetch(candidate, WINDOW, tmp_path)


# --- registry -------------------------------------------------------------


def test_registry_cadences_parse_and_no_lead_hours_category():
    from ingest.registry import FORECAST_CATEGORIES, get_config

    for source_id, cadence_seconds in (("noaa-swpc-kp", 10800), ("noaa-swpc-rtsw", 60), ("noaa-swpc-ovation", 600)):
        config = get_config(source_id)
        assert config.cycle_seconds == cadence_seconds, source_id
        assert config.freshness_threshold_seconds is not None, source_id
        assert config.ingestible is True, source_id
        assert config.category == "space_weather"
    assert "space_weather" not in FORECAST_CATEGORIES


# --- live smoke -----------------------------------------------------------


@pytest.mark.live_smoke
@pytest.mark.skipif(os.environ.get("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1 to contact SWPC")
def test_live_swpc_feed_shapes_are_pinned():
    """The schema-drift tripwire: all four real feeds still carry the fields
    the adapters read."""
    client = PoliteClient()
    observed = client.get(KP_OBSERVED_URL).json()
    forecast = client.get(KP_FORECAST_URL).json()
    rtsw = client.get(RTSW_MAG_URL).json()
    ovation = client.get(OVATION_URL).json()

    from ingest.adapters.swpc import _parse_time, _records

    observed_records = _records(observed, required=("time_tag", "Kp"))
    assert observed_records, "observed Kp feed shape changed"
    forecast_records = _records(forecast, required=("time_tag", "kp", "observed"))
    assert forecast_records, "forecast Kp feed shape changed"
    assert {str(r.get("observed", "")).lower() for r in forecast_records} <= {"observed", "estimated", "predicted"}
    rtsw_records = _records(rtsw, required=("time_tag", "bz_gsm"))
    assert rtsw_records, "rtsw feed shape changed"
    assert _parse_time(ovation.get("Observation Time")) is not None
    assert _parse_time(ovation.get("Forecast Time")) is not None
    coordinates = ovation.get("coordinates")
    assert isinstance(coordinates, list) and coordinates
    lons = [c[0] for c in coordinates[:2000]]
    lats = [c[1] for c in coordinates[:2000]]
    assert 0 <= min(lons) and max(lons) <= 360
    assert -90 <= min(lats) and max(lats) <= 90
