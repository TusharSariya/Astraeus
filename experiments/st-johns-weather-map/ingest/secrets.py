"""Provider credential lookup.

Credentials reach this experiment through the environment and nowhere else.
They are never written to an artifact, a provenance block, a log line, a
fixture, a commit or the browser bundle, and this module is the only place that
reads them, so there is exactly one thing to audit.

The important behaviour is what happens when a key is ABSENT. A missing
credential must leave its source honestly non-active with a stated reason -- it
must never crash the worker, never disable an unrelated source, and above all
never fall through to a substituted value. An adapter that cannot authenticate
has no evidence, and no evidence is reported as no evidence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Registry source id -> environment variable. Adding a row here is the whole
# job of granting a source a credential; nothing else reads the environment.
SECRET_ENV_BY_SOURCE = {
    "copernicus-cams": "WEATHER_SECRET_COPERNICUS_ADS_TOKEN",
    "nasa-earthdata-aerosol": "WEATHER_SECRET_NASA_EARTHDATA_TOKEN",
    "noaa-madis": "WEATHER_SECRET_MADIS_TOKEN",
    "purpleair": "WEATHER_SECRET_PURPLEAIR_API_KEY",
    "openaq": "WEATHER_SECRET_OPENAQ_API_KEY",
    "nl-511": "WEATHER_SECRET_NL511_API_KEY",
    "google-weathernext-2": "WEATHER_SECRET_GOOGLE_WEATHERNEXT_TOKEN",
}

# Redaction is applied to anything that might carry a key into a log or an
# error message. A provider that puts the key in the query string (NL 511 does)
# makes this necessary, not optional.
_REDACTION = "[redacted]"


class CredentialMissing(RuntimeError):
    """No credential is configured for this source.

    Carries the registration URL so the operator is told where to get one
    rather than being left with a bare failure.
    """

    def __init__(self, source_id: str, variable: str, registration_url: str | None) -> None:
        detail = f"{source_id} needs a credential in {variable}"
        if registration_url:
            detail += f"; obtain one at {registration_url}"
        super().__init__(detail)
        self.source_id = source_id
        self.variable = variable
        self.registration_url = registration_url


@dataclass(frozen=True)
class CredentialStatus:
    """Whether a source could authenticate, for honest status reporting."""

    source_id: str
    variable: str | None
    configured: bool
    registration_url: str | None

    @property
    def reason(self) -> str:
        if self.variable is None:
            return "this source does not require a credential"
        if self.configured:
            return f"credential supplied through {self.variable}"
        detail = f"no credential configured in {self.variable}"
        if self.registration_url:
            detail += f"; obtain one at {self.registration_url}"
        return detail


def _registration_url(source_id: str) -> str | None:
    """The provider's own sign-up URL, from the registry rather than hardcoded."""
    try:
        from ingest.registry import _load_registry  # noqa: PLC0415

        for record in _load_registry()["sources"]:
            if record["id"] == source_id:
                return record.get("authentication", {}).get("registration_url")
    except Exception:
        return None
    return None


def credential_for(source_id: str, *, environ: dict[str, str] | None = None) -> str | None:
    """Return the configured credential, or ``None`` when there is none.

    Blank and whitespace-only values are treated as absent: a placeholder left
    empty in ``.env`` must not be sent to a provider as if it were a key.
    """
    variable = SECRET_ENV_BY_SOURCE.get(source_id)
    if variable is None:
        return None
    value = (environ if environ is not None else os.environ).get(variable, "")
    return value.strip() or None


def require_credential(source_id: str, *, environ: dict[str, str] | None = None) -> str:
    """Return the credential or raise, for an adapter that cannot proceed without one."""
    value = credential_for(source_id, environ=environ)
    if value is None:
        variable = SECRET_ENV_BY_SOURCE.get(source_id, "(no variable is mapped for this source)")
        raise CredentialMissing(source_id, variable, _registration_url(source_id))
    return value


def credential_status(source_id: str, *, environ: dict[str, str] | None = None) -> CredentialStatus:
    """Report configuration WITHOUT revealing the value.

    This is what the API's source status may safely surface: whether a key is
    present, and where to get one if not.
    """
    variable = SECRET_ENV_BY_SOURCE.get(source_id)
    if variable is None:
        return CredentialStatus(source_id, None, True, None)
    return CredentialStatus(
        source_id=source_id,
        variable=variable,
        configured=credential_for(source_id, environ=environ) is not None,
        registration_url=_registration_url(source_id),
    )


def configured_sources(*, environ: dict[str, str] | None = None) -> tuple[str, ...]:
    return tuple(sorted(s for s in SECRET_ENV_BY_SOURCE if credential_for(s, environ=environ)))


def redact(text: str, *, environ: dict[str, str] | None = None) -> str:
    """Strip every configured credential out of a string before it is logged.

    Providers that accept a key as a query parameter put it in the URL, and a
    URL is exactly what ends up in an exception message and a log line.
    """
    result = text
    for source_id in SECRET_ENV_BY_SOURCE:
        value = credential_for(source_id, environ=environ)
        # A very short value would redact harmless substrings everywhere.
        if value and len(value) >= 8:
            result = result.replace(value, _REDACTION)
    return result
