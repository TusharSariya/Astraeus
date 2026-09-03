"""Reach, run cadence and measured publication latency, rule by rule.

Every test mutates a fresh copy of ``registry()`` and asserts the audit
notices, because the value of these rules is entirely in what they refuse. The
class and method names all carry "reach" so ``-k reach`` selects the file.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REGISTRY_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REGISTRY_DIR))

import audit  # noqa: E402
from source_data import registry  # noqa: E402


def _record(data: dict, source_id: str) -> dict:
    return next(item for item in data["sources"] if item["id"] == source_id)


class ReachDeclarationTests(unittest.TestCase):
    def test_reach_registry_passes_the_horizon_audit(self) -> None:
        self.assertEqual([], audit.horizon_errors(registry()))

    def test_reach_is_declared_by_every_registered_adapter_record(self) -> None:
        data = registry()
        declared = {item["id"] for item in data["sources"] if item.get("reach") is not None}
        missing = sorted(audit.adapter_source_ids() - declared)
        self.assertEqual([], missing)

    def test_reach_missing_on_an_adapter_record_is_refused(self) -> None:
        data = copy.deepcopy(registry())
        del _record(data, "eccc-hrdps")["reach"]
        errors = audit.horizon_errors(data)
        self.assertTrue(any("eccc-hrdps" in error and "declares no reach" in error for error in errors))

    def test_reach_for_an_adapter_id_absent_from_the_registry_is_refused(self) -> None:
        data = copy.deepcopy(registry())
        errors = audit.horizon_errors(data, adapter_ids=audit.adapter_source_ids() | {"invented-source"})
        self.assertTrue(any("invented-source" in error for error in errors))

    def test_reach_may_not_end_before_it_starts(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "eccc-hrdps")["reach"]["latest_hours"] = -1
        errors = audit.horizon_errors(data)
        self.assertTrue(any("earliest_hours is after latest_hours" in error for error in errors))

    def test_reach_of_an_observation_is_its_own_instant(self) -> None:
        for source_id in ("eccc-swob", "awc-metar-speci", "eccc-radar", "noaa-goes-east"):
            with self.subTest(source_id=source_id):
                reach = _record(registry(), source_id)["reach"]
                self.assertEqual({"earliest_hours": 0, "latest_hours": 0}, reach)

    def test_reach_values_match_the_planning_horizon_matrix(self) -> None:
        data = registry()
        expected = {
            "eccc-hrdps": 48, "eccc-rdps": 84, "eccc-gdps": 240, "eccc-reps": 72,
            "eccc-geps": 384, "dwd-icon-global": 180, "noaa-gfs": 384, "noaa-gefs": 384,
            "ecmwf-ifs": 360, "ecmwf-ens": 360, "ecmwf-aifs-single": 360, "ecmwf-aifs-ens": 360,
            "google-weathernext-2": 360,
        }
        for source_id, latest in expected.items():
            with self.subTest(source_id=source_id):
                self.assertEqual(latest, _record(data, source_id)["reach"]["latest_hours"])


class ReachPerCycleTests(unittest.TestCase):
    def test_reach_per_cycle_carries_the_ifs_short_cycles(self) -> None:
        for source_id in ("ecmwf-ifs", "ecmwf-ens"):
            with self.subTest(source_id=source_id):
                per_cycle = _record(registry(), source_id)["reach"]["per_cycle"]
                self.assertEqual({"00": 360, "06": 144, "12": 360, "18": 144}, per_cycle)

    def test_reach_per_cycle_is_absent_where_every_cycle_reaches_alike(self) -> None:
        for source_id in ("ecmwf-aifs-single", "ecmwf-aifs-ens", "noaa-gfs"):
            with self.subTest(source_id=source_id):
                self.assertNotIn("per_cycle", _record(registry(), source_id)["reach"])

    def test_reach_per_cycle_key_must_be_a_two_digit_utc_hour(self) -> None:
        data = copy.deepcopy(registry())
        reach = _record(data, "ecmwf-ifs")["reach"]
        reach["per_cycle"]["6"] = reach["per_cycle"].pop("06")
        errors = audit.horizon_errors(data)
        self.assertTrue(any("not a two-digit UTC hour" in error for error in errors))

    def test_reach_per_cycle_count_must_match_the_run_cadence(self) -> None:
        data = copy.deepcopy(registry())
        del _record(data, "ecmwf-ifs")["reach"]["per_cycle"]["18"]
        errors = audit.horizon_errors(data)
        self.assertTrue(any("states 3 cycles" in error for error in errors))

    def test_reach_per_cycle_needs_a_run_cadence_to_key_it_by(self) -> None:
        data = copy.deepcopy(registry())
        del _record(data, "ecmwf-ifs")["run_cadence_seconds"]
        errors = audit.horizon_errors(data)
        self.assertTrue(any("no run cadence to key it by" in error for error in errors))


class ReachCadenceTests(unittest.TestCase):
    def test_reach_forecast_record_needs_a_run_cadence(self) -> None:
        data = copy.deepcopy(registry())
        del _record(data, "eccc-hrdps")["run_cadence_seconds"]
        errors = audit.horizon_errors(data)
        self.assertTrue(any("declares no run cadence" in error for error in errors))

    def test_reach_forecast_record_needs_a_publication_latency(self) -> None:
        data = copy.deepcopy(registry())
        del _record(data, "eccc-hrdps")["publication_latency"]
        errors = audit.horizon_errors(data)
        self.assertTrue(any("declares no publication_latency" in error for error in errors))

    def test_reach_observation_record_needs_a_native_cadence(self) -> None:
        data = copy.deepcopy(registry())
        del _record(data, "eccc-radar")["native_cadence_seconds"]
        errors = audit.horizon_errors(data)
        self.assertTrue(any("declares no native cadence" in error for error in errors))

    def test_reach_record_may_not_declare_both_cadences(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "eccc-radar")["run_cadence_seconds"] = 21600
        errors = audit.horizon_errors(data)
        self.assertTrue(any("cannot use both" in error for error in errors))

    def test_reach_native_cadences_are_the_producers_own_intervals(self) -> None:
        data = registry()
        expected = {
            "eccc-radar": 360, "eccc-lightning": 600, "noaa-goes-east": 600,
            "awc-metar-speci": 3600, "eccc-swob": 3600, "noaa-swpc-rtsw": 60,
            "noaa-swpc-kp": 10800, "noaa-swpc-ovation": 600, "awc-taf": 600,
            "eccc-aqhi": 3600, "eccc-cap-alerts": 600,
        }
        for source_id, seconds in expected.items():
            with self.subTest(source_id=source_id):
                self.assertEqual(seconds, _record(data, source_id)["native_cadence_seconds"])

    def test_reach_audit_forecast_categories_match_the_scheduler(self) -> None:
        """The audit's copy of the forecast categories may not drift."""
        sys.path.insert(0, str(REGISTRY_DIR.parent))
        try:
            from ingest.registry import FORECAST_CATEGORIES
        except Exception as error:  # pragma: no cover - ingest needs numpy/xarray
            self.skipTest(f"ingest.registry is not importable here: {error}")
        self.assertEqual(set(FORECAST_CATEGORIES), set(audit.FORECAST_CATEGORIES))


class ReachLatencyTests(unittest.TestCase):
    def test_reach_seeds_are_the_matrix_measurements(self) -> None:
        data = registry()
        expected = {
            "dwd-icon-global": 12600, "noaa-gfs": 19080, "noaa-gefs": 19080,
            "ecmwf-ifs": 27360, "ecmwf-ens": 27360,
            "ecmwf-aifs-single": 27360, "ecmwf-aifs-ens": 27360,
        }
        for source_id, seconds in expected.items():
            with self.subTest(source_id=source_id):
                latency = _record(data, source_id)["publication_latency"]
                self.assertEqual(seconds, latency["estimate_seconds"])
                self.assertFalse(latency["measured"])
                self.assertEqual(0, latency["observation_count"])
                self.assertIn("planning-horizon-matrix", latency["basis"])

    def test_reach_unmeasured_sources_carry_a_null_estimate(self) -> None:
        data = registry()
        for source_id in ("eccc-gdps", "eccc-geps", "eccc-reps", "google-weathernext-2"):
            with self.subTest(source_id=source_id):
                latency = _record(data, source_id)["publication_latency"]
                self.assertIsNone(latency["estimate_seconds"])
                self.assertFalse(latency["measured"])
                self.assertEqual("none", latency["basis"])

    def test_reach_defaulted_latency_is_refused(self) -> None:
        data = copy.deepcopy(registry())
        latency = _record(data, "eccc-gdps")["publication_latency"]
        latency["estimate_seconds"] = 21600
        errors = audit.horizon_errors(data)
        self.assertTrue(any("no basis" in error for error in errors))

    def test_reach_latency_estimate_with_an_empty_basis_is_refused(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "noaa-gfs")["publication_latency"]["basis"] = "   "
        errors = audit.horizon_errors(data)
        self.assertTrue(any("no basis" in error for error in errors))

    def test_reach_unmeasured_latency_may_not_claim_observations(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "noaa-gfs")["publication_latency"]["observation_count"] = 3
        errors = audit.horizon_errors(data)
        self.assertTrue(any("claims 3 observations" in error for error in errors))

    def test_reach_unmeasured_latency_may_not_name_a_last_observed(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "noaa-gfs")["publication_latency"]["last_observed"] = "2026-09-02T05:18:00Z"
        errors = audit.horizon_errors(data)
        self.assertTrue(any("names a last observed instant" in error for error in errors))

    def test_reach_measured_latency_needs_an_observation_and_an_instant(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "noaa-gfs")["publication_latency"]["measured"] = True
        errors = audit.horizon_errors(data)
        self.assertTrue(any("carries no observation" in error for error in errors))
        self.assertTrue(any("names no last observed instant" in error for error in errors))

    def test_reach_null_estimate_must_report_measured_false(self) -> None:
        data = copy.deepcopy(registry())
        latency = _record(data, "noaa-gfs")["publication_latency"]
        latency["estimate_seconds"] = None
        latency["measured"] = True
        latency["observation_count"] = 2
        latency["last_observed"] = "2026-09-02T05:18:00Z"
        errors = audit.horizon_errors(data)
        self.assertTrue(any("does not report measured false" in error for error in errors))

    def test_reach_a_measured_latency_is_accepted_once_it_is_consistent(self) -> None:
        data = copy.deepcopy(registry())
        latency = _record(data, "noaa-gfs")["publication_latency"]
        latency.update(
            estimate_seconds=19000, observation_count=4,
            last_observed="2026-09-02T05:18:00Z", measured=True,
            basis="observed: 4 publications of noaa-gfs f384",
        )
        self.assertEqual([], audit.horizon_errors(data))


class ReachDatamartFallbackTests(unittest.TestCase):
    def test_reach_datamart_records_declare_the_dated_layout(self) -> None:
        data = registry()
        expected = {
            "eccc-hrdps": "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/{HH}/{FFF}/",
            "eccc-rdps": "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_rdps/10km/{HH}/{FFF}/",
            "eccc-gdps": "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_gdps/10km/{HH}/{FFF}/",
        }
        for source_id, path in expected.items():
            with self.subTest(source_id=source_id):
                self.assertEqual(path, _record(data, source_id)["datamart_fallback_path"])

    def test_reach_datamart_fallback_is_declared_nowhere_else(self) -> None:
        declared = {
            item["id"] for item in registry()["sources"]
            if item.get("datamart_fallback_path") is not None
        }
        self.assertEqual({"eccc-hrdps", "eccc-rdps", "eccc-gdps"}, declared)

    def test_reach_datamart_fallback_without_placeholders_is_refused(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "eccc-hrdps")["datamart_fallback_path"] = (
            "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/"
        )
        errors = audit.horizon_errors(data)
        self.assertTrue(any("missing {HH}, {FFF}" in error for error in errors))


class ReachSchemaTests(unittest.TestCase):
    def test_reach_full_audit_still_passes(self) -> None:
        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_reach_schema_refuses_an_unknown_subfield(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "eccc-hrdps")["reach"]["latest_days"] = 2
        _, errors = audit.validate(data)
        self.assertTrue(any("Additional properties" in error for error in errors))

    def test_reach_schema_refuses_a_zero_run_cadence(self) -> None:
        data = copy.deepcopy(registry())
        _record(data, "eccc-hrdps")["run_cadence_seconds"] = 0
        _, errors = audit.validate(data)
        self.assertTrue(errors)

    def test_reach_summary_counts_the_records_that_declare_one(self) -> None:
        report = audit.summary(registry())
        self.assertEqual(24, report["reach_declared"])
        self.assertEqual([], report["latency_measured"])
        # 17 adapters after horizon-tiers, plus the four ensemble adapters
        # (eccc-reps, ecmwf-aifs-ens, ecmwf-ens, noaa-gefs) registered by
        # ensemble-families-and-member-statistics, none schedulable.
        self.assertEqual(21, len(report["adapter_source_ids"]))


if __name__ == "__main__":
    unittest.main()
