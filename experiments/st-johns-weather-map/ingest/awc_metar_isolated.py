"""Kernel-bounded decoder for one complete AWC CYYT METAR response."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["OPENBLAS_NUM_THREADS"] = "1"

from ingest.adapters.awc import (
    AWCMetarAdapter,
    CLOUD_COVER_FLAGS,
    parse_visibility_meters,
)
from ingest.contract import AdapterUnavailable, FetchWindow, RunCandidate


_KNOWN_KEYS = {
    "altim", "clouds", "cover", "dewp", "elev", "fltCat", "icaoId",
    "lat", "lon", "metarId", "metarType", "name", "obsTime", "qcField", "rawOb",
    "receiptTime", "reportTime", "slp", "temp", "vertVis", "visib",
    "wdir", "wgst", "wspd", "wxString",
}
_TEXT_KEYS = {"fltCat", "metarType", "name", "rawOb", "wxString"}
_FINITE_KEYS = {"altim", "dewp", "elev", "lat", "lon", "metarId", "qcField", "slp", "temp", "vertVis", "wgst", "wspd"}


def _validate_native_row(row: dict[str, object], index: int) -> None:
    unknown = sorted(set(row) - _KNOWN_KEYS)
    if unknown:
        raise AdapterUnavailable(f"AWC METAR row {index} has unsupported keys: {','.join(unknown)}")
    for key in _TEXT_KEYS:
        value = row.get(key)
        if value is not None and not isinstance(value, str):
            raise AdapterUnavailable(f"AWC METAR row {index} has invalid {key}")
    for key in ("reportTime", "receiptTime"):
        value = row.get(key)
        if value is not None:
            if not isinstance(value, str):
                raise AdapterUnavailable(f"AWC METAR row {index} has invalid {key}")
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise AdapterUnavailable(f"AWC METAR row {index} has invalid {key}") from error
    for key in _FINITE_KEYS:
        value = row.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))):
            raise AdapterUnavailable(f"AWC METAR row {index} has invalid {key}")
    latitude, longitude = row.get("lat"), row.get("lon")
    if latitude is not None and not -90 <= float(latitude) <= 90:
        raise AdapterUnavailable(f"AWC METAR row {index} has invalid lat")
    if longitude is not None and not -180 <= float(longitude) <= 180:
        raise AdapterUnavailable(f"AWC METAR row {index} has invalid lon")
    direction = row.get("wdir")
    if direction is not None:
        if isinstance(direction, str) and direction.upper() == "VRB":
            pass
        elif isinstance(direction, bool) or not isinstance(direction, (int, float)) or not math.isfinite(float(direction)) or not 0 <= float(direction) <= 360:
            raise AdapterUnavailable(f"AWC METAR row {index} has invalid wdir")
    visibility = row.get("visib")
    if visibility is not None and parse_visibility_meters(visibility) is None:
        raise AdapterUnavailable(f"AWC METAR row {index} has invalid visib")
    cover = row.get("cover")
    if cover is not None and (not isinstance(cover, str) or cover.upper() not in CLOUD_COVER_FLAGS):
        raise AdapterUnavailable(f"AWC METAR row {index} has invalid cover")
    clouds = row.get("clouds")
    if clouds is not None:
        if not isinstance(clouds, list):
            raise AdapterUnavailable(f"AWC METAR row {index} has invalid clouds")
        for cloud in clouds:
            if not isinstance(cloud, dict) or set(cloud) - {"cover", "base"}:
                raise AdapterUnavailable(f"AWC METAR row {index} has invalid clouds")
            code = cloud.get("cover")
            base = cloud.get("base")
            if not isinstance(code, str) or code.upper() not in CLOUD_COVER_FLAGS:
                raise AdapterUnavailable(f"AWC METAR row {index} has invalid cloud cover")
            if base is not None and (isinstance(base, bool) or not isinstance(base, (int, float)) or not math.isfinite(float(base))):
                raise AdapterUnavailable(f"AWC METAR row {index} has invalid cloud base")


def _decode(raw: bytes, window: FetchWindow) -> list[dict[str, object]]:
    try:
        rows = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"AWC METAR response is not JSON: {error}") from error
    if not isinstance(rows, list) or not rows:
        raise AdapterUnavailable("AWC METAR response is not a non-empty row list")
    if len(rows) > 64:
        raise AdapterUnavailable("AWC METAR response exceeds 64-row measured bound")
    seen: set[int] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or "obsTime" not in row or row.get("icaoId") != "CYYT":
            raise AdapterUnavailable(f"AWC METAR row {index} has invalid identity")
        _validate_native_row(row, index)
        value = row["obsTime"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise AdapterUnavailable(f"AWC METAR row {index} has invalid obsTime")
        stamp = int(value)
        if float(stamp) != float(value) or stamp in seen:
            raise AdapterUnavailable(f"AWC METAR row {index} has duplicate or fractional obsTime")
        seen.add(stamp)
        if not window.covers(datetime.fromtimestamp(stamp, tz=window.now.tzinfo)):
            raise AdapterUnavailable(f"AWC METAR row {index} lies outside the requested window")
    return rows


def main() -> int:
    if len(sys.argv) != 5 or sys.argv[1] not in {"probe", "inspect", "normalize"}:
        print("usage: awc_metar_isolated probe|inspect|normalize START END OUTPUT", file=sys.stderr)
        return 2
    try:
        start = datetime.fromisoformat(sys.argv[2])
        end = datetime.fromisoformat(sys.argv[3])
        hours_back = (end - start).total_seconds() / 3600.0
        window = FetchWindow(end, back_hours=hours_back, forward_hours=0)
        raw = sys.stdin.buffer.read()
        if sys.argv[1] == "probe":
            if raw:
                raise AdapterUnavailable("AWC METAR allocation probe requires empty input")
            print('{"probe":"ok"}')
            return 0
        rows = _decode(raw, window)
        newest = max(int(row["obsTime"]) for row in rows)
        reply: dict[str, object] = {"count": len(rows), "newest": newest}
        if sys.argv[1] == "normalize":
            output = Path(sys.argv[4])
            result = AWCMetarAdapter().fetch(
                RunCandidate(f"cyyt-metar-{newest}", datetime.fromtimestamp(newest, tz=window.now.tzinfo), [], {"records": rows}),
                window,
                output.parent,
            )
            generated = output.parent / "cyyt_metar.zarr.zip"
            generated.replace(output)
            artifact = result.artifacts[0]
            reply.update({"run_time": result.run_time.isoformat(), "complete": result.complete,
                          "qc_passed": result.qc_passed, "provenance": artifact.provenance,
                          "notes": result.notes})
        print(json.dumps(reply, separators=(",", ":")))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
