"""Window rules resolve from registered DE442 geometry, or not at all."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ingest.derive import registry as derive_registry
from weather_api.astronomy import ASTRONOMICAL_DEG, NAUTICAL_DEG, SUN_HORIZON_DEG
from weather_api.ephemeris import EPHEMERIS_SHA256
from weather_api.profiles.windows import (
    GeometrySample,
    WindowRule,
    resolve_window,
    validate_window_rule,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 3, 0, 0, tzinfo=UTC)


def rule(name: str, **params) -> WindowRule:
    return WindowRule(
        rule=name,
        geometry_entry="de442_sun_moon_geometry",
        geometry_fields=("sun_altitude",),
        params=params,
    )


def samples(altitudes, *, start: datetime = NOW, step_minutes: int = 60):
    return [
        GeometrySample(at=start + timedelta(minutes=step_minutes * i), sun_altitude=value)
        for i, value in enumerate(altitudes)
    ]


# --- the block a profile declares -------------------------------------------


def test_from_profile_reads_the_window_block_of_a_whole_profile():
    parsed = WindowRule.from_profile(
        {
            "id": "running",
            "window": {
                "rule": "any_window_within_24h",
                "geometry_entry": "de442_sun_moon_geometry",
                "geometry_fields": ["sun_altitude"],
                "params": {"length_hours": 1, "daylight_only": True},
            },
        }
    )
    assert parsed.rule == "any_window_within_24h"
    assert parsed.geometry_fields == ("sun_altitude",)
    assert parsed.params["daylight_only"] is True


def test_from_profile_also_reads_a_bare_window_block():
    parsed = WindowRule.from_profile(
        {
            "rule": "dark_hours",
            "geometry_entry": "de442_sun_moon_geometry",
            "geometry_fields": ["sun_altitude"],
            "params": {},
        }
    )
    assert parsed.rule == "dark_hours"


# --- validation -------------------------------------------------------------


def test_a_conforming_rule_validates_clean():
    assert validate_window_rule(rule("astronomical_night"), profile_id="astronomy") == []


def test_a_wall_clock_parameter_is_refused_naming_the_profile_and_the_rule():
    messages = validate_window_rule(
        WindowRule(
            rule="dark_hours",
            geometry_entry="de442_sun_moon_geometry",
            geometry_fields=("sun_altitude",),
            params={"start_hour": 22, "end_hour": 5},
        ),
        profile_id="aurora",
    )
    joined = " ".join(messages)
    assert any("wall-clock" in message for message in messages)
    assert "aurora" in joined and "dark_hours" in joined
    assert "start_hour" in joined and "end_hour" in joined


@pytest.mark.parametrize("key", ["local_time", "wall_clock", "hours"])
def test_every_clock_parameter_name_is_refused(key):
    messages = validate_window_rule(
        WindowRule(
            rule="astronomical_night",
            geometry_entry="de442_sun_moon_geometry",
            geometry_fields=("sun_altitude",),
            params={key: 3},
        ),
        profile_id="astronomy",
    )
    assert any(key in message and "wall-clock" in message for message in messages)


def test_another_solar_model_is_refused():
    messages = validate_window_rule(
        WindowRule(
            rule="dark_hours",
            geometry_entry="noaa_solar_calculator",
            geometry_fields=("sun_altitude",),
            params={},
        ),
        profile_id="aurora",
    )
    assert any("de442_sun_moon_geometry" in message for message in messages)
    assert any("noaa_solar_calculator" in message for message in messages)


def test_a_geometry_field_that_is_not_an_output_of_the_entry_is_refused():
    messages = validate_window_rule(
        WindowRule(
            rule="dark_hours",
            geometry_entry="de442_sun_moon_geometry",
            geometry_fields=("sun_altitude", "cloud_cover"),
            params={},
        ),
        profile_id="aurora",
    )
    assert len(messages) == 1
    assert "cloud_cover" in messages[0]
    # The message lists the outputs the entry does carry, so the reader can see
    # what the field should have been.
    assert "moon_illuminated_fraction" in messages[0]


def test_an_unknown_rule_is_refused():
    messages = validate_window_rule(
        WindowRule(
            rule="whenever_it_feels_right",
            geometry_entry="de442_sun_moon_geometry",
            geometry_fields=("sun_altitude",),
            params={},
        ),
        profile_id="running",
    )
    assert any("whenever_it_feels_right" in message for message in messages)


def test_a_missing_or_extra_parameter_is_refused():
    missing = validate_window_rule(rule("sunrise_sunset_margin"), profile_id="landscape")
    assert any("margin_minutes" in message and "requires" in message for message in missing)
    extra = validate_window_rule(
        rule("astronomical_night", length_hours=2), profile_id="astronomy"
    )
    assert any("takes no parameter" in message for message in extra)


# --- resolution -------------------------------------------------------------


def test_astronomical_night_is_the_run_below_minus_eighteen():
    resolution = resolve_window(
        rule("astronomical_night"),
        samples([-5.0, -19.0, -25.0, -19.5, -10.0]),
        now=NOW,
    )
    assert resolution.unresolved is None
    assert resolution.intervals == [
        (NOW + timedelta(hours=1), NOW + timedelta(hours=3)),
    ]
    assert ASTRONOMICAL_DEG == -18.0


def test_dark_hours_is_the_run_below_minus_twelve():
    resolution = resolve_window(
        rule("dark_hours"),
        samples([-5.0, -13.0, -14.0, -11.0, -20.0, -19.0]),
        now=NOW,
    )
    assert resolution.intervals == [
        (NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
        (NOW + timedelta(hours=4), NOW + timedelta(hours=5)),
    ]
    assert NAUTICAL_DEG == -12.0


def test_the_provenance_names_the_entry_its_version_and_the_kernel():
    resolution = resolve_window(rule("dark_hours"), samples([-20.0, -20.0]), now=NOW)
    entry = derive_registry.get(derive_registry.DE442_GEOMETRY)
    assert resolution.provenance == {
        "derivation": "de442_sun_moon_geometry",
        "derivation_version": entry.version,
        "kernel_sha256": EPHEMERIS_SHA256,
        "evidence_class": "derived_here",
    }


def test_any_window_within_24h_keeps_only_runs_long_enough():
    # Daylight from hour 2 to hour 4 (2 h) and hour 8 to hour 9 (1 h).
    altitudes = [-10.0, -5.0, 5.0, 10.0, 5.0, -5.0, -5.0, -5.0, 5.0, 4.0, -5.0]
    resolution = resolve_window(
        rule("any_window_within_24h", length_hours=2, daylight_only=True),
        samples(altitudes),
        now=NOW,
    )
    assert resolution.intervals == [(NOW + timedelta(hours=2), NOW + timedelta(hours=4))]
    assert SUN_HORIZON_DEG == -0.833


def test_any_window_within_24h_without_daylight_only_spans_the_whole_horizon():
    resolution = resolve_window(
        rule("any_window_within_24h", length_hours=1, daylight_only=False),
        samples([-20.0, -20.0, 10.0, 10.0]),
        now=NOW,
    )
    assert resolution.intervals == [(NOW, NOW + timedelta(hours=3))]


def test_any_window_within_24h_ignores_samples_beyond_the_horizon():
    ahead = samples([5.0] * 4, start=NOW + timedelta(hours=30))
    inside = samples([5.0, 5.0, 5.0])
    resolution = resolve_window(
        rule("any_window_within_24h", length_hours=1, daylight_only=True),
        inside + ahead,
        now=NOW,
    )
    assert resolution.intervals == [(NOW, NOW + timedelta(hours=2))]


def test_an_absent_altitude_beyond_the_horizon_does_not_unresolve_the_day():
    inside = samples([5.0, 5.0, 5.0])
    later = [GeometrySample(at=NOW + timedelta(hours=40), sun_altitude=None)]
    resolution = resolve_window(
        rule("any_window_within_24h", length_hours=1, daylight_only=True),
        inside + later,
        now=NOW,
    )
    assert resolution.unresolved is None


def test_sunrise_sunset_margin_brackets_each_horizon_crossing():
    # Rises between hour 1 and hour 2, sets between hour 3 and hour 4, with
    # the crossings placed halfway so the interpolation is exact.
    altitudes = [-10.0, -5.833, 4.167, 4.167, -5.833]
    resolution = resolve_window(
        rule("sunrise_sunset_margin", margin_minutes=30),
        samples(altitudes),
        now=NOW,
    )
    assert resolution.intervals == [
        (NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
        (NOW + timedelta(hours=3), NOW + timedelta(hours=4)),
    ]


def test_a_sample_sitting_exactly_on_the_horizon_is_one_crossing_not_two():
    altitudes = [-5.0, SUN_HORIZON_DEG, 5.0]
    resolution = resolve_window(
        rule("sunrise_sunset_margin", margin_minutes=15),
        samples(altitudes),
        now=NOW,
    )
    assert len(resolution.intervals) == 1


# --- absence ----------------------------------------------------------------


def test_an_absent_geometry_field_is_reported_by_name_with_no_window():
    resolution = resolve_window(
        rule("astronomical_night"),
        [
            GeometrySample(at=NOW, sun_altitude=-20.0),
            GeometrySample(at=NOW + timedelta(hours=1), sun_altitude=None),
        ],
        now=NOW,
    )
    assert resolution.unresolved == "sun_altitude"
    assert resolution.intervals == []
    assert resolution.provenance["derivation"] == "de442_sun_moon_geometry"


def test_no_samples_at_all_is_unresolved_rather_than_an_empty_window():
    resolution = resolve_window(rule("dark_hours"), [], now=NOW)
    assert resolution.unresolved == "sun_altitude"
    assert resolution.intervals == []


def test_geometry_present_and_offering_nothing_is_not_unresolved():
    resolution = resolve_window(rule("astronomical_night"), samples([5.0, 6.0]), now=NOW)
    assert resolution.unresolved is None
    assert resolution.intervals == []
    assert resolution.resolved is True


def test_a_reader_disabled_geometry_entry_is_reported_with_its_refusal_code():
    resolution = resolve_window(
        rule("astronomical_night"),
        samples([-20.0, -21.0]),
        now=NOW,
        reader_disabled=(derive_registry.DE442_GEOMETRY,),
    )
    assert resolution.unresolved == "geometry_entry_disabled:reader_disabled"
    assert resolution.intervals == []


def test_a_deployment_disabled_geometry_entry_is_reported_the_same_way(monkeypatch):
    monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, "0")
    resolution = resolve_window(
        rule("astronomical_night"), samples([-20.0, -21.0]), now=NOW
    )
    assert resolution.unresolved is not None
    assert resolution.unresolved.startswith("geometry_entry_disabled:")
    assert resolution.intervals == []


def test_the_resolution_serialises_with_its_provenance():
    resolution = resolve_window(rule("dark_hours"), samples([-20.0, -20.0]), now=NOW)
    payload = resolution.as_dict()
    assert payload["unresolved"] is None
    assert payload["intervals"] == [
        {"start": NOW.isoformat(), "end": (NOW + timedelta(hours=1)).isoformat()}
    ]
    assert payload["provenance"]["kernel_sha256"] == EPHEMERIS_SHA256
