"""Credential handling.

Two properties matter more than the rest. A missing key must produce an honest
absence rather than a crash or a substituted value, and a key that IS present
must never escape into a log, an error message or an artifact.
"""

from __future__ import annotations

import pytest

from ingest.secrets import (
    SECRET_ENV_BY_SOURCE,
    CredentialMissing,
    configured_sources,
    credential_for,
    credential_status,
    redact,
    require_credential,
)


def test_absent_credential_is_none_not_an_error() -> None:
    """A worker cycle must survive every key being unset."""
    assert credential_for("openaq", environ={}) is None


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_blank_placeholder_counts_as_absent(blank: str) -> None:
    """An empty line left in .env must never be sent as if it were a key."""
    assert credential_for("openaq", environ={"WEATHER_SECRET_OPENAQ_API_KEY": blank}) is None


def test_a_supplied_credential_is_returned_and_stripped() -> None:
    value = credential_for("openaq", environ={"WEATHER_SECRET_OPENAQ_API_KEY": "  abc123def456  "})
    assert value == "abc123def456"


def test_a_source_with_no_mapped_variable_needs_no_credential() -> None:
    assert credential_for("eccc-hrdps", environ={}) is None
    status = credential_status("eccc-hrdps", environ={})
    assert status.configured is True
    assert status.variable is None


def test_require_credential_names_the_variable_and_where_to_get_one() -> None:
    """A bare failure leaves the operator stuck; the error must be actionable."""
    with pytest.raises(CredentialMissing) as raised:
        require_credential("openaq", environ={})

    error = raised.value
    assert error.source_id == "openaq"
    assert error.variable == "WEATHER_SECRET_OPENAQ_API_KEY"
    assert "WEATHER_SECRET_OPENAQ_API_KEY" in str(error)
    # The registration URL comes from the registry, not a hardcoded string.
    assert error.registration_url == "https://explore.openaq.org/register"
    assert "https://explore.openaq.org/register" in str(error)


def test_status_reports_configuration_without_revealing_the_value() -> None:
    secret = "super-secret-key-value"
    status = credential_status("openaq", environ={"WEATHER_SECRET_OPENAQ_API_KEY": secret})

    assert status.configured is True
    assert secret not in status.reason, "a status line must never carry the key itself"
    assert secret not in repr(status)


def test_unconfigured_status_says_where_to_get_a_key() -> None:
    status = credential_status("nl-511", environ={})
    assert status.configured is False
    assert "https://511nl.ca/developers/doc" in status.reason


def test_redact_removes_a_key_from_a_url() -> None:
    """NL 511 takes its key as a query parameter, so URLs carry it into logs."""
    secret = "abcd1234efgh5678"
    environ = {"WEATHER_SECRET_NL511_API_KEY": secret}
    message = f"GET https://511nl.ca/api/v2/get/events?key={secret}&format=json failed"

    cleaned = redact(message, environ=environ)

    assert secret not in cleaned
    assert "[redacted]" in cleaned
    assert "511nl.ca" in cleaned, "redaction must not destroy the diagnostic value of the message"


def test_redact_ignores_a_very_short_value() -> None:
    """Redacting a 2-character value would blank out unrelated substrings."""
    environ = {"WEATHER_SECRET_OPENAQ_API_KEY": "ab"}
    assert redact("a stable observation", environ=environ) == "a stable observation"


def test_configured_sources_lists_only_those_with_a_key() -> None:
    environ = {"WEATHER_SECRET_OPENAQ_API_KEY": "key-one-value", "WEATHER_SECRET_PURPLEAIR_API_KEY": "   "}
    assert configured_sources(environ=environ) == ("openaq",)


def test_every_mapped_variable_follows_the_naming_convention() -> None:
    for source_id, variable in SECRET_ENV_BY_SOURCE.items():
        assert variable.startswith("WEATHER_SECRET_"), f"{source_id} maps to {variable}"


@pytest.mark.xfail(strict=False, reason="viirs-dnb-night-lights record lands in task 7.6")
def test_every_mapped_source_exists_in_the_registry() -> None:
    """A mapping for a source id that does not exist is a silent dead letter."""
    from ingest.registry import ingest_configs

    known = set(ingest_configs())
    unknown = set(SECRET_ENV_BY_SOURCE) - known
    assert not unknown, f"secrets map references unknown source ids: {sorted(unknown)}"


def test_every_credential_required_registry_source_has_a_mapping() -> None:
    """A credential-gated source with no variable could never be enabled."""
    from ingest.registry import _load_registry

    gated = {
        record["id"]
        for record in _load_registry()["sources"]
        if record["authentication"]["required"]
    }
    missing = gated - set(SECRET_ENV_BY_SOURCE)
    assert not missing, f"credential-required sources with no env var mapped: {sorted(missing)}"
