from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import xarray
import zarr

from ingest import kp3h_isolated
from ingest.adapters.swpc import SWPCKpAdapter
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT

OBSERVED = [
    {"time_tag": "2026-09-06T00:00:00", "Kp": 1.0, "a_running": 4, "station_count": 8},
    {"time_tag": "2026-09-06T03:00:00", "Kp": 2.33, "a_running": 8, "station_count": 8},
]
FORECAST = [
    {"time_tag": "2026-09-06T03:00:00", "kp": 2.33, "observed": "observed", "noaa_scale": None},
    {"time_tag": "2026-09-06T06:00:00", "kp": 3.0, "observed": "predicted", "noaa_scale": None},
]


def _run(tmp_path: Path, action: str, mode: str, rows: object):
    output = tmp_path / f"{mode}.zip"
    result = subprocess.run(
        [sys.executable, "-m", "ingest.kp3h_isolated", action, mode, str(output)],
        input=json.dumps(rows).encode(), capture_output=True, check=False,
        env={**os.environ, "PYTHONPATH": str(Path(kp3h_isolated.__file__).resolve().parents[1])},
    )
    return result, output


@pytest.mark.parametrize("mode,rows,variables", [
    ("observed", OBSERVED, {"kp_index", "a_running"}),
    ("forecast", FORECAST, {"kp_index", "kp_status"}),
])
def test_kp3h_child_preserves_every_row(mode, rows, variables, tmp_path):
    result, output = _run(tmp_path, "normalize", mode, rows)
    assert result.returncode == 0
    assert json.loads(result.stdout)["count"] == len(rows)
    store = zarr.storage.ZipStore(str(output), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    assert set(dataset.data_vars) == variables
    assert dataset.sizes["valid_time"] == len(rows)
    store.close()


@pytest.mark.parametrize("mode,rows", [
    ("observed", OBSERVED + [{"time_tag": "bad", "Kp": 1, "a_running": 2}]),
    ("observed", OBSERVED + [{"time_tag": "2026-09-06T09:00:00", "Kp": "NaN", "a_running": 2}]),
    ("forecast", FORECAST + [{"time_tag": "2026-09-06T09:00:00", "kp": 2, "observed": "unknown"}]),
])
def test_kp3h_child_refuses_any_invalid_row_without_output(mode, rows, tmp_path):
    result, output = _run(tmp_path, "normalize", mode, rows)
    assert result.returncode != 0
    assert not output.exists()


def test_kp_operation_bounds_cover_both_documents_and_outputs(monkeypatch):
    monkeypatch.setattr(SWPCKpAdapter, "_require_bounded_runtime", staticmethod(lambda: None))
    bounds = SWPCKpAdapter().operation_bounds(FetchWindow(datetime(2026, 9, 6, tzinfo=timezone.utc)))
    assert bounds.received_bytes == 1024 * 1024
    assert bounds.store_bytes == 1024 * 1024
    assert bounds.filesystem_bytes == 1024 * 1024
    assert bounds.margin_bytes == 8192


def test_kp_refuses_unmeasured_filesystem_geometry(monkeypatch, tmp_path):
    class Geometry:
        st_dev = 1
        st_blksize = 8192
    monkeypatch.setattr(Path, "stat", lambda _path: Geometry())
    class VFS:
        f_frsize = 8192
    monkeypatch.setattr(os, "statvfs", lambda _path: VFS())
    with pytest.raises(AdapterUnavailable, match="requires measured 4096-byte filesystem blocks"):
        SWPCKpAdapter._require_measured_filesystem(tmp_path)


def test_kp_operation_preflight_refuses_unsupported_kernel_before_discovery(monkeypatch):
    def unavailable():
        raise RuntimeError("locked limits unavailable")
    monkeypatch.setattr(SWPCKpAdapter, "_require_bounded_runtime", staticmethod(unavailable))
    with pytest.raises(RuntimeError, match="locked limits unavailable"):
        SWPCKpAdapter().operation_bounds(FetchWindow(datetime(2026, 9, 6, tzinfo=timezone.utc)))


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS target-runtime verification")
def test_kp_adapter_runs_both_documents_under_linux_kernel_limits(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = FORECAST if "forecast" in str(request.url) else OBSERVED
        return httpx.Response(200, content=json.dumps(body).encode())
    client = PoliteClient(min_host_interval_seconds=0, attempts=1)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    adapter = SWPCKpAdapter(client=client)
    window = FetchWindow(datetime(2026, 9, 6, 7, tzinfo=timezone.utc))
    result = adapter.fetch(adapter.discover(window)[0], window, tmp_path)
    assert result.complete
    assert [artifact.logical_name for artifact in result.artifacts] == ["kp_observed", "kp_forecast"]
    assert all(artifact.payload_path.stat().st_size <= 512 * 1024 for artifact in result.artifacts)
