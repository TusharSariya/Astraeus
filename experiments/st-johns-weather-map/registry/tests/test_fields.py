"""What the field catalogue promises, asserted rather than described.

The defect this catalogue exists to stop is a name that means two things, so
most of what is pinned here is a *refusal*: two quantities may not share a key,
two definitions may not be comparable, a humidity may not travel without its
phase, and a manifest may not name a key the catalogue lacks.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = REGISTRY_DIR.parent
for path in (str(REGISTRY_DIR), str(EXPERIMENT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import audit  # noqa: E402
import fields  # noqa: E402


class CatalogueShapeTests(unittest.TestCase):
    def test_the_catalogue_passes_its_own_schema_and_semantic_audit(self) -> None:
        self.assertEqual([], audit.catalogue_errors())

    def test_every_field_belongs_to_exactly_one_family(self) -> None:
        by_family = {name: set(fields.members(name)) for name in (item.name for item in fields.families())}
        seen: set[str] = set()
        for name, keys in by_family.items():
            overlap = seen & keys
            self.assertEqual(set(), overlap, f"{name} shares {sorted(overlap)} with another family")
            seen |= keys
        self.assertEqual(set(fields.keys()), seen)

    def test_a_key_the_catalogue_lacks_raises_rather_than_returning_a_placeholder(self) -> None:
        with self.assertRaises(fields.UnknownFieldKey):
            fields.field("total_cloud")
        self.assertFalse(fields.has_field("total_cloud"))

    def test_the_catalogue_declares_a_unit_and_a_class_set_for_every_key(self) -> None:
        for key in fields.keys():
            entry = fields.field(key)
            self.assertTrue(entry.evidence_classes, key)
            self.assertTrue(entry.description.strip(), key)
            for name in entry.evidence_classes:
                self.assertIn(name, fields.EVIDENCE_CLASSES, key)

    def test_the_schema_file_and_the_module_agree(self) -> None:
        schema = json.loads((REGISTRY_DIR / "fields.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(schema["required"]),
            sorted(fields.catalogue()),
            "the schema's required blocks and the materialized catalogue must be the same set",
        )


class OneQuantityPerKeyTests(unittest.TestCase):
    """The defect that started this change: one word, three quantities."""

    def test_opacity_weighted_and_geometric_cloud_are_distinct_keys(self) -> None:
        opacity = fields.field("total_cloud_opacity")
        geometric = fields.field("total_cloud_geometric")
        self.assertEqual("cloud_cover", opacity.family)
        self.assertEqual("cloud_cover", geometric.family)
        self.assertNotEqual(opacity.comparability_group, geometric.comparability_group)

    def test_the_six_hour_mean_is_a_third_key_and_never_an_instant(self) -> None:
        mean = fields.field("total_cloud_mean_6h")
        self.assertEqual("cloud_cover", mean.family)
        self.assertNotEqual(mean.comparability_group, fields.field("total_cloud_opacity").comparability_group)
        self.assertNotEqual(mean.comparability_group, fields.field("total_cloud_geometric").comparability_group)

    def test_opacity_and_geometric_cloud_are_not_comparable_and_say_why(self) -> None:
        verdict = fields.comparability("total_cloud_opacity", "total_cloud_geometric")
        self.assertFalse(verdict.comparable)
        self.assertEqual("definition", verdict.reason)
        self.assertIn("opacity", (verdict.detail or "").lower())

    def test_two_sources_of_the_same_quantity_are_comparable(self) -> None:
        """HRDPS and RDPS publish the same opacity-weighted cover, so they
        resolve to one key and one key is trivially comparable with itself."""
        self.assertEqual(
            "total_cloud_opacity", fields.key_for_upstream("eccc-hrdps", "HRDPS.CONTINENTAL_NT")
        )
        self.assertEqual(
            "total_cloud_opacity", fields.key_for_upstream("eccc-rdps", "RDPS_10km_TotalCloudCover")
        )
        self.assertTrue(fields.comparability("total_cloud_opacity", "total_cloud_opacity").comparable)

    def test_fields_of_different_families_are_not_comparable_at_all(self) -> None:
        verdict = fields.comparability("total_cloud_opacity", "kp_index")
        self.assertFalse(verdict.comparable)
        self.assertEqual("family", verdict.reason)


class HumidityPhaseTests(unittest.TestCase):
    def test_relative_humidity_requires_a_phase_and_specific_humidity_does_not(self) -> None:
        self.assertTrue(fields.requires_phase("relative_humidity_2m"))
        self.assertTrue(fields.requires_phase("relative_humidity_850hPa"))
        self.assertFalse(fields.requires_phase("specific_humidity_2m"))
        self.assertFalse(fields.requires_phase("dew_point_2m"))

    def test_liquid_and_mixed_are_not_comparable_below_freezing(self) -> None:
        verdict = fields.comparability(
            "relative_humidity_2m", "relative_humidity_2m",
            phase_a="liquid", phase_b="mixed", temperature_k=268.15,
        )
        self.assertFalse(verdict.comparable)
        self.assertEqual("phase", verdict.reason)

    def test_liquid_and_mixed_are_comparable_above_freezing(self) -> None:
        verdict = fields.comparability(
            "relative_humidity_2m", "relative_humidity_2m",
            phase_a="liquid", phase_b="mixed", temperature_k=283.15,
        )
        self.assertTrue(verdict.comparable)

    def test_a_humidity_without_a_phase_is_not_comparable_with_anything(self) -> None:
        verdict = fields.comparability("relative_humidity_2m", "relative_humidity_2m")
        self.assertFalse(verdict.comparable)
        self.assertEqual("phase_missing", verdict.reason)

    def test_the_measured_conventions_map_onto_the_two_phases(self) -> None:
        self.assertEqual("liquid", fields.phase_from_convention("liquid_water"))
        self.assertEqual("mixed", fields.phase_from_convention("mixed_linear_253K_273K"))
        self.assertIsNone(fields.phase_from_convention(""))
        self.assertIsNone(fields.phase_from_convention("whatever_the_adapter_felt_like"))

    def test_the_two_producers_declare_the_phases_the_research_measured(self) -> None:
        self.assertEqual("liquid", fields.phase_of("eccc-hrdps", "relative_humidity_2m"))
        self.assertEqual("mixed", fields.phase_of("noaa-gfs", "relative_humidity_2m"))


class LevelConventionTests(unittest.TestCase):
    def test_height_fields_carry_the_level_in_the_key(self) -> None:
        for key in ("temperature_2m", "temperature_40m", "temperature_80m", "temperature_120m"):
            entry = fields.field(key)
            self.assertIsNone(entry.level_coordinate, key)
            self.assertTrue(key.endswith(entry.level.replace(" ", "")), key)

    def test_a_forty_metre_field_is_not_a_level_of_the_profile_field(self) -> None:
        self.assertEqual("temperature_40m", fields.resolve("temperature_40m").key)
        self.assertIsNone(fields.resolve("temperature_40m").level)
        self.assertNotEqual("temperature_pressure", fields.resolve("temperature_40m").key)

    def test_a_pressure_level_field_is_one_key_with_a_level_coordinate(self) -> None:
        entry = fields.field("relative_humidity_pressure")
        self.assertEqual("pressure", entry.level_coordinate)
        self.assertTrue(entry.is_profile)

    def test_a_level_expanded_variable_resolves_to_the_one_profile_key(self) -> None:
        resolved = fields.resolve("relative_humidity_850hPa")
        self.assertEqual("relative_humidity_pressure", resolved.key)
        self.assertEqual("850 hPa", resolved.level)
        self.assertEqual("wind_u_pressure", fields.resolve("wind_u_200hPa").key)
        self.assertEqual("omega_pressure", fields.resolve("omega_500hPa").key)

    def test_no_key_carries_a_pressure_level_of_its_own(self) -> None:
        for key in fields.keys():
            self.assertFalse(key.endswith("hPa"), f"{key} puts a pressure level in the key")


class SourceMappingTests(unittest.TestCase):
    def test_a_non_subsetting_feed_records_what_it_does_not_store(self) -> None:
        for source_id in ("noaa-gfs", "noaa-gefs", "ecmwf-ifs", "dwd-icon-global"):
            scope = fields.source_scope(source_id)
            self.assertIsNotNone(scope, source_id)
            assert scope is not None
            self.assertEqual("none", scope.subsetting, source_id)
            self.assertEqual("family_fields_only", scope.policy, source_id)
            self.assertTrue(fields.available_not_stored(source_id), source_id)

    def test_a_subsetting_source_stores_every_published_field(self) -> None:
        for source_id in ("eccc-hrdps", "eccc-rdps", "eccc-gdps"):
            scope = fields.source_scope(source_id)
            assert scope is not None
            self.assertEqual("server_side", scope.subsetting, source_id)
            self.assertEqual("every_published_field", scope.policy, source_id)
            self.assertEqual((), fields.available_not_stored(source_id), source_id)

    def test_available_not_stored_is_distinct_from_a_gap_the_producer_leaves(self) -> None:
        self.assertEqual("available-not-stored", fields.storage_of("noaa-gefs", "cloud_ceiling"))
        # REPS publishes speed and no components, so direction is not
        # retrievable at all: a different answer from "published, not fetched".
        self.assertEqual("not-published", fields.storage_of("eccc-reps", "wind_direction_10m"))
        self.assertEqual("stored", fields.storage_of("eccc-hrdps", "total_cloud_opacity"))
        self.assertIsNone(fields.storage_of("eccc-hrdps", "kp_index"))

    def test_gefs_column_cloud_is_the_mean_and_its_instantaneous_records_are_not_stored(self) -> None:
        self.assertEqual("stored", fields.storage_of("noaa-gefs", "total_cloud_mean_6h"))
        self.assertEqual("available-not-stored", fields.storage_of("noaa-gefs", "total_cloud_geometric"))

    def test_a_producer_name_resolves_through_the_source_mapping(self) -> None:
        self.assertEqual(
            "relative_humidity_pressure",
            fields.key_for_upstream("eccc-hrdps", "HRDPS.CONTINENTAL.PRES_HR.500"),
        )
        self.assertIsNone(fields.key_for_upstream("eccc-hrdps", "HRDPS.CONTINENTAL_SOMETHING_NEW"))


class AdapterManifestTests(unittest.TestCase):
    """Task 1.2's gate: an uncatalogued manifest key must fail, not warn."""

    def test_an_uncatalogued_manifest_key_fails(self) -> None:
        from ingest.manifest import ManifestError, RequiredField  # noqa: PLC0415

        with self.assertRaises(ManifestError) as caught:
            RequiredField("total_cloud", "percent")
        self.assertIn("uncatalogued_field:total_cloud", str(caught.exception))

    def test_a_manifest_key_with_the_wrong_unit_fails(self) -> None:
        from ingest.manifest import ManifestError, RequiredField  # noqa: PLC0415

        with self.assertRaises(ManifestError) as caught:
            RequiredField("temperature_2m", "K")
        self.assertIn("bad_units:temperature_2m", str(caught.exception))

    def test_every_key_the_adapters_declare_today_resolves(self) -> None:
        declared = audit.declared_field_keys()
        self.assertTrue(declared, "no adapter manifests were found to check")
        for path, keys in sorted(declared.items()):
            for key in keys:
                self.assertTrue(fields.has_field(key), f"{path} declares uncatalogued {key!r}")


if __name__ == "__main__":
    unittest.main()
