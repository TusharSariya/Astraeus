"""Kernel-bounded decoder for one complete AWC CYYT TAF response."""
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

from ingest.adapters.awc import AWCTafAdapter
from ingest.contract import AdapterUnavailable, FetchWindow, RunCandidate


def _epoch(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AdapterUnavailable(f"AWC TAF has invalid {label}")
    stamp = int(value)
    if float(stamp) != float(value):
        raise AdapterUnavailable(f"AWC TAF has fractional {label}")
    return stamp


def _decode(raw: bytes, window: FetchWindow) -> dict[str, object]:
    try:
        rows = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"AWC TAF response is not JSON: {error}") from error
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise AdapterUnavailable("AWC TAF response must contain exactly one report")
    taf = rows[0]
    if taf.get("icaoId") != "CYYT" or not isinstance(taf.get("rawTAF"), str) or not taf["rawTAF"].strip():
        raise AdapterUnavailable("AWC TAF report has invalid identity or raw report")
    issue = datetime.fromisoformat(str(taf.get("issueTime", "")).replace("Z", "+00:00"))
    if issue.tzinfo is None:
        raise AdapterUnavailable("AWC TAF issueTime is not timezone-aware")
    valid_from = _epoch(taf.get("validTimeFrom"), "validTimeFrom")
    valid_to = _epoch(taf.get("validTimeTo"), "validTimeTo")
    if valid_to <= valid_from:
        raise AdapterUnavailable("AWC TAF overall validity is not increasing")
    groups = taf.get("fcsts")
    if not isinstance(groups, list) or not groups or len(groups) > 32:
        raise AdapterUnavailable("AWC TAF forecast-group count is outside the measured 1..32 bound")
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise AdapterUnavailable(f"AWC TAF group {index} is not an object")
        start = _epoch(group.get("timeFrom"), f"group {index} timeFrom")
        end = _epoch(group.get("timeTo"), f"group {index} timeTo")
        if end <= start or start < valid_from or end > valid_to:
            raise AdapterUnavailable(f"AWC TAF group {index} has invalid validity")
        clouds = group.get("clouds")
        if clouds is not None and (not isinstance(clouds, list) or len(clouds) > 6):
            raise AdapterUnavailable(f"AWC TAF group {index} has unsupported cloud layers")
    taf["_issue_epoch"] = int(issue.timestamp())
    return taf


def main() -> int:
    if len(sys.argv) != 5 or sys.argv[1] not in {"probe", "inspect", "normalize"}:
        return 2
    try:
        start, end = datetime.fromisoformat(sys.argv[2]), datetime.fromisoformat(sys.argv[3])
        window = FetchWindow(end, back_hours=(end - start).total_seconds() / 3600.0, forward_hours=0)
        raw = sys.stdin.buffer.read()
        if sys.argv[1] == "probe":
            if raw:
                raise AdapterUnavailable("AWC TAF allocation probe requires empty input")
            print('{"probe":"ok"}')
            return 0
        taf = _decode(raw, window)
        issue_epoch = int(taf.pop("_issue_epoch"))
        reply: dict[str, object] = {"issue_epoch": issue_epoch, "group_count": len(taf["fcsts"])}
        if sys.argv[1] == "normalize":
            output = Path(sys.argv[4])
            run_time = datetime.fromtimestamp(issue_epoch, tz=window.now.tzinfo)
            result = AWCTafAdapter().fetch(RunCandidate(f"cyyt-taf-{issue_epoch}", run_time, [], {"taf": taf}), window, output.parent)
            (output.parent / "cyyt_taf.zarr.zip").replace(output)
            artifact = result.artifacts[0]
            reply.update(run_time=result.run_time.isoformat(), complete=result.complete, qc_passed=result.qc_passed,
                         provenance=artifact.provenance, notes=result.notes)
        print(json.dumps(reply, separators=(",", ":")))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
