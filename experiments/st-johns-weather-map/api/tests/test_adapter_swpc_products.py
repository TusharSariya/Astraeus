"""Fixture-backed contracts for the seven additional SWPC JSON products."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import xarray
import zarr

from ingest.adapters.swpc_products import (
    GOESMagnetometerAdapter,
    GOESXrayAdapter,
    SWPCAlertsAdapter,
    SWPCKp1mAdapter,
    KP1M_MAX_RECORDS,
    KP1M_ZARR_WORK_BYTES,
    SWPCKyotoDstAdapter,
    SWPCPropagatedSolarWindAdapter,
    SWPCScalesAdapter,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

UTC = timezone.utc
NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
WINDOW = FetchWindow(now=NOW)


def client(payload) -> PoliteClient:
    raw = json.dumps(payload).encode()
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=raw, headers={"Last-Modified": "Sat, 05 Sep 2026 19:59:00 GMT"}))
    result = PoliteClient(min_host_interval_seconds=0.0, attempts=1)
    result._client = httpx.Client(transport=transport, headers={"User-Agent": USER_AGENT})
    return result


def read(result) -> xarray.Dataset:
    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    return xarray.open_zarr(store, consolidated=False)


@pytest.mark.parametrize(
    ("adapter", "payload", "logical", "scope", "variable"),
    [
        (SWPCPropagatedSolarWindAdapter, [{"time_tag": "2026-09-05T19:58:00", "propagated_time_tag": "2026-09-05T20:41:00", "speed": 390, "density": 4.2, "bz": -3, "vx": -390, "vy": 1, "vz": 2, "temperature": 90000, "bx": 1, "by": 2, "bt": 4}], "propagated_solar_wind", "propagated", "propagated_time_unix"),
        (SWPCKp1mAdapter, [{"time_tag": "2026-09-05T19:58:00", "kp_index": 3.0, "estimated_kp": 3.33, "kp": "3P"}], "kp_1m", "planetary", "kp_code"),
        (SWPCAlertsAdapter, [{"product_id": "K04A", "issue_datetime": "2026-09-05 19:58:00", "message": "Space Weather Message Code: K04A\r\nSerial Number: 42\r\nNOAA Scale: G1\r\n"}], "alerts", "issued", "message"),
        (GOESMagnetometerAdapter, [{"time_tag": "2026-09-05T19:58:00", "satellite": 19, "He": 1, "Hp": 2, "Hn": 3, "total": 4, "arcjet_flag": False}], "goes_magnetometer", "geosynchronous", "total"),
        (GOESXrayAdapter, [{"time_tag": "2026-09-05T19:58:00", "satellite": 18, "energy": "0.05-0.4nm", "flux": 1e-7, "observed_flux": 1.1e-7, "electron_correction": 0, "electron_contaminaton": False}, {"time_tag": "2026-09-05T19:58:00", "satellite": 18, "energy": "0.1-0.8nm", "flux": 2e-7, "observed_flux": 2.1e-7, "electron_correction": 0, "electron_contaminaton": False}], "goes_xray", "geosynchronous", "xray_flux_long"),
        (SWPCKyotoDstAdapter, [{"time_tag": "2026-09-05T19:00:00", "dst": -12}], "kyoto_dst", "planetary", "dst_index"),
    ],
)
def test_series_products_preserve_shape_scope_and_receipt(tmp_path, adapter, payload, logical, scope, variable):
    instance = adapter(client=client(payload))
    candidate = instance.discover(WINDOW)[0]
    result = instance.fetch(candidate, WINDOW, tmp_path)
    assert result.complete and result.artifacts[0].logical_name == logical
    provenance = result.artifacts[0].provenance
    assert provenance["measurement_scope"] == scope
    assert provenance["retrieval"][0]["byte_count"] == len(json.dumps(payload).encode())
    assert len(provenance["retrieval"][0]["sha256"]) == 64
    assert variable in read(result)
    if logical == "kyoto_dst":
        assert provenance["evidence_classes"] == ["reprocessed"]
        assert provenance["intermediary"]["name"] == "NOAA SWPC"
        assert provenance["display_primary"] is False


def test_scales_keeps_provider_day_offsets(tmp_path):
    payload = {
        key: {"DateStamp": "2026-09-05", "TimeStamp": "19:58:00", "R": {"Scale": 0, "MinorProb": 5, "MajorProb": 1}, "S": {"Scale": 0, "Prob": 1}, "G": {"Scale": 1}}
        for key in ("-1", "0", "1", "2", "3")
    }
    adapter = SWPCScalesAdapter(client=client(payload))
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    dataset = read(result)
    assert list(dataset.day_offset.values) == ["-1", "0", "1", "2", "3"]
    assert result.artifacts[0].provenance["measurement_scope"] == "planetary"


def test_schema_drift_and_stale_http_200_fail_closed():
    unknown_band = [{"time_tag": "2026-09-05T19:58:00", "satellite": 18, "energy": "new-band", "flux": 1}]
    with pytest.raises(AdapterUnavailable, match="unrecognised energy"):
        GOESXrayAdapter(client=client(unknown_band)).discover(WINDOW)
    stale = [{"time_tag": "2026-09-04T00:00:00", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"}]
    with pytest.raises(AdapterUnavailable, match="stale"):
        SWPCKp1mAdapter(client=client(stale)).discover(WINDOW)


def test_kp1m_declares_complete_pre_discovery_and_writer_bounds(tmp_path):
    payload = [{"time_tag": "2026-09-05T19:58:00", "kp_index": 3, "estimated_kp": 3.33, "kp": "3P"}]
    adapter = SWPCKp1mAdapter(client=client(payload))

    operation = adapter.operation_bounds(WINDOW)
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)

    assert adapter.discovery_bounds(WINDOW).received_bytes == 512 * 1024
    assert adapter.resource_bounds(candidate, WINDOW) == operation
    assert operation.margin_bytes == 0
    assert operation.filesystem_bytes == KP1M_ZARR_WORK_BYTES
    assert result.artifacts[0].byte_size <= operation.store_bytes


def test_kp1m_refuses_record_count_above_its_wire_derived_bound(monkeypatch):
    row = {"time_tag": "2026-09-05T19:58:00", "kp_index": 3, "estimated_kp": 3.33, "kp": "3P"}
    adapter = SWPCKp1mAdapter(client=client([row]))
    monkeypatch.setattr("ingest.adapters.swpc_products.records", lambda *_args, **_kwargs: [row] * (KP1M_MAX_RECORDS + 1))

    with pytest.raises(AdapterUnavailable, match="record allocation bound"):
        adapter.discover(WINDOW)


def test_alert_collision_at_one_issue_instant_fails_closed():
    payload = [
        {"product_id": "A", "issue_datetime": "2026-09-05 19:58:00", "message": "one"},
        {"product_id": "B", "issue_datetime": "2026-09-05 19:58:00", "message": "two"},
    ]
    with pytest.raises(AdapterUnavailable, match="two distinct messages"):
        SWPCAlertsAdapter(client=client(payload)).discover(WINDOW)
