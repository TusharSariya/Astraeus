"""The site registration record shape and its refusals.

Every record here is written under ``tmp_path``. The three real site files are
exercised only where a test says so; these tests are about the shape.

Task 3.3 adds the ``off_site`` and ``no_registered_horizon`` tests for the
serving side to this file. They belong under their own heading at the end.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from registry import site_audit
from registry.site_audit import (
    Site,
    SiteError,
    audit_site,
    load_site,
    load_sites,
    registry_notice,
)

#: A complete, servable record: 36 bearings at 10 degrees, no gap, and a
#: terrain check that was not run and says so.
COMPLETE: dict[str, Any] = {
    "id": "test-quidi-vidi",
    "name": "Test Quidi Vidi",
    "position": {"latitude": 47.5806, "longitude": -52.6867},
    "elevation": {"metres": 5.0, "datum": "CGVD2013"},
    "horizon": {
        "bearing_resolution_deg": 10,
        "elevation_deg": [
            8.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.5, 0.5, 1.5,
            3.0, 4.0, 4.5, 5.0, 7.0, 9.0, 11.0, 12.0, 11.0, 9.0, 7.0, 6.0,
            5.0, 4.5, 4.0, 4.0, 4.0, 4.0, 4.5, 5.0, 6.0, 7.0, 7.5, 8.0,
        ],
    },
    "terrain_check": {
        "status": "not_run",
        "dem": None,
        "tolerance_deg": 1.0,
        "terrain_elevation_deg": None,
        "note": (
            "No digital elevation model is available in the repository; the terrain check "
            "was not run and the terrain horizon is not assumed to agree."
        ),
    },
    "registered": {"date": "2026-09-03", "by": "Tushar Sariya"},
}


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


def test_complete_record_is_servable(tmp_path: Path) -> None:
    site = load_site(_write(tmp_path / "sites", COMPLETE))
    assert audit_site(site) == []
    assert site.site_id == "test-quidi-vidi"
    assert len(site.elevation_deg) == 36


def test_a_site_with_no_horizon_is_refused(tmp_path: Path) -> None:
    record = _complete(id="test-no-horizon")
    record["horizon"] = {"bearing_resolution_deg": 10, "elevation_deg": []}
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert len(errors) == 1
    assert errors[0].startswith("site_horizon_missing")
    assert "test-no-horizon" in errors[0]


def test_a_record_with_no_horizon_key_is_refused_by_the_schema(tmp_path: Path) -> None:
    record = _complete(id="test-no-horizon-key")
    del record["horizon"]
    with pytest.raises(SiteError) as raised:
        load_site(_write(tmp_path / "sites", record))
    assert "horizon" in raised.value.detail


def test_a_horizon_gap_names_every_missing_bearing(tmp_path: Path) -> None:
    record = _complete(id="test-horizon-gap")
    record["horizon"]["elevation_deg"][3] = None
    record["horizon"]["elevation_deg"][20] = None
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert len(errors) == 2
    assert errors[0].startswith("site_horizon_gap:30:")
    assert errors[1].startswith("site_horizon_gap:200:")


def test_a_short_horizon_is_a_horizon_gap_at_every_uncovered_bearing(tmp_path: Path) -> None:
    record = _complete(id="test-horizon-gap-short")
    record["horizon"]["elevation_deg"] = record["horizon"]["elevation_deg"][:34]
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert [error.split(":")[1] for error in errors] == ["340", "350"]
    assert all(error.startswith("site_horizon_gap:") for error in errors)


def test_a_long_horizon_is_a_horizon_gap_naming_the_count(tmp_path: Path) -> None:
    record = _complete(id="test-horizon-gap-long")
    record["horizon"]["elevation_deg"] = record["horizon"]["elevation_deg"] + [1.0, 1.0]
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert len(errors) == 1
    assert errors[0].startswith("site_horizon_gap:extra:")
    assert "38" in errors[0] and "36" in errors[0]


def test_a_registration_below_a_synthetic_terrain_horizon_is_refused(tmp_path: Path) -> None:
    """The below-terrain rule, exercised against a terrain horizon made here.

    No digital elevation model is checked into the repository, so the terrain
    horizon is synthetic: level everywhere except two bearings where it stands
    above what was registered. The terrain cannot be seen through.
    """

    record = _complete(id="test-below-terrain")
    terrain = [0.0] * 36
    terrain[9] = 6.0  # 90 degrees, registered at 0.5
    terrain[26] = 4.5  # 260 degrees, registered at 4.0, inside the tolerance
    terrain[18] = 13.5  # 180 degrees, registered at 11.0
    record["terrain_check"] = {
        "status": "failed",
        "dem": "synthetic-flat-terrain",
        "tolerance_deg": 1.0,
        "terrain_elevation_deg": terrain,
        "note": "A synthetic terrain horizon written by the tests, not a digital elevation model.",
    }
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert len(errors) == 2
    assert errors[0].startswith("below_terrain:90:0.5:6")
    assert errors[1].startswith("below_terrain:180:11:13.5")
    assert "1 degree tolerance" in errors[0]


def test_a_passed_terrain_check_with_a_below_terrain_bearing_is_an_error(tmp_path: Path) -> None:
    record = _complete(id="test-passed-but-below-terrain")
    terrain = [0.0] * 36
    terrain[9] = 6.0
    record["terrain_check"] = {
        "status": "passed",
        "dem": "synthetic-flat-terrain",
        "tolerance_deg": 1.0,
        "terrain_elevation_deg": terrain,
        "note": "A synthetic terrain horizon written by the tests, not a digital elevation model.",
    }
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert [error.split(":")[0] for error in errors] == ["below_terrain"]


def test_a_failed_terrain_check_must_name_a_below_terrain_bearing(tmp_path: Path) -> None:
    record = _complete(id="test-failed-but-agreeing")
    record["terrain_check"] = {
        "status": "failed",
        "dem": "synthetic-flat-terrain",
        "tolerance_deg": 1.0,
        "terrain_elevation_deg": [0.0] * 36,
        "note": "A synthetic terrain horizon written by the tests, not a digital elevation model.",
    }
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert len(errors) == 1
    assert errors[0].startswith("terrain_check_incomplete")


def test_a_terrain_check_that_claims_to_have_run_without_a_dem_is_incomplete(tmp_path: Path) -> None:
    record = _complete(id="test-terrain-check-incomplete")
    record["terrain_check"] = {
        "status": "passed",
        "dem": None,
        "tolerance_deg": 1.0,
        "terrain_elevation_deg": None,
        "note": "A check that claims to have run against nothing.",
    }
    errors = audit_site(load_site(_write(tmp_path / "sites", record)))
    assert len(errors) == 1
    assert errors[0].startswith("terrain_check_incomplete")
    assert "terrain_check.dem" in errors[0]
    assert "terrain_check.terrain_elevation_deg" in errors[0]


def test_a_not_run_terrain_check_is_accepted_with_its_disclosure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "sites"
    _write(root, COMPLETE)
    site = load_site(root / "test-quidi-vidi.yaml")
    assert site.record["terrain_check"]["status"] == "not_run"
    assert audit_site(site) == []
    assert site_audit.main(["--all", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "terrain check not_run" in out
    assert "the terrain horizon is not assumed to agree" in out


def test_an_empty_registry_is_an_empty_mapping_with_a_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "sites"
    empty.mkdir()
    assert load_sites(empty) == {}
    assert registry_notice(empty) == site_audit.EMPTY_NOTICE
    assert site_audit.main(["--all", "--root", str(empty)]) == 0
    assert site_audit.EMPTY_NOTICE in capsys.readouterr().out


def test_an_unreadable_registry_is_an_empty_mapping_with_a_notice(tmp_path: Path) -> None:
    missing = tmp_path / "nothing-here"
    assert load_sites(missing) == {}
    notice = registry_notice(missing)
    assert notice is not None
    assert str(missing) in notice


def test_a_malformed_file_is_reported_without_stopping_the_others(tmp_path: Path) -> None:
    root = tmp_path / "sites"
    _write(root, COMPLETE)
    _write(root, _complete(id="test-cape-spear", name="Test Cape Spear"))
    (root / "test-broken.yaml").write_text("id: test-broken\n  bad: [indent\n", encoding="utf-8")
    (root / "test-mismatched.yaml").write_text(
        yaml.safe_dump(_complete(id="test-something-else"), sort_keys=True), encoding="utf-8"
    )

    loaded = load_sites(root)
    assert set(loaded) == {"test-quidi-vidi", "test-cape-spear", "test-broken", "test-mismatched"}
    assert isinstance(loaded["test-quidi-vidi"], Site)
    assert isinstance(loaded["test-cape-spear"], Site)
    assert isinstance(loaded["test-broken"], SiteError)
    assert isinstance(loaded["test-mismatched"], SiteError)
    assert "file stem" in loaded["test-mismatched"].detail
    assert registry_notice(root) is None
    assert site_audit.main(["--all", "--root", str(root)]) == 1


def test_an_unknown_key_is_refused_by_the_schema(tmp_path: Path) -> None:
    record = _complete(id="test-unknown-key")
    record["nearest_camera"] = "ccg-fort-amherst"
    with pytest.raises(SiteError) as raised:
        load_site(_write(tmp_path / "sites", record))
    assert "nearest_camera" in raised.value.detail


def test_an_elevation_without_a_known_datum_is_refused_by_the_schema(tmp_path: Path) -> None:
    record = _complete(id="test-no-datum")
    record["elevation"] = {"metres": 5.0, "datum": "assumed sea level"}
    with pytest.raises(SiteError) as raised:
        load_site(_write(tmp_path / "sites", record))
    assert "datum" in raised.value.detail


def test_the_real_registry_holds_three_servable_sites() -> None:
    loaded = load_sites()
    assert set(loaded) == {"signal-hill", "cape-spear", "quidi-vidi"}
    for site_id, entry in sorted(loaded.items()):
        if isinstance(entry, SiteError):
            pytest.fail(str(entry))
        assert audit_site(entry) == [], site_id
        assert len(entry.elevation_deg) == 36
        assert entry.record["terrain_check"]["status"] == "not_run"
        assert entry.record["registered"] == {"date": "2026-09-03", "by": "Tushar Sariya"}


# --- serving off-site (task 3.3) ------------------------------------------
# Sites are preferred locations and never a limit on where evidence is
# served. These tests are about the serving side in ``weather_api.sites``:
# what is served at a point that is not a site, and what is refused.

SIGNAL_HILL = (47.5704, -52.6816)

#: About 300 m due north of Signal Hill: close enough that borrowing the
#: horizon would look reasonable, far enough that it would be wrong.
NEAR_SIGNAL_HILL = (47.5731, -52.6816)

WHEN = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def test_a_point_off_site_near_signal_hill_gets_no_registered_horizon() -> None:
    """300 m from Signal Hill is not Signal Hill, and no horizon is borrowed."""

    from weather_api import sites

    registry = sites.load_site_registry()
    signal_hill = registry.by_id()["signal-hill"]
    assert (signal_hill.latitude, signal_hill.longitude) == SIGNAL_HILL

    latitude, longitude = NEAR_SIGNAL_HILL
    # The point is served: it is inside the box and is refused nothing.
    assert sites.inside_evidence_box(latitude, longitude)
    assert sites.refuse_outside_box(latitude, longitude) is None
    # And it carries no site id, so it has no horizon of its own.
    assert sites.horizon_for(None, registry=registry) is None
    assert sites.horizon_for(None) is None

    for field in sorted(sites.HORIZON_DEPENDENT_FIELDS):
        emitted = sites.horizon_dependent_null(field, valid_time=WHEN, units="m")
        assert emitted.field == field
        assert emitted.value is None
        assert emitted.absence_state == "null"
        assert emitted.blocked is None
        assert sites.NO_REGISTERED_HORIZON in emitted.provenance.quality.flags
        # Nothing of Signal Hill's registration travels on the absent field.
        assert emitted.provenance.source_id != signal_hill.id
        assert "signal-hill" not in emitted.provenance.source_id


def test_no_registered_horizon_never_borrows_a_nearby_site() -> None:
    """There is no nearest-site lookup to borrow from, by construction."""

    from weather_api import sites

    registry = sites.load_site_registry()
    # Every name this module exposes, so a nearest-site helper cannot be
    # added later without this test noticing.
    exported = {name for name in dir(sites) if not name.startswith("_")}
    assert not {name for name in exported if "nearest" in name.lower()}
    assert sites.horizon_for("signal-hill-ish", registry=registry) is None
    assert sites.horizon_for("", registry=registry) is None
    # The registered id still answers, so the misses above are exact-match
    # misses rather than a registry that answers nothing.
    assert sites.horizon_for("signal-hill", registry=registry) is not None


def test_every_catalogue_field_is_served_at_an_arbitrary_off_site_point() -> None:
    """An in-box point that is no site is accepted for the whole catalogue."""

    from registry import fields as catalogue
    from weather_api import sites

    # A point in Placentia Bay: inside the box, nowhere near a registered site.
    latitude, longitude = 47.2400, -54.0000
    assert sites.inside_evidence_box(latitude, longitude)

    keys = list(catalogue.keys())
    assert keys, "the field catalogue is empty"
    for key in keys:
        # Acceptance is a property of the point, not of the field: no
        # catalogue key is served only at a site.
        assert sites.refuse_outside_box(latitude, longitude) is None, key
    # The only fields that need a horizon are the sector statistic and the
    # two camera visibility bounds, and none of them is a catalogue key.
    assert sites.HORIZON_DEPENDENT_FIELDS == frozenset(
        {"sector_statistic", "visibility_bound_lower_m", "visibility_bound_upper_m"}
    )
    assert not sites.HORIZON_DEPENDENT_FIELDS & set(keys)


def test_a_point_outside_the_box_is_refused_off_site_naming_the_box() -> None:
    from weather_api import sites

    south, north, west, east = sites.EVIDENCE_BOX
    assert (south, north, west, east) == (45.0, 50.5, -58.0, -46.0)
    # The edges are inside.
    for latitude, longitude in ((south, west), (north, east)):
        assert sites.inside_evidence_box(latitude, longitude)
        assert sites.refuse_outside_box(latitude, longitude) is None

    for latitude, longitude in ((north + 0.1, -52.7), (47.5, west - 0.1), (30.0, 0.0)):
        assert not sites.inside_evidence_box(latitude, longitude)
        refusal = sites.refuse_outside_box(latitude, longitude)
        assert refusal is not None
        assert refusal.startswith(sites.OUTSIDE_EVIDENCE_BOX)
        for bound in (south, north, west, east):
            assert f"{bound:g}" in refusal


def test_a_registered_site_answers_the_off_site_lookup_with_its_disclosure() -> None:
    """An exact id returns the horizon and the terrain check that was not run."""

    from weather_api import sites

    registry = sites.load_site_registry()
    assert registry.notice is None
    assert sorted(site.id for site in registry.sites) == ["cape-spear", "quidi-vidi", "signal-hill"]

    horizon = sites.horizon_for("signal-hill", registry=registry)
    assert horizon is not None
    assert horizon.site_id == "signal-hill"
    assert horizon.bearing_resolution_deg == 10
    assert len(horizon.elevation_deg) == 36
    assert horizon.terrain_check_status == "not_run"
    assert "not assumed to agree" in horizon.terrain_check_note

    summary = registry.by_id()["signal-hill"]
    assert summary.datum == "CGVD2013"
    assert summary.registered_on == "2026-09-03"
    assert summary.registered_by == "Tushar Sariya"


def test_an_unreadable_registry_serves_off_site_points_unchanged(tmp_path: Path) -> None:
    """No registry failure of any kind changes what is served at a point."""

    from weather_api import sites

    missing = tmp_path / "nothing-here"
    registry = sites.load_site_registry(missing)
    assert registry.sites == []
    assert registry.notice is not None
    assert str(missing) in registry.notice
    assert "unaffected" in registry.notice

    # Field service at an arbitrary point is untouched by the failure.
    latitude, longitude = NEAR_SIGNAL_HILL
    assert sites.inside_evidence_box(latitude, longitude)
    assert sites.refuse_outside_box(latitude, longitude) is None
    assert sites.horizon_for(None, registry=registry) is None
    assert sites.horizon_for("signal-hill", registry=registry) is None
    emitted = sites.horizon_dependent_null("sector_statistic", valid_time=WHEN, units="1")
    assert emitted.value is None
    assert emitted.absence_state == "null"
    assert sites.NO_REGISTERED_HORIZON in emitted.provenance.quality.flags


def test_a_broken_record_is_left_out_off_site_and_named_in_the_notice(tmp_path: Path) -> None:
    """One unservable record never takes the registry or field service with it."""

    from weather_api import sites

    root = tmp_path / "sites"
    _write(root, COMPLETE)
    gapped = _complete(id="test-gapped")
    gapped["horizon"]["elevation_deg"][3] = None
    _write(root, gapped)
    (root / "test-broken.yaml").write_text("id: test-broken\n  bad: [indent\n", encoding="utf-8")

    registry = sites.load_site_registry(root)
    assert [site.id for site in registry.sites] == ["test-quidi-vidi"]
    assert registry.notice is not None
    assert "test-gapped" in registry.notice
    assert "test-broken" in registry.notice
    assert "unaffected" in registry.notice
    assert sites.horizon_for("test-gapped", registry=registry) is None
    assert sites.horizon_for("test-quidi-vidi", registry=registry) is not None
    assert sites.refuse_outside_box(*NEAR_SIGNAL_HILL) is None
