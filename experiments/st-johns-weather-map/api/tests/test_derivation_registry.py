"""The derivation method registry: shape, refusals and the three switches.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/derivation-method-registry/spec.md
Spec-Refs: openspec/changes/ensemble-families-and-member-statistics/specs/derivation-method-registry/spec.md
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from ingest.derive import registry as derive_registry
from ingest.derive.registry import (
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
    """`ensemble_statistics_within_run` was the disabled entry here until
    `ensemble-families-and-member-statistics` enabled it as the umbrella every
    member statistic goes through; sector sampling is still registered and
    disabled, so it carries the case now."""
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    refusal = derive_registry.resolve(SECTOR_SAMPLING)
    assert refusal is not None and refusal.code == "method_disabled"
    assert derive_registry.get(SECTOR_SAMPLING).enabled is False
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
    assert rows[SECTOR_SAMPLING]["refusal"]["code"] == "method_disabled"
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
