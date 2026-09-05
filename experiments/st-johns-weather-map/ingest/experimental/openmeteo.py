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
        return [RunCandidate(f"rolling-unknown-{digest[:16]}", None, [url], {"payload": payload, "sha256": digest})]

    def fetch(self, candidate: RunCandidate, window: FetchWindow, workdir: Path) -> RunResult:
        payload = candidate.detail.get("payload")
        if not isinstance(payload, dict):
            raise AdapterUnavailable("candidate carries no decoded response")
        hourly, units = payload.get("hourly"), payload.get("hourly_units")
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise AdapterUnavailable("missing hourly data or unit declarations")
        times = _times(hourly.get("time")); count = len(times)
        model = MODEL_SOURCES[self.source_id][0]
        data_vars: dict[str, Any] = {}
        disposition: dict[str, str] = {}
        manifest_fields: list[RequiredField] = []
        for upstream, (field, canonical_units) in OPEN_METEO_FIELDS.items():
            key = upstream if upstream in hourly else f"{upstream}_{model}"
            unit_key = upstream if upstream in units else f"{upstream}_{model}"
            if key not in hourly:
                disposition[field] = "missing: response omitted array"
                continue
            if upstream in DEFERRED_FIELDS:
                disposition[field] = DEFERRED_FIELDS[upstream]
                continue
            original = units.get(unit_key)
            expected = {"degC": "°C", "percent": "%", "m s-1": "m/s", "degree": "°", "hPa": "hPa", "mm": "mm"}[canonical_units]
            if original != expected:
                raise AdapterUnavailable(f"unexpected_units:{key}:{original!r}; expected {expected!r}")
            array = _numbers(hourly[key], count, key)
            data_vars[field] = (("valid_time", "latitude", "longitude"), array, {"units": canonical_units, "original_units": original})
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
            "run_identity": {"value": None, "certainty": "unknown", "reason": "rolling response has no per-value run reference"},
            "request_url": candidate.urls[0], "response_sha256": candidate.detail["sha256"],
            "field_disposition": disposition, "quality": validation.as_quality(), "coverage": validation.as_coverage(),
            "licence": "CC BY-SA 4.0 research-only" if self.source_id == "openmeteo-ukmo-global" else "Open-Meteo CC BY 4.0 plus upstream terms",
            **manifest.as_manifest_block(),
        }
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
        sources = payload.get("sources")
        if not isinstance(sources, list) or not any(str(s.get("wmo_station_id")) == "71801" for s in sources if isinstance(s, dict)):
            raise AdapterUnavailable("Bright Sky did not return exact WMO station 71801; nearest-station fallback forbidden")
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
        mapping = {
            "temperature": ("temperature_2m", "degC", 1.0), "dew_point": ("dew_point_2m", "degC", 1.0),
            "cloud_cover": ("total_cloud_geometric", "percent", 1.0), "visibility": ("visibility", "m", 1.0),
            "pressure_msl": ("mean_sea_level_pressure", "hPa", 1.0), "wind_speed": ("wind_speed_10m", "m s-1", 1 / 3.6),
            "wind_direction": ("wind_direction_10m", "degree", 1.0), "precipitation": ("precipitation_accumulation", "mm", 1.0),
        }
        data_vars, dispositions, fields = {}, {}, []
        count = len(selected)
        for upstream, (field, units, scale) in mapping.items():
            values = [record.get(upstream) for _, record in selected]
            array = _numbers(values, count, upstream) * scale
            data_vars[field] = (("valid_time", "latitude", "longitude"), array, {"units": units, "original_units": "km/h" if upstream == "wind_speed" else units})
            fields.append(RequiredField(field, units, evidence_class="reprocessed"))
            dispositions[field] = "retrieved" if numpy.isfinite(array).any() else "missing: all station values null"
        dispositions.update({
            "relative_humidity_2m": "missing: station values null; phase also undeclared",
            "wind_gust_speed": "unsupported: no catalogue key", "precipitation_probability": "unsupported: no catalogue key",
            "sunshine": "unsupported: no catalogue key", "solar": "unsupported: no catalogue key",
            "condition": "deferred: Bright Sky intermediary-derived categorical field",
        })
        source = next(s for s in payload["sources"] if str(s.get("wmo_station_id")) == "71801")
        dataset = xarray.Dataset(data_vars, coords={
            "valid_time": numpy.array([numpy.datetime64(t.replace(tzinfo=None), "ns") for t, _ in selected]),
            "latitude": [float(source["lat"])], "longitude": [float(source["lon"])],
        })
        manifest = RunManifest(self.source_id, tuple(fields), min_coverage_fraction=0.01)
        validation = validate_run(manifest, dataset, window=window)
        path = workdir / f"{self.source_id}.zarr.zip"; write_zarr(dataset, path)
        provenance = {
            "source_id": self.source_id, "producer": "Deutscher Wetterdienst", "intermediary": "Bright Sky",
            "product": "MOSMIX_L station forecast", "station": {"wmo_station_id": "71801", "source_id": source.get("id"), "name": source.get("station_name")},
            "access_path": self.endpoint, "request_url": candidate.urls[0], "response_sha256": candidate.detail["sha256"],
            "run_identity": {"value": None, "certainty": "unknown", "reason": "Bright Sky response carries no MOSMIX cycle"},
            "native_crs": "EPSG:4326", "field_disposition": dispositions,
            "quality": validation.as_quality(), "coverage": validation.as_coverage(), "licence": "DWD terms apply; Bright Sky public instance is free",
            **manifest.as_manifest_block(),
        }
        artifact = Artifact("station-71801", MEDIA_ZARR, path, provenance)
        return RunResult(self.source_id, candidate.provider_run_id, None, datetime.now(UTC), validation.complete, validation.qc_passed, [artifact], "EPSG:4326", "experimental; not registered or scheduled")
