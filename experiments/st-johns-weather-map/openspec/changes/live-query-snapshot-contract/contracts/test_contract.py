from datetime import datetime
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


SCHEMA = json.loads(Path(__file__).with_name("live-query.schema.json").read_text())


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]},
        format_checker=FormatChecker(),
    )


SELECTION = {
    "latitude": 47.5615,
    "longitude": -52.7126,
    "valid_time": "2026-09-06T12:00:00Z",
    "product": "HRDPS",
    "layer_ids": ["hrdps-total-cloud", "eccc-radar"],
}


class LiveQueryContractTests(unittest.TestCase):
    def test_snapshot_closes_every_revision_axis_for_the_selection(self) -> None:
        snapshot = {
            "snapshot_id": "snap-1",
            "selection": SELECTION,
            "selected_at": "2026-09-06T12:00:00Z",
            "expires_at": "2026-09-06T12:15:00Z",
            "state": "current",
            "revision_set": {
                "manifest_revisions": [{"source_id": "eccc-hrdps", "logical_stream": "surface", "revision_id": "rev-7"}],
                "registry_revision": "registry-3",
                "field_catalogue_revision": "fields-4",
                "derivation_versions": {"liquid_fog_state": "1"},
                "inventory_revision": "inventory-9",
            },
        }
        validator("snapshot").validate(snapshot)
        selected = datetime.fromisoformat(snapshot["selected_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(snapshot["expires_at"].replace("Z", "+00:00"))
        self.assertEqual((expires - selected).total_seconds(), 900)

    def test_snapshot_cannot_hide_revision_axes_or_add_mutable_fields(self) -> None:
        incomplete = {
            "snapshot_id": "snap-1", "selection": SELECTION,
            "selected_at": "2026-09-06T12:00:00Z", "expires_at": "2026-09-06T12:15:00Z",
            "state": "current", "revision_set": {"manifest_revisions": []},
        }
        with self.assertRaises(ValidationError):
            validator("snapshot").validate(incomplete)

    def test_selection_refresh_is_bound_to_the_baseline(self) -> None:
        validator("refresh_request").validate({"baseline_snapshot_id": "snap-1", "selection": SELECTION})
        with self.assertRaises(ValidationError):
            validator("refresh_request").validate({"selection": SELECTION})

    def test_partial_job_names_each_fragment_outcome(self) -> None:
        job = {
            "job_id": "job-1", "idempotency_key": "sha256:abc", "baseline_snapshot_id": "snap-1", "state": "partial",
            "fragment_outcomes": [
                {"source_id": "eccc-hrdps", "fragment_key": "surface/12Z/cloud", "outcome": "published", "manifest_revision": "rev-8"},
                {"source_id": "eccc-radar", "fragment_key": "rain/1210Z", "outcome": "retrieval_failed", "manifest_revision": None},
            ],
        }
        validator("refresh_job").validate(job)


if __name__ == "__main__":
    unittest.main()
