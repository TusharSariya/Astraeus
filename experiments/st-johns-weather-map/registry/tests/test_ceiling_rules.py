"""The exported ceiling, the migration split, the export paths and the glossary.

Everything here is a rule about what may leave the registry rather than about
what a single record says. The real records still carry the old status values
until the migration task lands, so each test works against a deep copy
rewritten into the new vocabulary and then breaks exactly one thing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = TESTS_DIR.parents[0]
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(REGISTRY_DIR))

import admission  # noqa: E402
import audit  # noqa: E402
from test_admission import record, rewritten_registry  # noqa: E402


class OperationalCeilingTests(unittest.TestCase):
    """``operational`` is in the vocabulary and reachable from nowhere."""

    def test_a_record_declaring_operational_is_refused(self) -> None:
        data = rewritten_registry()
        record(data, "eccc-hrdps")["status"] = "operational"
        _, errors = audit.validate(data)
        self.assertTrue(
            any("declares operational, which no source may claim" in error for error in errors),
            errors[:5],
        )

    def test_operational_is_lowered_to_unavailable_in_the_ceiling(self) -> None:
        self.assertEqual("unavailable", admission.ceiling_state("operational"))

    def test_an_unknown_state_is_lowered_the_same_way_as_operational(self) -> None:
        # A record written against a future vocabulary must not widen what this
        # deployment emits, so an unrecognised name falls to the same floor
        # rather than passing through.
        self.assertEqual("unavailable", admission.ceiling_state("made-up"))
        self.assertEqual("unavailable", admission.ceiling_state(""))

    def test_every_state_but_operational_maps_to_itself(self) -> None:
        for state in admission.STATES:
            if state == "operational":
                continue
            with self.subTest(state):
                self.assertEqual(state, admission.ceiling_state(state))

    def test_the_summary_exports_the_ceiling_with_operational_lowered(self) -> None:
        report = audit.summary(rewritten_registry())
        self.assertEqual(
            {state: admission.ceiling_state(state) for state in admission.STATES},
            report["ceiling"],
        )
        self.assertEqual("unavailable", report["ceiling"]["operational"])


class MigrationSummaryTests(unittest.TestCase):
    """The Decision 1 mapping, and the summary that lets a run be checked."""

    def test_migrate_status_maps_every_old_value(self) -> None:
        adapters = {"wired"}
        cases = [
            ({"id": "x", "status": "active"}, "operational"),
            ({"id": "x", "status": "credential_required"}, "credential-required"),
            ({"id": "x", "status": "licence_review"}, "licence-blocked"),
            ({"id": "x", "status": "unavailable"}, "unavailable"),
            ({"id": "x", "status": "rejected"}, "rejected"),
            ({"id": "x", "status": "retired"}, "unavailable"),
            (
                {"id": "x", "status": "retired", "superseded_by": {"source_id": "y", "detail": "d"}},
                "superseded",
            ),
            ({"id": "x", "status": "duplicate_evidence"}, "superseded"),
            ({"id": "x", "status": "unsupported_field"}, "unavailable"),
        ]
        for source, expected in cases:
            with self.subTest(source["status"]):
                self.assertEqual(expected, admission.migrate_status(source, adapters))

    def test_migrate_status_splits_implementing_on_the_objective_test(self) -> None:
        wired = {
            "id": "wired",
            "status": "implementing",
            "integration": {"kind": "typed_adapter"},
            "fixture_status": "passing",
        }
        self.assertEqual("implemented-unverified", admission.migrate_status(wired, {"wired"}))

        for broken in ("no_adapter", "link_only", "fixture"):
            with self.subTest(broken):
                source = dict(wired, integration=dict(wired["integration"]))
                adapters = {"wired"}
                if broken == "no_adapter":
                    adapters = set()
                elif broken == "link_only":
                    source["integration"]["kind"] = "link_only"
                else:
                    source["fixture_status"] = "planned"
                self.assertEqual("catalogued", admission.migrate_status(source, adapters))

    def test_migrate_status_leaves_a_new_vocabulary_value_alone(self) -> None:
        for state in admission.STATES:
            with self.subTest(state):
                self.assertEqual(state, admission.migrate_status({"id": "x", "status": state}, set()))

    def test_migrate_status_refuses_to_guess_at_an_unknown_value(self) -> None:
        with self.assertRaises(ValueError):
            admission.migrate_status({"id": "x", "status": "invented"}, set())

    def test_the_summary_reports_the_migration_split_and_what_is_schedulable(self) -> None:
        data = rewritten_registry()
        report = audit.summary(data)
        counts = report["status_counts"]
        self.assertEqual(
            {
                "implemented-unverified": counts.get("implemented-unverified", 0),
                "catalogued": counts.get("catalogued", 0),
            },
            report["migration_split"],
        )
        self.assertEqual(
            len(data["sources"]),
            sum(counts.values()),
            "every record lands on exactly one state",
        )
        for state in counts:
            self.assertIn(state, admission.STATES, "no record left on a retired status value")

        adapters = audit.adapter_source_ids()
        self.assertEqual(
            sorted(
                source["id"] for source in data["sources"]
                if admission.declaration_schedulable(source, adapters)
            ),
            report["schedulable_by_registry"],
        )
        # Nothing outside the implemented state may be scheduled, so the
        # schedulable list can never be longer than that half of the split.
        self.assertLessEqual(
            len(report["schedulable_by_registry"]),
            report["migration_split"]["implemented-unverified"],
        )

    def test_the_summary_lists_the_admission_ledger_keys(self) -> None:
        data = rewritten_registry()
        report = audit.summary(data)
        for key in (
            "admission_conditions_outstanding",
            "research_use_only",
            "credential_required",
            "no_access_path",
        ):
            with self.subTest(key):
                self.assertEqual(sorted(report[key]), report[key], "ids are reported sorted")
        self.assertEqual(
            sorted(
                source["id"] for source in data["sources"]
                if source["status"] == "credential-required"
            ),
            report["credential_required"],
        )
        # Every existing key the summary carried before this change is still
        # there: the summary is added to, never replaced.
        for key in ("registry_version", "source_count", "status_counts", "adapter_source_ids", "catalogue"):
            self.assertIn(key, report)


class RestrictedTermsExportTests(unittest.TestCase):
    """Research-use admission, and the two paths its values may not take."""

    def setUp(self) -> None:
        self.data = rewritten_registry()
        self.source = record(self.data, "raw-cwop-pws")
        self.source["licence"]["review_state"] = "restricted"
        self.source["restricted_terms"] = {
            "terms_text": "Data are provided for research use only and may not be redistributed.",
            "terms_source_url": "https://example.invalid/terms",
            "redistribution": False,
            "read_date": "2026-09-02",
        }

    def test_a_well_formed_restricted_block_passes(self) -> None:
        _, errors = audit.validate(self.data)
        self.assertEqual([], errors)

    def test_restricted_terms_without_text_are_refused_by_the_schema(self) -> None:
        self.source["restricted_terms"]["terms_text"] = ""
        _, errors = audit.validate(self.data)
        self.assertTrue(any("restricted_terms" in error for error in errors), errors[:5])

    def test_restricted_terms_with_blank_text_are_refused_semantically(self) -> None:
        self.source["restricted_terms"]["terms_text"] = "  \n "
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("needs the verbatim clause, not blank text" in error for error in errors),
            errors[:5],
        )

    def test_restricted_terms_without_a_source_url_are_refused(self) -> None:
        del self.source["restricted_terms"]["terms_source_url"]
        _, errors = audit.validate(self.data)
        self.assertTrue(any("terms_source_url" in error for error in errors), errors[:5])

    def test_restricted_terms_need_a_restricted_licence_review_state(self) -> None:
        self.source["licence"]["review_state"] = "verified"
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("requires licence.review_state 'restricted'" in error for error in errors),
            errors[:5],
        )

    def test_a_restricted_record_may_not_be_the_display_primary(self) -> None:
        self.source["display_primary"] = True
        errors = audit.export_errors(self.data)
        self.assertTrue(
            any("may not be display_primary" in error for error in errors), errors
        )
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("may not be display_primary" in error for error in errors), errors[:5]
        )

    def test_a_restricted_record_may_not_be_consensus_eligible(self) -> None:
        self.source["consensus"]["eligible"] = True
        errors = audit.export_errors(self.data)
        self.assertTrue(
            any("may not be consensus-eligible" in error for error in errors), errors
        )

    def test_a_record_with_no_restricted_terms_takes_no_export_error(self) -> None:
        del self.source["restricted_terms"]
        self.source["licence"]["review_state"] = "verified"
        self.assertEqual([], audit.export_errors(self.data))


class NoEndpointTests(unittest.TestCase):
    """A source cited but never fetched has to look that way in both places."""

    def cited(self, data: dict, source_id: str, status: str) -> dict:
        source = record(data, source_id)
        source["status"] = status
        source["access_endpoints"] = []
        source["integration"]["kind"] = "link_only"
        source["fixture_status"] = "not_applicable"
        source["live_smoke_test_status"] = "not_applicable"
        return source

    def test_a_well_formed_citation_record_takes_no_endpoint_error(self) -> None:
        for status in ("link-only", "partnership-only"):
            with self.subTest(status):
                data = rewritten_registry()
                source = self.cited(data, "raw-cwop-pws", status)
                self.assertEqual([], audit.no_endpoint_errors(source))

    def test_a_citation_record_may_not_carry_an_access_endpoint(self) -> None:
        for status in ("link-only", "partnership-only"):
            with self.subTest(status):
                data = rewritten_registry()
                source = self.cited(data, "raw-cwop-pws", status)
                source["access_endpoints"] = ["https://example.invalid/data"]
                errors = audit.no_endpoint_errors(source)
                self.assertTrue(
                    any("may not carry an access endpoint" in error for error in errors), errors
                )

    def test_a_citation_record_must_declare_a_link_only_integration(self) -> None:
        for status in ("link-only", "partnership-only"):
            with self.subTest(status):
                data = rewritten_registry()
                source = self.cited(data, "raw-cwop-pws", status)
                source["integration"]["kind"] = "typed_adapter"
                errors = audit.no_endpoint_errors(source)
                self.assertTrue(
                    any("requires integration.kind 'link_only'" in error for error in errors),
                    errors,
                )

    def test_no_endpoint_errors_say_nothing_about_any_other_state(self) -> None:
        data = rewritten_registry()
        for source in data["sources"]:
            with self.subTest(source["id"]):
                self.assertEqual([], audit.no_endpoint_errors(source))

    def test_the_audit_reports_a_no_endpoint_failure_on_the_whole_registry(self) -> None:
        data = rewritten_registry()
        self.cited(data, "raw-cwop-pws", "link-only")["integration"]["kind"] = "typed_adapter"
        _, errors = audit.validate(data)
        self.assertTrue(
            any("requires integration.kind 'link_only'" in error for error in errors), errors[:5]
        )


class GlossaryTests(unittest.TestCase):
    """The glossary at the repo root and the schema enum name the same states."""

    def test_the_real_glossary_agrees_with_the_state_vocabulary(self) -> None:
        self.assertEqual([], audit.glossary_state_errors())

    def test_the_glossary_entry_still_explains_the_credential_state(self) -> None:
        text = (audit.HERE.parents[2] / "CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("credential-required", text)
        self.assertIn("credential-blocked", text)

    def test_a_glossary_that_drops_a_state_fails(self) -> None:
        import tempfile

        source = (audit.HERE.parents[2] / "CONTEXT.md").read_text(encoding="utf-8")
        mutated = source.replace(", superseded.", ".", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CONTEXT.md"
            path.write_text(mutated, encoding="utf-8")
            errors = audit.glossary_state_errors(path)
        self.assertTrue(any("omits superseded" in error for error in errors), errors)

    def test_a_glossary_naming_a_state_the_schema_lacks_fails(self) -> None:
        import tempfile

        source = (audit.HERE.parents[2] / "CONTEXT.md").read_text(encoding="utf-8")
        mutated = source.replace(", superseded.", ", superseded, invented-state.", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CONTEXT.md"
            path.write_text(mutated, encoding="utf-8")
            errors = audit.glossary_state_errors(path)
        self.assertTrue(any("invented-state" in error for error in errors), errors)

    def test_a_missing_glossary_is_an_error_and_not_a_skip(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            errors = audit.glossary_state_errors(Path(tmp) / "CONTEXT.md")
        self.assertTrue(any("is missing" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
