from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy
import pytest

from ingest.contract import AdapterUnavailable, FetchWindow, RunCandidate
from ingest.adapters import LOADED
from ingest.experimental.native_deterministic import (
    EVIDENCE_BOUNDS,
    PRODUCT_INVENTORY,
    coverage,
    select_ecmwf_records,
    select_noaa_records,
    IndexedNativeCandidate,
    DWDIconNativeCandidate,
)
from ingest.registry import registered_adapters


def _ecmwf(param: str, *, level: int | None = None) -> dict[str, object]:
    row: dict[str, object] = {"date": "20260905", "time": "0000", "type": "fc", "stream": "oper", "step": "0",
        "levtype": "pl" if level else "sfc", "param": param, "_offset": 1, "_length": 9}
    if level: row["levelist"] = str(level)
    return row


def test_candidates_are_not_registered_and_existing_stubs_remain() -> None:
    assert "ecmwf_opendata" in LOADED and "dwd_icon" in LOADED
    registered = registered_adapters()
    assert "ecmwf-ifs-native" not in registered
    assert "ecmwf-aifs-single-native" not in registered
    assert "noaa-rap-parent-native" not in registered
    assert "noaa-nam-parent-native" not in registered
    assert registered["ecmwf-ifs"].adapter_version == "ecmwf-ifs-v1"
    assert registered["dwd-icon-global"].adapter_version == "dwd-icon-v1"


def test_ifs_inventory_accounts_for_every_selected_profile_level() -> None:
    rows = [_ecmwf("2t"), *(_ecmwf("r", level=level) for level in (1000, 925, 850))]
    selected, disposition = select_ecmwf_records(rows, PRODUCT_INVENTORY["ecmwf-ifs-native"])
    rh = next(item for item in disposition if item["upstream"] == "r")
    assert len(selected) == 4
    assert rh["retrieved_levels"] == [850, 925, 1000]
    assert rh["missing_levels"] == [10, 50, 100, 150, 200, 250, 300, 400, 500, 600, 700]
    assert rh["disposition"] == "missing"


def test_aifs_unavailable_fields_cannot_be_selected_or_invented() -> None:
    selected, disposition = select_ecmwf_records([_ecmwf("q", level=1000)], PRODUCT_INVENTORY["ecmwf-aifs-single-native"])
    assert selected == [_ecmwf("q", level=1000)]
    assert next(x for x in disposition if x["upstream"] == "r")["disposition"] == "catalogued-unavailable"
    assert next(x for x in disposition if x["upstream"] == "tcwv")["canonical"] is None
    q10 = next(x for x in disposition if x["upstream"] == "q" and x["selected_levels"] == [10])
    assert q10["disposition"] == "catalogued-unavailable"


def test_noaa_selection_is_exact_by_parameter_and_level() -> None:
    idx = "\n".join((
        "1:0:d=2026090512:TCDC:boundary layer cloud layer:anl:",
        "2:10:d=2026090512:TCDC:entire atmosphere (considered as a single layer):anl:",
        "3:30:d=2026090512:TMP:2 m above ground:anl:",
    ))
    selected, dispositions = select_noaa_records(idx, PRODUCT_INVENTORY["noaa-nam-parent-native"])
    assert selected == [{"param": "TCDC", "level": "entire atmosphere (considered as a single layer)", "forecast": "anl", "_offset": 10, "_length": 20}]
    assert dispositions[0]["count"] == 1


def test_noaa_trailing_selected_message_is_refused_without_a_file_size() -> None:
    with pytest.raises(AdapterUnavailable, match="unbounded trailing"):
        select_noaa_records("1:0:d=2026090512:TCDC:entire atmosphere:anl:", PRODUCT_INVENTORY["noaa-nam-parent-native"])


def test_geometry_proves_full_box_or_explicit_regional_exclusion() -> None:
    lat, lon = numpy.meshgrid(numpy.linspace(44, 51, 20), numpy.linspace(-59, -45, 30), indexing="ij")
    mask, proof = coverage(lat, lon)
    assert mask.any() and proof.covers_full_box
    rap_lon = numpy.full((3, 3), -60.0)
    _, excluded = coverage(numpy.full((3, 3), 47.0), rap_lon)
    assert excluded.selected_cells == 0
    assert not excluded.covers_full_box
    # Extrema alone appear to cover the rectangle, but the missing northeast
    # corner proves that this triangular footprint does not.
    _, triangular = coverage(numpy.array([[45.0, 45.0], [50.5, 50.5]]), numpy.array([[-58.0, -46.0], [-58.0, -58.0]]))
    assert triangular.native_east == -46.0 and triangular.native_north == 50.5
    assert not triangular.covers_full_box
    assert EVIDENCE_BOUNDS == {"south": 45.0, "west": -58.0, "north": 50.5, "east": -46.0}


def test_indexed_offline_replay_refuses_incomplete_retained_raw(tmp_path: Path) -> None:
    adapter = IndexedNativeCandidate("ecmwf-ifs-native")
    row = _ecmwf("2t")
    index = (json.dumps(row) + "\n").encode()
    (tmp_path / "ecmwf-ifs-native.grib2").write_bytes(b"GRIB7777")
    candidate = RunCandidate("2026090506", datetime(2026, 9, 5, 6, tzinfo=timezone.utc), ["data", "index"],
        {"index": index, "retained_raw": True})
    with pytest.raises(AdapterUnavailable, match="retained raw bundle size mismatch"):
        adapter.fetch(candidate, FetchWindow(datetime.now(timezone.utc), 0, 0), tmp_path)


def test_icon_offline_replay_requires_retained_coordinates(tmp_path: Path) -> None:
    adapter = DWDIconNativeCandidate()
    run = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    candidate = RunCandidate("2026090512", run, ["clat"], {"cycle": "12", "stamp": "2026090512", "retained_raw": True})
    with pytest.raises(AdapterUnavailable, match="retained ICON coordinate is absent"):
        adapter.fetch(candidate, FetchWindow(run, 0, 0), tmp_path)
