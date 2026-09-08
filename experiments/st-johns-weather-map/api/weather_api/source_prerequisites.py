"""Pure, source-specific configuration assessments for experimental paths.

Owning contract: api-first-source-delivery / configuration outcomes. Inputs are
caller-assessed facts, never configuration values. This module does not inspect
environment variables, credential files, remote services or source registries.
A ready result asserts supplied prerequisites only, not retrieval or admission.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime

from .source_contract import SourceConfiguration


@dataclass(frozen=True)
class DeliveryPrerequisites:
    native_contract_settled: bool | None = None
    software_implemented: bool | None = None
    access_denied: bool = False
    acquisition_failed: bool = False
    checked_at: datetime | None = None

    def __post_init__(self):
        for field in fields(self):
            if field.name != "checked_at":
                _fact(getattr(self, field.name))
        if self.access_denied is None or self.acquisition_failed is None:
            raise ValueError("observed outcome flags must be booleans")
        if self.checked_at is not None and (
            not isinstance(self.checked_at, datetime) or self.checked_at.utcoffset() is None
        ):
            raise ValueError("assessment time must be timezone-aware")


def _fact(value: bool | None) -> None:
    if value is not None and type(value) is not bool:
        raise ValueError("prerequisite facts must be booleans or unknown")


# name, supplied presence, missing state, documented environment names
_Check = tuple[str, bool | None, str, tuple[str, ...]]


def _assess(product: str, facts: DeliveryPrerequisites, checks: tuple[_Check, ...]) -> SourceConfiguration:
    # Validate every input even if an earlier prerequisite blocks delivery.
    for _, value, _, _ in checks:
        _fact(value)
    prerequisites: tuple[_Check, ...] = (
        ("native scientific contract", facts.native_contract_settled, "product_unavailable", ()),
        ("delivery software", facts.software_implemented, "product_unavailable", ()),
        *checks,
    )
    # Keep all known blockers in safe, fixed wording, while choosing the earliest
    # architectural blocker as the primary state. Never call unfinished software
    # a credentials-only problem or treat unknown presence as confirmed absence.
    missing = [check for check in prerequisites if check[1] is False]
    unknown = [check for check in prerequisites if check[1] is None]
    required = list(dict.fromkeys(name for check in missing for name in check[3]))
    if missing:
        structural = prerequisites[:2]
        state = (
            "unknown" if not any(check[1] is False for check in structural)
            and any(check[1] is None for check in structural)
            else missing[0][2]
        )
        reason = f"{product}: missing or unsettled " + ", ".join(check[0] for check in missing)
        if unknown:
            reason += "; not assessed: " + ", ".join(check[0] for check in unknown)
    elif unknown:
        state = "unknown"
        reason = f"{product}: not assessed: " + ", ".join(check[0] for check in unknown)
    else:
        state = "ready"
        reason = f"{product}: supplied prerequisites are ready; retrieval, coverage and serving permission are not established"
    # A concrete observed denial/failure is retained without erasing missing
    # prerequisites. Neither can be inferred from mere credential presence.
    if facts.access_denied:
        state = "access_denied"
        reason = f"{product}: access was denied; " + reason
    elif facts.acquisition_failed:
        state = "acquisition_failed"
        reason = f"{product}: acquisition failed; " + reason
    return SourceConfiguration(state=state, reason=reason, required_environment=required, checked_at=facts.checked_at)


def assess_weathernext_statistics(
    facts: DeliveryPrerequisites, *, google_auth_available: bool | None = None,
) -> SourceConfiguration:
    """Selected WeatherNext statistics GCS path; no API-key or mandatory ADC file.

    Google auth may be supplied through ADC without GOOGLE_APPLICATION_CREDENTIALS.
    Dataset entitlement remains distinct from locally available authentication.
    """
    return _assess("WeatherNext statistics", facts, (
        ("selected Google authentication", google_auth_available, "missing_configuration", ()),
    ))


def assess_aurora_foundry(
    facts: DeliveryPrerequisites, *, endpoint_configured: bool | None = None,
    credential_configured: bool | None = None, storage_configured: bool | None = None,
    deployment_available: bool | None = None, initialization_available: bool | None = None,
) -> SourceConfiguration:
    """Assess the selected customer-deployed Aurora Foundry path only."""
    return _assess("Aurora Foundry", facts, (
        ("model deployment", deployment_available, "missing_compute", ()),
        ("initialization data", initialization_available, "missing_compute", ()),
        ("endpoint configuration", endpoint_configured, "missing_configuration", ("FOUNDRY_ENDPOINT",)),
        ("authentication configuration", credential_configured, "missing_configuration", ("FOUNDRY_TOKEN",)),
        ("communication storage configuration", storage_configured, "missing_configuration", ("BLOB_URL_WITH_SAS",)),
    ))


def assess_fourcastnet_nim(
    facts: DeliveryPrerequisites, *, compute_available: bool | None = None,
    initialization_available: bool | None = None, deployment_available: bool | None = None,
    registry_setup_available: bool | None = None,
) -> SourceConfiguration:
    """Selected self-hosted NIM, not hosted historical demo or FCN1/FCN3.

    registry_setup_available includes an already provisioned image. A running
    deployment need not retain a registry key merely to serve inference.
    """
    return _assess("Self-hosted FourCastNet NIM", facts, (
        ("inference compute", compute_available, "missing_compute", ()),
        ("model deployment", deployment_available, "missing_compute", ()),
        ("initialization data", initialization_available, "missing_compute", ()),
        ("registry image setup", registry_setup_available, "missing_configuration", ("NGC_API_KEY",)),
    ))


def assess_chemistry(facts: DeliveryPrerequisites) -> SourceConfiguration:
    """RAQDPS/RDAQA complete-group contract; anonymous access needs no key.

    The caller must explicitly assess canonical gas/particulate/smoke quantities,
    statistic windows and analysis phases. A retained raw WCS reader alone does
    not constitute implemented point-delivery software.
    """
    return _assess("RAQDPS/RDAQA chemistry", facts, ())
