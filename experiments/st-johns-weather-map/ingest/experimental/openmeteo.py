"""Experimental named Open-Meteo and Bright Sky point-forecast adapters.

These adapters live outside ``ingest.adapters``: the source
contracts are draft and the registry remains ``operational: false``. Tests and
bounded evidence harnesses instantiate them directly.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

import numpy
import xarray

from ingest.contract import MEDIA_ZARR, AdapterUnavailable, Artifact, FetchWindow, RunCandidate, RunResult
from ingest.grib import write_zarr
from ingest.http import PoliteClient
from ingest.manifest import RequiredField, RunManifest, validate_run
from registry.source_data import OPEN_METEO_TRANSFORMATIONS

UTC = timezone.utc
MAX_JSON_BYTES = 4 * 1024 * 1024
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
BRIGHT_SKY_URL = "https://api.brightsky.dev/weather"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_CAMS_META_URL = "https://air-quality-api.open-meteo.com/data/cams_global/static/meta.json"
OPEN_METEO_SATELLITE_URL = "https://satellite-api.open-meteo.com/v1/archive"

OPEN_METEO_FIELDS = {
    "temperature_2m": ("temperature_2m", "degC"),
    "dew_point_2m": ("dew_point_2m", "degC"),
    "relative_humidity_2m": ("relative_humidity_2m", "percent"),
    "cloud_cover": ("total_cloud_geometric", "percent"),
    "cloud_cover_low": ("cloud_low", "percent"),
    "cloud_cover_mid": ("cloud_middle", "percent"),
    "cloud_cover_high": ("cloud_high", "percent"),
    "wind_speed_10m": ("wind_speed_10m", "m s-1"),
    "wind_direction_10m": ("wind_direction_10m", "degree"),
    "pressure_msl": ("mean_sea_level_pressure", "hPa"),
    "precipitation": ("precipitation_accumulation", "mm"),
}

# Source-specific pressure surfaces shown by the corresponding Open-Meteo
# model documentation on 2026-09-05.  They are deliberately not collapsed to
# one provider-wide list: JMA GSM has a materially smaller native inventory.
OPEN_METEO_PROFILE_LEVELS = {
    "openmeteo-jma-gsm": (1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100),
    "openmeteo-arpege": (1000, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300, 275, 250, 225, 200, 175, 150, 125, 100, 70, 50, 30, 20, 10),
    "openmeteo-ukmo-global": (1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 375, 350, 325, 300, 275, 250, 225, 200, 175, 150, 125, 100, 70, 50, 40, 30, 20, 10),
}

OPEN_METEO_PROFILE_FIELDS = {
    "temperature": ("temperature_pressure", "degC", "°C", "reprocessed"),
    "relative_humidity": (None, "percent", "%", "raw_phase_unknown"),
    "dew_point": (None, "degC", "°C", "intermediary_derived"),
    "cloud_cover": (None, "percent", "%", "intermediary_derived"),
    "wind_speed": ("wind_speed_pressure", "m s-1", "m/s", "reprocessed"),
    "wind_direction": ("wind_direction_pressure", "degree", "°", "reprocessed"),
    # Open-Meteo returns geometric vertical speed in m/s.  Astraeus's existing
    # pressure-profile vertical velocity is omega in Pa/s, so this stays raw.
    "vertical_velocity": (None, "m s-1", "m/s", "raw_incompatible_with_omega"),
    # Open-Meteo declares metres while the catalogue's GRIB profile key is
    # explicitly gpm.  Retain the response rather than silently equating them.
    "geopotential_height": (None, "m", "m", "raw_units_not_catalogued"),
}


def _profile_upstream_fields(source_id: str) -> tuple[str, ...]:
    return tuple(
        f"{kind}_{level}hPa"
        for level in OPEN_METEO_PROFILE_LEVELS[source_id]
        for kind in OPEN_METEO_PROFILE_FIELDS
    )

# The provider does not declare the saturation phase used by model RH. The
# catalogue refuses phase-less RH, so request it for source accounting but do
# not publish it as a comparable value.
DEFERRED_FIELDS = {"relative_humidity_2m": "deferred: saturation phase convention is not published"}

MODEL_SOURCES = {
    "openmeteo-jma-gsm": ("jma_gsm", "Japan Meteorological Agency", "JMA GSM"),
    "openmeteo-arpege": ("meteofrance_arpege_world025", "Meteo-France", "ARPEGE World 0.25 degree"),
    "openmeteo-ukmo-global": ("ukmo_global_deterministic_10km", "UK Met Office", "UKMO Global 10 km"),
}

COMPOSITION_FIELDS = {
    "pm2_5": ("pm2_5_surface", "kg m-3", "μg/m³", 1e-9),
    "pm10": ("pm10_surface", "kg m-3", "μg/m³", 1e-9),
    "aerosol_optical_depth": ("aerosol_optical_depth_550nm", "1", "", 1.0),
    "ozone": ("ozone_surface", "kg m-3", "μg/m³", 1e-9),
    "nitrogen_dioxide": ("nitrogen_dioxide_surface", "kg m-3", "μg/m³", 1e-9),
    "sulphur_dioxide": ("sulphur_dioxide_surface", "kg m-3", "μg/m³", 1e-9),
    "carbon_monoxide": ("carbon_monoxide_surface", "kg m-3", "μg/m³", 1e-9),
    "dust": ("dust_surface", "kg m-3", "μg/m³", 1e-9),
}
RADIATION_FIELDS = {
    "shortwave_radiation": ("downward_shortwave_flux_hour_mean", "W m-2", "hour_mean"),
    "shortwave_radiation_instant": ("downward_shortwave_flux_instant", "W m-2", "instant"),
    "direct_radiation": ("direct_shortwave_flux_hour_mean", "W m-2", "hour_mean"),
    "direct_radiation_instant": ("direct_shortwave_flux_instant", "W m-2", "instant"),
    "diffuse_radiation": ("diffuse_shortwave_flux_hour_mean", "W m-2", "hour_mean"),
    "diffuse_radiation_instant": ("diffuse_shortwave_flux_instant", "W m-2", "instant"),
    "direct_normal_irradiance": ("direct_normal_irradiance_hour_mean", "W m-2", "hour_mean"),
    "direct_normal_irradiance_instant": ("direct_normal_irradiance_instant", "W m-2", "instant"),
    "global_tilted_irradiance": ("global_tilted_irradiance_hour_mean", "W m-2", "hour_mean"),
    "global_tilted_irradiance_instant": ("global_tilted_irradiance_instant", "W m-2", "instant"),
    "terrestrial_radiation": ("terrestrial_radiation_flux_hour_mean", "W m-2", "hour_mean"),
    "terrestrial_radiation_instant": ("terrestrial_radiation_flux_instant", "W m-2", "instant"),
}
CAMS_COMPOSITION_TRANSFORMATIONS = (
    "Regridding the CAMS 0.4 degree producer grid onto Open-Meteo 0.1 degree cell centres.",
    "Temporal interpolation onto the hourly point-series step served by Open-Meteo.",
)
LSA_SAF_TRANSFORMATIONS = (
    "Regridding the LSA SAF MSG product onto Open-Meteo's 0.05 degree point grid.",
    "Serving separate provider hour-mean and instantaneous radiation series without merging them.",
)

BRIGHT_SKY_SOURCE = {
    "id": 1228,
    "wmo_station_id": "71801",
    "station_name": "ST.JOHNS NEUFUNDL.",
    "observation_type": "forecast",
}

BRIGHT_SKY_FIELDS = {
    "temperature": ("temperature_2m", "degC", 1.0, "instant"),
    "dew_point": ("dew_point_2m", "degC", 1.0, "instant"),
    "cloud_cover": ("total_cloud_geometric", "percent", 1.0, "instant"),
    "visibility": ("visibility", "m", 1.0, "instant"),
    "pressure_msl": ("mean_sea_level_pressure", "hPa", 1.0, "instant"),
    "wind_speed": ("wind_speed_10m", "m s-1", 1 / 3.6, "instant"),
    "wind_direction": ("wind_direction_10m", "degree", 1.0, "instant"),
    "wind_gust_speed": ("wind_gust_10m", "m s-1", 1 / 3.6, "instant"),
    "precipitation": ("precipitation_accumulation", "mm", 1.0, "preceding_hour"),
}

# These are relevant fields returned by Bright Sky for this product but cannot
# yet be published under a catalogue key without inventing semantics. Their raw
# values and nulls remain in provenance so retrieval status comes from the
# response rather than from a hard-coded assumption.
BRIGHT_SKY_RAW_FIELDS = (
    "relative_humidity", "wind_gust_direction", "precipitation_probability",
    "precipitation_probability_6h", "sunshine", "solar", "condition", "icon",
)


def _response_json(response: Any) -> tuple[dict[str, Any], str]:
    body = response.content
    if len(body) > MAX_JSON_BYTES:
        raise AdapterUnavailable(f"response exceeded {MAX_JSON_BYTES} bytes")
    digest = hashlib.sha256(body).hexdigest()
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterUnavailable(f"malformed provider JSON: {error}") from error
    if not isinstance(value, dict):
        raise AdapterUnavailable("provider JSON root is not an object")
    return value, digest


def _bounded_json(client: Any, url: str) -> tuple[dict[str, Any], str]:
    """Stream real HTTP clients to the byte ceiling before decoding.

    Small injected test clients retain the response-shaped seam used by the
    existing adapter tests.
    """
    if hasattr(client, "download"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.json"
            client.download(url, path, max_bytes=MAX_JSON_BYTES)
            body = path.read_bytes()
        return _response_json(type("BoundedResponse", (), {"content": body})())
    return _response_json(client.get(url))


def _numbers(values: Any, count: int, field: str) -> numpy.ndarray:
    if not isinstance(values, list) or len(values) != count:
        raise AdapterUnavailable(f"missing_or_misaligned_array:{field}")
    out = numpy.full((count, 1, 1), numpy.nan, dtype="float64")
    for index, value in enumerate(values):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise AdapterUnavailable(f"invalid_value:{field}@{index}")
        out[index, 0, 0] = float(value)
    return out


def _times(values: Any) -> list[datetime]:
    if not isinstance(values, list) or not values:
        raise AdapterUnavailable("missing hourly time axis")
    try:
        result = [datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in values]
    except ValueError as error:
        raise AdapterUnavailable(f"invalid hourly timestamp: {error}") from error
    return [value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC) for value in result]


def _open_meteo_keys(hourly: Mapping[str, Any], units: Mapping[str, Any], model: str, requested: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    """Bind one response shape to the explicitly requested model.

    Open-Meteo's documented single-model response uses unsuffixed keys. Some
    deployments return model-suffixed keys. Either complete shape is accepted;
    mixed shapes and every suffix other than the selected model fail closed.
    """
    selected = {f"{name}_{model}" for name in requested}
    foreign = []
    for key in set(hourly) | set(units):
        if key in requested or key in selected:
            continue
        # Match the longest field first because cloud_cover is a prefix of
        # cloud_cover_low/mid/high. Any suffix on a selected field is a model
        # identity claim; accepting only the exact requested selector avoids
        # silently treating a new or misspelled selector as unrelated data.
        if any(key.startswith(f"{name}_") for name in sorted(requested, key=len, reverse=True)):
            foreign.append(key)
    if foreign:
        raise AdapterUnavailable(f"foreign_model_arrays:{','.join(sorted(foreign))}")
    has_plain = any(name in hourly or name in units for name in requested)
    has_selected_suffix = any(f"{name}_{model}" in hourly or f"{name}_{model}" in units for name in requested)
    if has_plain and has_selected_suffix:
        raise AdapterUnavailable("mixed_model_response_shape")
    suffix = f"_{model}" if has_selected_suffix else ""
    resolved: dict[str, tuple[str, str]] = {}
    for name in requested:
        key = f"{name}{suffix}"
        if key not in hourly or key not in units:
            raise AdapterUnavailable(f"missing_selected_field:{key}")
        resolved[name] = (key, key)
    return resolved


def _bright_sky_source(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise AdapterUnavailable("Bright Sky response has no sources array")
    matches = [source for source in sources if isinstance(source, dict) and all(source.get(key) == value for key, value in BRIGHT_SKY_SOURCE.items())]
    if len(matches) != 1:
        raise AdapterUnavailable("Bright Sky exact source 1228 / WMO 71801 / ST.JOHNS NEUFUNDL. forecast identity mismatch; nearest-station fallback forbidden")
    return matches[0]


@dataclass
class OpenMeteoAdapter:
    source_id: str
    client: PoliteClient | None = None
    endpoint: str = OPEN_METEO_URL

    adapter_version = "openmeteo-named-point-v1"

    def __post_init__(self) -> None:
        if self.source_id not in MODEL_SOURCES:
            raise ValueError(f"unsupported named source: {self.source_id}")

    def _url(self, window: FetchWindow) -> str:
        model, _, _ = MODEL_SOURCES[self.source_id]
        requested = (*OPEN_METEO_FIELDS, *_profile_upstream_fields(self.source_id))
        params = {
            "latitude": "47.5615", "longitude": "-52.7126", "models": model,
            "hourly": ",".join(requested), "timezone": "GMT",
            "elevation": "nan", "cell_selection": "nearest", "wind_speed_unit": "ms",
            "start_hour": window.start.astimezone(UTC).strftime("%Y-%m-%dT%H:00"),
            "end_hour": window.end.astimezone(UTC).strftime("%Y-%m-%dT%H:00"),
        }
        return f"{self.endpoint}?{urlencode(params)}"

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        url = self._url(window)
        try:
            response = (self.client or PoliteClient()).get(url)
            payload, digest = _response_json(response)
        except AdapterUnavailable:
            raise
        except Exception as error:
            raise AdapterUnavailable(f"Open-Meteo request failed: {error}") from error
        # Rolling responses stitch latest values and expose no per-value run.
        return [RunCandidate(f"rolling-unknown-{digest[:16]}", None, [url], {"payload": payload, "sha256": digest, "model_selector": MODEL_SOURCES[self.source_id][0]})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        payload = candidate.detail.get("payload")
        if not isinstance(payload, dict):
            raise AdapterUnavailable("candidate carries no decoded response")
        hourly, units = payload.get("hourly"), payload.get("hourly_units")
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise AdapterUnavailable("missing hourly data or unit declarations")
        times = _times(hourly.get("time")); count = len(times)
        model = MODEL_SOURCES[self.source_id][0]
        if candidate.detail.get("model_selector") != model or f"models={model}" not in candidate.urls[0]:
            raise AdapterUnavailable("candidate model selector does not match adapter source")
        profile_only = candidate.detail.get("profile_only") is True
        requested = _profile_upstream_fields(self.source_id) if profile_only else (*OPEN_METEO_FIELDS, *_profile_upstream_fields(self.source_id))
        keys = _open_meteo_keys(hourly, units, model, requested)
        data_vars: dict[str, Any] = {}
        disposition: dict[str, str] = {}
        manifest_fields: list[RequiredField] = []
        for upstream, (field, canonical_units) in (() if profile_only else OPEN_METEO_FIELDS.items()):
            key, unit_key = keys[upstream]
            original = units.get(unit_key)
            expected = {"degC": "°C", "percent": "%", "m s-1": "m/s", "degree": "°", "hPa": "hPa", "mm": "mm"}[canonical_units]
            if original != expected:
                raise AdapterUnavailable(f"unexpected_units:{key}:{original!r}; expected {expected!r}")
            if upstream in DEFERRED_FIELDS:
                _numbers(hourly[key], count, key)
                disposition[field] = f"raw_retrieved; canonical_{DEFERRED_FIELDS[upstream]}"
                continue
            array = _numbers(hourly[key], count, key)
            attrs = {"units": canonical_units, "original_units": original}
            if field == "precipitation_accumulation":
                attrs["reporting_interval"] = "preceding_hour"
                attrs["reporting_interval_hours"] = 1
            data_vars[field] = (("valid_time", "latitude", "longitude"), array, attrs)
            manifest_fields.append(RequiredField(field, canonical_units, evidence_class="reprocessed"))
            disposition[field] = "retrieved" if numpy.isfinite(array).any() else "missing: all values null"
        if not data_vars and not profile_only:
            raise AdapterUnavailable("no declared fields were returned")
        dataset = xarray.Dataset(data_vars, coords={
            "valid_time": numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
            "latitude": [float(payload["latitude"])], "longitude": [float(payload["longitude"])],
        })
        manifest = None if profile_only else RunManifest(self.source_id, tuple(manifest_fields), min_coverage_fraction=0.01)
        validation = validate_run(manifest, dataset, window=window) if manifest is not None else None
        _, producer, product = MODEL_SOURCES[self.source_id]
        common_provenance = {
            "source_id": self.source_id, "producer": producer, "intermediary": "Open-Meteo",
            "product": product, "model_selector": model, "access_path": self.endpoint,
            "adapter_version": self.adapter_version, "native_crs": "EPSG:4326",
            "returned_coordinates": [payload["latitude"], payload["longitude"]],
            "requested_elevation": "nan", "cell_selection": "nearest",
            "intermediary_transformations": list(OPEN_METEO_TRANSFORMATIONS),
            "run_identity": {"value": None, "certainty": "unknown", "reason": "rolling response has no per-value run reference"},
            "request_url": candidate.urls[0], "response_sha256": candidate.detail["sha256"],
            "licence": "CC BY-SA 4.0 research-only" if self.source_id == "openmeteo-ukmo-global" else "Open-Meteo CC BY 4.0 plus upstream terms",
        }
        levels = OPEN_METEO_PROFILE_LEVELS[self.source_id]
        profile_vars: dict[str, Any] = {}
        profile_disposition: dict[str, str] = {}
        raw_profile_fields: dict[str, dict[str, Any]] = {}
        canonical_level_completeness: dict[str, dict[str, bool]] = {}
        profile_manifest_fields: list[RequiredField] = []
        for kind, (canonical, canonical_units, expected_units, delivery) in OPEN_METEO_PROFILE_FIELDS.items():
            rows = []
            for level in levels:
                upstream = f"{kind}_{level}hPa"
                key, unit_key = keys[upstream]
                original = units.get(unit_key)
                # A model may expose a documented field but return no values
                # and the literal unit ``undefined`` (observed for every
                # ARPEGE vertical-velocity level).  Preserve that as an
                # explicit unsupported result; never relabel it with units.
                values_are_all_null = isinstance(hourly[key], list) and all(value is None for value in hourly[key])
                if original != expected_units and not (original == "undefined" and values_are_all_null):
                    raise AdapterUnavailable(f"unexpected_units:{key}:{original!r}; expected {expected_units!r}")
                row = _numbers(hourly[key], count, key)[:, 0, 0]
                rows.append(row)
                values = [None if not math.isfinite(value) else float(value) for value in row]
                raw_profile_fields[upstream] = {
                    "values": values,
                    "missing_mask": [value is None for value in values],
                    "original_units": original,
                    "delivery": delivery,
                    "pressure_hpa": level,
                    "valid_times": [time.isoformat() for time in times],
                }
                status = "retrieved" if numpy.isfinite(row).any() else "missing: all values null"
                profile_disposition[upstream] = f"{status}; {delivery}"
            if canonical is not None:
                values = numpy.stack(rows, axis=1)[:, :, None, None]
                profile_vars[canonical] = (("valid_time", "pressure", "latitude", "longitude"), values, {"units": canonical_units, "original_units": expected_units})
                profile_manifest_fields.append(RequiredField(canonical, canonical_units, level="pressure levels", evidence_class="reprocessed"))
                canonical_level_completeness[canonical] = {
                    str(level): bool(numpy.isfinite(values[:, index, :, :]).all())
                    for index, level in enumerate(levels)
                }

        profile_dataset = xarray.Dataset(profile_vars, coords={
            "valid_time": numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
            "pressure": ("pressure", list(levels), {"units": "hPa", "positive": "down", "standard_name": "air_pressure"}),
            "latitude": [float(payload["latitude"])], "longitude": [float(payload["longitude"])],
        })
        # Every advertised canonical field must cover every advertised pressure
        # level and valid time. An average across the whole profile can hide an
        # entirely absent level, which would make a partial profile publishable.
        profile_manifest = RunManifest(self.source_id, tuple(profile_manifest_fields), min_coverage_fraction=1.0)
        profile_validation = validate_run(profile_manifest, profile_dataset, window=window)
        missing_canonical_levels = sorted(
            f"{field}@{level}hPa"
            for field, by_level in canonical_level_completeness.items()
            for level, complete in by_level.items()
            if not complete
        )
        profile_provenance = {
            **common_provenance, "vertical_coordinate": {"name": "pressure", "units": "hPa", "interpolation": "none"},
            "field_disposition": profile_disposition, "raw_deferred_profile_fields": raw_profile_fields,
            "canonical_level_completeness": canonical_level_completeness,
            "missing_required_canonical_levels": missing_canonical_levels,
            "quality": profile_validation.as_quality(), "coverage": profile_validation.as_coverage(), **profile_manifest.as_manifest_block(),
        }

        # Decode and validate every artifact before writing any of them. If a
        # later write fails, remove this run's files so callers cannot mistake
        # a partial work directory for a complete result.
        surface_path = workdir / f"{self.source_id}.zarr.zip"
        profile_path = workdir / f"{self.source_id}-pressure-profile.zarr.zip"
        paths = [profile_path] if profile_only else [surface_path, profile_path]
        try:
            if not profile_only:
                write_zarr(dataset, surface_path)
            write_zarr(profile_dataset, profile_path)
        except BaseException:
            for path in paths:
                path.unlink(missing_ok=True)
            raise

        artifacts: list[Artifact] = []
        if not profile_only:
            provenance = {**common_provenance, "field_disposition": disposition, "quality": validation.as_quality(), "coverage": validation.as_coverage(), **manifest.as_manifest_block()}
            provenance["sha256"] = hashlib.sha256(surface_path.read_bytes()).hexdigest()
            artifacts.append(Artifact("surface", MEDIA_ZARR, surface_path, provenance))
        profile_provenance["sha256"] = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        artifacts.append(Artifact("pressure-profile", MEDIA_ZARR, profile_path, profile_provenance))
        surface_complete = True if validation is None else validation.complete
        surface_qc = True if validation is None else validation.qc_passed
        return RunResult(self.source_id, candidate.provider_run_id, None, datetime.now(UTC), surface_complete and profile_validation.complete, surface_qc and profile_validation.qc_passed, artifacts, "EPSG:4326", "experimental; not registered or scheduled")


@dataclass
class OpenMeteoCompositionAdapter:
    """Bounded CAMS/LSA SAF point retrieval kept outside the adapter registry."""

    source_id: str
    client: PoliteClient | None = None
    latitude: float = 47.5615
    longitude: float = -52.7126

    adapter_version = "openmeteo-composition-point-v1"

    def __post_init__(self) -> None:
        if self.source_id not in {"openmeteo-cams-aod", "openmeteo-air-quality-particulates", "openmeteo-lsa-saf-radiation"}:
            raise ValueError(f"unsupported composition source: {self.source_id}")

    def _url(self, window: FetchWindow) -> str:
        if not (math.isfinite(self.latitude) and -90 <= self.latitude <= 90
                and math.isfinite(self.longitude) and -180 <= self.longitude <= 180):
            raise ValueError("Open-Meteo composition coordinates must be finite and in range")
        common = {"latitude": str(self.latitude), "longitude": str(self.longitude), "timezone": "GMT"}
        if self.source_id == "openmeteo-lsa-saf-radiation":
            fields = tuple(RADIATION_FIELDS)
            archive_end = min(window.end, window.now)
            params = {**common, "models": "eumetsat_lsa_saf_msg", "hourly": ",".join(fields),
                      "start_date": window.start.astimezone(UTC).date().isoformat(), "end_date": archive_end.astimezone(UTC).date().isoformat()}
            return f"{OPEN_METEO_SATELLITE_URL}?{urlencode(params)}"
        fields = ("aerosol_optical_depth",) if self.source_id == "openmeteo-cams-aod" else tuple(COMPOSITION_FIELDS)
        params = {**common, "domains": "cams_global", "hourly": ",".join(fields),
                  "start_hour": window.start.astimezone(UTC).strftime("%Y-%m-%dT%H:00"),
                  "end_hour": window.end.astimezone(UTC).strftime("%Y-%m-%dT%H:00")}
        return f"{OPEN_METEO_AIR_QUALITY_URL}?{urlencode(params)}"

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        client = self.client or PoliteClient(attempts=1)
        url = self._url(window)
        try:
            payload, digest = _bounded_json(client, url)
            meta = None
            if self.source_id != "openmeteo-lsa-saf-radiation":
                meta, _ = _bounded_json(client, OPEN_METEO_CAMS_META_URL)
        except AdapterUnavailable:
            raise
        except Exception as error:
            raise AdapterUnavailable(f"Open-Meteo composition request failed: {error}") from error
        latest_model_initialisation = None
        if meta is not None:
            stamp = meta.get("last_run_initialisation_time")
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
                raise AdapterUnavailable("CAMS metadata has no numeric last_run_initialisation_time")
            latest_model_initialisation = datetime.fromtimestamp(stamp, UTC).isoformat()
        # The rolling point series carries no per-value run reference.  The
        # latest model timestamp from meta.json is retained as context only;
        # assigning it to these values would invent their source run.
        identity = f"rolling-unknown-{digest[:16]}" if meta is not None else f"observation-{digest[:16]}"
        return [RunCandidate(identity, None, [url], {"payload": payload, "sha256": digest, "meta": meta,
                                                     "latest_model_initialisation": latest_model_initialisation})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        payload = candidate.detail.get("payload")
        hourly = payload.get("hourly") if isinstance(payload, dict) else None
        units = payload.get("hourly_units") if isinstance(payload, dict) else None
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise AdapterUnavailable("missing hourly data or unit declarations")
        if payload.get("utc_offset_seconds") != 0:
            raise AdapterUnavailable("Open-Meteo response is not declared UTC")
        try:
            returned_latitude, returned_longitude = float(payload["latitude"]), float(payload["longitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise AdapterUnavailable(f"invalid returned coordinates: {error}") from error
        if not math.isfinite(returned_latitude) or not math.isfinite(returned_longitude) or not (-90 <= returned_latitude <= 90) or not (-180 <= returned_longitude <= 180):
            raise AdapterUnavailable("invalid returned coordinates")
        times = _times(hourly.get("time"))
        original_count = len(times)
        indexes = [index for index, stamp in enumerate(times) if window.covers(stamp)]
        if not indexes:
            raise AdapterUnavailable("no returned values fall inside the requested window")
        times = [times[index] for index in indexes]; count = len(times)
        declared = RADIATION_FIELDS if self.source_id == "openmeteo-lsa-saf-radiation" else COMPOSITION_FIELDS
        selected = set(declared)
        if self.source_id == "openmeteo-cams-aod": selected = {"aerosol_optical_depth"}
        data_vars: dict[str, Any] = {}; fields: list[RequiredField] = []; dispositions: dict[str, str] = {}
        for upstream in selected:
            if upstream not in hourly or upstream not in units:
                raise AdapterUnavailable(f"missing_selected_field:{upstream}")
            if self.source_id == "openmeteo-lsa-saf-radiation":
                canonical, canonical_units, interval = declared[upstream]
                expected, scale = "W/m²", 1.0
            else:
                canonical, canonical_units, expected, scale = declared[upstream]
                interval = "instant"
            if units[upstream] != expected:
                raise AdapterUnavailable(f"unexpected_units:{upstream}:{units[upstream]!r}; expected {expected!r}")
            all_values = hourly[upstream]
            if not isinstance(all_values, list) or len(all_values) != original_count:
                raise AdapterUnavailable(f"missing_or_misaligned_array:{upstream}")
            array = _numbers([all_values[index] for index in indexes], count, upstream) * scale
            attrs = {"units": canonical_units, "original_units": expected, "reporting_interval": interval}
            data_vars[canonical] = (("valid_time", "latitude", "longitude"), array, attrs)
            fields.append(RequiredField(canonical, canonical_units, evidence_class="reprocessed"))
            dispositions[canonical] = "retrieved" if numpy.isfinite(array).any() else "missing: all values null"
        dataset = xarray.Dataset(data_vars, coords={"valid_time": numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
                                                    "latitude": [returned_latitude], "longitude": [returned_longitude]})
        manifest = RunManifest(self.source_id, tuple(fields), min_coverage_fraction=0.01)
        validation = validate_run(manifest, dataset, window=window)
        path = workdir / f"{self.source_id}.zarr.zip"; write_zarr(dataset, path)
        producer = "EUMETSAT LSA SAF" if self.source_id == "openmeteo-lsa-saf-radiation" else "ECMWF Copernicus Atmosphere Monitoring Service (CAMS)"
        product = "LSA SAF MSG surface radiation" if self.source_id == "openmeteo-lsa-saf-radiation" else "CAMS global atmospheric composition forecast"
        provenance = {"source_id": self.source_id, "producer": producer, "intermediary": "Open-Meteo", "product": product,
                      "adapter_version": self.adapter_version, "request_url": candidate.urls[0], "response_sha256": candidate.detail["sha256"],
                      "run_identity": {"value": None, "certainty": "unknown" if candidate.detail.get("meta") is not None else "not_applicable_observation",
                                       "reason": "rolling response has no per-value run reference" if candidate.detail.get("meta") is not None else "satellite retrieval is an observation"},
                      "latest_model_initialisation_context": candidate.detail.get("latest_model_initialisation"),
                      "native_crs": "EPSG:4326", "native_resolution": "0.05 degree" if self.source_id == "openmeteo-lsa-saf-radiation" else "0.4 degree served at 0.1 degree cell centres",
                      "returned_coordinates": [returned_latitude, returned_longitude], "field_disposition": dispositions,
                      "intermediary_transformations": list(LSA_SAF_TRANSFORMATIONS if self.source_id == "openmeteo-lsa-saf-radiation" else CAMS_COMPOSITION_TRANSFORMATIONS),
                      "quality": validation.as_quality(), "coverage": validation.as_coverage(), "licence": "Open-Meteo CC BY 4.0 plus upstream terms", **manifest.as_manifest_block()}
        provenance["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return RunResult(self.source_id, candidate.provider_run_id, candidate.run_time, datetime.now(UTC), validation.complete, validation.qc_passed,
                         [Artifact("composition" if self.source_id != "openmeteo-lsa-saf-radiation" else "radiation", MEDIA_ZARR, path, provenance)],
                         "EPSG:4326", "experimental; not registered or scheduled")


class BrightSkyMosmix71801Adapter:
    """Exact-station probe that refuses Bright Sky's nearest-station substitution."""

    source_id = "brightsky-dwd-mosmix-71801"

    def __init__(self, client: PoliteClient | None = None, endpoint: str = BRIGHT_SKY_URL) -> None:
        self.client, self.endpoint = client, endpoint

    def discover(self, window: FetchWindow) -> list[RunCandidate]:
        url = f"{self.endpoint}?{urlencode({'date': window.start.isoformat(), 'last_date': window.end.isoformat(), 'wmo_station_id': '71801', 'units': 'dwd'})}"
        try:
            response = (self.client or PoliteClient(attempts=1)).get(url)
            payload, digest = _response_json(response)
        except Exception as error:
            raise AdapterUnavailable(f"Bright Sky exact WMO station 71801 unavailable; nearest-station fallback forbidden: {error}") from error
        _bright_sky_source(payload)
        return [RunCandidate(f"mosmix-71801-unknown-{digest[:16]}", None, [url], {"payload": payload, "sha256": digest})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        payload = candidate.detail.get("payload")
        records = payload.get("weather") if isinstance(payload, dict) else None
        if not isinstance(records, list) or not records:
            raise AdapterUnavailable("exact WMO station 71801 returned no weather records")
        selected = []
        for record in records:
            if not isinstance(record, dict):
                raise AdapterUnavailable("malformed Bright Sky weather record")
            try: stamp = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00")).astimezone(UTC)
            except (KeyError, ValueError) as error: raise AdapterUnavailable(f"invalid Bright Sky timestamp: {error}") from error
            if window.covers(stamp): selected.append((stamp, record))
        if not selected: raise AdapterUnavailable("exact WMO station 71801 has no records in the requested window")
        source = _bright_sky_source(payload)
        if any(record.get("source_id") != BRIGHT_SKY_SOURCE["id"] for _, record in selected):
            raise AdapterUnavailable("Bright Sky weather row source_id does not match exact source 1228")
        data_vars, dispositions, fields = {}, {}, []
        count = len(selected)
        for upstream, (field, units, scale, interval) in BRIGHT_SKY_FIELDS.items():
            values = [record.get(upstream) for _, record in selected]
            array = _numbers(values, count, upstream) * scale
            attrs = {"units": units, "original_units": "km/h" if upstream in {"wind_speed", "wind_gust_speed"} else units}
            if field == "precipitation_accumulation":
                attrs["reporting_interval"] = interval
                attrs["reporting_interval_hours"] = 1
            data_vars[field] = (("valid_time", "latitude", "longitude"), array, attrs)
            fields.append(RequiredField(field, units, evidence_class="reprocessed"))
            dispositions[field] = "retrieved" if numpy.isfinite(array).any() else "missing: all station values null"
        raw_fields = {name: [record.get(name) for _, record in selected] for name in BRIGHT_SKY_RAW_FIELDS}
        for name, values in raw_fields.items():
            canonical = "relative_humidity_2m" if name == "relative_humidity" else name
            status = "raw_retrieved" if any(value is not None for value in values) else "raw_returned_null"
            dispositions[canonical] = f"{status}; canonical_deferred: catalogue semantics or producer convention unresolved"
        dataset = xarray.Dataset(data_vars, coords={
            "valid_time": numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t, _ in selected]),
            "latitude": [float(source["lat"])], "longitude": [float(source["lon"])],
        })
        manifest = RunManifest(self.source_id, tuple(fields), min_coverage_fraction=0.01)
        validation = validate_run(manifest, dataset, window=window)
        path = workdir / f"{self.source_id}.zarr.zip"; write_zarr(dataset, path)
        provenance = {
            "source_id": self.source_id, "producer": "Deutscher Wetterdienst", "intermediary": "Bright Sky",
            "product": "MOSMIX_L station forecast", "station": {"wmo_station_id": "71801", "source_id": source.get("id"), "name": source.get("station_name"), "observation_type": source.get("observation_type")},
            "access_path": self.endpoint, "request_url": candidate.urls[0], "response_sha256": candidate.detail["sha256"],
            "run_identity": {"value": None, "certainty": "unknown", "reason": "Bright Sky response carries no MOSMIX cycle"},
            "native_crs": "EPSG:4326", "field_disposition": dispositions, "raw_deferred_fields": raw_fields,
            "quality": validation.as_quality(), "coverage": validation.as_coverage(), "licence": "DWD terms apply; Bright Sky public instance is free",
            **manifest.as_manifest_block(),
        }
        provenance["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact = Artifact("station-71801", MEDIA_ZARR, path, provenance)
        return RunResult(self.source_id, candidate.provider_run_id, None, datetime.now(UTC), validation.complete, validation.qc_passed, [artifact], "EPSG:4326", "experimental; not registered or scheduled")
