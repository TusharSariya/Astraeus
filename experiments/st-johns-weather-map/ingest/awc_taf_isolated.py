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


_REPORT_KEYS = {"bulletinTime", "dbPopTime", "elev", "fcsts", "icaoId", "issueTime", "lat", "lon", "mostRecent", "name", "prior", "rawTAF", "remarks", "validTimeFrom", "validTimeTo"}
_GROUP_KEYS = {"altim", "cavok", "clouds", "fcstChange", "icgTurb", "notDecoded", "probability", "temp", "timeBec", "timeFrom", "timeTo", "vertVis", "visib", "wdir", "wgst", "windVariable", "wshearDir", "wshearHgt", "wshearSpd", "wspd", "wxString"}
_CHANGES = {None, "", "FM", "BECMG", "TEMPO", "PROB"}
_CLOUD_COVERS = {"SKC", "CLR", "NSC", "FEW", "SCT", "BKN", "OVC", "VV", "OVX", "CAVOK"}


def _finite_number(value: object, label: str, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise AdapterUnavailable(f"AWC TAF has invalid {label}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AdapterUnavailable(f"AWC TAF has invalid {label}") from None
    if not math.isfinite(number):
        raise AdapterUnavailable(f"AWC TAF has invalid {label}")
    if number < minimum or (maximum is not None and number > maximum):
        raise AdapterUnavailable(f"AWC TAF has out-of-range {label}")
    return number


def _decode(raw: bytes, window: FetchWindow) -> dict[str, object]:
    try:
        rows = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"AWC TAF response is not JSON: {error}") from error
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise AdapterUnavailable("AWC TAF response must contain exactly one report")
    taf = rows[0]
    unknown_report = set(taf) - _REPORT_KEYS
    if unknown_report:
        raise AdapterUnavailable(f"AWC TAF report has unsupported keys: {sorted(unknown_report)}")
    if taf.get("icaoId") != "CYYT" or not isinstance(taf.get("rawTAF"), str) or not taf["rawTAF"].strip():
        raise AdapterUnavailable("AWC TAF report has invalid identity or raw report")
    parsed_times = {}
    for key in ("issueTime", "bulletinTime", "dbPopTime"):
        try:
            parsed_times[key] = datetime.fromisoformat(str(taf.get(key, "")).replace("Z", "+00:00"))
        except ValueError as error:
            raise AdapterUnavailable(f"AWC TAF {key} is invalid") from error
        if parsed_times[key].tzinfo is None:
            raise AdapterUnavailable(f"AWC TAF {key} is not timezone-aware")
    issue = parsed_times["issueTime"]
    latitude = _finite_number(taf.get("lat"), "lat", minimum=-90, maximum=90)
    longitude = _finite_number(taf.get("lon"), "lon", minimum=-180, maximum=180)
    _finite_number(taf.get("elev"), "elev", minimum=-500, maximum=9000)
    if abs(latitude - 47.627) > 0.1 or abs(longitude - (-52.748)) > 0.1:
        raise AdapterUnavailable("AWC TAF report is outside the measured CYYT station position")
    for key in ("name", "remarks"):
        if taf.get(key) is not None and not isinstance(taf[key], str):
            raise AdapterUnavailable(f"AWC TAF has invalid {key}")
    for key in ("mostRecent", "prior"):
        if isinstance(taf.get(key), bool) or not isinstance(taf.get(key), int):
            raise AdapterUnavailable(f"AWC TAF has invalid {key}")
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
        unknown_group = set(group) - _GROUP_KEYS
        if unknown_group:
            raise AdapterUnavailable(f"AWC TAF group {index} has unsupported keys: {sorted(unknown_group)}")
        change = group.get("fcstChange")
        if change not in _CHANGES:
            raise AdapterUnavailable(f"AWC TAF group {index} has unsupported fcstChange")
        start = _epoch(group.get("timeFrom"), f"group {index} timeFrom")
        end = _epoch(group.get("timeTo"), f"group {index} timeTo")
        if end <= start or start < valid_from or end > valid_to:
            raise AdapterUnavailable(f"AWC TAF group {index} has invalid validity")
        time_bec = group.get("timeBec")
        if time_bec is not None:
            became = _epoch(time_bec, f"group {index} timeBec")
            if change != "BECMG" or became < start or became > end:
                raise AdapterUnavailable(f"AWC TAF group {index} has invalid timeBec")
        if change == "BECMG" and time_bec is None:
            raise AdapterUnavailable(f"AWC TAF group {index} BECMG has no timeBec")
        probability = group.get("probability")
        if probability is not None:
            _finite_number(probability, f"group {index} probability", maximum=100)
            if probability not in {30, 40}:
                raise AdapterUnavailable(f"AWC TAF group {index} has unsupported probability")
            if change != "PROB":
                raise AdapterUnavailable(f"AWC TAF group {index} probability is not a PROB group")
        if change == "PROB" and probability is None:
            raise AdapterUnavailable(f"AWC TAF group {index} PROB has no probability")
        for key in ("wspd", "wgst", "visib", "vertVis", "wshearHgt", "wshearSpd"):
            if group.get(key) is not None:
                _finite_number(group[key], f"group {index} {key}")
        direction = group.get("wdir")
        if direction is not None and str(direction).upper() != "VRB":
            _finite_number(direction, f"group {index} wdir", maximum=360)
        if group.get("wxString") is not None and not isinstance(group["wxString"], str):
            raise AdapterUnavailable(f"AWC TAF group {index} has invalid wxString")
        for key in ("altim", "notDecoded", "wshearDir", "wshearHgt", "wshearSpd"):
            if group.get(key) is not None:
                raise AdapterUnavailable(f"AWC TAF group {index} populated unsupported {key}")
        for key in ("temp", "icgTurb"):
            if group.get(key) not in (None, []):
                raise AdapterUnavailable(f"AWC TAF group {index} populated unsupported {key}")
        clouds = group.get("clouds")
        if clouds is not None and (not isinstance(clouds, list) or len(clouds) > 6):
            raise AdapterUnavailable(f"AWC TAF group {index} has unsupported cloud layers")
        for layer, cloud in enumerate(clouds or []):
            if not isinstance(cloud, dict) or set(cloud) - {"cover", "base", "type"}:
                raise AdapterUnavailable(f"AWC TAF group {index} cloud {layer} has unsupported shape")
            if str(cloud.get("cover") or "").upper() not in _CLOUD_COVERS:
                raise AdapterUnavailable(f"AWC TAF group {index} cloud {layer} has invalid cover")
            if cloud.get("base") is not None:
                _finite_number(cloud["base"], f"group {index} cloud {layer} base")
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
