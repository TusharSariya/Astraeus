"""A score says what thresholds it was produced under, including "none moved"."""

from __future__ import annotations

import pytest

from weather_api.profiles.overrides import (
    OverrideProvenance,
    ThresholdOverride,
    record_overrides,
)

PROFILE = {
    "id": "running",
    "version": 3,
    "thresholds": {
        "wind_gust": {
            "field": "wind_gust",
            "default": 40.0,
            "units": "km h-1",
            "comparison": "le",
        },
        "temperature": {
            "field": "air_temperature",
            "default": 22.0,
            "units": "degC",
            "comparison": "le",
        },
    },
}


def test_an_override_is_recorded_with_the_default_it_moved_away_from():
    record = record_overrides(PROFILE, {"wind_gust": 55.0})
    assert record.no_override_in_force is False
    assert record.overrides == [
        ThresholdOverride(threshold="wind_gust", profile_default=40.0, value=55.0)
    ]
    assert record.profile_id == "running"
    assert record.profile_version == 3


def test_no_override_is_recorded_explicitly_rather_than_omitted():
    record = record_overrides(PROFILE, {})
    assert isinstance(record, OverrideProvenance)
    assert record.overrides == []
    assert record.no_override_in_force is True
    assert record.as_dict()["no_override_in_force"] is True


def test_an_override_equal_to_the_default_is_still_an_override_in_force():
    record = record_overrides(PROFILE, {"wind_gust": 40.0})
    assert record.no_override_in_force is False
    assert len(record.overrides) == 1
    assert record.overrides[0].changes_the_default is False


def test_every_override_is_recorded_in_a_stable_order():
    record = record_overrides(PROFILE, {"temperature": 18.0, "wind_gust": 55.0})
    assert [item.threshold for item in record.overrides] == ["temperature", "wind_gust"]


def test_an_unknown_threshold_name_raises_naming_it():
    with pytest.raises(ValueError) as excinfo:
        record_overrides(PROFILE, {"windgust": 55.0})
    message = str(excinfo.value)
    assert "windgust" in message
    assert "running" in message


def test_a_threshold_with_no_declared_default_raises_naming_it():
    profile = {
        "id": "astronomy",
        "version": 1,
        "thresholds": {"cloud_cover": {"field": "cloud_cover", "units": "percent"}},
    }
    with pytest.raises(ValueError) as excinfo:
        record_overrides(profile, {"cloud_cover": 10.0})
    assert "cloud_cover" in str(excinfo.value)
    assert "default" in str(excinfo.value)


def test_the_record_serialises_with_both_numbers_for_every_override():
    payload = record_overrides(PROFILE, {"wind_gust": 55.0}).as_dict()
    assert payload == {
        "profile_id": "running",
        "profile_version": 3,
        "overrides": [
            {"threshold": "wind_gust", "profile_default": 40.0, "value": 55.0}
        ],
        "no_override_in_force": False,
    }


def test_a_profile_with_no_thresholds_still_yields_a_record():
    record = record_overrides({"id": "empty", "version": 1, "thresholds": {}}, {})
    assert record.no_override_in_force is True
    assert record.overrides == []
