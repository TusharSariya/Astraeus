"""Selected, non-operational ECCC analysis contracts for bounded WCS proof.

These declarations are isolated experiment inputs.  They neither register nor
schedule an adapter, and intentionally omit catalogue fields whose exact
semantics have not been selected.  Standalone FireWork is absent by design;
current wildfire-smoke coverages are RAQDPS/RDAQA fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ingest.adapters.eccc_geomet_wcs import CoverageField


@dataclass(frozen=True)
class ProductContract:
    source_id: str
    product: str
    access_path: str
    fields: tuple[CoverageField, ...]
    native_cadence: timedelta | None
    time_identity: str
    quality_semantics: str = "unknown; producer quality flags are not exposed by this WCS coverage"
    operational: bool = False


@dataclass(frozen=True)
class DeferredPath:
    source_id: str
    product: str
    reason: str
    operational: bool = False


PRODUCT_CONTRACTS = {
    "raqdps": ProductContract(
        "eccc-raqdps", "RAQDPS", "GeoMet WCS 2.0.1",
        (
            CoverageField("RAQDPS.SFC_PM2.5", "pm2_5_surface"),
            CoverageField("RAQDPS.EATM_PM2.5", "pm2_5_column"),
            CoverageField("RAQDPS.Sfc_PM2.5-WildfireSmokePlume", "raw__raqdps_smoke_pm2_5_surface"),
            CoverageField("RAQDPS.EAtm_PM2.5-WildfireSmokePlume", "raw__raqdps_smoke_pm2_5_column"),
        ), timedelta(hours=1), "forecast valid time plus explicit reference time",
    ),
    "rdaqa": ProductContract(
        "eccc-rdaqa", "RDAQA preliminary and FireWork contribution analysis", "GeoMet WCS 2.0.1",
        (
            CoverageField("RDAQA-Prelim_10km_PM2.5", "raw__rdaqa_prelim_pm2_5"),
            CoverageField("RDAQA-FW_10km_PM2.5", "raw__rdaqa_fire_contribution_pm2_5"),
        ), timedelta(hours=1), "analysis valid time; no forecast lead",
    ),
    "hrdpa": ProductContract(
        "eccc-hrdpa", "HRDPA final", "GeoMet WCS 2.0.1",
        (CoverageField("HRDPA_2.5km_Precip-Accum6h", "precipitation_accumulation"),),
        timedelta(hours=6), "end of six-hour analysis accumulation; no forecast lead",
    ),
    "rdpa": ProductContract(
        "eccc-rdpa", "RDPA final", "GeoMet WCS 2.0.1",
        (CoverageField("RDPA_10km_Precip-Accum6h", "precipitation_accumulation", "metadata-only-unresolved-epsg-102978"),),
        timedelta(hours=6), "end of six-hour analysis accumulation; no forecast lead",
    ),
    "hrepa": ProductContract(
        "eccc-hrepa", "HREPA percentile analysis", "GeoMet WCS 2.0.1",
        (
            CoverageField("HREPA.6P_2.5km_PCT25", "raw__hrepa_precipitation_percentile_25"),
            CoverageField("HREPA.6P_2.5km_PCT75", "raw__hrepa_precipitation_percentile_75"),
        ), timedelta(hours=6), "six-hour ensemble analysis valid time; no forecast lead",
    ),
    "hrdlps": ProductContract(
        "eccc-hrdlps", "HRDLPS", "GeoMet WCS 2.0.1",
        (
            CoverageField("HRDLPS_2.5km_AirTemp", "raw__hrdlps_air_temperature"),
            CoverageField("HRDLPS_2.5km_SoilLiquidWaterCont_0.075m", "raw__hrdlps_soil_liquid_water_0_075m"),
        ), None, "forecast valid time; reference-time availability must be read from metadata",
    ),
    "caldas": ProductContract(
        "eccc-caldas", "CaLDAS-NSRPS analysis", "GeoMet WCS 2.0.1",
        (
            CoverageField("CaLDAS-NSRPS_2.5km_AirTemp_1.5m", "raw__caldas_air_temperature_1_5m"),
            CoverageField("CaLDAS-NSRPS_2.5km_SnowDepth", "raw__caldas_snow_depth"),
        ), timedelta(hours=3), "analysis valid time; no forecast lead",
    ),
}

# These public products do not share the numeric WCS contract above.  Preserve
# their known access identity and absence explicitly until a bounded typed
# feature/text contract is selected; callers must not infer WCS support.
DEFERRED_PATHS = {
    "wildfire_hotspots": DeferredPath(
        "eccc-wildfire-hotspots", "CWFIS hotspots",
        "typed CWFIS feature schema, confidence flags, and immutable artifact contract are not selected",
    ),
    "integrated_nowcasting": DeferredPath(
        "eccc-integrated-nowcasting", "Integrated Nowcasting System",
        "Datamart matrix filenames and field semantics are not selected",
    ),
    "cap_alerts": DeferredPath(
        "eccc-cap-alerts", "CAP weather alerts",
        "CAP revision, expiry, area, and empty-feed semantics require a separate typed contract",
    ),
    "thunderstorm_outlook": DeferredPath(
        "eccc-thunderstorm-outlooks", "Thunderstorm outlook",
        "GeoMet collection is known but category and validity semantics are not selected",
    ),
    "hurricane_products": DeferredPath(
        "eccc-hurricane-products", "Hurricane tracks and advisories",
        "event-dependent collection linkage and advisory revision semantics are not selected",
    ),
    "standalone_firework": DeferredPath(
        "eccc-raqdps-firework", "Standalone RAQDPS-FireWork",
        "superseded product; smoke remains selected only through current RAQDPS and RDAQA coverages",
    ),
}


def product_contract(name: str) -> ProductContract:
    try:
        return PRODUCT_CONTRACTS[name]
    except KeyError as error:
        raise ValueError(f"unsupported ECCC analysis product: {name}") from error
