"""Selected, non-operational ECCC analysis contracts for bounded WCS proof.

These declarations are isolated experiment inputs.  They neither register nor
schedule an adapter, and intentionally omit catalogue fields whose exact
semantics have not been selected.  Standalone FireWork is absent by design;
current wildfire-smoke coverages are RAQDPS/RDAQA fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ingest.adapters.eccc_geomet_wcs import CoverageField


@dataclass(frozen=True)
class ProductContract:
    source_id: str
    product: str
    access_path: str
    fields: tuple[CoverageField, ...]
    native_cadence: timedelta | None
    time_identity: str
    product_phase: str | None = None
    quality_semantics: str = "unknown; producer quality flags are not exposed by this WCS coverage"
    operational: bool = False


@dataclass(frozen=True)
class DeferredPath:
    source_id: str
    product: str
    reason: str
    operational: bool = False


PRODUCT_CONTRACTS = {
    "raqdps_hourly": ProductContract(
        "eccc-raqdps", "RAQDPS hourly", "GeoMet WCS 2.0.1",
        (
            CoverageField("RAQDPS.SFC_PM2.5", "pm2_5_surface", vertical_scope="surface"),
            CoverageField("RAQDPS.EATM_PM2.5", "pm2_5_column", vertical_scope="entire_atmosphere"),
            CoverageField("RAQDPS.SFC_PM10", "pm10_surface", vertical_scope="surface"),
            CoverageField("RAQDPS.EATM_PM10", "raw__raqdps_pm10_column", vertical_scope="entire_atmosphere"),
            CoverageField("RAQDPS.SFC_O3", "raw__raqdps_ozone_surface_mole_fraction", vertical_scope="surface"),
            CoverageField("RAQDPS.SFC_NO", "raw__raqdps_nitric_oxide_surface", vertical_scope="surface"),
            CoverageField("RAQDPS.SFC_NO2", "raw__raqdps_nitrogen_dioxide_surface_mole_fraction", vertical_scope="surface"),
            CoverageField("RAQDPS.SFC_SO2", "raw__raqdps_sulphur_dioxide_surface_mole_fraction", vertical_scope="surface"),
            CoverageField("RAQDPS.Sfc_PM2.5-WildfireSmokePlume", "raw__raqdps_smoke_pm2_5_surface", vertical_scope="surface"),
            CoverageField("RAQDPS.EAtm_PM2.5-WildfireSmokePlume", "raw__raqdps_smoke_pm2_5_column", vertical_scope="entire_atmosphere"),
            CoverageField("RAQDPS.Sfc_PM10-WildfireSmokePlume", "raw__raqdps_smoke_pm10_surface", vertical_scope="surface"),
            CoverageField("RAQDPS.EAtm_PM10-WildfireSmokePlume", "raw__raqdps_smoke_pm10_column", vertical_scope="entire_atmosphere"),
        ), timedelta(hours=1), "hourly forecast valid time plus explicit reference time", "forecast",
    ),
    "raqdps_statistics": ProductContract(
        "eccc-raqdps", "RAQDPS 24-hour smoke statistics", "GeoMet WCS 2.0.1",
        (
            CoverageField("RAQDPS.Sfc_PM2.5-WildireSmokePlume-DAvg", "raw__raqdps_smoke_pm2_5_surface_24h_mean", vertical_scope="surface", statistic_window_hours=24),
            CoverageField("RAQDPS.Sfc_PM2.5-WildireSmokePlume-DMax", "raw__raqdps_smoke_pm2_5_surface_24h_max", vertical_scope="surface", statistic_window_hours=24),
        ), timedelta(hours=24), "24-hour statistic valid time plus explicit reference time", "forecast_statistic",
    ),
    "rdaqa_preliminary": ProductContract(
        "eccc-rdaqa", "RDAQA preliminary analysis", "GeoMet WCS 2.0.1",
        tuple(CoverageField(f"RDAQA-Prelim_10km_{provider}", f"raw__rdaqa_preliminary_{name}", vertical_scope="surface") for provider, name in (
            ("PM2.5", "pm2_5_surface"), ("PM10", "pm10_surface"), ("O3", "ozone_surface"),
            ("NO", "nitric_oxide_surface"), ("NO2", "nitrogen_dioxide_surface"), ("SO2", "sulphur_dioxide_surface"),
        )), timedelta(hours=1), "preliminary analysis valid time; no forecast lead", "preliminary_analysis",
    ),
    "rdaqa_final": ProductContract(
        "eccc-rdaqa", "RDAQA final analysis", "GeoMet WCS 2.0.1",
        tuple(CoverageField(f"RDAQA_10km_{provider}", f"raw__rdaqa_final_{name}", vertical_scope="surface") for provider, name in (
            ("PM2.5", "pm2_5_surface"), ("PM10", "pm10_surface"), ("O3", "ozone_surface"),
            ("NO", "nitric_oxide_surface"), ("NO2", "nitrogen_dioxide_surface"), ("SO2", "sulphur_dioxide_surface"),
        )), timedelta(hours=1), "final analysis valid time; no forecast lead", "final_analysis",
    ),
    "rdaqa_smoke": ProductContract(
        "eccc-rdaqa", "RDAQA FireWork-contribution analysis", "GeoMet WCS 2.0.1",
        (
            CoverageField("RDAQA-FW_10km_PM2.5", "raw__rdaqa_smoke_pm2_5_surface", vertical_scope="surface"),
            CoverageField("RDAQA-FW_10km_PM10", "raw__rdaqa_smoke_pm10_surface", vertical_scope="surface"),
        ), timedelta(hours=1), "smoke-contribution analysis valid time; no forecast lead", "firework_contribution_analysis",
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

MANIFEST_OWNER_GATE = (
    "canonical contracts are absent for PM10 column burden, surface gas mole fractions, "
    "wildfire-attributable particulate mass, 24-hour smoke statistics, and RDAQA analysis phases"
)


def fetch_unresolved_product(
    client, name: str, *, valid_time, reference_time, workdir,
):
    """Fetch every selected field but return a validator-owned refusal verdict.

    This is the explicit experiment seam while no truthful ``RunManifest`` can
    name every selected field. It must never be registered or published.
    """
    from ingest.contract import RunResult
    from ingest.manifest import unresolved_manifest_validation
    from ingest.adapters.eccc_geomet_wcs import fetch_artifact

    contract = product_contract(name)
    if contract.source_id not in {"eccc-raqdps", "eccc-rdaqa"}:
        raise ValueError("unresolved chemistry fetch accepts only RAQDPS/RDAQA products")
    model = "raqdps" if contract.source_id == "eccc-raqdps" else "rdaqa"
    if valid_time is None or valid_time.utcoffset() is None:
        raise ValueError("chemistry valid time must be timezone-aware")
    if model == "rdaqa" and reference_time is not None:
        raise ValueError("RDAQA is an analysis and cannot carry a forecast reference time")
    if model == "raqdps":
        if reference_time is None or reference_time.utcoffset() is None:
            raise ValueError("RAQDPS requires a timezone-aware forecast reference time")
        if reference_time > valid_time:
            raise ValueError("RAQDPS reference time cannot follow valid time")
    artifacts = [
        fetch_artifact(
            client, field, valid_time=valid_time, reference_time=reference_time,
            workdir=workdir / field.variable, model=model, product_phase=contract.product_phase,
        )
        for field in contract.fields
    ]
    selected_valid = {artifact.provenance["valid_time"] for artifact in artifacts}
    selected_runs = {artifact.provenance["run_time"] for artifact in artifacts}
    if len(selected_valid) != 1 or len(selected_runs) != 1:
        verdict = unresolved_manifest_validation(contract.source_id, "selected fields disagree on product time identity")
    else:
        verdict = unresolved_manifest_validation(contract.source_id, MANIFEST_OWNER_GATE)
    retrieved_at = max(datetime.fromisoformat(artifact.provenance["http_completed_at"]) for artifact in artifacts)
    run_time = None if selected_runs == {None} else datetime.fromisoformat(next(iter(selected_runs)))
    return RunResult(
        source_id=contract.source_id,
        provider_run_id=f"{name}:{next(iter(selected_valid))}:{next(iter(selected_runs))}",
        run_time=run_time,
        retrieved_at=retrieved_at,
        complete=verdict.complete,
        qc_passed=verdict.qc_passed,
        artifacts=artifacts,
        native_crs="EPSG:4326",
        notes=verdict.detail,
    )
