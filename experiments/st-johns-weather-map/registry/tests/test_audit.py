from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import admission  # noqa: E402
import audit  # noqa: E402
from source_data import registry  # noqa: E402

#: True while the registry still carries the pre-admission status values. The
#: schema landed with task 1.1 and the records are rewritten by task 3.1, which
#: removes this skip.
_UNMIGRATED = any(s["status"] not in admission.STATES for s in registry()["sources"])


class RegistryAuditTests(unittest.TestCase):
    @unittest.skipIf(
        _UNMIGRATED,
        "the records still carry the old status vocabulary; task 3.1 migrates them and removes this skip",
    )
    def test_registry_passes_schema_and_semantic_audit(self) -> None:
        data, errors = audit.validate()
        self.assertEqual([], errors)
        self.assertGreaterEqual(len(data["sources"]), 50)

    def test_every_allowed_status_is_machine_enforced(self) -> None:
        data = registry()
        data["sources"][0]["status"] = "maybe"
        _, errors = audit.validate(data)
        self.assertTrue(any("not one of" in error or "invalid status" in error for error in errors))

    def test_credential_required_cannot_claim_anonymous_access(self) -> None:
        data = registry()
        source = next(item for item in data["sources"] if item["id"] == "nl-511")
        source["status"] = "credential-required"
        source["credential"] = {
            "name": "WEATHER_SECRET_NL511_API_KEY",
            "registration_url": source["authentication"]["registration_url"],
        }
        source["authentication"]["required"] = False
        _, errors = audit.validate(data)
        self.assertTrue(any("authentication.required=true" in error for error in errors))

    def test_operational_may_never_be_declared(self) -> None:
        data = registry()
        source = data["sources"][0]
        source["status"] = "operational"
        _, errors = audit.validate(data)
        self.assertTrue(
            any("declares operational, which no source may claim" in error for error in errors)
        )

    def test_all_registry_ids_are_covered_by_plan_catalogue(self) -> None:
        data = registry()
        coverage = audit.load_json(REGISTRY_DIR / "catalogue_coverage.json")
        errors = audit.semantic_errors(data, coverage)
        self.assertFalse(any("absent from catalogue coverage" in error for error in errors))

    def test_invalid_fixture_is_rejected(self) -> None:
        fixture = audit.load_json(REGISTRY_DIR / "fixtures" / "invalid-registry.json")
        _, errors = audit.validate(fixture)
        self.assertTrue(errors)


class EnsembleDeclarationTests(unittest.TestCase):
    """The ensemble block's own refusals, one bad record at a time.

    Each test edits a copy of the real registry, because the point of every
    rule is that a real declaration cannot drift into the shape being
    constructed here without the audit saying so.
    """

    def setUp(self) -> None:
        self.data = registry()

    def source(self, source_id: str) -> dict:
        return next(item for item in self.data["sources"] if item["id"] == source_id)

    def errors(self) -> list[str]:
        return audit.ensemble_errors(self.data)

    def test_the_real_registry_declares_six_clean_families(self) -> None:
        self.assertEqual([], self.errors())
        blocks = [item for item in self.data["sources"] if item.get("ensemble")]
        self.assertEqual(6, len(blocks))

    def test_ensemble_category_without_a_block_is_refused(self) -> None:
        del self.source("eccc-reps")["ensemble"]
        self.assertTrue(any("carries no ensemble block" in error for error in self.errors()))

    def test_a_block_on_a_non_ensemble_record_is_refused(self) -> None:
        block = copy.deepcopy(self.source("noaa-gefs")["ensemble"])
        self.source("noaa-gfs")["ensemble"] = block
        self.assertTrue(any("its category is" in error for error in self.errors()))

    def test_no_subsettability_is_refused(self) -> None:
        self.source("eccc-reps")["ensemble"]["subsetting"] = None
        self.assertTrue(any("neither 'server_side' nor 'none'" in error for error in self.errors()))

    def test_storage_scope_inconsistent_with_subsettability_is_refused(self) -> None:
        self.source("noaa-gefs")["ensemble"]["storage_scope"] = "every_published_field"
        self.assertTrue(any("forces storage_scope" in error for error in self.errors()))

    def test_a_scope_the_field_catalogue_contradicts_is_refused(self) -> None:
        block = self.source("eccc-reps")["ensemble"]
        block["subsetting"] = "none"
        block["storage_scope"] = "family_fields_only"
        self.assertTrue(any("may not disagree" in error for error in self.errors()))

    def test_members_without_a_control_block_are_refused(self) -> None:
        self.source("noaa-gefs")["ensemble"]["control"] = None
        self.assertTrue(any("no control block" in error for error in self.errors()))

    def test_a_control_block_with_no_rule_is_refused(self) -> None:
        self.source("eccc-reps")["ensemble"]["control"]["rule"] = "   "
        self.assertTrue(any("states no rule" in error for error in self.errors()))

    def test_a_null_control_identifier_is_allowed_where_the_rule_says_so(self) -> None:
        # REPS and ICON-EPS publish members whose control nobody located. The
        # rule is keyed on the block and its prose, never on a non-null token.
        for source_id in ("eccc-reps", "dwd-icon-eps"):
            self.assertIsNone(self.source(source_id)["ensemble"]["control"]["identifier"])
        self.assertEqual([], self.errors())

    def test_a_member_family_listing_provider_reductions_is_refused(self) -> None:
        self.source("noaa-gefs")["ensemble"]["reductions"] = ["mean"]
        self.assertTrue(any("lists provider reductions" in error for error in self.errors()))

    def test_a_reduction_family_with_a_control_or_a_count_is_refused(self) -> None:
        block = self.source("eccc-geps")["ensemble"]
        block["control"] = {"identifier": "0", "rule": "invented", "separate_retrieval": False}
        block["member_count"] = 20
        errors = self.errors()
        self.assertTrue(any("reduction shape and a control" in error for error in errors))
        self.assertTrue(any("publishes no member axis to count" in error for error in errors))

    def test_a_reduction_family_listing_no_reductions_is_refused(self) -> None:
        self.source("eccc-geps")["ensemble"]["reductions"] = []
        self.assertTrue(any("lists no reductions" in error for error in self.errors()))

    def test_an_unmeasured_family_may_not_declare_a_member_count(self) -> None:
        self.source("dwd-icon-eps")["ensemble"]["member_count"] = 40
        self.assertTrue(any("cannot be used to check completeness" in error for error in self.errors()))

    def test_a_measured_member_family_must_declare_a_member_count(self) -> None:
        self.source("noaa-gefs")["ensemble"]["member_count"] = None
        self.assertTrue(any("no member_count" in error for error in self.errors()))

    def test_a_gap_the_catalogue_stores_for_the_same_source_is_refused(self) -> None:
        self.source("noaa-gefs")["ensemble"]["gaps"].append(
            {"field": "total_cloud_mean_6h", "reason": "claimed absent while the catalogue stores it"}
        )
        self.assertTrue(any("may not also be declared published" in error for error in self.errors()))

    def test_a_gap_the_catalogue_records_available_not_stored_passes(self) -> None:
        # GEFS declares total_cloud_geometric a gap; the catalogue maps the
        # single-level records it does publish available-not-stored. Not the
        # same claim, and not a refusal.
        gaps = [item["field"] for item in self.source("noaa-gefs")["ensemble"]["gaps"]]
        self.assertIn("total_cloud_geometric", gaps)
        self.assertEqual("available-not-stored", audit.field_catalogue.storage_of("noaa-gefs", "total_cloud_geometric"))
        self.assertEqual([], self.errors())

    def test_a_gap_on_an_unknown_key_is_refused(self) -> None:
        self.source("eccc-reps")["ensemble"]["gaps"].append({"field": "no_such_field", "reason": "typo"})
        self.assertTrue(any("not a catalogue key" in error for error in self.errors()))

    def test_a_duplicate_build_order_is_refused(self) -> None:
        self.source("eccc-geps")["ensemble"]["build_order"] = 4
        errors = self.errors()
        self.assertTrue(any("exactly once each" in error for error in errors))

    def test_a_build_order_disagreeing_with_the_registry_constant_is_refused(self) -> None:
        self.source("eccc-reps")["ensemble"]["build_order"] = 6
        self.source("dwd-icon-eps")["ensemble"]["build_order"] = 1
        self.assertTrue(any("ENSEMBLE_BUILD_ORDER" in error for error in self.errors()))

    def test_schedulable_with_an_unverified_field_is_refused(self) -> None:
        self.source("eccc-reps")["ensemble"]["schedulable"] = True
        errors = self.errors()
        self.assertTrue(any("cadence unverified" in error for error in errors))

    def test_schedulable_with_no_evidence_is_refused(self) -> None:
        self.source("dwd-icon-eps")["ensemble"]["schedulable"] = True
        self.assertTrue(any("names no evidence" in error for error in self.errors()))

    def test_schedulable_may_not_count_completeness_against_an_assumption(self) -> None:
        block = self.source("ecmwf-ens")["ensemble"]
        block["schedulable"] = True
        self.assertTrue(any("checked against an assumption" in error for error in self.errors()))

    def test_no_family_in_the_real_registry_is_schedulable(self) -> None:
        for source in self.data["sources"]:
            block = source.get("ensemble")
            if block:
                self.assertFalse(block["schedulable"], source["id"])


if __name__ == "__main__":
    unittest.main()
