"""Memory-isolated, all-row GFZ Hp30 decoder and writer."""
from __future__ import annotations

import json
import math
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

os.environ["OPENBLAS_NUM_THREADS"] = "1"

import numpy
import xarray
import zarr

from ingest.contract import AdapterUnavailable
from ingest.space_weather import format_time, parse_time, series_dataset


def decode(raw: bytes) -> tuple[list[str], list[float], dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"GFZ Hp30 is not JSON: {error}") from error
    if not isinstance(payload, dict):
        raise AdapterUnavailable("GFZ Hp30 returned a non-object payload")
    if set(payload) != {"Hp30", "datetime", "meta"}:
        raise AdapterUnavailable("GFZ Hp30 payload schema drift; refused without dropping fields")
    meta, values, stamps = payload["meta"], payload["Hp30"], payload["datetime"]
    if (not isinstance(meta, dict) or set(meta) != {"license", "source"}
            or meta.get("license") != "CC BY 4.0" or meta.get("source") != "GFZ Potsdam"):
        raise AdapterUnavailable(f"GFZ Hp30 declares licence {meta.get('license') if isinstance(meta,dict) else None!r}, not 'CC BY 4.0'")
    if not isinstance(values, list) or not isinstance(stamps, list) or not values or len(values) != len(stamps):
        raise AdapterUnavailable("GFZ Hp30 returned no values or value/datetime arrays are misaligned")
    times: list[str] = []
    numbers: list[float] = []
    for index, (stamp, value) in enumerate(zip(stamps, values, strict=True)):
        instant = parse_time(stamp)
        if instant is None:
            raise AdapterUnavailable(f"GFZ Hp30 row {index} has an unparseable datetime; refused without thinning")
        if value is None:
            number=float("nan")
        elif isinstance(value, bool) or not isinstance(value,(int,float)) or not __import__("math").isfinite(float(value)):
            raise AdapterUnavailable(f"GFZ Hp30 row {index} has an unsupported value")
        else:
            number=float(value)
        times.append(format_time(instant))
        numbers.append(number)
    if len(set(times)) != len(times):
        raise AdapterUnavailable("GFZ Hp30 served a repeated instant")
    order = sorted(range(len(times)), key=times.__getitem__)
    return [times[i] for i in order], [numbers[i] for i in order], meta


def write(times: list[str], values: list[float], output: Path) -> None:
    instants = [parse_time(value) for value in times]
    if any(value is None for value in instants):
        raise AdapterUnavailable("GFZ Hp30 isolated writer received an invalid time")
    dataset = series_dataset(
        [value for value in instants if value is not None],
        {"hp30_index": (numpy.asarray(values), {"units": "dimensionless", "original_units": "Hp30 index", "long_name": "Hp30 half-hour geomagnetic index, as retrieved"})},
        {"source": "GFZ Hp30 half-hour geomagnetic index", "licence": "CC BY 4.0", "status_note": "the Hp30 JSON declares no per-value nowcast/definitive status; none is invented"},
    )
    backing: dict[str, Any] = {}
    dataset.to_zarr(zarr.storage.MemoryStore(backing), mode="w", consolidated=False)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(backing):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type=zipfile.ZIP_STORED; info.external_attr=0o644 << 16
            archive.writestr(info, backing[name].to_bytes())
    store=zarr.storage.ZipStore(str(output),mode="r")
    try:
        reopened=xarray.open_zarr(store,consolidated=False)
        if set(reopened.data_vars)!={"hp30_index"} or reopened.sizes.get("valid_time")!=len(times):
            raise AdapterUnavailable("GFZ Hp30 artifact failed round-trip validation")
    finally: store.close()


def main() -> int:
    if len(sys.argv)!=3 or sys.argv[1] not in {"inspect","normalize"}:
        print("usage: gfz_hp30_isolated inspect|normalize OUTPUT",file=sys.stderr); return 2
    try:
        times,values,meta=decode(sys.stdin.buffer.read())
        if sys.argv[1]=="normalize": write(times,values,Path(sys.argv[2]))
        print(json.dumps({"count":len(times),"finite_count":sum(math.isfinite(value) for value in values),"times":times,"meta":meta},separators=(",",":"))); return 0
    except Exception as error:
        print(str(error),file=sys.stderr); return 1

if __name__ == "__main__": raise SystemExit(main())
