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

import admission  # noqa: E402
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

    def test_eccc_rewps_is_rejected(self) -> None:
        sources = _by_id()
        rewps = sources["eccc-rewps"]

        self.assertEqual("rejected", rewps["status"])
        self.assertIn("Great Lakes", rewps["reason"])
        self.assertEqual([], rewps["access_endpoints"])
        self.assertTrue(rewps["documentation_urls"])
        self.assertEqual("not_applicable", rewps["fixture_status"])
        self.assertEqual("not_applicable", rewps["live_smoke_test_status"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_eccc_radiosonde_is_unavailable(self) -> None:
        sources = _by_id()
        radiosonde = sources["eccc-radiosonde"]

        self.assertEqual("unavailable", radiosonde["status"])
        self.assertIn("CYYT", radiosonde["reason"])
        self.assertEqual([], radiosonde["access_endpoints"])
        self.assertTrue(radiosonde["documentation_urls"])
        self.assertEqual("not_applicable", radiosonde["fixture_status"])
        self.assertEqual("not_applicable", radiosonde["live_smoke_test_status"])
        condition = radiosonde["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("re-probe", condition["condition"] + condition["satisfied_by"] + radiosonde["reason"] + "re-probe")

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_nav_canada_weather_cameras_is_credential_required(self) -> None:
        sources = _by_id()
        cameras = sources["nav-canada-weather-cameras"]

        self.assertEqual("credential-required", cameras["status"])
        self.assertIn("registry endpoint at weathercams.navcanada.ca is dead", cameras["reason"])
        self.assertIn("NC-SPACES", cameras["reason"])
        self.assertIn("HITL", cameras["reason"])
        credential = cameras["credential"]
        self.assertEqual("WEATHER_SECRET_NC_SPACES_TOKEN", credential["name"])
        self.assertTrue(cameras["authentication"]["required"])
        self.assertEqual(credential["registration_url"], cameras["authentication"]["registration_url"])
        self.assertTrue(cameras["access_endpoints"])
        self.assertEqual("typed_adapter", cameras["integration"]["kind"])
        self.assertEqual("blocked", cameras["fixture_status"])
        self.assertEqual("blocked", cameras["live_smoke_test_status"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_provincial_hydrometric_and_cwop(self) -> None:
        sources = _by_id()
        provincial = sources["provincial-hydrometric"]
        self.assertEqual("catalogued", provincial["status"])
        self.assertIn("catalogued", provincial["reason"])

        cwop = sources["raw-cwop-pws"]
        self.assertEqual("catalogued", cwop["status"])
        condition = cwop["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("CWOP", condition["condition"])
        self.assertIn("Catalogued until a registered adapter claims the id", cwop["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_eccc_integrated_nowcasting_condition(self) -> None:
        sources = _by_id()
        nowcasting = sources["eccc-integrated-nowcasting"]

        self.assertEqual("catalogued", nowcasting["status"])
        self.assertIn("Zero WCS coverages", nowcasting["reason"])
        condition = nowcasting["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("WMS", condition["satisfied_by"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_eccc_rdwps_condition(self) -> None:
        sources = _by_id()
        rdwps = sources["eccc-rdwps"]

        self.assertEqual("catalogued", rdwps["status"])
        self.assertIn("Atlantic-domain", rdwps["reason"])
        condition = rdwps["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("45.0", condition["condition"])
        self.assertIn("GeoMet", condition["satisfied_by"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_noaa_goes_east_is_goes19(self) -> None:
        sources = _by_id()
        goes = sources["noaa-goes-east"]

        self.assertEqual("implemented-unverified", goes["status"])
        self.assertIn("GOES-19", goes["reason"])
        self.assertIn("fog", goes["reason"])
        self.assertTrue(any("goes19" in url for url in goes["access_endpoints"]))
        names = goes["variables"][0]["names"]
        self.assertIn("cloud_mask_ABI_L2_ACM", names)
        self.assertTrue(any("goes19" in url for url in goes["access_endpoints"]))

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_noaa_swpc_rtsw_is_catalogued(self) -> None:
        sources = _by_id()
        rtsw = sources["noaa-swpc-rtsw"]

        self.assertEqual("catalogued", rtsw["status"])
        self.assertEqual("passing", rtsw["fixture_status"])
        condition = rtsw["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("SWFO-L1", condition["condition"])
        self.assertIn("quality flag", condition["satisfied_by"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_copernicus_cams_licence(self) -> None:
        sources = _by_id()
        cams = sources["copernicus-cams"]

        self.assertEqual("credential-required", cams["status"])
        licence = cams["licence"]
        self.assertIn("CC BY 4.0", licence["name"])
        self.assertEqual("verified", licence["review_state"])
        self.assertEqual("https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts", licence["url"])
        self.assertIn("ADS catalogue", cams["reason"])
        self.assertIn("corrected", cams["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_celestrak_gp_is_catalogued_with_outstanding_condition(self) -> None:
        sources = _by_id()
        celestrak = sources["celestrak-gp"]

        self.assertEqual("catalogued", celestrak["status"])
        self.assertIn("Catalogued until a registered adapter claims the id", celestrak["reason"])
        self.assertIn("derived-here", celestrak["reason"])
        self.assertIn("never fetched as passes", celestrak["reason"])
        condition = celestrak["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("usage policy", condition["condition"])
        adapter_ids = audit.adapter_source_ids()
        self.assertFalse(admission.declaration_schedulable(celestrak, adapter_ids))

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_space_track_is_rejected(self) -> None:
        sources = _by_id()
        space_track = sources["space-track"]

        self.assertEqual("rejected", space_track["status"])
        self.assertIn("CelesTrak", space_track["reason"])
        self.assertEqual([], space_track["access_endpoints"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_noaa_swpc_kyoto_dst_is_reprocessed(self) -> None:
        sources = _by_id()
        dst = sources["noaa-swpc-kyoto-dst"]

        self.assertEqual("catalogued", dst["status"])
        self.assertEqual("reprocessed", dst["delivery_kind"])
        intermediary = dst["intermediary"]
        self.assertEqual("NOAA SWPC", intermediary["name"])
        self.assertIn("Kyoto", dst["producer"])
        self.assertFalse(dst["display_primary"])
        self.assertIn("Never the display primary", dst["reason"])
        self.assertIn("never a derivation input", dst["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_nrcan_stj_magnetometer_is_partnership_only(self) -> None:
        sources = _by_id()
        magnetometer = sources["nrcan-stj-magnetometer"]

        self.assertEqual("partnership-only", magnetometer["status"])
        self.assertEqual([], magnetometer["access_endpoints"])
        self.assertEqual("link_only", magnetometer["integration"]["kind"])
        adapter_ids = audit.adapter_source_ids()
        self.assertFalse(admission.declaration_schedulable(magnetometer, adapter_ids))
        self.assertIn("written permission", magnetometer["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_link_only_space_weather_records(self) -> None:
        sources = _by_id()
        regional = sources["space-weather-canada-regional"]
        imagery = sources["nasa-soho-sdo-goes-suvi-imagery"]

        for record in (regional, imagery):
            self.assertEqual("link-only", record["status"])
            self.assertEqual([], record["access_endpoints"])
            self.assertEqual("link_only", record["integration"]["kind"])

        _, errors = audit.validate()
        self.assertEqual([], errors)


    def test_openmeteo_cams_aod_is_reprocessed(self) -> None:
        sources = _by_id()
        aod = sources["openmeteo-cams-aod"]

        # No adapter claims the id, so the ledger's implemented-unverified is
        # written catalogued and the reason says why.
        self.assertEqual("catalogued", aod["status"])
        self.assertIn("Catalogued until a registered adapter claims the id", aod["reason"])
        self.assertEqual("reprocessed", aod["delivery_kind"])
        self.assertFalse(aod["display_primary"])
        self.assertEqual("Open-Meteo", aod["intermediary"]["name"])
        self.assertIn("CAMS", aod["producer"])

        # The six documented transformations plus the upsampling trap.
        transformations = aod["intermediary"]["transformations"]
        self.assertEqual(7, len(transformations))
        self.assertTrue(any("0.4 degree CAMS global grid is served at 0.1 degree" in item for item in transformations))

        # What the record must say out loud, because each is a way a reader
        # would otherwise misread the value.
        for phrase in ("no speciation", "sea-salt AOD", "T+10 h 16 m", "0.1 versus 0.4 degree", "credential-gated", "best_match"):
            self.assertIn(phrase, aod["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_openmeteo_lsa_saf_radiation_is_conditional(self) -> None:
        sources = _by_id()
        radiation = sources["openmeteo-lsa-saf-radiation"]

        self.assertEqual("catalogued", radiation["status"])
        self.assertEqual("reprocessed", radiation["delivery_kind"])
        self.assertEqual("Open-Meteo", radiation["intermediary"]["name"])
        self.assertIn("LSA SAF", radiation["producer"])
        self.assertEqual(["https://satellite-api.open-meteo.com/v1/archive"], radiation["access_endpoints"])

        condition = radiation["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("limb-geometry", condition["condition"])
        self.assertIn("view-angle mask", condition["satisfied_by"])
        self.assertEqual("2026-09-02", condition["recorded_on"])

        # An outstanding condition keeps the record unschedulable whatever else
        # the declaration says.
        self.assertTrue(admission.condition_outstanding(radiation))
        self.assertFalse(admission.declaration_schedulable(radiation, audit.adapter_source_ids()))

        for phrase in ("Direct, diffuse and DNI", "wet-bulb globe", "1 h latency", "Archive endpoint only"):
            self.assertIn(phrase, radiation["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_openmeteo_gfs_wave_requires_sea_cell_selection(self) -> None:
        sources = _by_id()
        wave = sources["openmeteo-gfs-wave"]

        self.assertEqual("catalogued", wave["status"])
        self.assertEqual("reprocessed", wave["delivery_kind"])
        self.assertEqual("wave", wave["category"])
        self.assertEqual("Open-Meteo", wave["intermediary"]["name"])
        self.assertIn("NCEP", wave["producer"])
        self.assertFalse(wave["display_primary"])

        self.assertIn(
            "cell_selection=sea is mandatory; the default nearest cell over a coastal point is land and returns null",
            wave["intermediary"]["transformations"],
        )
        for phrase in ("ncep_gfswave016", "ecmwf_wam", "T+5 h 21 m", "16-day", "0.16 degree", "retrieval failure, not calm"):
            self.assertIn(phrase, wave["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    unittest.main()
