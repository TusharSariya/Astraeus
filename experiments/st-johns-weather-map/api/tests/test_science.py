from datetime import datetime, timezone

import pytest

from weather_api.science import (
    ConsensusCandidate,
    build_consensus,
    fog_state,
    interpolate_wind,
    radar_echo_semantics,
    relative_humidity_from_dewpoint,
    resolve_relative_humidity,
    resolve_wind,
    select_fallback,
    precipitation_interval_hours,
    to_newfoundland,
    validate_distinct_environmental_quantity,
)


def test_humidity_preserves_direct_value_and_derives_only_when_absent():
    assert resolve_relative_humidity(73.0, 20.0, 10.0) == (73.0, None, None)
    value, derivation, version = resolve_relative_humidity(None, 20.0, 10.0)
    assert value == pytest.approx(52.5, abs=0.1)
    assert "liquid-water phase" in derivation
    assert version == "metpy-1.7.1-liquid-v1"
    assert resolve_relative_humidity(None, 20.0, None) == (None, None, None)


@pytest.mark.parametrize(("temperature", "dewpoint", "expected"), [(0, 0, 100), (-10, -15, 67), (30, 20, 55)])
def test_humidity_units_and_clamping(temperature, dewpoint, expected):
    assert relative_humidity_from_dewpoint(temperature, dewpoint) == pytest.approx(expected, abs=1)
    assert relative_humidity_from_dewpoint(0, 5) == 100


def test_fog_unknown_and_radar_no_echo_are_not_favourable_claims():
    assert fog_state(provider_diagnostic=None, visibility_m=None, fog_code=False) == "unknown"
    assert fog_state(provider_diagnostic=None, visibility_m=100, fog_code=False) == "unknown"
    assert fog_state(provider_diagnostic=True, visibility_m=None, fog_code=None) == "evidence_present"
    assert radar_echo_semantics(False) == "no_detected_precipitating_echo"
    assert radar_echo_semantics(None) == "unknown"


def test_consensus_requires_eccc_independent_centre_and_ensemble():
    base = [
        ConsensusCandidate("hrdps", "ECCC", "regional", 10, is_eccc_regional=True),
        ConsensusCandidate("gfs", "NOAA", "global", 14),
    ]
    assert not build_consensus(base).available
    result = build_consensus(base + [ConsensusCandidate("reps", "ECCC", "ensemble", 50, is_ensemble=True)])
    assert result.available
    assert result.value == 12
    assert result.centre_range == (10, 14)
    assert "reps" not in result.contributors


def test_related_models_from_same_family_do_not_double_vote():
    candidates = [
        ConsensusCandidate("hrdps", "ECCC", "regional", 10, is_eccc_regional=True),
        ConsensusCandidate("rdps", "ECCC", "regional", 30, is_eccc_regional=True),
        ConsensusCandidate("gfs", "NOAA", "global", 14),
        ConsensusCandidate("reps", "ECCC", "ensemble", 12, is_ensemble=True),
    ]
    result = build_consensus(candidates)
    assert result.value == 12
    assert result.contributors == ("hrdps", "gfs")


def test_same_centre_different_families_still_cast_one_vote():
    candidates = [
        ConsensusCandidate("hrdps", "ECCC", "regional", 10, is_eccc_regional=True),
        ConsensusCandidate("gdps", "ECCC", "global", 30),
        ConsensusCandidate("gfs", "NOAA", "global", 14),
        ConsensusCandidate("reps", "ECCC", "ensemble", 12, is_ensemble=True),
    ]
    assert build_consensus(candidates).value == 12


@pytest.mark.parametrize(
    ("consensus", "hrdps", "rdps", "badge"),
    [(True, True, True, "Experimental consensus"), (False, True, True, "HRDPS primary - consensus unavailable"), (False, False, True, "RDPS fallback"), (False, False, False, "forecast unavailable")],
)
def test_fallback_chain(consensus, hrdps, rdps, badge):
    assert select_fallback(consensus, hrdps_fresh=hrdps, rdps_fresh=rdps)[1] == badge


def test_wind_vector_interpolation_uses_components():
    assert interpolate_wind(0, 10, 10, 0, 0.5) == (5, 5)
    with pytest.raises(ValueError):
        interpolate_wind(0, 0, 1, 1, 1.1)


def test_wind_is_derived_from_components_in_the_meteorological_from_convention():
    """A northerly is a wind *from* the north: u=0, v<0 must read as 0/360 deg."""
    speed, direction, derivation, version = resolve_wind(0.0, -5.0)
    assert speed == 5.0
    assert direction in (0.0, 360.0)
    assert "MetPy" in derivation and "from" in derivation
    assert version == "metpy-1.7.1-wind-v1"

    _, easterly, _, _ = resolve_wind(-3.0, 0.0)
    assert easterly == 90.0
    _, southerly, _, _ = resolve_wind(0.0, 3.0)
    assert southerly == 180.0
    speed, _, _, _ = resolve_wind(3.0, 4.0)
    assert speed == 5.0


def test_newfoundland_dst_and_precipitation_interval_semantics():
    summer = to_newfoundland(datetime(2026, 8, 29, 15, tzinfo=timezone.utc))
    winter = to_newfoundland(datetime(2026, 1, 29, 15, tzinfo=timezone.utc))
    assert summer.utcoffset().total_seconds() == -(2.5 * 3600)
    assert winter.utcoffset().total_seconds() == -(3.5 * 3600)
    assert precipitation_interval_hours(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, 6, tzinfo=timezone.utc)) == 6
    with pytest.raises(ValueError):
        precipitation_interval_hours(datetime(2026, 1, 1, 6, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_air_quality_and_water_level_quantities_are_not_interchangeable():
    for quantity, unit in [("aqhi", "index"), ("pm2_5", "ug m-3"), ("aerosol_optical_depth", "1"), ("extinction", "m-1"), ("tide_prediction", "m"), ("observed_water_level", "m"), ("storm_surge", "m")]:
        validate_distinct_environmental_quantity(quantity, unit)
    with pytest.raises(ValueError):
        validate_distinct_environmental_quantity("aqhi", "ug m-3")
