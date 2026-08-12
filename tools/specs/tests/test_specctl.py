from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import specctl
import yaml
from jsonschema import Draft202012Validator


class SpecctlTests(unittest.TestCase):
    def load_module_registry(self) -> tuple[dict, dict]:
        registry = yaml.safe_load(
            specctl.MODULE_REGISTRY.read_text(encoding="utf-8")
        )
        schema = json.loads(
            specctl.MODULE_REGISTRY_SCHEMA.read_text(encoding="utf-8")
        )
        return registry, schema

    def test_markdown_slug_matches_github_style_for_requirement_heading(self) -> None:
        self.assertEqual(
            specctl.markdown_slug("ECL26-SAFE-001 — Unknown access"),
            "ecl26-safe-001-unknown-access",
        )

    def test_parse_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "document.md"
            path.write_text("---\nid: TEST\n---\n# Body\n", encoding="utf-8")
            metadata, body = specctl.parse_frontmatter(path)
            self.assertEqual(metadata["id"], "TEST")
            self.assertEqual(body, "# Body\n")

    def test_behavior_path_classification(self) -> None:
        self.assertTrue(specctl.behavior_changing(["services/api/main.py"]))
        self.assertTrue(
            specctl.behavior_changing(
                ["docs/specv1/features/eclipse-2026-08-12/SCIENCE_SPEC.md"]
            )
        )
        self.assertFalse(specctl.behavior_changing(["docs/research/note.md"]))

    def test_conventional_title(self) -> None:
        self.assertIsNotNone(
            specctl.CONVENTIONAL_RE.fullmatch(
                "feat(eclipse): implement local contact calculation"
            )
        )
        self.assertIsNone(specctl.CONVENTIONAL_RE.fullmatch("Implement feature"))

    def test_behavior_pr_requires_accepted_linked_requirement(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "feat(eclipse): implement local contact calculation",
                "body": (
                    "[ECL26-GEO-001](docs/specv1/features/eclipse-2026-08-12/"
                    "SCIENCE_SPEC.md#ecl26-geo-001-calculate-local-circumstances-per-candidate)\n\n"
                    "Spec-Refs: ECL26-GEO-001\n"
                    "Verification: geometry fixture passed\n"
                ),
                "labels": [],
            }
        }
        known = {"ECL26-GEO-001": {"status": "accepted"}}
        specctl.validate_pr_payload(
            validation, payload, known, ["services/api/geometry.py"]
        )
        self.assertEqual(validation.errors, [])

    def test_no_spec_impact_requires_rationale(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "docs(research): add provider notes",
                "body": "Spec-Impact: none\n",
                "labels": [],
            }
        }
        specctl.validate_pr_payload(
            validation, payload, {}, ["docs/research/provider.md"]
        )
        self.assertIn(
            "Spec-Impact: none requires No-Spec-Impact-Rationale",
            validation.errors,
        )

    def test_behavior_pr_without_spec_refs_is_rejected(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "feat(eclipse): implement local contact calculation",
                "body": "No traceability here\n",
                "labels": [],
            }
        }
        specctl.validate_pr_payload(
            validation, payload, {}, ["services/api/geometry.py"]
        )
        self.assertIn("behavior-changing PR requires Spec-Refs", validation.errors)

    def test_proposed_requirement_is_rejected(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "feat(eclipse): implement local contact calculation",
                "body": (
                    "[ECL26-GEO-001](docs/spec.md#ecl26-geo-001)\n"
                    "Spec-Refs: ECL26-GEO-001\n"
                    "Verification: fixture passed\n"
                ),
                "labels": [],
            }
        }
        specctl.validate_pr_payload(
            validation,
            payload,
            {"ECL26-GEO-001": {"status": "proposed"}},
            ["services/api/geometry.py"],
        )
        self.assertTrue(any("proposed requirement" in error for error in validation.errors))

    def test_requirement_without_clickable_link_is_rejected(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "feat(eclipse): implement local contact calculation",
                "body": (
                    "Spec-Refs: ECL26-GEO-001\n"
                    "Verification: fixture passed\n"
                ),
                "labels": [],
            }
        }
        specctl.validate_pr_payload(
            validation,
            payload,
            {"ECL26-GEO-001": {"status": "accepted"}},
            ["services/api/geometry.py"],
        )
        self.assertIn(
            "PR must include a clickable link for ECL26-GEO-001",
            validation.errors,
        )

    def test_commented_template_example_is_inert(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "feat(eclipse): implement local contact calculation",
                "body": (
                    "<!-- [GOV-SPEC-001](docs/spec.md#gov-spec-001)\n"
                    "Spec-Refs: GOV-SPEC-001 -->\n"
                ),
                "labels": [],
            }
        }
        specctl.validate_pr_payload(
            validation,
            payload,
            {"GOV-SPEC-001": {"status": "accepted"}},
            ["services/api/geometry.py"],
        )
        self.assertIn("behavior-changing PR requires Spec-Refs", validation.errors)

    def test_protected_status_change_requires_owner_label(self) -> None:
        validation = specctl.Validation()
        payload = {
            "pull_request": {
                "title": "spec(eclipse): accept geometry contract",
                "body": (
                    "[GOV-SPEC-002](docs/spec.md#gov-spec-002)\n"
                    "Spec-Refs: GOV-SPEC-002\n"
                    "Verification: owner review recorded\n"
                ),
                "labels": [],
            }
        }
        specctl.validate_pr_payload(
            validation,
            payload,
            {"GOV-SPEC-002": {"status": "accepted"}},
            ["docs/specv1/features/example/README.md"],
            ["docs/specv1/features/example/README.md"],
        )
        self.assertTrue(
            any("spec-status-approved" in error for error in validation.errors)
        )

    def test_observation_module_registry_is_schema_valid(self) -> None:
        registry, schema = self.load_module_registry()
        validation = specctl.Validation()
        self.assertTrue(
            specctl.validate_module_registry_data(validation, registry, schema)
        )
        self.assertEqual(validation.errors, [])

    def test_observation_module_registry_rejects_duplicate_identity(self) -> None:
        registry, schema = self.load_module_registry()
        registry["modules"].append(copy.deepcopy(registry["modules"][0]))
        validation = specctl.Validation()
        self.assertFalse(
            specctl.validate_module_registry_data(validation, registry, schema)
        )
        self.assertTrue(any("duplicate module identity" in error for error in validation.errors))

    def test_observation_module_registry_rejects_unknown_capability(self) -> None:
        registry, schema = self.load_module_registry()
        registry["modules"][0]["geometry_types"] = ["imaginary_geometry"]
        validation = specctl.Validation()
        self.assertFalse(
            specctl.validate_module_registry_data(validation, registry, schema)
        )
        self.assertTrue(any("imaginary_geometry" in error for error in validation.errors))

    def test_active_module_requires_owner_approval(self) -> None:
        registry, schema = self.load_module_registry()
        registry["modules"][0]["status"] = "active"
        validation = specctl.Validation()
        self.assertFalse(
            specctl.validate_module_registry_data(validation, registry, schema)
        )
        self.assertTrue(any("accepted_by" in error for error in validation.errors))

    def test_generic_plan_contract_has_no_eclipse_creation_path(self) -> None:
        openapi = yaml.safe_load(
            (specctl.SPEC_ROOT / "contracts" / "openapi.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("/v1/plans", openapi["paths"])
        self.assertNotIn("/v1/eclipse/plans", openapi["paths"])
        plan_request = openapi["components"]["schemas"]["PlanRequest"]
        self.assertEqual(plan_request["discriminator"]["propertyName"], "module_id")
        self.assertEqual(
            list(plan_request["discriminator"]["mapping"]), ["solar-eclipse"]
        )

    def test_score_component_applicability_is_fail_closed(self) -> None:
        openapi = yaml.safe_load(
            (specctl.SPEC_ROOT / "contracts" / "openapi.yaml").read_text(
                encoding="utf-8"
            )
        )
        schema = openapi["components"]["schemas"]["ScoreComponent"]
        validator = Draft202012Validator(schema)
        base = {
            "component_id": "atmospheric_transmission",
            "applicability": "not_applicable",
            "value": None,
            "evidence_quality": "not_applicable",
            "provenance_refs": [],
        }
        self.assertEqual(list(validator.iter_errors(base)), [])

        bad_not_applicable = {**base, "value": 100}
        self.assertTrue(list(validator.iter_errors(bad_not_applicable)))

        insufficient = {
            **base,
            "applicability": "applicable",
            "evidence_quality": "insufficient",
            "provenance_refs": ["provider-run"],
        }
        self.assertEqual(list(validator.iter_errors(insufficient)), [])

        bad_sufficient = {
            **insufficient,
            "evidence_quality": "high",
            "value": None,
        }
        self.assertTrue(list(validator.iter_errors(bad_sufficient)))


if __name__ == "__main__":
    unittest.main()
