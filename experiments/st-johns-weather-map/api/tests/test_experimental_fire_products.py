from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.fire_products import CWFISFireProductsAdapter, FIRMSPermissionRequiredAdapter, MAX_CSV_BYTES
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc
WINDOW = FetchWindow(datetime(2026, 9, 6, 6, tzinfo=UTC))
HOTSPOT = "20260905.csv"
CFFEPS = "in20260905.csv"


def client(*, wfs: bytes, hotspot: bytes, cffeps: bytes) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/ows"):
            return httpx.Response(200, content=wfs, headers={"content-type": "application/json"})
        if path.endswith("/cffeps/"):
            return httpx.Response(200, content=f'<a href="{CFFEPS}">{CFFEPS}</a>'.encode())
        if path.endswith("/hotspots/"):
            return httpx.Response(200, content=f'<a href="{HOTSPOT}">{HOTSPOT}</a><a href="cffeps/">cffeps</a>'.encode())
        if path.endswith(CFFEPS): return httpx.Response(200, content=cffeps)
        if path.endswith(HOTSPOT): return httpx.Response(200, content=hotspot)
        raise AssertionError(path)
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return result


def test_cwfis_records_are_retained_verbatim_but_nonpublishable(tmp_path: Path) -> None:
    wfs = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {"lat": 47.5, "frp": 2.0}}]}).encode()
    adapter = CWFISFireProductsAdapter(client=client(wfs=wfs, hotspot=b"lat,lon,frp\n47.5,-52.7,2\n", cffeps=b"lat,lon,hfi\n47.5,-52.7,3\n"), downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert len(result.artifacts) == 3 and not result.complete and result.qc_passed
    assert result.run_time is None and result.native_crs is None
    assert [item.logical_name for item in result.artifacts] == ["wfs_hotspots", "daily_hotspots", "cffeps"]
    assert result.artifacts[0].provenance["field_dispositions"]["frp"] == "retrieved"
    assert result.artifacts[1].provenance["field_dispositions"] == {"lat": "retrieved", "lon": "retrieved", "frp": "retrieved"}
    assert all(item.provenance["source_qc"]["status"] == "unknown" for item in result.artifacts)
    assert all(item.provenance["upstream_sha256"] == item.provenance["artifact_sha256"] for item in result.artifacts)
    assert result.artifacts[0].payload_path.read_bytes() == wfs
    assert result.artifacts[1].payload_path.read_bytes() == b"lat,lon,frp\n47.5,-52.7,2\n"
    assert result.artifacts[2].payload_path.read_bytes() == b"lat,lon,hfi\n47.5,-52.7,3\n"
    assert all(item.provenance["field_interpretation"]["times"] == "verbatim, not normalized" for item in result.artifacts)
    assert all(item.provenance["valid_times"] == [] for item in result.artifacts)
    assert result.artifacts[1].provenance["source_file_date"] == HOTSPOT


def test_malformed_wfs_feature_fails_closed_before_writing(tmp_path: Path) -> None:
    adapter = CWFISFireProductsAdapter(client=client(
        wfs=b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":[]}]}',
        hotspot=b"lat,lon\n47.5,-52.7\n", cffeps=b"lat,lon\n47.5,-52.7\n"),
        downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    with pytest.raises(AdapterUnavailable, match="invalid properties"):
        adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_csv_or_oversize_cleans_all_prior_artifacts(tmp_path: Path) -> None:
    wfs = json.dumps({"type": "FeatureCollection", "features": []}).encode()
    bad = CWFISFireProductsAdapter(client=client(wfs=wfs, hotspot=b"lat,lon\n47.5\n", cffeps=b"lat,lon\n47.5,-52.7\n"), downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    with pytest.raises(AdapterUnavailable, match="row does not match"):
        bad.fetch(bad.discover(WINDOW)[0], WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []
    empty = CWFISFireProductsAdapter(client=client(wfs=wfs, hotspot=b"", cffeps=b"lat,lon\n47.5,-52.7\n"), downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    with pytest.raises(AdapterUnavailable, match="invalid CSV"):
        empty.fetch(empty.discover(WINDOW)[0], WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []
    huge = CWFISFireProductsAdapter(client=client(wfs=wfs, hotspot=b"x" * (MAX_CSV_BYTES + 1), cffeps=b"lat,lon\n47.5,-52.7\n"), downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    with pytest.raises(AdapterUnavailable, match="unavailable daily_hotspots"):
        huge.fetch(huge.discover(WINDOW)[0], WINDOW, tmp_path)


def test_firms_permission_is_explicit_without_secret_handling() -> None:
    with pytest.raises(AdapterUnavailable, match="requires a MAP_KEY"):
        FIRMSPermissionRequiredAdapter().discover(WINDOW)


def firms_client(*, index: bytes, rows: dict[str, bytes]) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/active_fire_files/all":
            return httpx.Response(200, content=index, headers={"content-type": "application/json"})
        for sensor, content in rows.items():
            if request.url.path.endswith(f"/{sensor}_Canada_24h.csv"):
                return httpx.Response(200, content=content)
        raise AssertionError(request.url.path)
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return result


def firms_index() -> bytes:
    return json.dumps({"csv": {sensor: {"Canada": [f"/data/active_fire/{sensor}_Canada_24h.csv"]}
                               for sensor in ("modis", "snpp", "noaa20", "noaa21")}}).encode()


def test_public_firms_modis_and_viirs_downloads_are_retained_nonpublishably(tmp_path: Path) -> None:
    from ingest.experimental.fire_products import FIRMSActiveFireDownloadsAdapter
    raw = {sensor: b"latitude,longitude,acq_date,acq_time,confidence\n47.5,-52.7,2026-09-06,0012,n\n"
           for sensor in ("modis", "snpp", "noaa20", "noaa21")}
    adapter = FIRMSActiveFireDownloadsAdapter(client=firms_client(index=firms_index(), rows=raw),
                                              index="https://fixture.invalid/api/active_fire_files/all?format=json",
                                              origin="https://fixture.invalid")
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert not result.complete and result.qc_passed and result.run_time is None
    assert len(result.artifacts) == 4
    assert [item.logical_name for item in result.artifacts] == [
        "firms_modis_canada_24h", "firms_snpp_canada_24h", "firms_noaa20_canada_24h", "firms_noaa21_canada_24h"]
    assert all(item.provenance["field_dispositions"]["acq_time"] == "retrieved" for item in result.artifacts)
    assert all(item.payload_path.read_bytes() == raw[item.logical_name.removeprefix("firms_").removesuffix("_canada_24h")] for item in result.artifacts)
    assert all(item.provenance["field_interpretation"]["format"] == "UTF-8 CSV header and row widths validated only" for item in result.artifacts)
    assert all(item.provenance["upstream_sha256"] == item.provenance["artifact_sha256"] for item in result.artifacts)


def test_public_firms_index_rejects_unsafe_or_missing_sensor_path() -> None:
    from ingest.experimental.fire_products import FIRMSActiveFireDownloadsAdapter
    unsafe = json.dumps({"csv": {sensor: {"Canada": [f"/data/active_fire/{sensor}_Canada_24h.csv"]}
                                  for sensor in ("modis", "snpp", "noaa20", "noaa21")}}).replace(
                                      "/data/active_fire/modis_Canada_24h.csv", "/data/active_fire/../modis_Canada_24h.csv").encode()
    adapter = FIRMSActiveFireDownloadsAdapter(client=firms_client(index=unsafe, rows={}),
                                              index="https://fixture.invalid/api/active_fire_files/all?format=json",
                                              origin="https://fixture.invalid")
    with pytest.raises(AdapterUnavailable, match="safe Canada"):
        adapter.discover(WINDOW)


def test_receipts_use_transport_completion_when_available(tmp_path: Path) -> None:
    wfs = b'{"type":"FeatureCollection","features":[]}'
    mock = client(wfs=wfs, hotspot=b"lat,lon\n47.5,-52.7\n", cffeps=b"lat,lon\n47.5,-52.7\n")
    completed = datetime(2026, 9, 6, 5, 30, 0, tzinfo=UTC)
    original = mock.get_bytes_with_headers_completed
    mock.get_bytes_with_headers_completed = lambda url, *, max_bytes: (*original(url, max_bytes=max_bytes)[:2], completed)  # type: ignore[method-assign]
    adapter = CWFISFireProductsAdapter(client=mock, downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert result.retrieved_at == completed
    assert all(item.provenance["acquisition"]["response"]["completed_at"] == completed.isoformat() for item in result.artifacts)
