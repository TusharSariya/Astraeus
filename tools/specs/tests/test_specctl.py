from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import specctl


class SpecctlTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
