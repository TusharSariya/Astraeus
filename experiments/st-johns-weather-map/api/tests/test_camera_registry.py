"""The camera registration record shape and its refusals.

Every record here is written under ``tmp_path``. The seventeen real camera
files are a separate task; these tests exercise the shape, not the inventory.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from registry import camera_audit
from registry.camera_audit import (
    Camera,
    CameraError,
    audit_camera,
    load_camera,
    load_cameras,
    retrieval_allowed,
)

COMPLETE: dict[str, Any] = {
    "id": "test-harbour-mouth",
    "name": "Test Harbour Mouth",
    "source_id": "ccg-harbour-cameras",
    "operator": "Canadian Coast Guard",
    "status": "licensed",
    "terms": {
        "text": "Licensed for automated retrieval and redistribution under the fixture licence.",
        "url": "https://example.invalid/terms",
        "read_date": "2026-09-02",
        "redistribution": False,
        "permission": {
            "requested_on": "2026-09-02",
            "requested_from": "Canadian Coast Guard",
            "granted_on": "2026-09-03",
            "document": "docs/permissions/fixture.pdf",
        },
    },
    "endpoint": {
        "url": "https://example.invalid/cam.jpg",
        "format": "jpeg",
        "cadence_seconds": 600,
        "cadence_measured_on": "2026-09-02",
    },
    "position": {
        "latitude": 47.564,
        "longitude": -52.684,
        "elevation": {"metres": 41.0, "datum": "CGVD2013"},
        "surveyed": True,
    },
    "orientation": {"bearing_deg": 95.0, "hfov_deg": 62.0, "vfov_deg": 35.0, "roll_deg": 0.0},
    "image": {"width_px": 1280, "height_px": 720},
    "landmarks": [
        {"name": "Chain Rock", "bearing_deg": 88.0, "distance_m": 410.0, "pixel": {"x": 512, "y": 380}},
        {"name": "Signal Hill", "bearing_deg": 104.0, "distance_m": 1900.0, "pixel": {"x": 880, "y": 300}},
    ],
    "privacy_masks": [{"name": "wharf apron", "polygon": [[0, 640], [320, 640], [320, 720], [0, 720]]}],
    "registered": {"date": "2026-09-03", "by": "change lead"},
    "geometry_validation": {
        "reprojection_tolerance_px": 8.0,
        "skyline_tolerance_deg": 0.5,
        "status": "passed",
        "dem": "cdem-nl-2015",
    },
}

PARTNERSHIP_TEXT = (
    "these cameras are intented for operational use for the CCG. The images are offered to "
    "the public as a courtesy and are for information only."
)


def _write(root: Path, record: dict[str, Any], stem: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stem = stem or record["id"]
    path = root / f"{stem}.yaml"
    path.write_text(yaml.safe_dump(record, sort_keys=True), encoding="utf-8")
    return path


def _complete(**overrides: Any) -> dict[str, Any]:
    record = copy.deepcopy(COMPLETE)
    record.update(overrides)
    return record


def _partnership_only() -> dict[str, Any]:
    record = _complete(id="ccg-fort-amherst", name="Fort Amherst", status="partnership-only")
    record["terms"]["text"] = PARTNERSHIP_TEXT
    record["terms"]["permission"] = {
        "requested_on": "2026-09-03",
        "requested_from": "Canadian Coast Guard",
        "granted_on": None,
        "document": None,
    }
    record["endpoint"] = {
        "url": "https://e-nav.ccg-gcc.gc.ca/nvss-svsn/sequences/FortAmherst.mp4",
        "format": "mp4_sequence",
        "cadence_seconds": 1200,
        "cadence_measured_on": "2026-09-02",
    }
    return record


def test_complete_record_audits_complete(tmp_path: Path) -> None:
    camera = load_camera(_write(tmp_path / "cameras", COMPLETE))
    verdict = audit_camera(camera)
    assert verdict.status == "complete"
    assert verdict.missing == []
    assert verdict.errors == []
    assert retrieval_allowed(camera) is None


def test_incomplete_record_names_every_missing_element(tmp_path: Path) -> None:
    record = _complete(id="ccg-st-johns-base", name="St. John's Base")
    record["orientation"] = {"bearing_deg": None, "hfov_deg": None, "vfov_deg": None, "roll_deg": None}
    record["image"] = {"width_px": None, "height_px": None}
    record["position"]["elevation"] = {"metres": None, "datum": None}
    record["position"]["surveyed"] = False
    record["landmarks"] = []
    record["privacy_masks"] = []
    record["registered"] = {"date": None, "by": None}
    record["geometry_validation"] = {
        "reprojection_tolerance_px": 8.0,
        "skyline_tolerance_deg": 0.5,
        "status": "not_run",
        "dem": None,
    }
    verdict = audit_camera(load_camera(_write(tmp_path / "cameras", record)))
    assert verdict.status == "incomplete"
    assert set(verdict.missing) == {
        "position.elevation.metres",
        "position.elevation.datum",
        "orientation.bearing_deg",
        "orientation.hfov_deg",
        "orientation.vfov_deg",
        "orientation.roll_deg",
        "image.width_px",
        "image.height_px",
        "landmarks",
        "privacy_masks",
        "registered.date",
        "registered.by",
        "geometry_validation.dem",
        "geometry_validation.status",
    }


def test_incomplete_record_with_one_landmark_names_landmarks(tmp_path: Path) -> None:
    record = _complete(id="ntv-downtown", name="Downtown")
    record["landmarks"] = [
        {"name": "Cabot Tower", "bearing_deg": 91.0, "distance_m": 2100.0, "pixel": {"x": None, "y": 240}},
    ]
    verdict = audit_camera(load_camera(_write(tmp_path / "cameras", record)))
    assert verdict.status == "incomplete"
    assert "landmarks" in verdict.missing
    assert "landmarks[0].pixel.x" in verdict.missing


def test_incomplete_record_is_refused_retrieval_naming_the_missing_elements(tmp_path: Path) -> None:
    record = _complete(id="ntv-george-street", name="George Street")
    record["orientation"]["hfov_deg"] = None
    camera = load_camera(_write(tmp_path / "cameras", record))
    refusal = retrieval_allowed(camera)
    assert refusal is not None
    assert refusal.code == "registration_incomplete"
    assert refusal.camera_id == "ntv-george-street"
    assert "orientation.hfov_deg" in refusal.detail


def test_incomplete_record_missing_a_required_key_is_an_error(tmp_path: Path) -> None:
    record = _complete(id="ntv-logy-bay-road", name="Logy Bay Road")
    del record["orientation"]
    with pytest.raises(CameraError) as raised:
        load_camera(_write(tmp_path / "cameras", record))
    assert "orientation" in raised.value.detail


def test_retrieval_allowed_refuses_a_partnership_only_camera(tmp_path: Path) -> None:
    camera = load_camera(_write(tmp_path / "cameras", _partnership_only()))
    refusal = retrieval_allowed(camera)
    assert refusal is not None
    assert refusal.code == "partnership_only"
    assert refusal.camera_id == "ccg-fort-amherst"
    assert "Fort Amherst" in refusal.detail
    assert PARTNERSHIP_TEXT in refusal.detail


def test_empty_registry_is_an_empty_mapping_with_a_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "cameras"
    empty.mkdir()
    assert load_cameras(empty) == {}
    assert camera_audit.main(["--all", "--root", str(empty)]) == 0
    assert camera_audit.EMPTY_NOTICE in capsys.readouterr().out


def test_missing_registry_directory_is_an_empty_mapping(tmp_path: Path) -> None:
    assert load_cameras(tmp_path / "nothing-here") == {}


def test_a_malformed_file_is_reported_without_stopping_the_others(tmp_path: Path) -> None:
    root = tmp_path / "cameras"
    _write(root, COMPLETE)
    _write(root, _partnership_only())
    (root / "ntv-broken.yaml").write_text("id: ntv-broken\n  bad: [indent\n", encoding="utf-8")
    (root / "ntv-mismatched.yaml").write_text(
        yaml.safe_dump(_complete(id="ntv-something-else"), sort_keys=True), encoding="utf-8"
    )

    loaded = load_cameras(root)
    assert set(loaded) == {"test-harbour-mouth", "ccg-fort-amherst", "ntv-broken", "ntv-mismatched"}
    assert isinstance(loaded["test-harbour-mouth"], Camera)
    assert isinstance(loaded["ccg-fort-amherst"], Camera)
    assert isinstance(loaded["ntv-broken"], CameraError)
    assert isinstance(loaded["ntv-mismatched"], CameraError)
    assert "file stem" in loaded["ntv-mismatched"].detail
    assert camera_audit.main(["--all", "--root", str(root)]) == 1


def test_redistribution_true_is_refused_by_the_schema(tmp_path: Path) -> None:
    record = _complete(id="ccg-sir-humphrey-gilbert", name="Sir Humphrey Gilbert Building")
    record["terms"]["redistribution"] = True
    with pytest.raises(CameraError) as raised:
        load_camera(_write(tmp_path / "cameras", record))
    assert "redistribution" in raised.value.detail


def test_an_unknown_key_is_refused_by_the_schema(tmp_path: Path) -> None:
    record = _complete(id="city-shea-heights", name="Shea Heights")
    record["black_ice"] = True
    with pytest.raises(CameraError) as raised:
        load_camera(_write(tmp_path / "cameras", record))
    assert "black_ice" in raised.value.detail


def test_the_real_registry_admits_no_camera() -> None:
    for entry in load_cameras().values():
        if isinstance(entry, CameraError):
            pytest.fail(str(entry))
        assert retrieval_allowed(entry) is not None
