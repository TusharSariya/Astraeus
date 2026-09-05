"""Experimental named Open-Meteo and Bright Sky point-forecast adapters.

These adapters live outside ``ingest.adapters``: the source
contracts are draft and the registry remains ``operational: false``. Tests and
bounded evidence harnesses instantiate them directly.
"""

from __future__ import annotations

import hashlib
import json
import math
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

# The provider does not declare the saturation phase used by model RH. The
# catalogue refuses phase-less RH, so request it for source accounting but do
# not publish it as a comparable value.
DEFERRED_FIELDS = {"relative_humidity_2m": "deferred: saturation phase convention is not published"}

MODEL_SOURCES = {
    "openmeteo-jma-gsm": ("jma_gsm", "Japan Meteorological Agency", "JMA GSM"),
    "openmeteo-arpege": ("meteofrance_arpege_world025", "Meteo-France", "ARPEGE World 0.25 degree"),
    "openmeteo-ukmo-global": ("ukmo_global_deterministic_10km", "UK Met Office", "UKMO Global 10 km"),
}

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


def _open_meteo_keys(hourly: Mapping[str, Any], units: Mapping[str, Any], model: str) -> dict[str, tuple[str, str]]:
    """Bind one response shape to the explicitly requested model.

    Open-Meteo's documented single-model response uses unsuffixed keys. Some
    deployments return model-suffixed keys. Either complete shape is accepted;
    mixed shapes and suffixes naming another contracted model fail closed.
    """
    known_models = {item[0] for item in MODEL_SOURCES.values()}
    foreign = [
        key for key in set(hourly) | set(units)
        if any(key.endswith(f"_{other}") for other in known_models if other != model)
    ]
    if foreign:
        raise AdapterUnavailable(f"foreign_model_arrays:{','.join(sorted(foreign))}")
    has_plain = any(name in hourly or name in units for name in OPEN_METEO_FIELDS)
    has_selected_suffix = any(f"{name}_{model}" in hourly or f"{name}_{model}" in units for name in OPEN_METEO_FIELDS)
    if has_plain and has_selected_suffix:
        raise AdapterUnavailable("mixed_model_response_shape")
    suffix = f"_{model}" if has_selected_suffix else ""
    resolved: dict[str, tuple[str, str]] = {}
    for name in OPEN_METEO_FIELDS:
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
        params = {
            "latitude": "47.5615", "longitude": "-52.7126", "models": model,
            "hourly": ",".join(OPEN_METEO_FIELDS), "timezone": "GMT",
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
        keys = _open_meteo_keys(hourly, units, model)
        data_vars: dict[str, Any] = {}
        disposition: dict[str, str] = {}
        manifest_fields: list[RequiredField] = []
        for upstream, (field, canonical_units) in OPEN_METEO_FIELDS.items():
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
        if not data_vars:
            raise AdapterUnavailable("no declared fields were returned")
        dataset = xarray.Dataset(data_vars, coords={
            "valid_time": numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t in times]),
            "latitude": [float(payload["latitude"])], "longitude": [float(payload["longitude"])],
        })
        manifest = RunManifest(self.source_id, tuple(manifest_fields), min_coverage_fraction=0.01)
        validation = validate_run(manifest, dataset, window=window)
        path = workdir / f"{self.source_id}.zarr.zip"; write_zarr(dataset, path)
        _, producer, product = MODEL_SOURCES[self.source_id]
        provenance = {
            "source_id": self.source_id, "producer": producer, "intermediary": "Open-Meteo",
            "product": product, "model_selector": model, "access_path": self.endpoint,
            "adapter_version": self.adapter_version, "native_crs": "EPSG:4326",
            "returned_coordinates": [payload["latitude"], payload["longitude"]],
            "requested_elevation": "nan", "cell_selection": "nearest",
            "intermediary_transformations": list(OPEN_METEO_TRANSFORMATIONS),
            "run_identity": {"value": None, "certainty": "unknown", "reason": "rolling response has no per-value run reference"},
            "request_url": candidate.urls[0], "response_sha256": candidate.detail["sha256"],
            "field_disposition": disposition, "quality": validation.as_quality(), "coverage": validation.as_coverage(),
            "licence": "CC BY-SA 4.0 research-only" if self.source_id == "openmeteo-ukmo-global" else "Open-Meteo CC BY 4.0 plus upstream terms",
            **manifest.as_manifest_block(),
        }
        provenance["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact = Artifact("surface", MEDIA_ZARR, path, provenance)
        return RunResult(self.source_id, candidate.provider_run_id, None, datetime.now(UTC), validation.complete, validation.qc_passed, [artifact], "EPSG:4326", "experimental; not registered or scheduled")


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
