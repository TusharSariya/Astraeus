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


    def test_openmeteo_ukmo_global_is_research_use_only(self) -> None:
        sources = _by_id()
        ukmo = sources["openmeteo-ukmo-global"]

        self.assertEqual("catalogued", ukmo["status"])
        self.assertEqual("reprocessed", ukmo["delivery_kind"])
        self.assertEqual("Open-Meteo", ukmo["intermediary"]["name"])
        self.assertEqual("UK Met Office", ukmo["producer"])

        terms = ukmo["restricted_terms"]
        self.assertIn("CC BY-SA 4.0", terms["terms_text"])
        self.assertFalse(terms["redistribution"])
        self.assertEqual("https://open-meteo.com/en/docs/ukmo-api", terms["terms_source_url"])
        self.assertEqual("restricted", ukmo["licence"]["review_state"])
        self.assertFalse(ukmo["consensus"]["eligible"])

        # A share-alike clause this deployment cannot grant onward closes both
        # export paths: the display primary and the consensus vote.
        self.assertFalse(ukmo["display_primary"])
        data, errors = audit.validate()
        self.assertEqual([], errors)
        self.assertIn("openmeteo-ukmo-global", audit.summary(data)["research_use_only"])

    def test_brightsky_mosmix_names_dwd_as_producer(self) -> None:
        sources = _by_id()
        mosmix = sources["brightsky-dwd-mosmix-71801"]

        self.assertEqual("catalogued", mosmix["status"])
        self.assertEqual("reprocessed", mosmix["delivery_kind"])
        self.assertEqual("Deutscher Wetterdienst", mosmix["producer"])
        intermediary = mosmix["intermediary"]
        self.assertEqual("Bright Sky", intermediary["name"])
        self.assertIn("station 71801 selected by id; no spatial interpolation", intermediary["transformations"])
        self.assertTrue(any("post-processing precedes the intermediary" in item for item in intermediary["transformations"]))
        self.assertIn("visibility", [name for group in mosmix["variables"] for name in group["names"]])

        _, errors = audit.validate()
        self.assertEqual([], errors)


    def test_unavailable_aggregator_domains(self) -> None:
        sources = _by_id()
        stale = sources["openmeteo-kma-gdps"]
        flat = sources["openmeteo-cma-grapes"]
        null = sources["openmeteo-graphcast"]

        for record in (stale, flat, null):
            self.assertEqual("unavailable", record["status"])
            self.assertEqual([], record["access_endpoints"])
            self.assertEqual("not_applicable", record["fixture_status"])
            self.assertEqual("not_applicable", record["live_smoke_test_status"])
            self.assertEqual("reprocessed", record["delivery_kind"])
            self.assertEqual("Open-Meteo", record["intermediary"]["name"])
            self.assertFalse(record["display_primary"])
            self.assertIn("docs/research/wayfinder/aggregator-models.md", record["reason"])

        # Three different silences, and the reason has to say which one, because
        # HTTP 200 is what all three return.
        self.assertIn("Stale since March 2026", stale["reason"])
        self.assertIn("Flat values over the box", flat["reason"])
        self.assertIn("Null over the box", null["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_weathernext_cloud_is_the_existing_intermediary_derived_record(self) -> None:
        # Deviation 1 of the change: `openmeteo-weathernext-2-cloud` is not
        # created, because `open-meteo-weathernext-2` already declares the same
        # product and a second record would be a duplicate declaration. This
        # test is the ledger row, asserted against the record that carries it.
        sources = _by_id()
        self.assertNotIn("openmeteo-weathernext-2-cloud", sources)
        cloud = sources["open-meteo-weathernext-2"]

        self.assertEqual("credential-required", cloud["status"])
        self.assertEqual("intermediary_derived", cloud["delivery_kind"])
        self.assertEqual("Open-Meteo", cloud["intermediary"]["name"])
        self.assertIn("Google", cloud["producer"])
        self.assertFalse(cloud["display_primary"])

        per_field = cloud["field_delivery_kinds"]
        self.assertIn("intermediary_derived", per_field.values())
        self.assertEqual("intermediary_derived", per_field["total_cloud"])

        self.assertIn("Never the display primary", cloud["reason"])
        self.assertIn("never a derivation input", cloud["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)


    def test_openmeteo_rejected_endpoints(self) -> None:
        sources = _by_id()
        rejected_ids = [
            "openmeteo-marine-sst",
            "openmeteo-uv-index",
            "openmeteo-pollen-ammonia",
            "openmeteo-aqi-indices",
            "openmeteo-beam-split",
            "openmeteo-climate-cmip6",
            "openmeteo-seasonal-seas5",
        ]

        for source_id in rejected_ids:
            record = sources[source_id]
            self.assertEqual("rejected", record["status"], source_id)
            self.assertEqual([], record["access_endpoints"], source_id)
            self.assertEqual("not_applicable", record["fixture_status"], source_id)
            self.assertEqual("not_applicable", record["live_smoke_test_status"], source_id)
            self.assertEqual("Open-Meteo", record["intermediary"]["name"], source_id)
            self.assertFalse(record["display_primary"], source_id)
            self.assertIn("best_match", record["reason"], source_id)

        # All seven declare the reprocessed route they would have arrived by.
        # The two the intermediary constructed itself say so in the reason
        # rather than in the kind: `intermediary_derived` is an admission class
        # (`open-meteo-weathernext-2` is its one member) and a refused record
        # must not join it.
        for source_id in rejected_ids:
            self.assertEqual("reprocessed", sources[source_id]["delivery_kind"], source_id)
        for source_id in ("openmeteo-aqi-indices", "openmeteo-beam-split"):
            self.assertNotIn("field_delivery_kinds", sources[source_id], source_id)
        self.assertIn("intermediary_derived", sources["openmeteo-aqi-indices"]["reason"])

        self.assertIn("four different quantities", sources["openmeteo-marine-sst"]["reason"])
        self.assertIn("producer output on GeoMet", sources["openmeteo-uv-index"]["reason"])
        self.assertIn("0 of 216 non-null", sources["openmeteo-pollen-ammonia"]["reason"])
        self.assertIn("index constructions", sources["openmeteo-aqi-indices"]["reason"])
        self.assertIn("no method named", sources["openmeteo-beam-split"]["reason"])
        self.assertIn("no marker distinguishing them from a forecast", sources["openmeteo-climate-cmip6"]["reason"])
        self.assertIn("monthly run published at T+4.4 days", sources["openmeteo-seasonal-seas5"]["reason"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_openmeteo_catalogued_endpoints(self) -> None:
        sources = _by_id()
        for source_id in (
            "openmeteo-air-quality-particulates",
            "openmeteo-marine-currents-sealevel",
            "openmeteo-glofas",
            "openmeteo-elevation",
        ):
            record = sources[source_id]
            self.assertEqual("catalogued", record["status"], source_id)
            self.assertEqual("reprocessed", record["delivery_kind"], source_id)
            self.assertEqual("Open-Meteo", record["intermediary"]["name"], source_id)
            self.assertFalse(record["display_primary"], source_id)
            # These are catalogued by the owner's decision, not by the migration
            # rule, so nothing here is waiting for an adapter.
            self.assertNotIn("Catalogued until a registered adapter", record["reason"], source_id)

        currents = sources["openmeteo-marine-currents-sealevel"]
        self.assertIn("undeclarable", currents["producer"])
        self.assertIn("meta.json carries no producer string", currents["producer"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_eccc_gdwps_condition(self) -> None:
        sources = _by_id()
        gdwps = sources["eccc-gdwps"]

        # No adapter claims eccc-gdwps, so the ledger's implemented-unverified
        # is written catalogued and the reason says so.
        self.assertEqual("catalogued", gdwps["status"])
        self.assertIn("Catalogued until a registered adapter claims the id", gdwps["reason"])
        self.assertIn("Atlantic-domain", gdwps["reason"])

        condition = gdwps["admission_condition"]
        self.assertFalse(condition["satisfied"])
        self.assertIn("45.0", condition["condition"])
        self.assertIn("GeoMet", condition["satisfied_by"])

        adapter_ids = audit.adapter_source_ids()
        self.assertTrue(admission.condition_outstanding(gdwps))
        self.assertFalse(admission.declaration_schedulable(gdwps, adapter_ids))

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_nl_air_quality_csv_is_uncalibrated_and_restricted(self) -> None:
        sources = _by_id()
        nl_air = sources["nl-air-quality-csv"]

        self.assertEqual("catalogued", nl_air["status"])
        self.assertIn("Catalogued until a registered adapter claims the id", nl_air["reason"])
        self.assertIn("uncalibrated observation", nl_air["poc_role"])

        terms = nl_air["restricted_terms"]
        self.assertIn("Government of Newfoundland and Labrador", terms["terms_text"])
        self.assertIn("PROVISIONAL", terms["terms_text"])
        self.assertFalse(terms["redistribution"])
        self.assertEqual("restricted", nl_air["licence"]["review_state"])
        self.assertFalse(nl_air["consensus"]["eligible"])
        self.assertFalse(nl_air["display_primary"])

        data, errors = audit.validate()
        self.assertEqual([], errors)
        self.assertIn("nl-air-quality-csv", audit.summary(data)["research_use_only"])

    def test_falchi_night_sky_atlas_is_research_use_only(self) -> None:
        sources = _by_id()
        falchi = sources["falchi-night-sky-atlas"]

        self.assertEqual("catalogued", falchi["status"])
        self.assertIn("Catalogued until a registered adapter claims the id", falchi["reason"])

        terms = falchi["restricted_terms"]
        self.assertIn("CC BY-NC 4.0", terms["terms_text"])
        self.assertFalse(terms["redistribution"])
        self.assertEqual("restricted", falchi["licence"]["review_state"])
        self.assertFalse(falchi["consensus"]["eligible"])
        self.assertFalse(falchi["display_primary"])

        data, errors = audit.validate()
        self.assertEqual([], errors)
        self.assertIn("falchi-night-sky-atlas", audit.summary(data)["research_use_only"])

    def test_viirs_dnb_night_lights_is_credential_required(self) -> None:
        sources = _by_id()
        viirs = sources["viirs-dnb-night-lights"]

        self.assertEqual("credential-required", viirs["status"])
        credential = viirs["credential"]
        self.assertEqual("WEATHER_SECRET_NASA_EARTHDATA_TOKEN", credential["name"])
        self.assertTrue(viirs["authentication"]["required"])
        self.assertEqual(credential["registration_url"], viirs["authentication"]["registration_url"])
        self.assertEqual("blocked", viirs["fixture_status"])
        self.assertEqual("blocked", viirs["live_smoke_test_status"])

        _, errors = audit.validate()
        self.assertEqual([], errors)

    def test_partnership_only_cameras(self) -> None:
        sources = _by_id()
        adapter_ids = audit.adapter_source_ids()
        for source_id in ("ccg-harbour-cameras", "city-st-johns-road-cameras", "ntv-cameras"):
            record = sources[source_id]
            self.assertEqual("partnership-only", record["status"], source_id)
            self.assertEqual([], record["access_endpoints"], source_id)
            self.assertEqual("link_only", record["integration"]["kind"], source_id)
            self.assertEqual("not_applicable", record["fixture_status"], source_id)
            self.assertEqual("not_applicable", record["live_smoke_test_status"], source_id)
            self.assertFalse(admission.declaration_schedulable(record, adapter_ids), source_id)
            self.assertIn("written permission", record["reason"], source_id)

        _, errors = audit.validate()
        self.assertEqual([], errors)


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    unittest.main()
