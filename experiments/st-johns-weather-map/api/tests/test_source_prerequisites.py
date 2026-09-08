"""Configuration outcomes are safe and independent (API-first contract)."""
from datetime import datetime, timezone

import pytest

from weather_api.source_prerequisites import (
    DeliveryPrerequisites, assess_aurora_foundry, assess_chemistry,
    assess_fourcastnet_nim, assess_weathernext_statistics,
)

STAMP = datetime(2026, 9, 7, 22, tzinfo=timezone.utc)
READY = DeliveryPrerequisites(native_contract_settled=True, software_implemented=True, checked_at=STAMP)
AURORA_READY = dict(endpoint_configured=True, credential_configured=True, storage_configured=True,
                    deployment_available=True, initialization_available=True)
NIM_READY = dict(compute_available=True, initialization_available=True, deployment_available=True,
                 registry_setup_available=True)


@pytest.mark.parametrize("assess", [assess_weathernext_statistics, assess_aurora_foundry,
                                    assess_fourcastnet_nim, assess_chemistry])
def test_unassessed_is_never_ready_or_missing_credentials(assess):
    result = assess(DeliveryPrerequisites())
    assert result.state == "unknown"
    assert result.checked_at is None
    assert result.required_environment == []


@pytest.mark.parametrize("facts", [
    DeliveryPrerequisites(native_contract_settled=False, software_implemented=False),
    DeliveryPrerequisites(native_contract_settled=True, software_implemented=False),
])
def test_incomplete_software_contract_is_not_credentials_only(facts):
    result = assess_weathernext_statistics(facts, google_auth_available=False)
    assert result.state == "product_unavailable"
    assert "delivery software" in result.reason
    assert "selected Google authentication" in result.reason


def test_unknown_auth_is_distinct_from_absent_auth():
    assert assess_weathernext_statistics(READY).state == "unknown"
    missing = assess_weathernext_statistics(READY, google_auth_available=False)
    assert missing.state == "missing_configuration"
    assert missing.required_environment == []  # ADC does not require an env-file path.
    ready = assess_weathernext_statistics(READY, google_auth_available=True)
    assert ready.state == "ready" and ready.checked_at == STAMP
    assert "serving permission are not established" in ready.reason


@pytest.mark.parametrize(("name", "environment"), [
    ("endpoint_configured", "FOUNDRY_ENDPOINT"),
    ("credential_configured", "FOUNDRY_TOKEN"),
    ("storage_configured", "BLOB_URL_WITH_SAS"),
])
def test_aurora_names_missing_configuration_without_values(name, environment):
    result = assess_aurora_foundry(READY, **{**AURORA_READY, name: False})
    assert result.state == "missing_configuration"
    assert result.required_environment == [environment]


@pytest.mark.parametrize("name", ["deployment_available", "initialization_available"])
def test_aurora_compute_and_initialization_are_not_credentials(name):
    result = assess_aurora_foundry(READY, **{**AURORA_READY, name: False})
    assert result.state == "missing_compute"
    assert result.required_environment == []


@pytest.mark.parametrize("name", ["compute_available", "deployment_available", "initialization_available"])
def test_nim_inference_prerequisites_are_not_a_hosted_api_key(name):
    result = assess_fourcastnet_nim(READY, **{**NIM_READY, name: False})
    assert result.state == "missing_compute"
    assert result.required_environment == []


def test_nim_registry_setup_is_separate_from_compute():
    missing = assess_fourcastnet_nim(READY, **{**NIM_READY, "registry_setup_available": False})
    assert missing.state == "missing_configuration"
    assert missing.required_environment == ["NGC_API_KEY"]
    assert assess_fourcastnet_nim(READY, **NIM_READY).state == "ready"


def test_chemistry_gate_remains_product_unavailable_without_credential_request():
    result = assess_chemistry(DeliveryPrerequisites(native_contract_settled=False, software_implemented=False))
    assert result.state == "product_unavailable"
    assert result.required_environment == []
    assert "native scientific contract" in result.reason


@pytest.mark.parametrize(("flag", "state"), [("access_denied", "access_denied"),
                                             ("acquisition_failed", "acquisition_failed")])
def test_explicit_outcome_retains_structural_blockers(flag, state):
    facts = DeliveryPrerequisites(native_contract_settled=False, software_implemented=False, **{flag: True})
    result = assess_chemistry(facts)
    assert result.state == state
    assert "native scientific contract" in result.reason and "delivery software" in result.reason


@pytest.mark.parametrize("value", ["private-token-value", "https://private.invalid?sig=secret", 1, {}, []])
def test_configuration_values_are_rejected_without_echo(value):
    with pytest.raises(ValueError) as error:
        assess_weathernext_statistics(READY, google_auth_available=value)
    assert str(error.value) == "prerequisite facts must be booleans or unknown"
    with pytest.raises(ValueError):
        DeliveryPrerequisites(software_implemented=value)


def test_no_implicit_clock_and_naive_assessment_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        DeliveryPrerequisites(checked_at=STAMP.replace(tzinfo=None))
    assert assess_chemistry(READY).checked_at == STAMP


def test_all_ready_inference_prerequisites_do_not_assert_observation_or_entitlement():
    result = assess_aurora_foundry(READY, **AURORA_READY)
    assert result.state == "ready"
    assert result.required_environment == []
    assert "retrieval, coverage and serving permission are not established" in result.reason


def test_unknown_software_is_not_promoted_to_credentials_only():
    result = assess_weathernext_statistics(DeliveryPrerequisites(), google_auth_available=False)
    assert result.state == "unknown"
    assert "delivery software" in result.reason and "Google authentication" in result.reason


def test_assessment_performs_no_environment_file_or_clock_discovery(monkeypatch):
    import os
    from pathlib import Path

    def forbidden(*_args, **_kwargs):
        raise AssertionError("assessment must consume supplied facts only")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    assert assess_aurora_foundry(READY, **AURORA_READY).checked_at == STAMP
    assert assess_fourcastnet_nim(READY, **NIM_READY).state == "ready"
