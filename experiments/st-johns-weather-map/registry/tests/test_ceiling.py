"""The ceiling the API reads: what a response may report for a declared state.

The point of a ceiling is that it can only lower. ``operational`` is the state
no source may claim and no response may emit, and a state written against a
vocabulary this deployment does not know must fall to ``unavailable`` rather
than passing through and widening what gets emitted.

Plain unittest, importing nothing but ``registry/admission.py``, so it runs
under a system ``python3`` with no third-party package installed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REGISTRY_DIR = TESTS_DIR.parents[0]
sys.path.insert(0, str(REGISTRY_DIR))

import admission  # noqa: E402


class CeilingTableTests(unittest.TestCase):
    """The table itself: what each of the ten states maps to."""

    def test_the_ceiling_maps_every_state_to_itself_except_operational(self) -> None:
        for state in admission.STATES:
            expected = "unavailable" if state == "operational" else state
            with self.subTest(state=state):
                self.assertEqual(admission.ceiling_state(state), expected)

    def test_the_ceiling_lowers_operational_to_unavailable(self) -> None:
        self.assertEqual(admission.CEILING["operational"], "unavailable")
        self.assertEqual(admission.ceiling_state("operational"), "unavailable")

    def test_the_ceiling_covers_exactly_the_ten_states(self) -> None:
        self.assertEqual(tuple(admission.CEILING), admission.STATES)
        self.assertEqual(len(admission.STATES), 10)

    def test_the_ceiling_never_returns_a_state_outside_the_vocabulary(self) -> None:
        for state in admission.STATES:
            with self.subTest(state=state):
                self.assertIn(admission.ceiling_state(state), admission.STATES)


class UnknownStateCeilingTests(unittest.TestCase):
    """A state the table does not know falls, it does not pass through."""

    def test_an_unknown_state_ceilings_to_unavailable(self) -> None:
        for status in ("implementing", "invented-tomorrow", "", "OPERATIONAL"):
            with self.subTest(status=status):
                self.assertEqual(admission.ceiling_state(status), "unavailable")

    def test_active_is_not_a_state_and_ceilings_to_unavailable(self) -> None:
        self.assertNotIn("active", admission.STATES)
        self.assertNotIn("active", admission.CEILING)
        self.assertEqual(admission.ceiling_state("active"), "unavailable")

    def test_every_old_status_value_ceilings_to_unavailable(self) -> None:
        """The pre-migration vocabulary is gone; none of it survives the ceiling."""
        for status in (
            "active",
            "implementing",
            "credential_required",
            "licence_review",
            "duplicate_evidence",
            "unsupported_field",
            "retired",
        ):
            with self.subTest(status=status):
                self.assertEqual(admission.ceiling_state(status), "unavailable")


if __name__ == "__main__":
    unittest.main()
