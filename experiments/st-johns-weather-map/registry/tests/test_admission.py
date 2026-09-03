"""The admission vocabulary and the four record blocks that hang off it.

The real registry still carries the old status values until the migration task
lands, so nothing here asserts that the registry as written passes. Each test
instead rewrites a deep copy of the real records into the new vocabulary and
then breaks exactly one thing, because the point of every rule is that a real
declaration cannot drift into the shape being constructed here without the
audit saying so.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import admission  # noqa: E402
import audit  # noqa: E402
from source_data import registry  # noqa: E402

#: The mechanical mapping of Decision 1, applied here so the tests have a
#: registry in the new vocabulary to work against before task 3.1 writes one.
#: ``retired`` lands on ``unavailable`` rather than ``superseded`` because the
#: successor is a per-record judgement the migration task makes, not this file.
def rewritten_registry() -> dict:
    data = copy.deepcopy(registry())
    adapters = audit.adapter_source_ids()
    for source in data["sources"]:
        status = source["status"]
        if status == "implementing":
            if source["id"] in adapters and source["integration"]["kind"] != "link_only":
                source["fixture_status"] = "passing"
                source["status"] = "implemented-unverified"
            else:
                source["status"] = "catalogued"
        elif status == "credential_required":
            url = source["authentication"]["registration_url"]
            source["authentication"]["required"] = True
            source["status"] = "credential-required"
            source["credential"] = {
                "name": "WEATHER_SECRET_" + source["id"].upper().replace("-", "_"),
                "registration_url": url,
            }
        elif status == "licence_review":
            source["status"] = "licence-blocked"
        elif status == "retired":
            source["status"] = "unavailable"
    return data


def record(data: dict, source_id: str) -> dict:
    return next(item for item in data["sources"] if item["id"] == source_id)


class VocabularyTests(unittest.TestCase):
    def test_the_ten_states_are_in_the_pinned_order(self) -> None:
        self.assertEqual(
            (
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
            ),
            admission.STATES,
        )
        self.assertEqual(set(admission.STATES), audit.ALLOWED_STATUSES)

    def test_operational_is_refused(self) -> None:
        data = rewritten_registry()
        data["sources"][0]["status"] = "operational"
        _, errors = audit.validate(data)
        self.assertTrue(
            any("declares operational, which no source may claim" in error for error in errors),
            errors[:5],
        )

    def test_the_ceiling_never_lets_operational_out(self) -> None:
        self.assertEqual("unavailable", admission.ceiling_state("operational"))
        self.assertEqual("unavailable", admission.ceiling_state("something-else"))
        for state in admission.STATES:
            if state != "operational":
                self.assertEqual(state, admission.ceiling_state(state))

    def test_old_status_values_are_refused(self) -> None:
        for stale in (
            "implementing",
            "credential_required",
            "licence_review",
            "retired",
            "duplicate_evidence",
            "unsupported_field",
            "active",
        ):
            with self.subTest(stale):
                data = rewritten_registry()
                data["sources"][0]["status"] = stale
                _, errors = audit.validate(data)
                self.assertTrue(
                    any(f"invalid status {stale!r}" in error for error in errors),
                    errors[:5],
                )

    def test_the_rewritten_registry_is_clean_under_the_new_vocabulary(self) -> None:
        _, errors = audit.validate(rewritten_registry())
        self.assertEqual([], errors)


class CredentialBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = rewritten_registry()
        self.source = record(self.data, "nl-511")

    def test_credential_block_required(self) -> None:
        del self.source["credential"]
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("credential-required needs a credential block" in error for error in errors),
            errors[:5],
        )

    def test_a_credential_block_without_the_state_is_refused(self) -> None:
        other = record(self.data, "eccc-hrdps")
        other["credential"] = dict(self.source["credential"])
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("credential block without status credential-required" in error for error in errors),
            errors[:5],
        )

    def test_no_value_field_may_be_written_into_the_block(self) -> None:
        self.source["credential"]["value"] = "not-a-real-key"
        _, errors = audit.validate(self.data)
        self.assertTrue(any("Additional properties" in error for error in errors), errors[:5])

    def test_the_name_must_be_a_weather_secret_variable(self) -> None:
        self.source["credential"]["name"] = "NL511_API_KEY"
        _, errors = audit.validate(self.data)
        self.assertTrue(any("WEATHER_SECRET" in error for error in errors), errors[:5])

    def test_the_authentication_block_must_agree(self) -> None:
        self.source["authentication"]["required"] = False
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("authentication.required=true" in error for error in errors), errors[:5]
        )


class RestrictedTermsTests(unittest.TestCase):
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

    def test_a_well_formed_block_passes(self) -> None:
        _, errors = audit.validate(self.data)
        self.assertEqual([], errors)

    def test_restricted_terms_require_text(self) -> None:
        self.source["restricted_terms"]["terms_text"] = "   "
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("needs the verbatim clause, not blank text" in error for error in errors),
            errors[:5],
        )

    def test_redistribution_may_not_be_claimed(self) -> None:
        self.source["restricted_terms"]["redistribution"] = True
        _, errors = audit.validate(self.data)
        self.assertTrue(errors)

    def test_the_licence_review_state_must_say_restricted(self) -> None:
        self.source["licence"]["review_state"] = "verified"
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("requires licence.review_state 'restricted'" in error for error in errors),
            errors[:5],
        )


class SupersededTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = rewritten_registry()
        self.source = record(self.data, "eccc-raqdps-firework")
        self.source["status"] = "superseded"

    def test_superseded_requires_successor(self) -> None:
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("must name its successor in superseded_by" in error for error in errors),
            errors[:5],
        )

    def test_the_successor_must_be_a_record_that_exists(self) -> None:
        self.source["superseded_by"] = {
            "source_id": "not-a-record",
            "detail": "RAQDPS smoke-plume layers",
        }
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("superseded_by names unknown source id" in error for error in errors),
            errors[:5],
        )

    def test_a_named_successor_satisfies_the_rule(self) -> None:
        self.source["superseded_by"] = {
            "source_id": "eccc-raqdps",
            "detail": "RAQDPS smoke-plume layers",
        }
        _, errors = audit.validate(self.data)
        self.assertEqual([], errors)

    def test_superseded_by_without_the_state_is_refused(self) -> None:
        self.source["status"] = "unavailable"
        self.source["superseded_by"] = {
            "source_id": "eccc-raqdps",
            "detail": "RAQDPS smoke-plume layers",
        }
        _, errors = audit.validate(self.data)
        self.assertTrue(
            any("superseded_by without status superseded" in error for error in errors),
            errors[:5],
        )


class AdmissionConditionTests(unittest.TestCase):
    """The condition is the registry's half of schedulability, on its own.

    Built from a synthetic record rather than a real one, because what is under
    test is the rule and not any particular source: an implemented record with
    an adapter and a passing fixture is schedulable, and the only thing taken
    away between the two assertions is the satisfied flag.
    """

    def synthetic(self) -> dict:
        return {
            "id": "synthetic-source",
            "status": "implemented-unverified",
            "integration": {"kind": "typed_adapter"},
            "fixture_status": "passing",
            "access_endpoints": ["https://example.invalid/data"],
        }

    def test_condition_blocks_schedulability(self) -> None:
        adapter_ids = {"synthetic-source"}
        source = self.synthetic()
        source["admission_condition"] = {
            "condition": "no licence answer from the producer",
            "satisfied_by": "a written answer permitting research use",
            "satisfied": False,
            "recorded_on": "2026-09-02",
        }
        self.assertTrue(admission.condition_outstanding(source))
        self.assertTrue(admission.implemented_unverified_ok(source, adapter_ids))
        self.assertFalse(admission.declaration_schedulable(source, adapter_ids))

        source["admission_condition"]["satisfied"] = True
        self.assertFalse(admission.condition_outstanding(source))
        self.assertTrue(admission.declaration_schedulable(source, adapter_ids))

    def test_a_record_with_no_condition_is_not_blocked(self) -> None:
        source = self.synthetic()
        self.assertFalse(admission.condition_outstanding(source))
        self.assertTrue(admission.declaration_schedulable(source, {"synthetic-source"}))

    def test_only_implemented_unverified_is_schedulable(self) -> None:
        for state in admission.STATES:
            if state == "implemented-unverified":
                continue
            with self.subTest(state):
                source = self.synthetic()
                source["status"] = state
                self.assertFalse(admission.declaration_schedulable(source, {"synthetic-source"}))

    def test_a_blank_condition_is_refused(self) -> None:
        data = rewritten_registry()
        record(data, "eccc-hrdps")["admission_condition"] = {
            "condition": "   ",
            "satisfied_by": "   ",
            "satisfied": False,
            "recorded_on": "2026-09-02",
        }
        _, errors = audit.validate(data)
        self.assertTrue(
            any("needs a condition, not blank text" in error for error in errors), errors[:5]
        )
        self.assertTrue(
            any("needs to say what would satisfy it" in error for error in errors), errors[:5]
        )


class NoAccessPathTests(unittest.TestCase):
    def test_a_link_only_record_may_not_carry_an_endpoint(self) -> None:
        data = rewritten_registry()
        source = record(data, "eccc-hrdps")
        source["status"] = "link-only"
        _, errors = audit.validate(data)
        self.assertTrue(
            any("declares no data path, so access_endpoints must be empty" in error for error in errors),
            errors[:5],
        )

    def test_access_path_of_reads_the_first_endpoint_or_none(self) -> None:
        self.assertEqual(
            "https://example.invalid/a",
            admission.access_path_of({"access_endpoints": ["https://example.invalid/a"]}),
        )
        self.assertIsNone(admission.access_path_of({"access_endpoints": []}))
        self.assertIsNone(admission.access_path_of({}))


if __name__ == "__main__":
    unittest.main()
