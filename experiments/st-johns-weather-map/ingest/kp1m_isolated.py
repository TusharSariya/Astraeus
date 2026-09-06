"""Memory-isolated decoder for the bounded NOAA SWPC Kp-1m document."""

from __future__ import annotations

import json
import math
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    # The bounded runner deliberately changes cwd to its private workspace.
    # Make direct execution resolve the sibling ``ingest`` package without
    # relying on a caller-controlled PYTHONPATH.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# One decoder process has one numeric workload. Prevent BLAS from reserving a
# machine-dependent thread pool before the address-space limit can constrain it.
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy
import xarray
import zarr

from ingest.contract import AdapterUnavailable
from ingest.space_weather import flag_attrs, parse_time, series_dataset

KP_CODES = (
    "0Z", "0P", "1M", "1Z", "1P", "2M", "2Z", "2P", "3M", "3Z", "3P",
    "4M", "4Z", "4P", "5M", "5Z", "5P", "6M", "6Z", "6P", "7M", "7Z",
    "7P", "8M", "8Z", "8P", "9M", "9Z",
)
_CODE_INDEX = {code: index for index, code in enumerate(KP_CODES)}
_REQUIRED = ("time_tag", "kp_index", "estimated_kp", "kp")


def decode_rows(raw: bytes) -> list[tuple[datetime, float, float, int]]:
    """Decode every raw row or refuse the entire document without thinning."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"SWPC 1-minute Kp is not JSON: {error}") from error
    if not isinstance(payload, list) or not payload:
        raise AdapterUnavailable("SWPC 1-minute Kp is not a non-empty row list")
    decoded: list[tuple[datetime, float, float, int]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or any(field not in row for field in _REQUIRED):
            raise AdapterUnavailable(
                f"SWPC 1-minute Kp row {index} is malformed or incomplete; refused without thinning"
            )
        stamp = parse_time(row["time_tag"])
        if stamp is None:
            raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has an unparseable time_tag")
        numbers: list[float] = []
        for field in ("kp_index", "estimated_kp"):
            value = row[field]
            if value is None or isinstance(value, bool):
                raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has invalid {field}")
            try:
                number = float(value)
            except (TypeError, ValueError) as error:
                raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has invalid {field}") from error
            if not math.isfinite(number):
                raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has non-finite {field}")
            numbers.append(number)
        code = str(row["kp"]).strip()
        if code not in _CODE_INDEX:
            raise AdapterUnavailable(f"SWPC 1-minute Kp row {index} has an unsupported kp code")
        decoded.append((stamp, numbers[0], numbers[1], _CODE_INDEX[code]))
    decoded.sort(key=lambda item: item[0])
    if len({item[0] for item in decoded}) != len(decoded):
        raise AdapterUnavailable("SWPC 1-minute Kp carries duplicate instants")
    return decoded


def _write_memory_zarr(rows: list[tuple[datetime, float, float, int]], output: Path) -> None:
    times = [row[0] for row in rows]
    dataset = series_dataset(
        times,
        {
            "kp_index": (numpy.array([row[1] for row in rows]), {"units": "dimensionless", "original_units": "Kp index", "long_name": "planetary K index, 1-minute, as retrieved"}),
            "estimated_kp": (numpy.array([row[2] for row in rows]), {"units": "dimensionless", "original_units": "Kp index", "long_name": "estimated planetary K index, as retrieved"}),
            "kp_code": (numpy.array([row[3] for row in rows], dtype="float64"), flag_attrs(list(KP_CODES), long_name="the provider's own Kp thirds code, as retrieved")),
        },
        {"source": "SWPC 1-minute planetary K index"},
    )
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
        if set(reopened.data_vars) != {"kp_index", "estimated_kp", "kp_code"}:
            raise AdapterUnavailable("isolated Kp artifact failed round-trip validation")
    finally:
        store.close()


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"inspect", "normalize"}:
        print("usage: python -m ingest.kp1m_isolated inspect|normalize OUTPUT", file=sys.stderr)
        return 2
    output = Path(sys.argv[2])
    try:
        rows = decode_rows(sys.stdin.buffer.read())
        if sys.argv[1] == "normalize":
            _write_memory_zarr(rows, output)
        print(json.dumps({
            "count": len(rows),
            "times": [row[0].isoformat() for row in rows],
            "newest": rows[-1][0].isoformat(),
        }, separators=(",", ":")))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
