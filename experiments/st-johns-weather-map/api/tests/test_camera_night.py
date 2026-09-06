"""Night frames refuse daytime derivations, and validation is a 30-day record.

Darkness is decided by the daylight boundary of the registered DE442 entry,
never by a clock and never by default: a frame whose sun altitude is unknown,
or whose DE442 entry is refused at the deployment level, carries
``darkness_unknown`` and refuses the same derivations a night frame does. The
one night path, the sky-dome method, is still disabled awaiting validation,
and what would lift that is a record spanning 30 days and all five
conditions with no METAR gap.

Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from ingest.cameras import night as night_module
from ingest.cameras.derive import AWAITING_VALIDATION, derive
from ingest.cameras.frames import HEALTH_FLAGS, Frame, Raster
from ingest.cameras.night import (
    DARKNESS,
    DARKNESS_UNKNOWN,
    DAYTIME_METHODS,
    SUN_HORIZON_DEG,
    darkness_flag,
    darkness_flag_for,
    flag_frame,
    refuse_daytime_derivation,
)
from ingest.cameras.validation_record import (
    INCOMPLETE_VALIDATION,
    METAR_STATION,
    MINIMUM_DAYS,
    REQUIRED_CONDITIONS,
    ValidationRecord,
    may_enable,
)
from ingest.derive.registry import (
    CAMERA_METHODS,
    CAMERA_SECTOR_CLOUD_FRACTION,
    CAMERA_SKYDOME_NIGHT_CLOUD,
    DE442_GEOMETRY,
    DERIVED_HERE_ENV,
)

UTC = timezone.utc


def _frame(flags: frozenset[str] = frozenset()) -> Frame:
    return Frame(
        camera_id="ntv-st-johns-sky",
        sha256="0" * 64,
        capture_time=datetime(2026, 9, 3, 3, 0, tzinfo=UTC),
        retrieval_time=datetime(2026, 9, 3, 3, 1, tzinfo=UTC),
        raster=Raster(width=2, height=2, pixels=bytes([10, 10, 10, 10])),
        flags=flags,
    )


def _complete_record(**overrides: object) -> ValidationRecord:
    fields: dict[str, object] = {
        "method": CAMERA_SECTOR_CLOUD_FRACTION,
        "start": date(2026, 1, 1),
        "end": date(2026, 1, 1) + timedelta(days=MINIMUM_DAYS - 1),
        "conditions": frozenset(REQUIRED_CONDITIONS),
        "metar_gaps": (),
        "comparisons": 240,
        "approved_by": "@TusharSariya",
    }
    fields.update(overrides)
    return ValidationRecord(**fields)  # type: ignore[arg-type]


# --- the boundary and the flags -------------------------------------------


def test_night_frame_boundary_is_the_registered_de442_horizon() -> None:
    """The mirrored constant is the DE442 daylight boundary, named as such."""
    assert SUN_HORIZON_DEG == -0.833
    assert DE442_GEOMETRY in (night_module.__doc__ or "")
    assert DARKNESS in HEALTH_FLAGS


def test_night_frame_below_the_horizon_is_flagged_darkness() -> None:
    assert darkness_flag(SUN_HORIZON_DEG - 5.0) == DARKNESS
    assert darkness_flag(SUN_HORIZON_DEG) == DARKNESS
    assert darkness_flag(-90.0) == DARKNESS


def test_daylight_frame_gets_no_flag() -> None:
    """A frame in daylight is the one case that carries no darkness flag."""
    assert darkness_flag(10.0) is None
    assert darkness_flag(SUN_HORIZON_DEG + 0.001) is None
    frame = _frame()
    assert flag_frame(frame, 30.0).flags == frame.flags


def test_night_frame_keeps_its_computed_health_flags_when_flagged() -> None:
    frame = _frame(flags=frozenset({"blur"}))
    flagged = flag_frame(frame, -12.0)
    assert flagged.flags == frozenset({"blur", DARKNESS})
    assert flagged.sha256 == frame.sha256
    assert frame.flags == frozenset({"blur"})


def test_darkness_unknown_when_the_sun_altitude_is_absent() -> None:
    """An absent altitude is never read as daylight."""
    assert darkness_flag(None) == DARKNESS_UNKNOWN
    assert flag_frame(_frame(), None).flags == frozenset({DARKNESS_UNKNOWN})


def test_darkness_unknown_when_the_de442_entry_is_disabled_at_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WEATHER_DERIVED_HERE=off refuses DE442, so darkness cannot be decided."""
    monkeypatch.setenv(DERIVED_HERE_ENV, "off")
    assert darkness_flag_for(30.0) == DARKNESS_UNKNOWN
    assert darkness_flag_for(-30.0) == DARKNESS_UNKNOWN
    assert flag_frame(_frame(), 30.0).flags == frozenset({DARKNESS_UNKNOWN})


def test_darkness_unknown_when_the_reader_switched_de442_off() -> None:
    assert darkness_flag_for(30.0, reader_disabled=(DE442_GEOMETRY,)) == DARKNESS_UNKNOWN
    assert darkness_flag_for(30.0) is None


# --- refusing daytime derivations -----------------------------------------


def test_night_frame_refuses_every_daytime_derivation() -> None:
    """Sector cloud fraction on a dark frame is null naming the flag."""
    for method in DAYTIME_METHODS:
        assert refuse_daytime_derivation(method, {DARKNESS}) == DARKNESS


def test_darkness_unknown_refuses_daytime_derivations_too() -> None:
    for method in DAYTIME_METHODS:
        assert refuse_daytime_derivation(method, {DARKNESS_UNKNOWN}) == DARKNESS_UNKNOWN


def test_daytime_methods_are_every_camera_method_but_the_night_one() -> None:
    assert DAYTIME_METHODS == frozenset(CAMERA_METHODS) - {CAMERA_SKYDOME_NIGHT_CLOUD}
    assert CAMERA_SECTOR_CLOUD_FRACTION in DAYTIME_METHODS


def test_night_frame_does_not_refuse_the_sky_dome_night_method() -> None:
    assert refuse_daytime_derivation(CAMERA_SKYDOME_NIGHT_CLOUD, {DARKNESS}) is None
    assert refuse_daytime_derivation(CAMERA_SECTOR_CLOUD_FRACTION, set()) is None


def test_the_sky_dome_night_method_is_refused_as_disabled() -> None:
    """The one night path is still awaiting its validation."""
    result = derive(CAMERA_SKYDOME_NIGHT_CLOUD, "ntv-st-johns-sky", "2026-09-03T03:00Z")
    assert result.value is None
    assert result.refusal == AWAITING_VALIDATION
    assert CAMERA_SKYDOME_NIGHT_CLOUD in result.detail


# --- the validation record ------------------------------------------------


def test_a_complete_record_may_enable() -> None:
    record = _complete_record()
    assert record.days == MINIMUM_DAYS
    assert may_enable(record) is None


def test_incomplete_validation_names_the_missing_conditions() -> None:
    """30 days of fog and rain with no snow and no night is refused."""
    refusal = may_enable(_complete_record(conditions=frozenset({"day", "fog", "rain"})))
    assert refusal is not None
    assert refusal.startswith(f"{INCOMPLETE_VALIDATION}:")
    assert "night" in refusal
    assert "snow" in refusal


def test_incomplete_validation_names_the_metar_gap() -> None:
    gap = (date(2026, 1, 10), date(2026, 1, 12))
    refusal = may_enable(_complete_record(metar_gaps=(gap,)))
    assert refusal is not None
    assert refusal.startswith(f"{INCOMPLETE_VALIDATION}:")
    assert METAR_STATION in refusal
    assert "2026-01-10" in refusal and "2026-01-12" in refusal


def test_incomplete_validation_names_the_day_shortfall() -> None:
    """Twenty-nine days is refused on its day count."""
    record = _complete_record(end=date(2026, 1, 1) + timedelta(days=MINIMUM_DAYS - 2))
    assert record.days == MINIMUM_DAYS - 1
    refusal = may_enable(record)
    assert refusal is not None
    assert refusal.startswith(f"{INCOMPLETE_VALIDATION}:")
    assert "29" in refusal and str(MINIMUM_DAYS) in refusal


def test_incomplete_validation_names_a_missing_approval_and_no_comparisons() -> None:
    refusal = may_enable(_complete_record(approved_by=None, comparisons=0))
    assert refusal is not None
    assert "approval" in refusal
    assert "comparison" in refusal


def test_incomplete_validation_refuses_a_method_that_is_not_a_camera_method() -> None:
    refusal = may_enable(_complete_record(method=DE442_GEOMETRY))
    assert refusal is not None
    assert refusal.startswith(f"{INCOMPLETE_VALIDATION}:")


def test_incomplete_validation_gate_flips_no_registry_entry() -> None:
    """may_enable reads a record; it enables nothing, and says so."""
    from ingest.derive import registry as derive_registry

    assert may_enable(_complete_record()) is None
    for method in CAMERA_METHODS:
        entry = derive_registry.get(method)
        assert entry is not None
        assert entry.enabled is False
