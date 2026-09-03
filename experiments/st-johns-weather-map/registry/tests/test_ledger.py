"""Ledger completeness: every source the resolutions decided is declared here.

The four owner resolutions of 2026-09-02 (tickets 24, 25, 26 and 28) name a
state, an access path or an explicit none, and a reason for every source in the
St. John's evidence layer. ``audit.LEDGER_SOURCE_IDS`` transcribes the ids from
the ledger table in ``openspec/changes/source-admissions-ledger/design.md``, and
what these tests hold is that the transcription is the right size, that the
registry is checked against it, and that a record cannot be declared without the
three things the ledger promised.

Nothing here calls ``audit.validate``. The registry on this branch is genuinely
short of the section 7 records, so the whole-registry audit is red by design
until they land; each test calls ``audit.ledger_errors`` directly so that it is
testing the rule rather than the state of the migration.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import audit  # noqa: E402
from source_data import registry  # noqa: E402

#: The ledger ids section 7 of ``tasks.md`` has still to write as records. This
#: constant is scaffolding for exactly one commit: once section 7 merges, the
#: change lead deletes it and asserts ``[]`` instead, and the assertion below
#: becomes the standing statement that the ledger is complete.
SECTION_7_IDS = [
    "7timer",
    "ccg-harbour-cameras",
    "ccg-navwarn",
    "city-st-johns-road-cameras",
    "eccc-gdwps",
    "eccc-riops",
    "falchi-night-sky-atlas",
    "globe-at-night",
    "meteosource",
    "netatmo",
    "nl-air-quality-csv",
    "noaa-nam",
    "noaa-rap",
    "ntv-cameras",
    "viirs-dnb-night-lights",
    "weather-underground",
]


def ledger_registry() -> dict:
    """A deep copy of the real registry, safe to break one field at a time."""
    return copy.deepcopy(registry())


def first_ledger_record(data: dict, status: str | None = None) -> dict:
    """A real record the ledger names, optionally in a given state.

    Tests break a record that actually exists rather than inventing one, so a
    rule cannot pass here against a shape the registry never writes.
    """
    for source in data["sources"]:
        if source["id"] not in audit.LEDGER_SOURCE_IDS:
            continue
        if status is None or source["status"] == status:
            return source
    raise AssertionError(f"no ledger record with status {status!r} in the registry")


class LedgerTranscriptionTest(unittest.TestCase):
    def test_ledger_transcription_holds_one_hundred_and_eleven_ids(self):
        # 112 distinct ids appear in the design's ledger table; Deviation 1
        # omits openmeteo-weathernext-2-cloud, and eccc-rdps appears twice in
        # the table and counts once.
        self.assertEqual(111, len(audit.LEDGER_SOURCE_IDS))

    def test_ledger_excludes_records_other_changes_govern(self):
        for source_id in ("dwd-icon-eps", "open-meteo-weathernext-2", "eccc-geps", "noaa-gefs"):
            self.assertNotIn(source_id, audit.LEDGER_SOURCE_IDS)


class LedgerCompletenessTest(unittest.TestCase):
    def test_ledger_names_a_decided_source_with_no_record(self):
        data = ledger_registry()
        removed = first_ledger_record(data)["id"]
        data["sources"] = [s for s in data["sources"] if s["id"] != removed]
        errors = audit.ledger_errors(data)
        self.assertTrue(
            any(error.startswith(f"{removed}: named in the 2026-09-02 resolutions") for error in errors),
            f"a removed ledger record was not reported: {errors}",
        )

    def test_ledger_missing_ids_are_the_records_section_seven_still_owes(self):
        # When section 7 merges, the change lead deletes SECTION_7_IDS and
        # asserts audit.ledger_missing_ids(registry()) == [].
        self.assertEqual(sorted(SECTION_7_IDS), audit.ledger_missing_ids(registry()))

    def test_ledger_missing_ids_are_sorted_and_absent_from_the_registry(self):
        data = ledger_registry()
        missing = audit.ledger_missing_ids(data)
        self.assertEqual(sorted(missing), missing)
        declared = {source["id"] for source in data["sources"]}
        self.assertEqual([], [source_id for source_id in missing if source_id in declared])


class LedgerRecordShapeTest(unittest.TestCase):
    def test_ledger_record_with_a_blank_reason_fails(self):
        data = ledger_registry()
        record = first_ledger_record(data)
        record["reason"] = "   "
        self.assertIn(
            f"{record['id']}: ledger record needs a reason, not blank text",
            audit.ledger_errors(data),
        )

    def test_ledger_record_with_an_unknown_state_fails(self):
        data = ledger_registry()
        record = first_ledger_record(data)
        record["status"] = "implementing"
        self.assertIn(
            f"{record['id']}: ledger record declares state 'implementing', which is not an admission state",
            audit.ledger_errors(data),
        )

    def test_ledger_implemented_unverified_record_with_no_endpoint_fails(self):
        data = ledger_registry()
        record = first_ledger_record(data, status="implemented-unverified")
        record["access_endpoints"] = []
        self.assertIn(
            f"{record['id']}: admitted implemented-unverified with no access endpoint; "
            "a retrievable source with no path is a contradiction",
            audit.ledger_errors(data),
        )

    def test_ledger_accepts_every_record_the_registry_carries_today(self):
        # Only the 16 absences are open. No record already written is short of
        # a state, a path or a reason, so the audit's ledger redness has one
        # cause and it is named.
        errors = [
            error
            for error in audit.ledger_errors(registry())
            if "named in the 2026-09-02 resolutions" not in error
        ]
        self.assertEqual([], errors)


class LedgerSummaryTest(unittest.TestCase):
    def test_ledger_summary_reports_declared_and_missing(self):
        data = registry()
        report = audit.summary(data)
        self.assertEqual(audit.ledger_missing_ids(data), report["ledger_missing"])
        self.assertEqual(
            len(audit.LEDGER_SOURCE_IDS) - len(report["ledger_missing"]),
            report["ledger_declared"],
        )


if __name__ == "__main__":
    unittest.main()
