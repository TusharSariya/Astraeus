"""What the admissions ledger decided about individual records.

The audit checks the shape of every record; this file checks that particular
owner decisions from the 2026-09-02 resolutions are the ones the registry
actually carries. A shape test would pass on a record that named the wrong
successor, so the successor is named here.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import audit  # noqa: E402
from source_data import registry  # noqa: E402


def _by_id() -> dict[str, dict]:
    return {source["id"]: source for source in registry()["sources"]}


class LedgerRecordTests(unittest.TestCase):
    def test_firework_is_superseded_by_raqdps(self) -> None:
        sources = _by_id()
        firework = sources["eccc-raqdps-firework"]

        self.assertEqual("superseded", firework["status"])
        successor = firework["superseded_by"]
        self.assertEqual("eccc-raqdps", successor["source_id"])
        self.assertIn("smoke-plume", successor["detail"])

        # A tombstone that pointed at nothing would still be a dead end, so the
        # successor has to be a record a reader can actually go and look at.
        self.assertIn(successor["source_id"], sources)

        # Nothing is expected from a superseded record, so neither test may sit
        # in a state that says one is still coming.
        self.assertEqual("not_applicable", firework["fixture_status"])
        self.assertEqual("not_applicable", firework["live_smoke_test_status"])

        _, errors = audit.validate()
        self.assertEqual([], errors)


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    unittest.main()
