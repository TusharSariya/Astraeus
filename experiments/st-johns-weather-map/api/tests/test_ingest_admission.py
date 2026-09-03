"""The scheduler's view of admission agrees with the registry's own.

``registry/admission.py`` decides whether a record's declaration permits a
fetch at all; ``IngestConfig.ingestible`` adds the scheduler's own conditions
(freshness, reach, cadence, the ensemble flag) on top of it. The one thing that
must never happen is the scheduler admitting something the registry refuses, so
this module checks the implication in that direction over every real record.
"""

from __future__ import annotations

import ingest.adapters  # noqa: F401  (registers the present adapter families)
from ingest.registry import _load_registry, get_config, registered_adapters
from registry import admission


def _records() -> list[dict]:
    return list(_load_registry()["sources"])


def test_every_ingestible_config_is_a_schedulable_declaration() -> None:
    """The scheduler never admits a record the registry refuses.

    Spec-Refs: experiments/st-johns-weather-map/openspec/specs/source-registry-catalogue/spec.md
    """
    adapter_ids = set(registered_adapters())
    for record in _records():
        source_id = str(record["id"])
        if not get_config(source_id).ingestible:
            continue
        assert admission.declaration_schedulable(record, adapter_ids), (
            f"{source_id} is ingestible but its declaration is not schedulable: "
            f"status {record['status']}, fixture {record['fixture_status']}, "
            f"integration {record['integration']['kind']}, "
            f"adapter registered: {source_id in adapter_ids}"
        )


def test_no_ingestible_config_carries_an_outstanding_condition() -> None:
    """An admission condition nobody has recorded as met stops a fetch."""
    for record in _records():
        source_id = str(record["id"])
        if admission.condition_outstanding(record):
            assert get_config(source_id).admission_condition_outstanding
            assert not get_config(source_id).ingestible, source_id


def test_only_implemented_unverified_records_are_ingestible() -> None:
    """Every other state is a catalogue entry, a blocked one or a dead one."""
    for record in _records():
        source_id = str(record["id"])
        if record["status"] != "implemented-unverified":
            assert not get_config(source_id).ingestible, f"{source_id} is {record['status']}"


def test_every_record_declares_a_state_in_the_vocabulary() -> None:
    for record in _records():
        assert record["status"] in admission.STATES, f"{record['id']}: {record['status']}"
        assert record["status"] != "operational", record["id"]
