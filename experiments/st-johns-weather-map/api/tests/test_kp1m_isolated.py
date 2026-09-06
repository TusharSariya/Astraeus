from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import xarray
import zarr

from ingest.adapters.swpc_products import SWPCKp1mAdapter
from ingest.contract import FetchWindow
from ingest.http import PoliteClient, USER_AGENT
from ingest import kp1m_isolated
import httpx
from datetime import datetime, timezone


def _run(tmp_path, rows, mode="normalize"):
    output = tmp_path / ("kp.zip" if mode == "normalize" else "marker")
    result = subprocess.run(
        [sys.executable, "-m", "ingest.kp1m_isolated", mode, str(output)],
        input=json.dumps(rows).encode(), capture_output=True, check=False,
        env={**os.environ, "PYTHONPATH": str(Path(kp1m_isolated.__file__).resolve().parents[1])},
    )
    return result, output


def test_isolated_kp_decoder_preserves_every_row_in_one_output(tmp_path):
    rows = [
        {"time_tag": "2026-09-06T04:20:00", "kp_index": 1, "estimated_kp": 1.33, "kp": "1P"},
        {"time_tag": "2026-09-06T04:21:00", "kp_index": 0, "estimated_kp": 0, "kp": "0Z"},
    ]
    result, output = _run(tmp_path, rows)

    assert result.returncode == 0
    assert json.loads(result.stdout)["count"] == len(rows)
    assert [item.name for item in tmp_path.iterdir()] == ["kp.zip"]
    store = zarr.storage.ZipStore(str(output), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    assert dataset.kp_index.values.tolist() == [1.0, 0.0]
    assert dataset.estimated_kp.values.tolist() == [1.33, 0.0]
    assert dataset.kp_code.values.tolist() == [4.0, 0.0]
    store.close()


@pytest.mark.parametrize(
    "row",
    [
        {"time_tag": "bad", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"},
        {"time_tag": "2026-09-06T04:20:00", "kp_index": "NaN", "estimated_kp": 1, "kp": "1Z"},
        {"time_tag": "2026-09-06T04:20:00", "kp_index": 1, "estimated_kp": 1, "kp": "new"},
    ],
)
def test_isolated_kp_decoder_refuses_any_invalid_row_without_output(tmp_path, row):
    good = {"time_tag": "2026-09-06T04:19:00", "kp_index": 1, "estimated_kp": 1, "kp": "1Z"}
    result, output = _run(tmp_path, [good, row])

    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS target-runtime verification")
def test_kp_adapter_runs_discovery_and_normalization_under_linux_kernel_limits(tmp_path):
    rows = [
        {"time_tag": "2026-09-06T04:20:00", "kp_index": 1, "estimated_kp": 1.33, "kp": "1P"},
        {"time_tag": "2026-09-06T04:21:00", "kp_index": 0, "estimated_kp": 0, "kp": "0Z"},
    ]
    raw = json.dumps(rows).encode()
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=raw))
    client = PoliteClient(min_host_interval_seconds=0, attempts=1)
    client._client = httpx.Client(transport=transport, headers={"User-Agent": USER_AGENT})
    adapter = SWPCKp1mAdapter(client=client)
    window = FetchWindow(datetime(2026, 9, 6, 4, 22, tzinfo=timezone.utc))

    candidate = adapter.discover(window)[0]
    result = adapter.fetch(candidate, window, tmp_path)

    assert candidate.detail["valid_times"] == [row["time_tag"] + "Z" for row in rows]
    assert result.complete and result.qc_passed
    assert result.artifacts[0].payload_path.stat().st_size <= 512 * 1024
