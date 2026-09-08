"""Leaf process reusing the experimental NL station parser without API imports."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# The existing adapter imports numpy/xarray; constrain native thread allocation
# before importing them inside the process address-space limit.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest.contract import FetchWindow
from ingest.experimental.nl_air_quality import MAX_CSV_BYTES, _parse


def decode(body: bytes, start: datetime, end: datetime) -> list[dict[str, object]]:
    if len(body) > MAX_CSV_BYTES:
        raise ValueError("NL CSV exceeds the byte ceiling")
    rows = _parse(body, FetchWindow(end, back_hours=(end - start).total_seconds() / 3600, forward_hours=0))
    return [{**row, "time": row["time"].isoformat()} for row in rows]


def main() -> int:
    try:
        start, end = (datetime.fromisoformat(value) for value in sys.argv[1:3])
        if start.tzinfo is None or end.tzinfo is None or not 0 <= (end - start).total_seconds() <= 35 * 86400:
            raise ValueError("NL window must be offset-aware and at most 35 days")
        rows = decode(sys.stdin.buffer.read(MAX_CSV_BYTES + 1), start, end)
        json.dump(rows, sys.stdout, allow_nan=False, separators=(",", ":"))
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
