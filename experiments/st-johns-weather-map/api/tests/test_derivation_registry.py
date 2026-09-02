"""The derivation method registry: shape, refusals and the three switches.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/derivation-method-registry/spec.md
"""

from __future__ import annotations

import dataclasses

import pytest

from ingest.derive import registry as derive_registry
from ingest.derive.registry import (
    DE442_GEOMETRY,
    ENSEMBLE_STATISTICS,
    ENTRIES,
    FOG_STATE,
    RELATIVE_HUMIDITY,
    SECTOR_SAMPLING,
    WIND_SPEED_AND_DIRECTION,
    Approval,
    DerivationMethod,
    DerivationRegistry,
    Input,
    Output,
    RegistryError,
    UnregisteredMethod,
)

APPROVAL = Approval(approver="@TusharSariya", decided_on="2026-09-02", record="ADR 0001", note="test entry")


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
    monkeypatch.delenv(derive_registry.DERIVED_HERE_ENV, raising=False)
    refusal = derive_registry.resolve(ENSEMBLE_STATISTICS)
    assert refusal is not None and refusal.code == "method_disabled"
    assert derive_registry.get(SECTOR_SAMPLING).enabled is False


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
    assert rows[ENSEMBLE_STATISTICS]["refusal"]["code"] == "method_disabled"


# --- Physical range and the wiring the API calls ---


def test_a_result_outside_the_range_is_bounded_and_flagged() -> None:
    assert derive_registry.bound(RELATIVE_HUMIDITY, "relative_humidity", 50.0) == (50.0, ())
    assert derive_registry.bound(RELATIVE_HUMIDITY, "relative_humidity", 104.0) == (100.0, ("range_clamped",))
    assert derive_registry.bound(WIND_SPEED_AND_DIRECTION, "wind_direction", 370.0) == (10.0, ("range_wrapped",))
    assert derive_registry.bound(ENSEMBLE_STATISTICS, "ensemble_statistic", 9e9) == (9e9, ())


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
