"""Development fixtures: deliberately synthetic weather.

Nothing here is a reading. It exists so the UI and the contract can be worked on
without a database, and it is reachable only under an explicit
``WEATHER_DATA_MODE=fixture``. Every value it produces is stamped
``data_mode=fixture`` on the field's own provenance so no caller can mistake a
``math.sin`` curve for evidence. Source ids match real registry ids so nothing
in the catalogue dangles.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import (
    Coverage,
    DataMode,
    ContributorProvenance,
    EvidenceField,
    Freshness,
    Layer,
    ProfileLevel,
    Provenance,
    Quality,
    SourceRecord,
    SourceState,
    TimelineItem,
)
from .science import (
    ConsensusCandidate,
    HUMIDITY_DERIVATION,
    build_consensus,
    fog_state,
    radar_echo_semantics,
    resolve_relative_humidity,
)

UTC = timezone.utc
NEWFOUNDLAND = ZoneInfo("America/St_Johns")
AVALON_CORE_BOUNDS = {"south": 46.5, "west": -55.0, "north": 48.5, "east": -51.0}
BACK_HOURS = 3
FORWARD_HOURS = 24


def now() -> datetime:
    """The rolling reference time, truncated to the hour.

    Truncation keeps the evidence window exactly 28 hourly steps whenever it is
    asked for, which is the contract the timeline and the UI depend on.
    """
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def window_start(reference: datetime | None = None) -> datetime:
    return (reference or now()) - timedelta(hours=BACK_HOURS)


def window_end(reference: datetime | None = None) -> datetime:
    return (reference or now()) + timedelta(hours=FORWARD_HOURS)


SOURCES = [
    SourceRecord(
        id="eccc-hrdps", category="deterministic_forecast", schedulable=True, producer="ECCC", product="HRDPS", state=SourceState.IMPLEMENTING,
        status_reason="fixture contract passes; live smoke test has not run, so adapter is not active", role="planned primary deterministic and fallback", may_enter_consensus=True,
        exact_variables=["temperature_2m", "dew_point_2m", "relative_humidity_2m", "wind_10m", "visibility"],
        levels=["surface", "2 m", "10 m", "1000-300 hPa"], geographic_coverage="Avalon and Atlantic context",
        cadence="6 hours", forecast_horizon="48 hours", authentication="none", licence="Open Government Licence - Canada",
        attribution="Environment and Climate Change Canada", caching="fixture only", archival="original artifacts planned",
        redistribution="attribution required", schema_version="fixture-v1", freshness_threshold_seconds=21600,
        documentation_url="https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart-en/",
        access_endpoint="https://dd.weather.gc.ca/model_hrdps/", integration="raw GRIB2 via ecCodes/cfgrib planned",
        fixture_status="passing", live_smoke_status="not_run",
    ),
    SourceRecord(
        id="eccc-rdps", category="deterministic_forecast", schedulable=True, producer="ECCC", product="RDPS", state=SourceState.IMPLEMENTING,
        status_reason="fixture contract passes; live smoke test has not run, so adapter is not active", role="planned regional fallback", may_enter_consensus=True,
        exact_variables=["temperature_2m", "dew_point_2m", "wind_10m", "precipitation"], levels=["surface", "pressure levels"],
        geographic_coverage="Canada and adjacent waters", cadence="6 hours", forecast_horizon="84 hours", authentication="none",
        licence="Open Government Licence - Canada", attribution="Environment and Climate Change Canada", caching="fixture only",
        archival="original artifacts planned", redistribution="attribution required", schema_version="fixture-v1",
        freshness_threshold_seconds=21600, documentation_url="https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps-datamart-en/",
        access_endpoint="https://dd.weather.gc.ca/model_gem_regional/", integration="raw GRIB2 via ecCodes/cfgrib planned",
        fixture_status="passing", live_smoke_status="not_run",
    ),
    SourceRecord(
        id="eccc-reps", category="ensemble", schedulable=True, producer="ECCC", product="REPS", state=SourceState.IMPLEMENTING,
        status_reason="fixture contract passes; live smoke test has not run, so adapter is not active", role="planned ensemble distribution", may_enter_consensus=True,
        exact_variables=["temperature_2m", "precipitation", "wind_10m"], levels=["surface", "pressure levels"],
        geographic_coverage="North America", cadence="12 hours", forecast_horizon="72 hours", authentication="none",
        licence="Open Government Licence - Canada", attribution="Environment and Climate Change Canada", caching="fixture only",
        archival="members retained separately", redistribution="attribution required", schema_version="fixture-v1",
        freshness_threshold_seconds=43200, documentation_url="https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps-datamart-en/",
        access_endpoint="https://dd.weather.gc.ca/ensemble/reps/", integration="raw GRIB2 via ecCodes/cfgrib planned",
        fixture_status="passing", live_smoke_status="not_run",
    ),
    SourceRecord(
        id="noaa-gfs", category="deterministic_forecast", schedulable=True, producer="NOAA", product="GFS", state=SourceState.IMPLEMENTING,
        status_reason="fixture contract passes; live smoke test has not run, so adapter is not active", role="planned independent comparison", may_enter_consensus=True,
        exact_variables=["temperature_2m", "dew_point_2m", "wind_10m"], levels=["surface", "pressure levels"],
        geographic_coverage="global", cadence="6 hours", forecast_horizon="384 hours", authentication="none",
        licence="US public domain", attribution="NOAA/NCEP", caching="fixture only", archival="original artifacts planned",
        redistribution="public domain attribution requested", schema_version="fixture-v1", freshness_threshold_seconds=21600,
        documentation_url="https://www.nco.ncep.noaa.gov/pmb/products/gfs/", access_endpoint="https://noaa-gfs-bdp-pds.s3.amazonaws.com/",
        integration="Herbie with official S3 fallback planned", fixture_status="passing", live_smoke_status="not_run",
    ),
    SourceRecord(
        id="awc-metar-speci", category="observation", schedulable=True, producer="NAV CANADA / ECCC", product="CYYT METAR/SPECI", state=SourceState.IMPLEMENTING,
        status_reason="fixture contract passes; live smoke test has not run, so adapter is not active", role="planned observation supporting evidence", may_enter_consensus=False,
        exact_variables=["temperature", "dew_point", "visibility", "cloud_layers", "weather_codes"], levels=["surface"],
        geographic_coverage="CYYT", cadence="hourly and special", forecast_horizon="observation", authentication="none",
        licence="provider terms apply", attribution="Aviation Weather Center and source producer", caching="fixture only",
        archival="three-hour minimum planned", redistribution="review before redistribution", schema_version="fixture-v1",
        freshness_threshold_seconds=5400, documentation_url="https://aviationweather.gov/data/api/", access_endpoint="https://aviationweather.gov/api/data/metar",
        integration="official OpenAPI generated client planned", fixture_status="passing", live_smoke_status="not_run",
    ),
    SourceRecord(
        id="eccc-radar", category="observation", schedulable=True, producer="ECCC", product="Weather radar", state=SourceState.IMPLEMENTING,
        status_reason="fixture contract passes; live smoke test has not run, so adapter is not active", role="planned precipitation observation", may_enter_consensus=False,
        exact_variables=["precipitation_rate", "precipitation_type"], levels=["composite"], geographic_coverage="Newfoundland radar domain",
        cadence="6 minutes", forecast_horizon="observation", authentication="none", licence="Open Government Licence - Canada",
        attribution="Environment and Climate Change Canada", caching="fixture only", archival="three-hour minimum planned",
        redistribution="attribution required", schema_version="fixture-v1", freshness_threshold_seconds=1200,
        documentation_url="https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_en/", access_endpoint="https://dd.weather.gc.ca/radar/",
        integration="GeoTIFF/raw protocol planned", fixture_status="passing", live_smoke_status="not_run",
    ),
]


LAYERS = [
    Layer(id="consensus-temperature", title="Experimental temperature consensus", kind="raster", field="temperature", product="consensus", units="degC", semantics="approximately 10 km independent-centre mean", cadence_seconds=3600, staleness_tolerance_seconds=1800, z_index=0),
    Layer(id="hrdps-relative-humidity", title="HRDPS 2 m relative humidity", kind="raster", field="relative_humidity", product="HRDPS", units="percent", semantics="provider RH preserved; derived only if absent", cadence_seconds=3600, staleness_tolerance_seconds=1800, z_index=1),
    Layer(id="radar-echo", title="ECCC radar", kind="raster", field="radar_echo", product="Weather radar", units="category", semantics="no echo means no detected precipitating echo, not clear sky", cadence_seconds=360, staleness_tolerance_seconds=600, z_index=2),
    Layer(id="fog-evidence", title="Fog evidence", kind="mask", field="fog_state", product="multi-evidence", units="category", semantics="categorical evidence; high RH alone never proves fog", cadence_seconds=3600, staleness_tolerance_seconds=1800, z_index=3),
    Layer(id="cyyt-observation", title="CYYT METAR", kind="point", field="station_weather", product="CYYT METAR/SPECI", units="mixed", semantics="observation, never blended", cadence_seconds=3600, staleness_tolerance_seconds=5400, z_index=10),
]


def provenance(
    source: str,
    product: str,
    centre: str,
    valid_time: datetime,
    *,
    units: str,
    level: str = "2 m above ground",
    derivation: str | None = None,
    derivation_version: str | None = None,
    contributors: list[str] | None = None,
) -> Provenance:
    record = next((item for item in SOURCES if item.product == product), None)
    unavailable = product == "forecast-unavailable"
    source_id = record.id if record else "experimental-consensus" if product == "experimental-consensus" else "forecast-unavailable"
    contributor_records = [item for item in SOURCES if item.id in (contributors or [])]
    return Provenance(
        data_mode=DataMode.FIXTURE,  # unmistakable: this number was computed, not retrieved
        source_id=source_id,
        provider=source, product=product, forecast_centre=centre,
        run_time=None if unavailable or product in {"CYYT METAR/SPECI", "Weather radar"} else now() - timedelta(hours=3),
        valid_time=valid_time, retrieval_time=now() - timedelta(minutes=5), member=None,
        vertical_level=level, original_units=units, normalized_units=units,
        native_resolution="unavailable" if unavailable else "approximately 10 km" if product == "experimental-consensus" else "2.5 km" if product == "HRDPS" else "fixture point",
        native_crs="unavailable" if unavailable else "EPSG:4326",
        quality=Quality(status="unknown" if unavailable else "passed", flags=["forecast_unavailable"] if unavailable else []),
        coverage=Coverage(status="unknown" if unavailable else "complete", fraction=None if unavailable else 1),
        freshness=Freshness.evaluate(None, record.freshness_threshold_seconds if record else 21600),
        licence=record.licence if record else "Mixed contributor licences; see contributors" if contributor_records else "Not applicable",
        attribution=record.attribution if record else "Contributing providers; see contributors" if contributor_records else "Fixture unavailable marker",
        derivation=derivation, derivation_version=derivation_version,
        adapter_version="fixture-adapter-v1", contributing_evidence=contributors or [],
        contributors=[ContributorProvenance(source_id=item.id, provider=item.producer, product=item.product, licence=item.licence, attribution=item.attribution) for item in contributor_records],
    )


import math


def point_fields(valid_time: datetime) -> tuple[list[EvidenceField], object]:
    dt_hours = (valid_time - now()).total_seconds() / 3600.0 if valid_time else 0.0
    diurnal = round(0.8 * math.sin((dt_hours + 2) * 0.25) * 2.5, 1)

    hrdps_temp = round(16.0 + diurnal, 1)
    gfs_temp = round(14.0 + diurnal, 1)
    reps_temp = round(15.0 + diurnal, 1)

    candidates = [
        ConsensusCandidate("eccc-hrdps", "ECCC", "regional", hrdps_temp, is_eccc_regional=True),
        ConsensusCandidate("noaa-gfs", "NOAA", "global", gfs_temp),
        ConsensusCandidate("eccc-reps", "ECCC", "regional-ensemble", reps_temp, is_ensemble=True),
    ]
    consensus = build_consensus(candidates)
    base_temp = consensus.value if consensus.value is not None else 15.2
    base_dew = round(base_temp - (2.5 + 0.5 * math.cos(dt_hours * 0.2)), 1)
    rh, derivation, derivation_version = resolve_relative_humidity(None, base_temp, base_dew)

    wind_spd = round(max(3.0, 8.5 + 1.8 * math.sin(dt_hours * 0.3)), 1)
    wind_gst = round(wind_spd * 1.5, 1)

    c_low = round(min(100.0, max(10.0, 85.0 - dt_hours * 1.8 + 10.0 * math.sin(dt_hours * 0.4))), 1)
    c_mid = round(min(100.0, max(5.0, 40.0 + dt_hours * 1.5)), 1)
    c_high = round(min(100.0, max(5.0, 15.0 + dt_hours * 2.2)), 1)
    c_tot = round(min(100.0, max(15.0, 88.0 - dt_hours * 0.8)), 1)

    is_night_or_fog = (dt_hours < -1.5 or (10.0 <= dt_hours <= 18.0))
    vis_km = 4.5 if is_night_or_fog else 12.0
    fog_code = is_night_or_fog

    fields = [
        EvidenceField(field="temperature", value=consensus.value, provenance=provenance("multi-centre", "experimental-consensus", "independent centres", valid_time, units="degC", level="approximately 10 km grid", contributors=list(consensus.contributors))),
        EvidenceField(field="relative_humidity", value=rh, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="percent", derivation=derivation, derivation_version=derivation_version)),
        EvidenceField(field="dew_point", value=base_dew, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="degC")),
        EvidenceField(field="wind_speed", value=wind_spd, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="m s-1", level="10 m above ground")),
        EvidenceField(field="wind_gust", value=wind_gst, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="m s-1", level="10 m above ground")),
        EvidenceField(field="visibility", value=vis_km, provenance=provenance("CYYT", "CYYT METAR/SPECI", "observation", valid_time, units="km", level="surface")),
        EvidenceField(field="cloud_low", value=c_low, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="percent", level="low cloud")),
        EvidenceField(field="cloud_middle", value=c_mid, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="percent", level="middle cloud")),
        EvidenceField(field="cloud_high", value=c_high, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="percent", level="high cloud")),
        EvidenceField(field="total_cloud", value=c_tot, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="percent", level="total atmosphere")),
        EvidenceField(field="fog_state", value=fog_state(provider_diagnostic=None, visibility_m=int(vis_km * 1000), fog_code=fog_code), provenance=provenance("CYYT", "CYYT METAR/SPECI", "observation", valid_time, units="category", level="surface")),
        EvidenceField(field="radar_echo", value=radar_echo_semantics(False), provenance=provenance("ECCC", "Weather radar", "ECCC", valid_time, units="category", level="composite")),
    ]
    return fields, consensus


def fallback_temperature(valid_time: datetime, product: str) -> EvidenceField:
    prod = product.upper()
    dt_hours = (valid_time - now()).total_seconds() / 3600.0 if valid_time else 0.0
    diurnal = round(0.8 * math.sin((dt_hours + 2) * 0.25) * 2.5, 1)

    if prod == "HRDPS":
        return EvidenceField(field="temperature", value=round(16.0 + diurnal, 1), provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="degC"))
    if prod == "RDPS":
        return EvidenceField(field="temperature", value=round(15.5 + diurnal, 1), provenance=provenance("ECCC", "RDPS", "ECCC", valid_time, units="degC"))
    if prod in {"IFS", "ECMWF"}:
        return EvidenceField(field="temperature", value=round(15.2 + diurnal, 1), provenance=provenance("ECMWF", "IFS", "ECMWF", valid_time, units="degC"))
    if prod in {"GFS", "NOAA"}:
        return EvidenceField(field="temperature", value=round(14.0 + diurnal, 1), provenance=provenance("NOAA", "GFS", "NOAA", valid_time, units="degC"))
    if prod in {"ICON", "DWD"}:
        return EvidenceField(field="temperature", value=round(14.8 + diurnal, 1), provenance=provenance("DWD", "ICON", "DWD", valid_time, units="degC"))
    if prod == "REPS":
        return EvidenceField(field="temperature", value=round(15.0 + diurnal, 1), provenance=provenance("ECCC", "REPS", "ECCC", valid_time, units="degC"))
    raise ValueError(f"unsupported fallback product: {product}")


def selected_forecast_fields(valid_time: datetime, product: str) -> list[EvidenceField]:
    prod = product.upper()
    dt_hours = (valid_time - now()).total_seconds() / 3600.0 if valid_time else 0.0
    diurnal = round(0.8 * math.sin((dt_hours + 2) * 0.25) * 2.5, 1)

    if prod == "HRDPS":
        temp, dew, provider, product_name = round(16.0 + diurnal, 1), round(12.1 + diurnal * 0.7, 1), "ECCC", "HRDPS"
    elif prod == "RDPS":
        temp, dew, provider, product_name = round(15.5 + diurnal, 1), round(11.5 + diurnal * 0.7, 1), "ECCC", "RDPS"
    elif prod in {"IFS", "ECMWF"}:
        temp, dew, provider, product_name = round(15.2 + diurnal, 1), round(11.8 + diurnal * 0.7, 1), "ECMWF", "IFS"
    elif prod in {"GFS", "NOAA"}:
        temp, dew, provider, product_name = round(14.0 + diurnal, 1), round(10.5 + diurnal * 0.7, 1), "NOAA", "GFS"
    elif prod in {"ICON", "DWD"}:
        temp, dew, provider, product_name = round(14.8 + diurnal, 1), round(11.0 + diurnal * 0.7, 1), "DWD", "ICON"
    elif prod == "REPS":
        temp, dew, provider, product_name = round(15.0 + diurnal, 1), round(11.9 + diurnal * 0.7, 1), "ECCC", "REPS"
    else:
        raise ValueError(f"unsupported selected product: {product}")
    rh, derivation, version = resolve_relative_humidity(None, temp, dew)
    return [
        fallback_temperature(valid_time, product),
        EvidenceField(field="relative_humidity", value=rh, provenance=provenance(provider, product_name, provider, valid_time, units="percent", derivation=derivation, derivation_version=version)),
        EvidenceField(field="dew_point", value=dew, provenance=provenance(provider, product_name, provider, valid_time, units="degC")),
    ]


def unavailable_forecast_fields(valid_time: datetime) -> list[EvidenceField]:
    return [
        EvidenceField(field=field, value=None, provenance=provenance("none", "forecast-unavailable", "none", valid_time, units=units))
        for field, units in [("temperature", "degC"), ("relative_humidity", "percent"), ("dew_point", "degC")]
    ]


def profile_levels(valid_time: datetime) -> list[ProfileLevel]:
    result: list[ProfileLevel] = []
    for pressure, temp, dew, wind in [(1000, 15.2, 12.1, 8.0), (850, 8.0, 3.0, 14.0), (700, -2.0, -10.0, 22.0), (500, -18.0, -32.0, 31.0), (300, -43.0, -56.0, 45.0)]:
        rh, derivation, version = resolve_relative_humidity(None, temp, dew)
        level = f"{pressure} hPa"
        result.append(ProfileLevel(pressure_hpa=pressure, fields=[
            EvidenceField(field="temperature", value=temp, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="degC", level=level)),
            EvidenceField(field="dew_point", value=dew, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="degC", level=level)),
            EvidenceField(field="relative_humidity", value=rh, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="percent", level=level, derivation=derivation, derivation_version=version)),
            EvidenceField(field="wind_speed", value=wind, provenance=provenance("ECCC", "HRDPS", "ECCC", valid_time, units="m s-1", level=level)),
        ]))
    return result


def timeline(reference: datetime | None = None) -> list[TimelineItem]:
    moment = reference or now()
    start = window_start(moment)
    result: list[TimelineItem] = []
    for index in range(BACK_HOURS + FORWARD_HOURS + 1):
        valid_time = start + timedelta(hours=index)
        products = ["HRDPS", "GFS", "REPS"]
        if valid_time <= moment:
            products.append("CYYT METAR/SPECI")
        result.append(TimelineItem(valid_time_utc=valid_time, valid_time_newfoundland=valid_time.astimezone(NEWFOUNDLAND), available_products=products))
    return result

