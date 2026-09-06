#!/usr/bin/env python3
"""The admission vocabulary, in one dependency-free place.

The audit, the API and the ingest registry all read their state names, their
ceiling and their schedulability test from here, so no two of them can
disagree about what a state means. Nothing in this module imports anything but
the standard library, and nothing in it reads a file: it is pure vocabulary,
importable from a CI job that has neither ``jsonschema`` nor a network stack.

The type annotations describe a registry record as a plain mapping because
that is what ``source_data.registry()`` hands back; this module deliberately
does not depend on that module, or on any schema.
"""

from __future__ import annotations

from typing import Any, Mapping

#: The ten admission states, in the order the design pins them.
#:
#: ``operational`` is first and is unreachable. It is listed so that the
#: vocabulary is complete and so that ``CEILING`` has something to map, but no
#: record may declare it and no response may emit it: the audit refuses it on
#: every record and ``ceiling_state`` maps it to ``unavailable``.
STATES: tuple[str, ...] = (
    "operational",
    "implemented-unverified",
    "catalogued",
    "credential-required",
    "licence-blocked",
    "link-only",
    "partnership-only",
    "unavailable",
    "rejected",
    "superseded",
)

#: The only state a record may be scheduled from. A declaration that has not
#: been implemented against a real adapter is a catalogue entry, and a
#: catalogue entry is never fetched.
SCHEDULABLE_STATES = frozenset({"implemented-unverified"})

#: States that assert there is no data path at all. ``access_endpoints`` must
#: be ``[]`` on these: a link-only or partnership-only source is cited through
#: ``documentation_urls`` and never fetched, and a rejected one is not fetched
#: because it was refused.
NO_ACCESS_PATH_STATES = frozenset({"link-only", "partnership-only", "rejected"})

#: States from which no evidence will arrive. ``fixture_status`` and
#: ``live_smoke_test_status`` must both be ``not_applicable`` on these, so that
#: a terminal record cannot carry a planned test that will never run.
TERMINAL_STATES = frozenset(
    {"unavailable", "rejected", "superseded", "link-only", "partnership-only"}
)

#: The highest state a response may report for a record, by declared state.
#: Every state maps to itself except ``operational``, which maps to
#: ``unavailable`` so that the value stays unreachable no matter what a record
#: or a live retrieval claims.
CEILING: dict[str, str] = {state: state for state in STATES}
CEILING["operational"] = "unavailable"


def ceiling_state(status: str) -> str:
    """The state a response may report for ``status``.

    An unknown state falls to ``unavailable`` rather than passing through, so
    that a record written against a future vocabulary cannot widen what this
    deployment emits.
    """
    return CEILING.get(status, "unavailable")


def condition_outstanding(record: Mapping[str, Any]) -> bool:
    """Whether an unmet admission condition stands against this record.

    True only when the record carries an ``admission_condition`` block whose
    ``satisfied`` is false. A record with no block has no condition, which is
    not the same as having a satisfied one, but for schedulability the two
    behave alike.
    """
    condition = record.get("admission_condition")
    if not condition:
        return False
    return not condition.get("satisfied", False)


def implemented_unverified_ok(
    record: Mapping[str, Any], adapter_ids: set[str] | frozenset[str]
) -> bool:
    """The objective test that separates an implemented record from a catalogued one.

    Three conditions, all of them checkable without asking anyone's opinion: a
    registered adapter claims the id, the integration is something other than a
    bare link, and the fixture suite passes. Anything short of that is a
    catalogue entry, whatever the prose says.
    """
    return (
        record["id"] in adapter_ids
        and record["integration"]["kind"] != "link_only"
        and record["fixture_status"] == "passing"
    )


def declaration_schedulable(
    record: Mapping[str, Any], adapter_ids: set[str] | frozenset[str]
) -> bool:
    """The registry half of schedulability: may this declaration be fetched at all?

    The ingest half (freshness, reach, cadence, the ensemble flag) stays in
    ``ingest/registry.py``. What is decided here is only whether the record's
    own declaration permits a fetch: it is in a schedulable state, it really is
    implemented, and no admission condition is outstanding against it.
    """
    return (
        record["status"] in SCHEDULABLE_STATES
        and implemented_unverified_ok(record, adapter_ids)
        and not condition_outstanding(record)
    )


def access_path_of(record: Mapping[str, Any]) -> str | None:
    """The first access endpoint, or ``None`` where the record declares no path.

    ``None`` rather than an empty string, so that a caller has to decide what
    to show; the API renders it as the literal ``"unavailable"``.
    """
    endpoints = record.get("access_endpoints") or []
    return endpoints[0] if endpoints else None


#: The mechanical part of Decision 1: every old ``status`` value the registry
#: shipped before this change, and the new state it becomes. Only the values
#: that rename or fold live here; the split (``implementing``) and the value
#: that depends on the rest of the record (``retired``) are decided in
#: ``migrate_status`` because a table cannot express them.
_MIGRATION: dict[str, str] = {
    "active": "operational",
    "credential_required": "credential-required",
    "licence_review": "licence-blocked",
    "duplicate_evidence": "superseded",
    "unsupported_field": "unavailable",
}


def migrate_status(
    record: Mapping[str, Any], adapter_ids: set[str] | frozenset[str]
) -> str:
    """The new state for a record still carrying an old ``status`` value.

    Mechanical by design, so the migration can be checked rather than argued:
    a record already written in the new vocabulary is returned unchanged,
    ``implementing`` is split by the objective test of Decision 1, ``retired``
    becomes ``superseded`` only where the record names its successor, and the
    remaining old values are a rename or a fold. An unrecognised value raises
    rather than guessing, because guessing is how a state gets widened.
    """
    status = record["status"]
    if status in STATES:
        return status
    if status == "implementing":
        return (
            "implemented-unverified"
            if implemented_unverified_ok(record, adapter_ids)
            else "catalogued"
        )
    if status == "retired":
        return "superseded" if record.get("superseded_by") else "unavailable"
    try:
        return _MIGRATION[status]
    except KeyError:
        raise ValueError(f"no migration rule for status {status!r}") from None
