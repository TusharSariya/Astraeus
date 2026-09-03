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


class EveryRecordDeclaresDeliveryTests(unittest.TestCase):
    """Task 4.0: the field itself, on every record, and the primary rule."""

    def test_every_record_declares_a_delivery_kind(self) -> None:
        for record in registry()["sources"]:
            self.assertIn(
                record["delivery_kind"],
                {"published_cell", "reprocessed", "intermediary_derived"},
                record["id"],
            )

    def test_a_record_without_a_delivery_kind_fails_the_audit(self) -> None:
        data = registry()
        data["sources"][0].pop("delivery_kind")
        _, errors = audit.validate(data)
        self.assertTrue(any("delivery_kind" in error or "declares no delivery kind" in error for error in errors))

    def test_a_reprocessed_record_names_its_intermediary_and_transformations(self) -> None:
        reprocessed = [item for item in registry()["sources"] if item["delivery_kind"] == "reprocessed"]
        self.assertEqual(["noaa-madis", "openaq", "raw-cwop-pws"], sorted(item["id"] for item in reprocessed))
        for record in reprocessed:
            self.assertTrue(record["intermediary"]["name"], record["id"])
            self.assertNotEqual(record["intermediary"]["name"].lower(), record["producer"].lower())
            self.assertTrue(record["intermediary"]["transformations"], record["id"])

    def test_a_reprocessed_record_naming_no_intermediary_fails(self) -> None:
        data = registry()
        next(item for item in data["sources"] if item["id"] == "openaq").pop("intermediary")
        _, errors = audit.validate(data)
        self.assertTrue(any("declares reprocessed and names no intermediary" in error for error in errors))

    def test_a_reprocessed_record_documenting_no_transformation_fails(self) -> None:
        data = registry()
        next(item for item in data["sources"] if item["id"] == "openaq")["intermediary"]["transformations"] = []
        _, errors = audit.validate(data)
        self.assertTrue(any("states no transformation" in error or "too short" in error for error in errors))

    def test_only_a_published_cell_record_may_be_the_display_primary(self) -> None:
        # A record that is not the producer's own cell is never the display
        # primary. The converse holds only where no restricted terms are
        # declared: a research-use-only record keeps its published cell and
        # still may not be what the map shows first (audit.export_errors).
        for record in registry()["sources"]:
            if record["display_primary"]:
                self.assertEqual("published_cell", record["delivery_kind"], record["id"])
            if "restricted_terms" not in record:
                self.assertEqual(record["delivery_kind"] == "published_cell", record["display_primary"], record["id"])

    def test_the_audit_refuses_a_reprocessed_record_as_a_display_primary(self) -> None:
        for source_id in ("openaq", RECORD_ID):
            with self.subTest(source_id):
                data = registry()
                next(item for item in data["sources"] if item["id"] == source_id)["display_primary"] = True
                _, errors = audit.validate(data)
                self.assertTrue(any("may not be the display primary" in error for error in errors))

    def test_the_summary_names_what_may_not_be_the_display_primary(self) -> None:
        data, errors = audit.validate()
        self.assertEqual([], errors)
        self.assertEqual(
            ["google-weathernext-2", "noaa-madis", "open-meteo-weathernext-2", "openaq", "raw-cwop-pws"],
            audit.summary(data)["not_display_primary"],
        )


class DeliveryKindTests(unittest.TestCase):
    def test_the_open_meteo_weathernext_record_passes_the_audit(self) -> None:
        data, errors = audit.validate()
        self.assertEqual([], errors)
        record = _record(data)
        self.assertEqual("intermediary_derived", record["delivery_kind"])
        self.assertEqual("credential-required", record["status"])
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
