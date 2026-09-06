"""Fixture-backed contracts for the seven additional SWPC JSON products."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import xarray
import zarr

from ingest.adapters.swpc_products import (
    GOESMagnetometerAdapter,
    GOESXrayAdapter,
    SWPCAlertsAdapter,
    SWPCKp1mAdapter,
    SWPCKyotoDstAdapter,
    SWPCPropagatedSolarWindAdapter,
    SWPCScalesAdapter,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import MaxBytesExceeded, PoliteClient, USER_AGENT
from ingest.isolation import BoundedProcessError
from ingest import kp1m_isolated

UTC = timezone.utc
NOW = datetime(2026, 9, 5, 20, 0, tzinfo=UTC)
WINDOW = FetchWindow(now=NOW)


@pytest.fixture(autouse=True)
def local_kp_child(monkeypatch):
    """Exercise adapter protocol on Darwin; kernel enforcement is Linux-tested."""
    def run(mode, raw, destination):
        output = destination or Path("/tmp/unused-kp-inspect")
        result = subprocess.run(
            [sys.executable, "-m", "ingest.kp1m_isolated", mode, str(output)],
            input=raw, capture_output=True, check=False,
            env={**os.environ, "PYTHONPATH": str(Path(kp1m_isolated.__file__).resolve().parents[1])},
        )
        if result.returncode:
            from ingest.isolation import BoundedProcessError
            raise BoundedProcessError(result.stderr.decode())
        return SimpleNamespace(output_path=destination, stdout=result.stdout)

    from pathlib import Path
    monkeypatch.setattr(SWPCKp1mAdapter, "_isolated", staticmethod(run))


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


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"time_tag": "bad", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"}, "unparseable time_tag"),
        ({"time_tag": "2026-09-05T19:58:00", "kp_index": "bad", "estimated_kp": 1, "kp": "1Z"}, "invalid kp_index"),
        ({"time_tag": "2026-09-05T19:58:00", "kp_index": 1, "estimated_kp": 1, "kp": "new"}, "unsupported kp code"),
        ({"time_tag": "2026-09-05T19:58:00", "kp_index": 1, "estimated_kp": 1}, "without thinning"),
    ],
)
def test_kp1m_refuses_every_malformed_raw_row_without_thinning(row, message):
    with pytest.raises(AdapterUnavailable, match=message):
        SWPCKp1mAdapter(client=client([row])).discover(WINDOW)


@pytest.mark.parametrize("field", ["kp_index", "estimated_kp"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_kp1m_refuses_non_finite_numeric_rows(field, value):
    row = {"time_tag": "2026-09-05T19:58:00", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"}
    row[field] = value

    with pytest.raises(AdapterUnavailable, match=f"non-finite {field}"):
        SWPCKp1mAdapter(client=client([row])).discover(WINDOW)


def test_kp1m_complete_operation_bounds_cover_one_isolated_artifact():
    bounds = SWPCKp1mAdapter(client=client([])).operation_bounds(WINDOW)

    assert bounds.received_bytes == 512 * 1024
    assert bounds.store_bytes == 512 * 1024
    assert bounds.filesystem_bytes == 512 * 1024
    assert bounds.margin_bytes == 4096


def test_kp1m_maps_transport_limit_to_unavailable_without_candidate(monkeypatch):
    adapter = SWPCKp1mAdapter(client=client([]))
    monkeypatch.setattr(
        adapter._client,
        "get_bytes_with_headers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(MaxBytesExceeded("too large")),
    )

    with pytest.raises(AdapterUnavailable, match="isolated discovery failed"):
        adapter.discover(WINDOW)


def test_kp1m_removes_promoted_output_when_reply_is_invalid(tmp_path, monkeypatch):
    rows = [{"time_tag": "2026-09-05T19:58:00", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"}]
    adapter = SWPCKp1mAdapter(client=client(rows))
    candidate = adapter.discover(WINDOW)[0]

    def invalid_reply(_mode, _raw, destination):
        destination.write_bytes(b"promoted")
        return SimpleNamespace(output_path=destination, stdout=b"not-json")

    monkeypatch.setattr(adapter, "_isolated", invalid_reply)
    with pytest.raises(AdapterUnavailable, match="normalization failed"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_kp1m_leaves_no_output_when_bounded_child_fails(tmp_path, monkeypatch):
    rows = [{"time_tag": "2026-09-05T19:58:00", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"}]
    adapter = SWPCKp1mAdapter(client=client(rows))
    candidate = adapter.discover(WINDOW)[0]
    monkeypatch.setattr(
        adapter,
        "_isolated",
        lambda *_args: (_ for _ in ()).throw(BoundedProcessError("allocation limit")),
    )

    with pytest.raises(AdapterUnavailable, match="normalization failed"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_alert_collision_at_one_issue_instant_fails_closed():
    payload = [
        {"product_id": "A", "issue_datetime": "2026-09-05 19:58:00", "message": "one"},
        {"product_id": "B", "issue_datetime": "2026-09-05 19:58:00", "message": "two"},
    ]
    with pytest.raises(AdapterUnavailable, match="two distinct messages"):
        SWPCAlertsAdapter(client=client(payload)).discover(WINDOW)
