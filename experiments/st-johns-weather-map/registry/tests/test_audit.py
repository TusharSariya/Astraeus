from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import audit  # noqa: E402
from source_data import registry  # noqa: E402


class RegistryAuditTests(unittest.TestCase):
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
        source["authentication"]["required"] = False
        _, errors = audit.validate(data)
        self.assertTrue(any("credential_required" in error for error in errors))

    def test_active_requires_fixture_and_live_evidence(self) -> None:
        data = registry()
        source = data["sources"][0]
        source["status"] = "active"
        _, errors = audit.validate(data)
        self.assertTrue(any("active requires passing" in error for error in errors))

    def test_all_registry_ids_are_covered_by_plan_catalogue(self) -> None:
        data = registry()
        coverage = audit.load_json(REGISTRY_DIR / "catalogue_coverage.json")
        errors = audit.semantic_errors(data, coverage)
        self.assertFalse(any("absent from catalogue coverage" in error for error in errors))

    def test_invalid_fixture_is_rejected(self) -> None:
        fixture = audit.load_json(REGISTRY_DIR / "fixtures" / "invalid-registry.json")
        _, errors = audit.validate(fixture)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
