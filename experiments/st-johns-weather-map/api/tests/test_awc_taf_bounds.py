from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ingest.adapters.awc import AWC_TAF_ARTIFACT_BYTES, AWC_TAF_DOCUMENT_BYTES, AWCTafAdapter, validate_taf_structure
from ingest.awc_taf_isolated import _decode
from ingest.contract import AdapterUnavailable, FetchWindow

UTC = timezone.utc
WINDOW = FetchWindow(datetime(2026, 9, 6, 12, tzinfo=UTC), back_hours=3, forward_hours=24)


def report(*groups):
    return [{"icaoId": "CYYT", "issueTime": "2026-09-06T11:41:00Z", "validTimeFrom": 1788696000,
             "validTimeTo": 1788782400, "rawTAF": "TAF CYYT 061141Z 0612/0712",
             "fcsts": list(groups)}]


def group(start=1788696000, end=1788714000, **extra):
    return {"timeFrom": start, "timeTo": end, "wspd": 12, "wdir": 180, "visib": "6", "clouds": [], **extra}


def payload(value):
    return json.dumps(value, separators=(",", ":")).encode()


def test_strict_decoder_retains_ordered_duplicate_start_groups():
    rows = report(group(fcstChange="FM"), group(fcstChange="TEMPO"))
    decoded = _decode(payload(rows), WINDOW)
    assert [item["fcstChange"] for item in decoded["fcsts"]] == ["FM", "TEMPO"]


@pytest.mark.parametrize(("value", "message"), [
    ([], "exactly one"),
    (report(*[group(start=1788696000 + i, end=1788714000 + i) for i in range(33)]), "1..32"),
    (report(group(end=1788695999)), "validity"),
    (report(group(clouds=[{"cover": "FEW", "base": 100}] * 7)), "cloud layers"),
])
def test_strict_decoder_refuses_whole_unsupported_response(value, message):
    with pytest.raises(AdapterUnavailable, match=message):
        _decode(payload(value), WINDOW)


def test_declared_taf_limits_cover_all_enforced_channels(monkeypatch):
    monkeypatch.setattr(AWCTafAdapter, "_require_target", staticmethod(lambda _path: None))
    monkeypatch.setattr(AWCTafAdapter, "_isolated", staticmethod(lambda *_args: object()))
    bounds = AWCTafAdapter().operation_bounds(WINDOW)
    assert bounds.received_bytes == AWC_TAF_DOCUMENT_BYTES
    assert bounds.store_bytes == bounds.filesystem_bytes == AWC_TAF_ARTIFACT_BYTES
    assert bounds.margin_bytes == 8192
    assert bounds.filesystem_bytes + bounds.margin_bytes == 65536 + 4096 + 4096

@pytest.mark.parametrize("mutation", [
    {"fcstChange": "UNKNOWN"},
    {"fcstChange": "PROB", "probability": 101},
    {"fcstChange": "BECMG", "timeBec": None},
    {"wspd": float("nan")},
    {"wdir": 361},
    {"visib": "not-a-number"},
    {"wxString": ["FG"]},
    {"clouds": [{"cover": "BOGUS", "base": 100}]},
    {"clouds": [{"cover": "FEW", "base": float("inf")}]},
    {"unexpected": 1},
])
def test_strict_decoder_rejects_invalid_present_fields(mutation):
    with pytest.raises(AdapterUnavailable):
        _decode(payload(report(group(**mutation))), WINDOW)


def test_strict_decoder_accepts_variable_direction():
    decoded = _decode(payload(report(group(wdir="VRB"))), WINDOW)
    assert decoded["fcsts"][0]["wdir"] == "VRB"


def test_structural_validation_accepts_vrb_but_refuses_empty_sky_declaration():
    stamp = datetime(2026, 9, 6, 12, tzinfo=UTC)
    vrb = group(wdir="VRB", clouds=[{"cover": "OVC", "base": 400}])
    assert validate_taf_structure({}, [(stamp, vrb)], []).complete
    empty = group(wdir="VRB", clouds=[])
    result = validate_taf_structure({}, [(stamp, empty)], [])
    assert not result.complete
    assert "self_contained_sky@0" in result.detail
