"""The derivation method registry: shape, refusals and the three switches.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/derivation-method-registry/spec.md
Spec-Refs: openspec/changes/ensemble-families-and-member-statistics/specs/derivation-method-registry/spec.md
Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/camera-evidence/spec.md
Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/site-registry/spec.md
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Sequence

import pytest

from ingest.derive import registry as derive_registry
from ingest.cameras.derive import (
    AWAITING_VALIDATION,
    NUMERIC_VISIBILITY_REFUSED,
    RefusedClaim,
    derive as derive_from_camera,
    request_numeric_visibility,
)
from ingest.derive.registry import (
    CAMERA_ENABLED_WITHOUT_VALIDATION,
    CAMERA_FOG_VISIBILITY_CLASS,
    CAMERA_HORIZON_FOG_BANK,
    CAMERA_METHODS,
    CAMERA_SECTOR_CLOUD_FRACTION,
    CAMERA_SKYDOME_NIGHT_CLOUD,
    CAMERA_VISIBILITY_BOUND,
    DE442_GEOMETRY,
    ENSEMBLE_ENTRY_BY_STATISTIC,
    ENSEMBLE_MEAN,
    ENSEMBLE_MEMBER_COUNT,
    ENSEMBLE_QUANTILE,
    ENSEMBLE_SPREAD,
    ENSEMBLE_STATISTIC_ENTRIES,
    ENSEMBLE_STATISTICS,
    ENSEMBLE_THRESHOLD_PROBABILITY,
    ENTRIES,
    FOG_STATE,
    RELATIVE_HUMIDITY,
    SECTOR_SAMPLING,
    WIND_SPEED_AND_DIRECTION,
    Approval,
    DerivationMethod,
    DerivationRegistry,
    Input,
    MemberSet,
    MemberValue,
    Output,
    RegistryError,
    UnregisteredMethod,
    derive_ensemble_statistic,
    validation_errors,
)
from ingest.derive.sector import (
    MINIMUM_COVERED_FRACTION,
    REDUCTION,
    SectorInput,
    SectorParameters,
    sample_sector,
)

APPROVAL = Approval(approver="@TusharSariya", decided_on="2026-09-02", record="ADR 0001", note="test entry")

RUN = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
LATER_RUN = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)


def _members(*values: float | None, control_first: bool = False) -> tuple[MemberValue, ...]:
    return tuple(
        MemberValue(
            member=f"m{index:02d}",
            control=control_first and index == 0,
            value=value,
            quality_status="passed",
        )
        for index, value in enumerate(values)
    )


def _member_set(*values: float | None, **overrides) -> MemberSet:
    base = MemberSet(
        family="eccc-reps",
        source_id="eccc-geomet-reps",
        run_time=RUN,
        field="air_temperature",
        declared=len(values),
        members=_members(*values),
    )
    return dataclasses.replace(base, **overrides)


def _entry(**overrides) -> DerivationMethod:
    base = DerivationMethod(
        name="test_entry",
        version="v1",
        citation="A published construction",
        inputs=(Input(field="air_temperature", family="air_temperature"),),
        outputs=(Output(field="relative_humidity", units="percent", minimum=0.0, maximum=100.0, range_rule="clamp"),),
        approval=APPROVAL,
    )
    return dataclasses.replace(base, **overrides)


# --- Requirement: every derived-here value names an enabled registry entry ---


def test_every_entry_carries_the_declared_shape() -> None:
    for entry in ENTRIES:
        assert entry.name and entry.version and entry.citation
        assert entry.inputs, f"{entry.name} declares no inputs"
        assert entry.outputs, f"{entry.name} declares no output"
        assert isinstance(entry.enabled, bool)
        assert entry.approval.approver and entry.approval.decided_on and entry.approval.record
        for output in entry.outputs:
            assert output.range_rule in {"clamp", "wrap", "null", "inherit_input_range"}
            if output.range_rule != "inherit_input_range":
                assert output.minimum is not None and output.maximum is not None


def test_the_first_entries_are_registered() -> None:
    """The derivations this deployment already serves or has specified. Fog
    state joined them once ``/point`` began gating it on the registry: it was
    already served, and an unregistered served derivation is the gap this
    registry exists to close."""
    assert [entry.name for entry in ENTRIES] == [
        RELATIVE_HUMIDITY,
        WIND_SPEED_AND_DIRECTION,
        FOG_STATE,
        ENSEMBLE_STATISTICS,
        *ENSEMBLE_STATISTIC_ENTRIES,
        SECTOR_SAMPLING,
        DE442_GEOMETRY,
        *CAMERA_METHODS,
    ]


def test_an_unregistered_method_is_refused_and_nothing_is_served() -> None:
    with pytest.raises(UnregisteredMethod) as excinfo:
        derive_registry.require("humidity_by_vibes")
    assert excinfo.value.code == "unregistered_method"
    assert derive_registry.get("humidity_by_vibes") is None
    assert derive_registry.resolve("humidity_by_vibes").code == "unregistered_method"


def test_a_registered_entry_carries_its_provenance() -> None:
    record = derive_registry.provenance(RELATIVE_HUMIDITY)
    assert record["evidence_class"] == "derived_here"
    assert record["derivation"] == RELATIVE_HUMIDITY
    assert record["derivation_version"] == "metpy-1.7.1-liquid-v1"
    assert "Bolton" in record["derivation_citation"]
    assert [item["field"] for item in record["derivation_inputs"]] == ["air_temperature", "dew_point"]


# --- Requirement: registration is owner-approved and refuses blending ---


def test_an_entry_without_approval_refuses_to_load() -> None:
    unapproved = _entry(approval=Approval(approver="", decided_on="", record="", note=""))
    with pytest.raises(RegistryError) as excinfo:
        DerivationRegistry((unapproved,))
    assert any("no approval record" in error for error in excinfo.value.errors)


def test_a_blending_entry_is_refused_naming_the_rule() -> None:
    blending = _entry(
        inputs=(
            Input(field="total_cloud_opacity_weighted", family="cloud_cover", source="eccc-hrdps"),
            Input(field="total_cloud_geometric", family="cloud_cover", source="noaa-gfs"),
        ),
        outputs=(Output(field="total_cloud", units="percent", minimum=0.0, maximum=100.0, range_rule="clamp"),),
    )
    with pytest.raises(RegistryError) as excinfo:
        DerivationRegistry((blending,))
    assert any("blending refused" in error and "cloud_cover" in error for error in excinfo.value.errors)


def test_the_same_field_from_two_sources_is_blending() -> None:
    blending = _entry(
        inputs=(
            Input(field="air_temperature", family="air_temperature", source="eccc-hrdps"),
            Input(field="air_temperature", family="air_temperature", source="noaa-gfs"),
        ),
    )
    with pytest.raises(RegistryError) as excinfo:
        DerivationRegistry((blending,))
    assert any("more than one source" in error for error in excinfo.value.errors)


def test_a_provider_reduction_with_another_member_set_is_blending() -> None:
    blending = _entry(
        inputs=(
            Input(field="geps_mean", family="ensemble_reduction", source="eccc-geps", kind="provider_reduction"),
            Input(field="gefs_member", family="ensemble_member_field", source="noaa-gefs", kind="member_statistic"),
        ),
    )
    with pytest.raises(RegistryError) as excinfo:
        DerivationRegistry((blending,))
    assert any("another member set" in error for error in excinfo.value.errors)


def test_different_fields_from_different_sources_are_derivation_not_blending() -> None:
    air_sea = _entry(
        inputs=(
            Input(field="sea_surface_temperature", family="sea_surface_temperature", source="eccc-ciops-east"),
            Input(field="dew_point", family="humidity_dew_point", source="eccc-hrdps"),
        ),
        outputs=(
            Output(field="air_sea_temperature_difference", units="K", minimum=-40.0, maximum=40.0, range_rule="clamp"),
        ),
    )
    assert DerivationRegistry((air_sea,)).get("test_entry") is not None


# --- Requirement: a method can be disabled at three levels ---


def test_disabled_entry_produces_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The registered-and-disabled example has moved twice. It was
    `ensemble_statistics_within_run` until that change enabled it as the
    umbrella every member statistic goes through, then sector sampling until
    `activity-profiles-sites-and-cameras` gave it a sampler; the camera
    entries carry the case now, and unlike the other two they stay disabled
    until a validation record exists."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    refusal = derive_registry.resolve(CAMERA_FOG_VISIBILITY_CLASS)
    assert refusal is not None and refusal.code == "method_disabled"
    assert derive_registry.get(CAMERA_FOG_VISIBILITY_CLASS).enabled is False
    assert derive_registry.get(ENSEMBLE_STATISTICS).enabled is True
    assert derive_registry.resolve(ENSEMBLE_STATISTICS) is None


def test_deployment_disabled_refuses_every_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, "off")
    assert derive_registry.derivations_enabled() is False
    refusal = derive_registry.resolve(RELATIVE_HUMIDITY)
    assert refusal is not None
    assert refusal.code == "deployment_refused"
    assert derive_registry.DERIVED_HERE_ENV in refusal.detail
    derived = derive_registry.derive_relative_humidity(20.0, 10.0)
    assert derived.value is None
    assert derived.refusal is not None and derived.refusal.code == "deployment_refused"
    assert derive_registry.resolve_registered_relative_humidity(None, 20.0, 10.0) == (None, None, None)
    # A retrieved value is unaffected: a published relative humidity is served
    # unchanged whatever the switch says.
    assert derive_registry.resolve_registered_relative_humidity(73.0, 20.0, 10.0) == (73.0, None, None)


def test_deployment_disabled_reads_the_variable_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("off", "0", "false", "NO", " Off "):
        monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, value)
        assert derive_registry.derivations_enabled() is False
    for value in ("", "on", "1"):
        monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, value)
        assert derive_registry.derivations_enabled() is True


def test_reader_disabled_affects_only_that_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    refusal = derive_registry.resolve(RELATIVE_HUMIDITY, reader_disabled=[RELATIVE_HUMIDITY])
    assert refusal is not None and refusal.code == "reader_disabled"
    assert derive_registry.resolve(RELATIVE_HUMIDITY) is None
    switched_off = derive_registry.derive_relative_humidity(20.0, 10.0, reader_disabled=[RELATIVE_HUMIDITY])
    assert switched_off.value is None
    assert derive_registry.derive_relative_humidity(20.0, 10.0).value is not None


def test_the_catalogue_is_the_reader_switch_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    rows = {row["name"]: row for row in derive_registry.catalogue(reader_disabled=[WIND_SPEED_AND_DIRECTION])}
    assert set(rows) == {entry.name for entry in ENTRIES}
    humidity = rows[RELATIVE_HUMIDITY]
    assert humidity["available"] is True
    assert humidity["refusal"] is None
    assert humidity["reader_switchable"] is True and humidity["reader_default_on"] is True
    assert rows[WIND_SPEED_AND_DIRECTION]["refusal"]["code"] == "reader_disabled"
    assert rows[CAMERA_FOG_VISIBILITY_CLASS]["refusal"]["code"] == "method_disabled"
    assert rows[SECTOR_SAMPLING]["available"] is True
    assert rows[ENSEMBLE_STATISTICS]["available"] is True


# --- Physical range and the wiring the API calls ---


def test_a_result_outside_the_range_is_bounded_and_flagged() -> None:
    assert derive_registry.bound(RELATIVE_HUMIDITY, "relative_humidity", 50.0) == (50.0, ())
    assert derive_registry.bound(RELATIVE_HUMIDITY, "relative_humidity", 104.0) == (100.0, ("range_clamped",))
    assert derive_registry.bound(WIND_SPEED_AND_DIRECTION, "wind_direction", 370.0) == (10.0, ("range_wrapped",))
    assert derive_registry.bound(ENSEMBLE_STATISTICS, "ensemble_statistic", 9e9) == (9e9, ())
    assert derive_registry.bound(ENSEMBLE_MEAN, "ensemble_mean", 9e9) == (9e9, ())
    assert derive_registry.bound(ENSEMBLE_THRESHOLD_PROBABILITY, "ensemble_threshold_probability", 1.4) == (
        1.0,
        ("range_clamped",),
    )


def test_relative_humidity_is_served_through_its_registry_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    value, derivation, version = derive_registry.resolve_registered_relative_humidity(None, 20.0, 10.0)
    assert derivation == RELATIVE_HUMIDITY
    assert version == "metpy-1.7.1-liquid-v1"
    assert value is not None and 50.0 < value < 55.0
    # The same number the bare construction gives: the registry gates it, it
    # does not change it.
    from ingest.meteorology import relative_humidity_from_dewpoint

    assert value == relative_humidity_from_dewpoint(20.0, 10.0)
    assert derive_registry.provenance(derivation)["evidence_class"] == "derived_here"


def test_a_published_relative_humidity_is_never_replaced() -> None:
    assert derive_registry.resolve_registered_relative_humidity(73.0, 20.0, 10.0) == (73.0, None, None)


def test_wind_is_served_through_its_registry_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    speed, direction, derivation, version = derive_registry.resolve_registered_wind(3.0, 4.0)
    assert (speed, derivation, version) == (5.0, WIND_SPEED_AND_DIRECTION, "metpy-1.7.1-wind-v1")
    assert 0.0 <= direction <= 360.0
    assert derive_registry.resolve_registered_wind(3.0, None) == (None, None, None, None)


# --- Requirement: the five ensemble statistics are registered entries -------


@pytest.fixture(autouse=False)
def _derivations_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)


def test_the_five_ensemble_statistics_are_registered_entries() -> None:
    assert ENSEMBLE_STATISTIC_ENTRIES == (
        ENSEMBLE_MEAN,
        ENSEMBLE_SPREAD,
        ENSEMBLE_QUANTILE,
        ENSEMBLE_THRESHOLD_PROBABILITY,
        ENSEMBLE_MEMBER_COUNT,
    )
    assert ENSEMBLE_ENTRY_BY_STATISTIC == {
        "mean": ENSEMBLE_MEAN,
        "spread": ENSEMBLE_SPREAD,
        "quantile": ENSEMBLE_QUANTILE,
        "threshold_probability": ENSEMBLE_THRESHOLD_PROBABILITY,
        "member_count": ENSEMBLE_MEMBER_COUNT,
    }
    for name in ENSEMBLE_STATISTIC_ENTRIES:
        entry = derive_registry.require(name)
        assert entry.version == "within-run-v1"
        assert entry.enabled is True
        assert "Wilks (2019)" in entry.citation and "chapter 8" in entry.citation
        assert entry.conventions, f"{name} declares no convention"
        assert entry.include_control is True
        # Owner gate 6.4: no minimum is declared, so none is invented.
        assert entry.minimum_members is None
        assert [item.as_dict() for item in entry.inputs] == [
            {
                "field": "ensemble_member_field",
                "family": "ensemble_member_field",
                "source": derive_registry.SAME_SOURCE,
                "kind": "member_statistic",
            }
        ]


def test_the_ensemble_umbrella_entry_is_enabled_and_is_not_replaced() -> None:
    umbrella = derive_registry.require(ENSEMBLE_STATISTICS)
    assert umbrella.enabled is True
    assert umbrella.name not in ENSEMBLE_STATISTIC_ENTRIES


def test_an_ensemble_mean_names_its_own_entry_and_member_set(_derivations_on: None) -> None:
    result = derive_ensemble_statistic("mean", [_member_set(1.0, 2.0, 3.0)])
    assert result.value == 2.0
    assert result.method is not None and result.method.name == ENSEMBLE_MEAN
    record = derive_registry.provenance(result.method.name)
    assert record["derivation"] == ENSEMBLE_MEAN
    assert record["derivation_version"] == "within-run-v1"
    assert result.member_set is not None and result.member_set.family == "eccc-reps"
    assert (result.members_used, result.members_declared) == (3, 3)
    assert result.flags == ("derived",)
    assert result.partial is False


def test_an_ensemble_statistic_reports_control_treatment(_derivations_on: None) -> None:
    with_control = _member_set(1.0, 2.0, 3.0)
    with_control = dataclasses.replace(
        with_control, members=_members(1.0, 2.0, 3.0, control_first=True)
    )
    assert derive_ensemble_statistic("mean", [with_control]).control_included is True
    # A set with no control member declares nothing about one.
    assert derive_ensemble_statistic("mean", [_member_set(1.0, 2.0)]).control_included is None


def test_an_unregistered_ensemble_statistic_is_refused(_derivations_on: None) -> None:
    result = derive_ensemble_statistic("median", [_member_set(1.0, 2.0, 3.0)])
    assert result.value is None
    assert result.refusal is not None and result.refusal.code == "unregistered_method"


def test_the_ensemble_spread_and_quantile_follow_their_declared_conventions(_derivations_on: None) -> None:
    # Sample standard deviation, n-1 denominator.
    spread = derive_ensemble_statistic("spread", [_member_set(2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0)])
    assert spread.value == pytest.approx(2.13808993)
    assert derive_ensemble_statistic("spread", [_member_set(3.0, 3.0, 3.0)]).value == 0.0
    # Hyndman and Fan type 7, the numpy default: 0.5 * (n-1) = 1.5 on four
    # members interpolates halfway between the second and third.
    quantile = derive_ensemble_statistic("quantile", [_member_set(1.0, 2.0, 3.0, 4.0)], quantile=0.5)
    assert quantile.value == pytest.approx(2.5)
    assert quantile.quantile == 0.5
    assert derive_ensemble_statistic(
        "quantile", [_member_set(0.0, 10.0, 20.0)], quantile=0.9
    ).value == pytest.approx(18.0)


def test_an_ensemble_threshold_probability_carries_threshold_unit_and_sense(_derivations_on: None) -> None:
    result = derive_ensemble_statistic(
        "threshold_probability",
        [_member_set(1.0, 5.0, 9.0, 11.0)],
        threshold=5.0,
        threshold_units="mm",
        comparison="ge",
    )
    assert result.value == pytest.approx(0.75)
    assert (result.threshold, result.threshold_units, result.comparison) == (5.0, "mm", "ge")
    strictly = derive_ensemble_statistic(
        "threshold_probability", [_member_set(1.0, 5.0, 9.0, 11.0)],
        threshold=5.0, threshold_units="mm", comparison="gt",
    )
    assert strictly.value == pytest.approx(0.5)
    with pytest.raises(ValueError):
        derive_ensemble_statistic("threshold_probability", [_member_set(1.0)], threshold=5.0)


def test_an_ensemble_member_count_reports_used_and_declared(_derivations_on: None) -> None:
    partial = _member_set(1.0, 2.0, None, None, declared=6)
    result = derive_ensemble_statistic("member_count", [partial])
    assert result.value == 2.0
    assert (result.members_used, result.members_declared) == (2, 6)
    assert result.members_missing == ("m02", "m03")


def test_the_ensemble_umbrella_switch_nulls_every_statistic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    for statistic in ENSEMBLE_ENTRY_BY_STATISTIC:
        result = derive_ensemble_statistic(
            statistic, [_member_set(1.0, 2.0, 3.0)], quantile=0.5,
            threshold=1.0, threshold_units="K", comparison="ge",
            reader_disabled=[ENSEMBLE_STATISTICS],
        )
        assert result.value is None
        assert result.refusal is not None and result.refusal.code == "reader_disabled"
        assert result.refusal.method == ENSEMBLE_STATISTICS
    # The deployment switch names its own level.
    monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, "off")
    refused = derive_ensemble_statistic("mean", [_member_set(1.0, 2.0)])
    assert refused.value is None
    assert refused.refusal is not None and refused.refusal.code == "deployment_refused"


def test_one_ensemble_statistic_can_be_switched_off_alone(_derivations_on: None) -> None:
    off = derive_ensemble_statistic("spread", [_member_set(1.0, 2.0)], reader_disabled=[ENSEMBLE_SPREAD])
    assert off.value is None and off.refusal is not None and off.refusal.code == "reader_disabled"
    assert derive_ensemble_statistic("mean", [_member_set(1.0, 2.0)], reader_disabled=[ENSEMBLE_SPREAD]).value == 1.5


# --- Requirement: an entry stays inside one family, one run, one quantity ---


def test_an_ensemble_entry_naming_two_sources_is_refused_at_registration() -> None:
    two_families = _entry(
        name="ensemble_mean_across_centres",
        inputs=(
            Input(field="air_temperature", family="ensemble_member_field", source="noaa-gefs", kind="member_statistic"),
            Input(field="air_temperature", family="ensemble_member_field", source="eccc-reps", kind="member_statistic"),
        ),
        conventions=("arithmetic",),
    )
    errors = validation_errors((two_families,))
    assert any("one-family rule" in error for error in errors)


def test_an_ensemble_entry_mixing_averaged_and_instantaneous_is_refused() -> None:
    mixed = _entry(
        name="ensemble_mean_cloud",
        inputs=(
            Input(field="total_cloud_mean_6h", family="cloud_cover", kind="member_statistic"),
            Input(field="total_cloud_geometric", family="cloud_cover", kind="member_statistic"),
        ),
        conventions=("arithmetic",),
    )
    errors = validation_errors((mixed,))
    assert any("averaged-with-instantaneous refused" in error for error in errors)
    assert "total_cloud_mean_6h" in derive_registry.TIME_AVERAGED_FIELDS


def test_an_ensemble_quantile_entry_without_a_convention_is_refused() -> None:
    unstated = _entry(
        name="ensemble_quantile_unstated",
        inputs=(Input(field="air_temperature", family="ensemble_member_field", kind="member_statistic"),),
        conventions=(),
    )
    errors = validation_errors((unstated,))
    assert any("quantile convention" in error for error in errors)
    with pytest.raises(RegistryError):
        DerivationRegistry((unstated,))


def test_an_ensemble_entry_taking_a_provider_reduction_beside_members_is_refused() -> None:
    errors = validation_errors((
        _entry(
            name="ensemble_mean_with_reduction",
            inputs=(
                Input(field="geps_mean", family="ensemble_reduction", source="eccc-geps", kind="provider_reduction"),
                Input(field="air_temperature", family="ensemble_member_field", source="eccc-reps", kind="member_statistic"),
            ),
        ),
    ))
    assert any("another member set" in error for error in errors)


def test_ensemble_conditions_are_checked_again_at_derive_time(_derivations_on: None) -> None:
    gefs = _member_set(1.0, 2.0, family="noaa-gefs", source_id="noaa-gefs")
    cross_family = derive_ensemble_statistic("mean", [_member_set(3.0, 4.0), gefs])
    assert cross_family.value is None
    assert cross_family.condition_failed == "one_family:eccc-reps,noaa-gefs"

    cross_run = derive_ensemble_statistic("mean", [_member_set(3.0, 4.0), _member_set(5.0, 6.0, run_time=LATER_RUN)])
    assert cross_run.value is None
    assert cross_run.condition_failed is not None
    assert cross_run.condition_failed.startswith("one_run:")

    reduction = derive_ensemble_statistic(
        "mean", [_member_set(3.0, 4.0, family="ensemble_reduction")]
    )
    assert reduction.condition_failed == "provider_reduction_mixed"

    averaged = derive_ensemble_statistic(
        "mean",
        [_member_set(0.2, 0.4, field="total_cloud_mean_6h", time_averaged=True), _member_set(0.6, 0.8)],
    )
    assert averaged.value is None
    assert averaged.condition_failed == "averaged_with_instantaneous"


def test_a_failed_ensemble_condition_never_computes_over_the_subset(_derivations_on: None) -> None:
    bigger_run = _member_set(10.0, 10.0, 10.0, run_time=LATER_RUN)
    result = derive_ensemble_statistic("mean", [_member_set(1.0), bigger_run])
    assert result.value is None
    assert result.condition_failed is not None


# --- Requirement: a statistic carries the member set it covered ------------


def test_a_partial_ensemble_member_set_is_labelled_with_the_members_it_missed(_derivations_on: None) -> None:
    partial = _member_set(1.0, 2.0, 3.0, None, None, declared=5)
    result = derive_ensemble_statistic("mean", [partial])
    assert result.value == 2.0
    assert result.partial is True
    assert "partial_member_set" in result.flags
    assert (result.members_used, result.members_declared) == (3, 5)
    assert result.members_missing == ("m03", "m04")
    assert partial.missing_count == 2


def test_a_complete_ensemble_member_set_is_not_labelled_partial(_derivations_on: None) -> None:
    result = derive_ensemble_statistic("mean", [_member_set(1.0, 2.0, 3.0)])
    assert result.partial is False
    assert result.members_used == result.members_declared == 3


def test_an_ensemble_set_below_a_declared_minimum_produces_nothing(_derivations_on: None) -> None:
    """No minimum is declared today, so the one path that has an intrinsic
    floor is the sample standard deviation: one member is not a sample."""
    result = derive_ensemble_statistic("spread", [_member_set(4.0, None, declared=2)])
    assert result.value is None
    assert result.condition_failed == "below_minimum:1/2"


def test_no_ensemble_member_resolved_is_null_not_zero(_derivations_on: None) -> None:
    empty = _member_set(None, None, declared=21)
    for statistic in ("mean", "spread", "member_count"):
        result = derive_ensemble_statistic(statistic, [empty])
        assert result.value is None, f"{statistic} invented a value over no members"
        assert result.condition_failed == "no_member_resolved"
    assert derive_ensemble_statistic("mean", []).condition_failed == "no_member_resolved"


def test_an_ensemble_statistic_is_no_better_than_its_worst_member(_derivations_on: None) -> None:
    members = (
        MemberValue(member="m00", control=False, value=1.0, quality_status="passed"),
        MemberValue(member="m01", control=False, value=3.0, quality_status="suspect"),
    )
    member_set = dataclasses.replace(_member_set(1.0, 3.0), members=members)
    result = derive_ensemble_statistic("mean", [member_set])
    assert result.value == 2.0
    assert result.quality_status == "suspect"
    assert "derived" in result.flags


# --- Camera methods: registered, disabled, and refusing a number ---

_CAMERA_VERSIONS = {
    CAMERA_FOG_VISIBILITY_CLASS: "camera-class-v0",
    CAMERA_VISIBILITY_BOUND: "camera-landmark-bound-v0",
    CAMERA_SECTOR_CLOUD_FRACTION: "camera-sector-cloud-v0",
    CAMERA_HORIZON_FOG_BANK: "camera-fog-bank-v0",
    CAMERA_SKYDOME_NIGHT_CLOUD: "camera-starfield-v0",
}

_CAMERA_OUTPUTS = {
    CAMERA_FOG_VISIBILITY_CLASS: {
        "camera_fog_class",
        "camera_visibility_class",
        "camera_class_confidence",
    },
    CAMERA_VISIBILITY_BOUND: {"visibility_bound_lower_m", "visibility_bound_upper_m"},
    CAMERA_SECTOR_CLOUD_FRACTION: {"camera_sector_cloud_fraction"},
    CAMERA_HORIZON_FOG_BANK: {"horizon_fog_bank_present"},
    CAMERA_SKYDOME_NIGHT_CLOUD: {"skydome_night_cloud_fraction"},
}


def test_the_five_camera_methods_are_registered_camera_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """All five enter the registry disabled: four permitted claims plus the
    sky-dome night cloud, none of them enabled by this change."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    assert len(CAMERA_METHODS) == 5
    assert set(CAMERA_METHODS) == set(_CAMERA_VERSIONS)
    for name in CAMERA_METHODS:
        entry = derive_registry.get(name)
        assert entry is not None, name
        assert entry.enabled is False, name
        assert entry.version == _CAMERA_VERSIONS[name]
        assert {item.field for item in entry.outputs} == _CAMERA_OUTPUTS[name]
        assert entry.approval.approver
        refusal = derive_registry.resolve(name)
        assert refusal is not None and refusal.code == "method_disabled"
    # Every camera method reads one frame from one registered camera, and the
    # bound also reads the registered landmarks. Nothing else.
    for name in CAMERA_METHODS:
        entry = derive_registry.get(name)
        sources = {item.source for item in entry.inputs}
        assert sources == {"registered-camera"}, name
        assert "camera_frame" in {item.field for item in entry.inputs}, name
    bound = derive_registry.get(CAMERA_VISIBILITY_BOUND)
    assert {item.field for item in bound.inputs} == {"camera_frame", "camera_landmarks"}
    for item in bound.outputs:
        assert item.units == "m" and (item.minimum, item.maximum) == (0.0, 100000.0)
        assert item.range_rule == "clamp"


def test_a_camera_entry_enabled_without_validation_is_camera_disabled_at_registration() -> None:
    """Flipping `enabled` is not a validation record, so the registry refuses
    to load and the deployment does not start."""
    entry = derive_registry.get(CAMERA_FOG_VISIBILITY_CLASS)
    enabled = dataclasses.replace(entry, enabled=True)
    with pytest.raises(RegistryError) as raised:
        DerivationRegistry((enabled,))
    message = str(raised.value)
    assert CAMERA_ENABLED_WITHOUT_VALIDATION in message
    assert CAMERA_FOG_VISIBILITY_CLASS in message
    assert "30-day CYYT METAR" in message
    assert validation_errors((enabled,))
    assert validation_errors((entry,)) == []


def test_every_camera_disabled_method_derives_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    for name in CAMERA_METHODS:
        result = derive_from_camera(name, "cam-ntv-signal-hill", datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
        assert result.value is None, name
        assert result.refusal == AWAITING_VALIDATION, name
        assert result.available is False
        assert name in result.detail
        assert AWAITING_VALIDATION in result.detail


def test_an_unregistered_camera_disabled_method_names_the_registry() -> None:
    result = derive_from_camera("camera_black_ice_detected", "cam-x", "2026-09-03T12:00:00Z")
    assert result.value is None
    assert result.refusal == "unregistered_method"
    assert "camera_black_ice_detected" in result.detail


def test_a_numeric_visibility_refused_by_name() -> None:
    """A visibility in metres from the image alone is refused before any
    computation, and the refusal names the interval that is served instead."""
    with pytest.raises(RefusedClaim) as raised:
        request_numeric_visibility("cam-ntv-signal-hill", datetime(2026, 9, 3, 12, tzinfo=timezone.utc))
    assert raised.value.rule == NUMERIC_VISIBILITY_REFUSED
    assert "cam-ntv-signal-hill" in raised.value.detail
    assert CAMERA_VISIBILITY_BOUND in raised.value.detail
    assert NUMERIC_VISIBILITY_REFUSED in str(raised.value)


def test_the_numeric_visibility_refused_rule_leaves_the_bound_an_interval() -> None:
    """The permitted claim is an interval between two named landmarks; the
    entry says so in its conventions, and there is no single-number output."""
    entry = derive_registry.get(CAMERA_VISIBILITY_BOUND)
    conventions = " ".join(entry.conventions)
    assert "interval" in conventions
    assert "named" in conventions
    assert len(entry.outputs) == 2
    assert not any(item.field == "visibility_m" for item in entry.outputs)
    for item in entry.outputs:
        assert "landmark" in item.note


# --- Requirement: sector sampling along a bearing ---
# Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/site-registry/spec.md

#: Signal Hill, near enough. Every sector case below points north from here.
SECTOR_ORIGIN = (47.5615, -52.7126)

SECTOR_PARAMS = SectorParameters(
    origin_latitude=SECTOR_ORIGIN[0],
    origin_longitude=SECTOR_ORIGIN[1],
    bearing_deg=0.0,
    width_deg=60.0,
    max_range_km=20.0,
    elevation_band_deg=(0.0, 10.0),
)

#: Five cells due north of the origin, from 2.2 km to 11.1 km out, plus two
#: the sector does not contain: one due south (outside the width) and one far
#: north (outside the range). A reduction that took either would show it.
SECTOR_CELLS: tuple[tuple[float, float, float | None], ...] = (
    (47.5815, -52.7126, 10.0),
    (47.6015, -52.7126, 20.0),
    (47.6215, -52.7126, 30.0),
    (47.6415, -52.7126, 40.0),
    (47.6615, -52.7126, 50.0),
    (47.5115, -52.7126, 1000.0),
    (47.9615, -52.7126, 1000.0),
)


def _sector_input(
    cells: Sequence[tuple[float, float, float | None]] = SECTOR_CELLS,
    *,
    field: str = "total_cloud_cover",
    family: str = "total_cloud",
    source_id: str = "eccc-hrdps",
    evidence_class: str = "retrieved",
    quality_status: str = "passed",
) -> SectorInput:
    return SectorInput(
        field=field,
        family=family,
        source_id=source_id,
        evidence_class=evidence_class,
        quality_status=quality_status,
        cells=tuple(cells),
    )


def test_sector_sampling_is_registered_and_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The entry now has a sampler, so it is enabled and resolves. Its name,
    version and citation are unchanged; what changed is that the summary no
    longer says the sampler does not exist, and the conventions name the
    reduction, the parameters and the minimum covered fraction."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    entry = derive_registry.get(SECTOR_SAMPLING)
    assert entry.enabled is True
    assert derive_registry.resolve(SECTOR_SAMPLING) is None
    assert entry.version == "geodesic-sector-v1"
    assert "Karney" in entry.citation
    assert "disabled until" not in entry.summary
    conventions = " ".join(entry.conventions)
    assert "mean" in conventions
    assert "0.8" in conventions
    for parameter in ("origin", "bearing", "width", "range", "elevation"):
        assert parameter in conventions
    assert "retrieved" in conventions
    assert [item.field for item in entry.inputs] == ["gridded_field", "site_geometry"]
    assert entry.output.field == "sector_statistic"


def test_sector_sampling_serves_a_sample_with_its_sector_and_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The served scenario: the value carries the entry name and version, the
    origin, bearing, width and range, and every input source."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    result = sample_sector([_sector_input()], SECTOR_PARAMS)
    assert result.refusal is None
    assert result.available is True
    # The mean of the five in-sector cells, not of all seven: the southern
    # cell and the far northern one are outside the sector.
    assert result.value == pytest.approx(30.0)
    assert result.covered_fraction == pytest.approx(1.0)
    assert result.quality_status == "passed"
    record = result.provenance
    assert record["derivation"] == SECTOR_SAMPLING
    assert record["derivation_version"] == "geodesic-sector-v1"
    assert record["origin"] == SECTOR_ORIGIN
    assert record["bearing_deg"] == 0.0
    assert record["width_deg"] == 60.0
    assert record["max_range_km"] == 20.0
    assert record["elevation_band_deg"] == (0.0, 10.0)
    assert record["reduction"] == REDUCTION == "mean"
    assert [item["source_id"] for item in record["inputs"]] == ["eccc-hrdps"]
    assert record["inputs"][0]["evidence_class"] == "retrieved"
    assert record["inputs"][0]["field"] == "total_cloud_cover"


@pytest.mark.parametrize("evidence_class", ["reprocessed", "intermediary_derived"])
def test_sector_sampling_refuses_an_input_that_is_not_retrieved(
    evidence_class: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sector sample is a statement about what a centre published on its own
    grid, so an input of any other class is refused naming the class, and no
    sample is produced from it."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    result = sample_sector([_sector_input(evidence_class=evidence_class)], SECTOR_PARAMS)
    assert result.value is None
    assert result.refusal == f"input_class_refused:{evidence_class}"
    assert evidence_class in result.refusal
    assert result.provenance["inputs"][0]["evidence_class"] == evidence_class


def test_sector_sampling_carries_the_worst_input_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    """Worst-first, mirroring ``api.weather_api.models.QUALITY_SEVERITY``:
    passed < suspect < unknown < failed. Nothing here may raise a status."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    assert sample_sector([_sector_input()], SECTOR_PARAMS).quality_status == "passed"
    for status in ("suspect", "unknown", "failed"):
        result = sample_sector([_sector_input(quality_status=status)], SECTOR_PARAMS)
        assert result.quality_status == status
        assert result.value == pytest.approx(30.0)
    worst = sample_sector(
        [
            _sector_input(quality_status="passed"),
            _sector_input(
                field="site_geometry", family="site_geometry", quality_status="suspect"
            ),
        ],
        SECTOR_PARAMS,
    )
    assert worst.quality_status == "suspect"
    assert derive_registry.QUALITY_SEVERITY == {"passed": 0, "suspect": 1, "unknown": 2, "failed": 3}


def test_sector_sampling_is_null_when_the_sector_is_not_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Part of the sector falling outside the grid, or over missing cells, is
    null naming the uncovered fraction. At exactly the declared minimum the
    sample is served; below it nothing is computed from the covered part."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    assert MINIMUM_COVERED_FRACTION == 0.8
    four_of_five = [
        (latitude, longitude, None if value == 50.0 else value)
        for latitude, longitude, value in SECTOR_CELLS
    ]
    met = sample_sector([_sector_input(four_of_five)], SECTOR_PARAMS)
    assert met.covered_fraction == pytest.approx(0.8)
    assert met.refusal is None and met.value == pytest.approx(25.0)

    three_of_five = [
        (latitude, longitude, None if value in {40.0, 50.0} else value)
        for latitude, longitude, value in SECTOR_CELLS
    ]
    short = sample_sector([_sector_input(three_of_five)], SECTOR_PARAMS)
    assert short.value is None
    assert short.covered_fraction == pytest.approx(0.6)
    assert short.refusal.startswith("uncovered_fraction:")
    assert "0.6" in short.refusal

    # A sector with no cells in it at all is never a mean over nothing.
    away = dataclasses.replace(SECTOR_PARAMS, bearing_deg=180.0, width_deg=10.0, max_range_km=1.0)
    empty = sample_sector([_sector_input()], away)
    assert empty.value is None
    assert empty.refusal == "uncovered_fraction:0.0"


def test_sector_sampling_refuses_one_field_from_two_sources_as_a_blend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same catalogue field, or two members of one family, from two
    centres is the same field averaged across centres by another name."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    same_field = sample_sector(
        [_sector_input(source_id="eccc-hrdps"), _sector_input(source_id="noaa-gfs")],
        SECTOR_PARAMS,
    )
    assert same_field.value is None
    assert same_field.refusal == "blend_refused"

    same_family = sample_sector(
        [
            _sector_input(field="total_cloud_opacity_weighted", source_id="eccc-hrdps"),
            _sector_input(field="total_cloud_geometric", source_id="noaa-gfs"),
        ],
        SECTOR_PARAMS,
    )
    assert same_family.value is None
    assert same_family.refusal == "blend_refused"

    # Two different families from two sources is not a blend: a grid from one
    # centre with the site's own geometry is exactly the intended shape.
    allowed = sample_sector(
        [
            _sector_input(source_id="eccc-hrdps"),
            _sector_input(field="site_geometry", family="site_geometry", source_id="registered-site"),
        ],
        SECTOR_PARAMS,
    )
    assert allowed.refusal is None


def test_sector_sampling_refused_at_each_of_the_three_switch_levels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled at any of the three levels, every sector field is null with a
    notice naming the level, and no unsectored substitute is served."""
    monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, "off")
    deployment = sample_sector([_sector_input()], SECTOR_PARAMS)
    assert deployment.value is None and deployment.refusal == "deployment_refused"

    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    reader = sample_sector([_sector_input()], SECTOR_PARAMS, reader_disabled=[SECTOR_SAMPLING])
    assert reader.value is None and reader.refusal == "reader_disabled"
    # Another reader's switch is not this reader's.
    assert sample_sector([_sector_input()], SECTOR_PARAMS, reader_disabled=[FOG_STATE]).refusal is None

    switched_off = DerivationRegistry(
        tuple(
            dataclasses.replace(entry, enabled=False) if entry.name == SECTOR_SAMPLING else entry
            for entry in ENTRIES
        )
    )
    monkeypatch.setattr(derive_registry, "REGISTRY", switched_off)
    entry_level = sample_sector([_sector_input()], SECTOR_PARAMS)
    assert entry_level.value is None and entry_level.refusal == "method_disabled"
    # The provenance still says what was asked for, refused or not.
    assert entry_level.provenance["derivation"] == SECTOR_SAMPLING
    assert entry_level.provenance["bearing_deg"] == 0.0
