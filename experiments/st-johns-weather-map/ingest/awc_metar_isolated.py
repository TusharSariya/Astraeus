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

from ingest.adapters.awc import AWCMetarAdapter
from ingest.contract import AdapterUnavailable, FetchWindow, RunCandidate


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
