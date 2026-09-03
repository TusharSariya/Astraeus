"""Which declarations may be fetched at all, state by state.

``declaration_schedulable`` is the registry half of schedulability: it answers
only whether the record's own declaration permits a fetch. One state permits
it, and only then when a registered adapter claims the id, the integration is
more than a bare link, the fixture suite passes and no admission condition
stands outstanding. Every other state is refused, and the refusal is a fact
about the record rather than about anything the worker observed.

Plain unittest, importing nothing but ``registry/admission.py``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = TESTS_DIR.parents[0]
sys.path.insert(0, str(REGISTRY_DIR))

import admission  # noqa: E402

ADAPTER_IDS = frozenset({"eccc-hrdps"})


def _record(**overrides: object) -> dict:
    """A record that is schedulable, so each test breaks exactly one thing."""
    record = {
        "id": "eccc-hrdps",
        "status": "implemented-unverified",
        "integration": {"kind": "http_client", "client": "httpx"},
        "fixture_status": "passing",
        "access_endpoints": ["https://dd.weather.gc.ca/model_hrdps/"],
    }
    record.update(overrides)
    return record


class SchedulableStateTests(unittest.TestCase):
    """Only implemented-unverified is a schedulable state."""

    def test_the_baseline_record_is_schedulable(self) -> None:
        self.assertTrue(admission.declaration_schedulable(_record(), ADAPTER_IDS))

    def test_the_schedulable_set_holds_one_state(self) -> None:
        self.assertEqual(admission.SCHEDULABLE_STATES, frozenset({"implemented-unverified"}))

    def test_no_other_state_is_schedulable(self) -> None:
        for state in (
            "catalogued",
            "credential-required",
            "licence-blocked",
            "link-only",
            "partnership-only",
            "unavailable",
            "rejected",
            "superseded",
            "operational",
        ):
            with self.subTest(state=state):
                self.assertFalse(
                    admission.declaration_schedulable(_record(status=state), ADAPTER_IDS)
                )

    def test_an_unknown_state_is_not_schedulable(self) -> None:
        for state in ("implementing", "active", "invented-tomorrow"):
            with self.subTest(state=state):
                self.assertFalse(
                    admission.declaration_schedulable(_record(status=state), ADAPTER_IDS)
                )


class SchedulableWiringTests(unittest.TestCase):
    """The three objective conditions behind implemented-unverified."""

    def test_a_record_no_adapter_claims_is_not_schedulable(self) -> None:
        self.assertFalse(admission.declaration_schedulable(_record(), frozenset()))
        self.assertFalse(
            admission.declaration_schedulable(_record(id="eccc-radiosonde"), ADAPTER_IDS)
        )

    def test_a_link_only_integration_is_not_schedulable(self) -> None:
        record = _record(integration={"kind": "link_only", "client": "none"})
        self.assertFalse(admission.declaration_schedulable(record, ADAPTER_IDS))

    def test_a_fixture_that_is_not_passing_is_not_schedulable(self) -> None:
        for fixture in ("planned", "failing", "not_applicable"):
            with self.subTest(fixture=fixture):
                self.assertFalse(
                    admission.declaration_schedulable(
                        _record(fixture_status=fixture), ADAPTER_IDS
                    )
                )


class SchedulableConditionTests(unittest.TestCase):
    """An admission subject to a check is not an admission until it is recorded."""

    def test_an_outstanding_condition_makes_a_wired_record_unschedulable(self) -> None:
        record = _record(
            admission_condition={
                "condition": "the Atlantic-domain check over the evidence box is unrecorded",
                "satisfied_by": "a recorded probe covering the box",
                "satisfied": False,
                "recorded_on": "2026-09-02",
            }
        )
        self.assertTrue(admission.condition_outstanding(record))
        self.assertFalse(admission.declaration_schedulable(record, ADAPTER_IDS))

    def test_a_satisfied_condition_leaves_the_record_schedulable(self) -> None:
        record = _record(
            admission_condition={
                "condition": "the Atlantic-domain check over the evidence box",
                "satisfied_by": "a recorded probe covering the box",
                "satisfied": True,
                "recorded_on": "2026-09-02",
            }
        )
        self.assertFalse(admission.condition_outstanding(record))
        self.assertTrue(admission.declaration_schedulable(record, ADAPTER_IDS))

    def test_a_record_with_no_condition_block_is_not_blocked(self) -> None:
        self.assertFalse(admission.condition_outstanding(_record()))


class SchedulableAccessPathTests(unittest.TestCase):
    """A record with no declared path has None, never an empty string."""

    def test_access_path_of_is_none_for_empty_endpoints(self) -> None:
        self.assertIsNone(admission.access_path_of(_record(access_endpoints=[])))
        self.assertIsNone(admission.access_path_of({"id": "x"}))

    def test_access_path_of_reads_the_first_endpoint(self) -> None:
        record = _record(access_endpoints=["https://first/", "https://second/"])
        self.assertEqual(admission.access_path_of(record), "https://first/")

    def test_the_no_path_states_are_the_three_that_declare_no_data_path(self) -> None:
        self.assertEqual(
            admission.NO_ACCESS_PATH_STATES,
            frozenset({"link-only", "partnership-only", "rejected"}),
        )
        for state in admission.NO_ACCESS_PATH_STATES:
            with self.subTest(state=state):
                self.assertNotIn(state, admission.SCHEDULABLE_STATES)


if __name__ == "__main__":
    unittest.main()
