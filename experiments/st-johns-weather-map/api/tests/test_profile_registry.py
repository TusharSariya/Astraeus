"""The activity profile registry: the file shape and what validation refuses.

Every profile file here is written under ``tmp_path``. The four real profiles
are a separate task, and a test that read them would be testing that task's
content rather than this module's rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from registry import fields as catalogue
from registry import profile_audit


# A profile that passes everything, used as the base every refusal mutates one
# field of. Real catalogue keys, real catalogue units, real family names.
def valid_profile(profile_id: str = "running") -> dict:
    return {
        "id": profile_id,
        "version": 1,
        "title": "Running",
        "families": ["temperature", "wind", "lightning", "visibility"],
        "thresholds": {
            "hot": {"field": "temperature_2m", "default": 24.0, "units": "degC", "comparison": "ge"},
            "gust": {"field": "wind_gust_10m", "default": 15.0, "units": "m s-1", "comparison": "ge"},
            "lightning_in_range": {
                "field": "lightning_strike",
                "default": 0.1,
                "units": "flash km-2 min-1",
                "comparison": "ge",
            },
        },
        "weights": {"heat": 0.5, "wind": 0.5},
        "hard_stops": [
            {"name": "lightning", "field": "lightning_strike", "threshold": "lightning_in_range"}
        ],
        "graded_criteria": [
            {"name": "heat", "field": "temperature_2m", "threshold": "hot", "weight": "heat"},
            {"name": "gustiness", "field": "wind_gust_10m", "threshold": "gust", "weight": "wind"},
        ],
        "window": {
            "rule": "any_window_within_24h",
            "geometry_entry": "de442_sun_moon_geometry",
            "geometry_fields": ["sun_altitude"],
            "params": {"length_hours": 1.0, "daylight_only": True},
        },
        "site_needs": {
            "horizon_required": False,
            "sectors": [
                {
                    "name": "north_cloud",
                    "field": "cloud_high",
                    "bearing_deg": 0.0,
                    "width_deg": 90.0,
                    "max_range_km": 200.0,
                }
            ],
        },
        "blocked_fields": [
            {
                "field": "road_state",
                "reason": "licence",
                "source_id": "nl-511",
                "terms": "NL 511 publishes no reusable feed and its terms forbid redistribution",
                "request": None,
            }
        ],
        "wanted_not_catalogued": [
            {"field": "humidex", "note": "the owner's list names humidex; the catalogue has no key"}
        ],
    }


def write_profile(root: Path, data: dict, *, stem: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{stem or data['id']}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1.1 the file shape and its schema
# ---------------------------------------------------------------------------


def test_schema_is_draft_2020_12_and_closed() -> None:
    schema = json.loads(profile_audit.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "id",
        "version",
        "title",
        "families",
        "thresholds",
        "weights",
        "hard_stops",
        "graded_criteria",
        "window",
        "site_needs",
        "blocked_fields",
        "wanted_not_catalogued",
    }


def test_schema_accepts_a_complete_profile(tmp_path: Path) -> None:
    path = write_profile(tmp_path, valid_profile())
    profile = profile_audit.load_profile(path)
    assert profile.id == "running"
    assert profile.version == 1
    assert profile.path == path
    assert profile_audit.audit_profile(profile) == []


def test_schema_refuses_an_unknown_top_level_key(tmp_path: Path) -> None:
    data = valid_profile()
    data["skip_validation"] = True
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError) as excinfo:
        profile_audit.load_profile(path)
    assert "skip_validation" in str(excinfo.value)


def test_schema_refuses_an_id_that_is_not_the_file_stem(tmp_path: Path) -> None:
    path = write_profile(tmp_path, valid_profile(), stem="astronomy")
    with pytest.raises(profile_audit.ProfileError) as excinfo:
        profile_audit.load_profile(path)
    assert "astronomy" in str(excinfo.value)


def test_schema_requires_a_threshold_comparison_from_the_declared_set(tmp_path: Path) -> None:
    data = valid_profile()
    data["thresholds"]["hot"]["comparison"] = "approximately"
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError):
        profile_audit.load_profile(path)


def test_schema_refuses_a_weight_above_one(tmp_path: Path) -> None:
    data = valid_profile()
    data["weights"]["heat"] = 1.4
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError) as excinfo:
        profile_audit.load_profile(path)
    assert "weights" in str(excinfo.value)

    # And out of range is an audit error too, for a profile built in memory.
    errors = profile_audit.audit_profile(
        profile_audit.Profile(id="running", path=tmp_path / "running.yaml", data=data)
    )
    assert any("outside the declared range" in message for message in errors)


def test_schema_requires_the_registered_geometry_entry(tmp_path: Path) -> None:
    data = valid_profile()
    data["window"]["geometry_entry"] = "some_other_solar_model"
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError):
        profile_audit.load_profile(path)


# ---------------------------------------------------------------------------
# 1.2 what the audit refuses
# ---------------------------------------------------------------------------


def test_unknown_family_is_refused_naming_profile_family_and_file(tmp_path: Path) -> None:
    data = valid_profile()
    data["families"].append("vibes")
    path = write_profile(tmp_path, data)
    errors = profile_audit.audit_profile(profile_audit.load_profile(path))
    assert len(errors) == 1
    message = errors[0]
    assert message.startswith("running: vibes:")
    assert "unknown family" in message
    assert "running.yaml" in message


def test_unknown_family_stops_the_profile_being_reported_valid(tmp_path: Path, capsys) -> None:
    data = valid_profile()
    data["families"] = ["not_a_family"]
    write_profile(tmp_path, data)
    code = profile_audit.main(["--all", "--root", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 1
    assert "valid" not in out.out
    assert "not_a_family" in out.err


def test_unit_mismatch_names_the_field_the_declared_and_the_catalogue_units(tmp_path: Path) -> None:
    data = valid_profile()
    data["thresholds"]["gust"]["units"] = "km h-1"
    path = write_profile(tmp_path, data)
    errors = profile_audit.audit_profile(profile_audit.load_profile(path))
    assert len(errors) == 1
    message = errors[0]
    assert message.startswith("running: gust:")
    assert "wind_gust_10m" in message
    assert "km h-1" in message
    assert repr(catalogue.units_for("wind_gust_10m")) in message


def test_unit_mismatch_is_not_reported_for_a_matching_unit(tmp_path: Path) -> None:
    path = write_profile(tmp_path, valid_profile())
    assert profile_audit.audit_profile(profile_audit.load_profile(path)) == []


def test_no_default_threshold_is_refused_by_the_schema(tmp_path: Path) -> None:
    data = valid_profile()
    del data["thresholds"]["gust"]["default"]
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError) as excinfo:
        profile_audit.load_profile(path)
    assert "default" in str(excinfo.value)


def test_no_default_threshold_is_an_audit_error_naming_the_threshold(tmp_path: Path) -> None:
    data = valid_profile()
    del data["thresholds"]["gust"]["default"]
    errors = profile_audit.audit_profile(
        profile_audit.Profile(id="running", path=tmp_path / "running.yaml", data=data)
    )
    assert any(message.startswith("running: gust:") and "no default" in message for message in errors)


def test_both_lists_naming_one_field_is_refused(tmp_path: Path) -> None:
    data = valid_profile()
    data["graded_criteria"].append(
        {
            "name": "lightning_grade",
            "field": "lightning_strike",
            "threshold": "lightning_in_range",
            "weight": "wind",
        }
    )
    path = write_profile(tmp_path, data)
    errors = profile_audit.audit_profile(profile_audit.load_profile(path))
    assert len(errors) == 1
    message = errors[0]
    assert message.startswith("running: lightning_strike:")
    assert "hard stops" in message and "graded criteria" in message


def test_both_lists_is_not_reported_for_disjoint_fields(tmp_path: Path) -> None:
    path = write_profile(tmp_path, valid_profile())
    assert profile_audit.audit_profile(profile_audit.load_profile(path)) == []


def test_an_unknown_field_key_in_a_threshold_is_refused(tmp_path: Path) -> None:
    data = valid_profile()
    data["thresholds"]["hot"]["field"] = "temperature_2metres"
    path = write_profile(tmp_path, data)
    errors = profile_audit.audit_profile(profile_audit.load_profile(path))
    assert any("temperature_2metres" in message for message in errors)


# ---------------------------------------------------------------------------
# Fail closed, the window rule, blocked fields, and one bad file among many
# ---------------------------------------------------------------------------


def test_catalogue_unavailable_fails_closed(tmp_path: Path, monkeypatch) -> None:
    path = write_profile(tmp_path, valid_profile())
    profile = profile_audit.load_profile(path)

    def unavailable():
        raise profile_audit.CatalogueUnavailable("no module named registry.fields")

    monkeypatch.setattr(profile_audit, "load_catalogue", unavailable)
    errors = profile_audit.audit_profile(profile)
    assert errors
    assert all(message.startswith("running: ") for message in errors)
    assert any(profile_audit.CATALOGUE_UNAVAILABLE in message for message in errors)


def test_catalogue_unavailable_reports_no_profile_valid(tmp_path: Path, monkeypatch, capsys) -> None:
    write_profile(tmp_path, valid_profile())

    def unavailable():
        raise profile_audit.CatalogueUnavailable("simulated")

    monkeypatch.setattr(profile_audit, "load_catalogue", unavailable)
    code = profile_audit.main(["--all", "--root", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 1
    assert "valid" not in out.out
    assert profile_audit.CATALOGUE_UNAVAILABLE in out.err


def test_a_wall_clock_window_is_refused_naming_the_profile_and_the_rule(tmp_path: Path) -> None:
    data = valid_profile()
    data["window"]["params"]["local_time_start"] = "18:00"
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError) as excinfo:
        profile_audit.load_profile(path)
    message = str(excinfo.value)
    assert message.startswith("running:")
    assert "any_window_within_24h" in message
    assert "local_time_start" in message


def test_an_hour_range_window_parameter_is_refused(tmp_path: Path) -> None:
    data = valid_profile()
    data["window"]["params"]["start_hour"] = 18
    path = write_profile(tmp_path, data)
    with pytest.raises(profile_audit.ProfileError) as excinfo:
        profile_audit.load_profile(path)
    assert "start_hour" in str(excinfo.value)


def test_an_astronomical_window_rule_takes_no_parameters(tmp_path: Path) -> None:
    data = valid_profile("astronomy")
    data["window"] = {
        "rule": "astronomical_night",
        "geometry_entry": "de442_sun_moon_geometry",
        "geometry_fields": ["sun_altitude", "moon_altitude", "moon_illuminated_fraction"],
        "params": {},
    }
    path = write_profile(tmp_path, data)
    profile = profile_audit.load_profile(path)
    assert profile_audit.audit_profile(profile) == []


def test_a_blocked_field_the_catalogue_carries_is_refused(tmp_path: Path) -> None:
    assert catalogue.has_field("visibility")
    data = valid_profile()
    data["blocked_fields"][0]["field"] = "visibility"
    path = write_profile(tmp_path, data)
    errors = profile_audit.audit_profile(profile_audit.load_profile(path))
    assert len(errors) == 1
    message = errors[0]
    assert message.startswith("running: visibility:")
    assert "must be removed" in message


def test_a_blocked_field_the_catalogue_lacks_is_accepted(tmp_path: Path) -> None:
    assert not catalogue.has_field("road_state")
    path = write_profile(tmp_path, valid_profile())
    assert profile_audit.audit_profile(profile_audit.load_profile(path)) == []


def test_a_malformed_file_is_a_profile_error_and_the_others_still_load(tmp_path: Path) -> None:
    write_profile(tmp_path, valid_profile("running"))
    write_profile(tmp_path, valid_profile("astronomy"), stem="astronomy")
    (tmp_path / "aurora.yaml").write_text("id: aurora\n  version: [1\n", encoding="utf-8")

    loaded = profile_audit.load_profiles(tmp_path)
    assert set(loaded) == {"running", "astronomy", "aurora"}
    assert isinstance(loaded["aurora"], profile_audit.ProfileError)
    assert loaded["aurora"].profile == "aurora"
    assert isinstance(loaded["running"], profile_audit.Profile)
    assert isinstance(loaded["astronomy"], profile_audit.Profile)


def test_a_malformed_file_makes_only_its_own_profile_unavailable(tmp_path: Path, capsys) -> None:
    write_profile(tmp_path, valid_profile("running"))
    (tmp_path / "aurora.yaml").write_text(": : :\n", encoding="utf-8")
    code = profile_audit.main(["--all", "--root", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 1
    assert "aurora: unavailable" in out.out
    assert "running: valid" in out.out


def test_an_empty_registry_prints_a_notice_and_exits_zero(tmp_path: Path, capsys) -> None:
    code = profile_audit.main(["--all", "--root", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 0
    assert "empty" in out.out
    assert profile_audit.load_profiles(tmp_path) == {}


def test_strict_fails_on_a_warning(tmp_path: Path, capsys) -> None:
    data = valid_profile()
    data["thresholds"]["unused"] = {
        "field": "visibility",
        "default": 1000.0,
        "units": "m",
        "comparison": "le",
    }
    write_profile(tmp_path, data)
    assert profile_audit.main(["--all", "--root", str(tmp_path)]) == 0
    assert profile_audit.main(["--all", "--root", str(tmp_path), "--strict"]) == 1
    assert "unused" in capsys.readouterr().err


def test_the_real_profiles_root_is_audited_by_the_script_entry_point(capsys) -> None:
    # Task 1.3 adds the four real files. Whatever is there now must audit
    # cleanly, including the case where nothing is there yet.
    assert profile_audit.main(["--all"]) == 0
    assert capsys.readouterr().out
