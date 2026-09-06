"""Memory-isolated decoders for NOAA SWPC observed and forecast 3-hour Kp."""
from __future__ import annotations

import json
import math
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy
import xarray
import zarr

from ingest.contract import AdapterUnavailable
from ingest.space_weather import parse_time, series_dataset

_STATUS = {"observed": 0, "estimated": 1, "predicted": 2}


def _number(row: dict[str, Any], field: str, index: int) -> float:
    value = row.get(field)
    if value is None or isinstance(value, bool):
        raise AdapterUnavailable(f"SWPC Kp row {index} has invalid {field}")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise AdapterUnavailable(f"SWPC Kp row {index} has invalid {field}") from error
    if not math.isfinite(result):
        raise AdapterUnavailable(f"SWPC Kp row {index} has non-finite {field}")
    return result


def decode(raw: bytes, mode: str) -> list[tuple[datetime, float, float]]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"SWPC Kp is not JSON: {error}") from error
    if not isinstance(payload, list) or not payload:
        raise AdapterUnavailable("SWPC Kp is not a non-empty row list")
    fields = ("time_tag", "Kp", "a_running") if mode == "observed" else ("time_tag", "kp", "observed")
    if isinstance(payload[0], list):
        header = payload[0]
        if not header or len(set(header)) != len(header) or any(field not in header for field in fields):
            raise AdapterUnavailable("SWPC Kp header row is malformed or incomplete")
        if any(not isinstance(row, list) or len(row) != len(header) for row in payload[1:]):
            raise AdapterUnavailable("SWPC Kp data row does not match its header; refused without thinning")
        payload = [dict(zip(header, row, strict=True)) for row in payload[1:]]
        if not payload:
            raise AdapterUnavailable("SWPC Kp header carries no data rows")
    rows: list[tuple[datetime, float, float]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or any(field not in row for field in fields):
            raise AdapterUnavailable(f"SWPC Kp row {index} is malformed or incomplete; refused without thinning")
        stamp = parse_time(row["time_tag"])
        if stamp is None:
            raise AdapterUnavailable(f"SWPC Kp row {index} has an unparseable time_tag")
        kp = _number(row, "Kp" if mode == "observed" else "kp", index)
        if mode == "observed":
            context = _number(row, "a_running", index)
        else:
            status = str(row["observed"]).strip().lower()
            if status not in _STATUS:
                raise AdapterUnavailable(f"SWPC Kp row {index} has unsupported observed status")
            context = float(_STATUS[status])
        rows.append((stamp, kp, context))
    rows.sort(key=lambda item: item[0])
    if len({row[0] for row in rows}) != len(rows):
        raise AdapterUnavailable("SWPC Kp carries duplicate instants")
    return rows


def _write(rows: list[tuple[datetime, float, float]], mode: str, output: Path) -> None:
    times = [row[0] for row in rows]
    variables = {
        "kp_index": (numpy.array([row[1] for row in rows]), {"units": "dimensionless", "original_units": "Kp index", "long_name": "planetary K index, 3-hourly, as retrieved"}),
    }
    if mode == "observed":
        variables["a_running"] = (numpy.array([row[2] for row in rows]), {"units": "dimensionless", "original_units": "a index", "long_name": "running a index, as retrieved"})
        source = "SWPC planetary K index (observed series)"
    else:
        variables["kp_status"] = (numpy.array([row[2] for row in rows]), {"units": "flag", "original_units": "provider status string", "flag_values": [0, 1, 2], "flag_meanings": "observed estimated predicted"})
        source = "SWPC planetary K index forecast; per-value status is the provider's own"
    dataset = series_dataset(times, variables, {"source": source})
    backing: dict[str, Any] = {}
    dataset.to_zarr(zarr.storage.MemoryStore(backing), mode="w", consolidated=False)
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(backing):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, backing[name].to_bytes())
    store = zarr.storage.ZipStore(str(output), mode="r")
    try:
        reopened = xarray.open_zarr(store, consolidated=False)
        expected = {"kp_index", "a_running" if mode == "observed" else "kp_status"}
        if set(reopened.data_vars) != expected:
            raise AdapterUnavailable("isolated SWPC Kp artifact failed round-trip validation")
    finally:
        store.close()


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in {"inspect", "normalize"} or sys.argv[2] not in {"observed", "forecast"}:
        print("usage: kp3h_isolated inspect|normalize observed|forecast OUTPUT", file=sys.stderr)
        return 2
    action, mode = sys.argv[1:3]
    try:
        rows = decode(sys.stdin.buffer.read(), mode)
        if action == "normalize":
            _write(rows, mode, Path(sys.argv[3]))
        print(json.dumps({"count": len(rows), "times": [row[0].isoformat() for row in rows]}, separators=(",", ":")))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
