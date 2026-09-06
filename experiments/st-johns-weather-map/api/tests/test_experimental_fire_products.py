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
    huge = CWFISFireProductsAdapter(client=client(wfs=wfs, hotspot=b"x" * (MAX_CSV_BYTES + 1), cffeps=b"lat,lon\n47.5,-52.7\n"), downloads="https://fixture.invalid/hotspots", wfs="https://fixture.invalid/ows")
    with pytest.raises(AdapterUnavailable, match="unavailable daily_hotspots"):
        huge.fetch(huge.discover(WINDOW)[0], WINDOW, tmp_path)


def test_firms_permission_is_explicit_without_secret_handling() -> None:
    with pytest.raises(AdapterUnavailable, match="requires a MAP_KEY"):
        FIRMSPermissionRequiredAdapter().discover(WINDOW)
