"""Unit tests for ECCC OGC API SWOB adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
import xarray
import zarr

from ingest.adapters.eccc_ogc import ECCCOGCSWOBAdapter
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc

SAMPLE_SWOB_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "stn-1-202608291400",
            "geometry": {"type": "Point", "coordinates": [-52.7126, 47.5615]},
            "properties": {
                "stn_nam-value": "ST. JOHN'S WEST",
                "date_tm-value": "2026-08-29T14:00:00Z",
                "air_temp": 16.5,
                "air_temp-qa": "passed",
                "dwpt_temp": 15.0,
                "dwpt_temp-qa": "passed",
                "rel_hum": 91.0,
                "mslp": 1012.8,
                "wnd_spd": 5.2,
                "wnd_dir": 180.0,
            },
        },
        {
            "type": "Feature",
            "id": "stn-2-202608291400",
            "geometry": {"type": "Point", "coordinates": [-53.07, 46.65]},
            "properties": {
                "stn_nam-value": "CAPE RACE (AUT)",
                "date_tm-value": "2026-08-29T14:00:00Z",
                "air_temp": 15.9,
                "air_temp-qa": "passed",
                "dwpt_temp": 15.9,
                "rel_hum": 100.0,
                "mslp": 1013.1,
                "wnd_spd": 8.0,
                "wnd_dir": 210.0,
            },
        },
    ],
}


def make_mock_client(data: Any, status_code: int = 200) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=data if status_code == 200 else None)

    client = PoliteClient(min_host_interval_seconds=0.0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": USER_AGENT},
    )
    return client


def test_swob_discover():
    client = make_mock_client(SAMPLE_SWOB_GEOJSON)
    adapter = ECCCOGCSWOBAdapter(client=client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)

    candidates = adapter.discover(window)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.run_time == datetime(2026, 8, 29, 14, 0, tzinfo=UTC)
    assert candidate.provider_run_id.startswith("swob-")


def test_swob_discover_empty_raises():
    client = make_mock_client({"type": "FeatureCollection", "features": []})
    adapter = ECCCOGCSWOBAdapter(client=client)
    window = FetchWindow(now=datetime(2026, 8, 29, 15, tzinfo=UTC))
    with pytest.raises(AdapterUnavailable):
        adapter.discover(window)


def test_swob_fetch_creates_zarr(tmp_path: Path):
    client = make_mock_client(SAMPLE_SWOB_GEOJSON)
    adapter = ECCCOGCSWOBAdapter(client=client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)

    candidates = adapter.discover(window)
    result = adapter.fetch(candidates[0], window, tmp_path)

    assert result.source_id == "eccc-swob"
    assert result.complete is True
    assert result.qc_passed is True
    assert len(result.artifacts) == 1

    artifact = result.artifacts[0]
    assert artifact.logical_name == "surface"
    assert artifact.payload_path.exists()

    # Open and verify Zarr content
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    ds = xarray.open_zarr(store, consolidated=False)

    assert "temperature_2m" in ds.data_vars
    assert "dew_point_2m" in ds.data_vars
    assert "relative_humidity_2m" in ds.data_vars
    assert "mean_sea_level_pressure" in ds.data_vars
    assert "wind_u_10m" in ds.data_vars
    assert "wind_v_10m" in ds.data_vars

    # St. John's West station: T=16.5, Td=15.0, RH=91.0
    st_johns_val = float(ds["temperature_2m"].sel(latitude=47.5615, longitude=-52.7126, method="nearest").values[0])
    assert st_johns_val == pytest.approx(16.5, abs=0.1)

    # Cape Race station: T=15.9, Td=15.9, RH=100.0
    cape_race_rh = float(ds["relative_humidity_2m"].sel(latitude=46.65, longitude=-53.07, method="nearest").values[0])
    assert cape_race_rh == pytest.approx(100.0, abs=0.1)

    # Provider QC flags (the raw ``*-qa`` / ``*-data_flag`` properties SWOB sent)
    # live under quality.provider_flags; quality.flags is reserved for the
    # validator's own machine-readable failure reasons, which is empty on a
    # clean run.
    assert artifact.provenance["quality"]["status"] == "passed"
    assert artifact.provenance["quality"]["flags"] == []
    assert "air_temp-qa:passed" in artifact.provenance["quality"]["provider_flags"]


def test_swob_fetch_with_temperature_missing_everywhere_comes_back_incomplete(tmp_path: Path):
    """Mirror image of the happy path: every feature omits ``air_temp``, the
    one mandatory SWOB field. SWOB always materializes its declared fields as
    a (time, lat, lon) array -- even absent data leaves the variable present,
    just entirely NaN -- so the fail-closed signal here is ``empty_field:``
    rather than ``missing_field:``, but it is the same guarantee: a run
    missing its one mandatory field must never be marked complete."""
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                **feature,
                "properties": {k: v for k, v in feature["properties"].items() if k not in ("air_temp", "air_temp-qa")},
            }
            for feature in SAMPLE_SWOB_GEOJSON["features"]
        ],
    }
    client = make_mock_client(geojson)
    adapter = ECCCOGCSWOBAdapter(client=client)
    now = datetime(2026, 8, 29, 15, tzinfo=UTC)
    window = FetchWindow(now=now, back_hours=3, forward_hours=24)

    candidates = adapter.discover(window)
    result = adapter.fetch(candidates[0], window, tmp_path)

    assert result.complete is False
    flags = result.artifacts[0].provenance["quality"]["flags"]
    assert any(flag.startswith("empty_field:temperature_2m") for flag in flags)
