"""The intermediary-derived delivery kind and what a record declaring it carries.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/source-registry-catalogue/spec.md
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import audit  # noqa: E402
from source_data import registry  # noqa: E402

RECORD_ID = "open-meteo-weathernext-2"


def _record(data: dict) -> dict:
    return next(item for item in data["sources"] if item["id"] == RECORD_ID)


class DeliveryKindTests(unittest.TestCase):
    def test_the_open_meteo_weathernext_record_passes_the_audit(self) -> None:
        data, errors = audit.validate()
        self.assertEqual([], errors)
        record = _record(data)
        self.assertEqual("intermediary_derived", record["delivery_kind"])
        self.assertEqual("credential_required", record["status"])
        self.assertEqual("Google DeepMind", record["producer"])
        self.assertEqual("Open-Meteo", record["intermediary"]["name"])
        self.assertIn("relative humidity", record["intermediary"]["method"])
        self.assertTrue(record["intermediary"]["transformations"])

    def test_cloud_is_intermediary_derived_and_the_rest_is_reprocessed(self) -> None:
        kinds = _record(registry())["field_delivery_kinds"]
        for field in ("total_cloud", "low_cloud", "middle_cloud", "high_cloud"):
            self.assertEqual("intermediary_derived", kinds[field], field)
        for field in ("air_temperature", "dew_point", "mean_sea_level_pressure"):
            self.assertEqual("reprocessed", kinds[field], field)

    def test_the_summary_lists_the_record(self) -> None:
        data, errors = audit.validate()
        self.assertEqual([], errors)
        report = audit.summary(data)
        self.assertIn(RECORD_ID, report["intermediary_derived_sources"])
        self.assertEqual(1, report["delivery_kind_counts"]["intermediary_derived"])

    def test_a_record_naming_no_intermediary_fails_the_audit(self) -> None:
        data = registry()
        _record(data).pop("intermediary")
        _, errors = audit.validate(data)
        self.assertTrue(any(f"{RECORD_ID}: declares intermediary_derived and names no intermediary" in error for error in errors))

    def test_an_empty_intermediary_name_fails_the_audit(self) -> None:
        data = registry()
        _record(data)["intermediary"]["name"] = ""
        _, errors = audit.validate(data)
        self.assertTrue(any("names no intermediary" in error or "minLength" in error or "too short" in error for error in errors))

    def test_the_intermediary_must_be_distinct_from_the_producer(self) -> None:
        data = registry()
        _record(data)["intermediary"]["name"] = "Google DeepMind"
        _, errors = audit.validate(data)
        self.assertTrue(any("distinct from the producer" in error for error in errors))

    def test_a_record_declaring_the_kind_must_name_a_field_that_carries_it(self) -> None:
        data = registry()
        record = _record(data)
        record["field_delivery_kinds"] = {name: "reprocessed" for name in record["field_delivery_kinds"]}
        _, errors = audit.validate(data)
        self.assertTrue(any("names no field that carries it" in error for error in errors))

    def test_a_per_field_kind_may_not_exceed_the_record_kind(self) -> None:
        data = registry()
        record = _record(data)
        record["delivery_kind"] = "reprocessed"
        _, errors = audit.validate(data)
        self.assertTrue(any("is intermediary_derived but the record is not" in error for error in errors))

    def test_a_per_field_kind_names_a_field_the_record_publishes(self) -> None:
        data = registry()
        _record(data)["field_delivery_kinds"]["ceiling"] = "reprocessed"
        _, errors = audit.validate(data)
        self.assertTrue(any("which the record does not publish" in error for error in errors))

    def test_an_intermediary_without_a_delivery_kind_is_refused(self) -> None:
        data = registry()
        source = next(item for item in data["sources"] if item["id"] == "eccc-hrdps")
        source["intermediary"] = {"name": "Someone", "method": None, "transformations": ["regrid"]}
        _, errors = audit.validate(data)
        self.assertTrue(any("names an intermediary but its delivery kind" in error for error in errors))

    def test_an_unknown_delivery_kind_is_rejected_by_the_schema(self) -> None:
        data = registry()
        _record(data)["delivery_kind"] = "vibes"
        _, errors = audit.validate(data)
        self.assertTrue(any("vibes" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
