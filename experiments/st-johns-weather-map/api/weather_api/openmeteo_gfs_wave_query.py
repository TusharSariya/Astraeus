"""Bounded live Open-Meteo GFS-Wave point queries.

The Marine API does not declare a producer-run identifier in its point response.
This path therefore records the actual HTTP retrieval and returned grid cell, but
does not invent a run stamp from another Open-Meteo endpoint's metadata.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

import httpx

from .models import Coverage, DataMode, EvidenceField, Freshness, Provenance, Quality

OPEN_METEO_GFS_WAVE_URL = "https://marine-api.open-meteo.com/v1/marine"
OPEN_METEO_GFS_WAVE_MODEL = "ncep_gfswave016"
OPEN_METEO_GFS_WAVE_FIELDS = (
    "wave_height", "wave_period", "wave_direction",
    "swell_wave_height", "swell_wave_period", "swell_wave_direction",
    "wind_wave_height", "wind_wave_period", "wind_wave_direction",
)
OPEN_METEO_GFS_WAVE_UNITS = {
    "wave_height": ("m", "m"), "swell_wave_height": ("m", "m"), "wind_wave_height": ("m", "m"),
    "wave_period": ("s", "s"), "swell_wave_period": ("s", "s"), "wind_wave_period": ("s", "s"),
    "wave_direction": ("°", "degree"), "swell_wave_direction": ("°", "degree"), "wind_wave_direction": ("°", "degree"),
}
OPEN_METEO_GFS_WAVE_API_FIELDS = {
    "wave_height": ("wave_height", "significant_wave_height"),
    "wave_period": ("wave_period", "wave_period"),
    "wave_direction": ("wave_direction", "wave_direction"),
    "swell_wave_height": ("swell_height", "swell_height"),
    "swell_wave_period": ("swell_wave_period", "swell_wave_period"),
    "swell_wave_direction": ("swell_wave_direction", "swell_wave_direction"),
    "wind_wave_height": ("wind_wave_height", "wind_wave_height"),
    "wind_wave_period": ("wind_wave_period", "wind_wave_period"),
    "wind_wave_direction": ("wind_wave_direction", "wind_wave_direction"),
}
OPEN_METEO_GFS_WAVE_CACHE_TTL_SECONDS = 300
OPEN_METEO_GFS_WAVE_CACHE_MAX_ENTRIES = 32
OPEN_METEO_GFS_WAVE_CACHE_MAX_BYTES = 256 * 1024
# The fixed one-hour, nine-field shape and 2 KiB received-body ceiling bound
# both transient JSON decoding and retained data.  Only normalized values and
# selected freshness metadata remain in the aggregate cache budget.
OPEN_METEO_GFS_WAVE_MAX_RESPONSE_BYTES = 2 * 1024
_MAX_AGE = re.compile(r"(?:^|,)\s*max-age=(\d+)\s*(?:,|$)", re.I)


class OpenMeteoGfsWaveUnavailable(RuntimeError):
    """The exact requested marine hour has no fresh validated response."""


@dataclass(frozen=True)
class OpenMeteoGfsWaveRequestKey:
    latitude: str
    longitude: str
    valid_time: datetime
    fields: tuple[str, ...]
    model: str = OPEN_METEO_GFS_WAVE_MODEL
    cell_selection: str = "sea"


@dataclass(frozen=True)
class OpenMeteoGfsWaveEntry:
    key: OpenMeteoGfsWaveRequestKey
    values: Mapping[str, float | None]
    sampled_latitude: float
    sampled_longitude: float
    completed_at: datetime
    body_sha256: str
    body_bytes: int
    effective_url: str
    response_headers: Mapping[str, str]
    missing_fields: tuple[str, ...] = ()
    cache_ttl_seconds: int = OPEN_METEO_GFS_WAVE_CACHE_TTL_SECONDS

    @property
    def backing_bytes(self) -> int:
        # Raw bytes and decoded JSON are transient: only the nine values,
        # compact transport metadata, and provenance-driving identity remain
        # resident after this method returns.
        return len(json.dumps({"values": self.values, "headers": self.response_headers}, sort_keys=True).encode()) + 1024


def _canonical_coordinate(value: float) -> str:
    if not math.isfinite(value) or not -180 <= value <= 180:
        raise ValueError("Open-Meteo GFS-Wave coordinate is invalid")
    return f"{value:.6f}"


def _hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Open-Meteo GFS-Wave selected time must include an offset")
    instant = value.astimezone(UTC)
    if instant.minute or instant.second or instant.microsecond:
        raise ValueError("Open-Meteo GFS-Wave only serves exact native hourly timestamps")
    return instant


def _native_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave hourly time is not a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave hourly time is invalid") from error
    # The canonical request explicitly asks for GMT, so the documented
    # offset-less ISO result is UTC.  A supplied offset is preserved instead.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class OpenMeteoGfsWaveQueryService:
    """Cache one canonical point-hour request and coalesce identical misses."""

    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=30, follow_redirects=False,
        )
        self._clock, self._utcnow = clock, utcnow
        self._lock = threading.Lock()
        self._entries: dict[OpenMeteoGfsWaveRequestKey, tuple[float, OpenMeteoGfsWaveEntry]] = {}
        self._inflight: dict[OpenMeteoGfsWaveRequestKey, Future[OpenMeteoGfsWaveEntry]] = {}

    def query(self, latitude: float, longitude: float, selected_time: datetime) -> OpenMeteoGfsWaveEntry:
        valid_time = _hour(selected_time)
        key = OpenMeteoGfsWaveRequestKey(
            _canonical_coordinate(latitude), _canonical_coordinate(longitude), valid_time, OPEN_METEO_GFS_WAVE_FIELDS,
        )
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and self._clock() < cached[0]:
                return cached[1]
            self._entries.pop(key, None)
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            entry = self._fetch(key)
            if entry.key != key or entry.backing_bytes <= 0 or entry.backing_bytes > OPEN_METEO_GFS_WAVE_CACHE_MAX_BYTES:
                raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response violates the bounded canonical cache")
            with self._lock:
                self._entries[key] = (self._clock() + entry.cache_ttl_seconds, entry)
                while (
                    len(self._entries) > OPEN_METEO_GFS_WAVE_CACHE_MAX_ENTRIES
                    or sum(item.backing_bytes for _, item in self._entries.values()) > OPEN_METEO_GFS_WAVE_CACHE_MAX_BYTES
                ):
                    oldest = next(iter(self._entries))
                    self._entries.pop(oldest)
            future.set_result(entry)
            return entry
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def _fetch(self, key: OpenMeteoGfsWaveRequestKey) -> OpenMeteoGfsWaveEntry:
        stamp = key.valid_time.strftime("%Y-%m-%dT%H:%M")
        params = {
            "latitude": key.latitude, "longitude": key.longitude, "hourly": ",".join(key.fields),
            "models": key.model, "cell_selection": key.cell_selection, "timezone": "GMT",
            "start_hour": stamp, "end_hour": stamp,
        }
        try:
            with self._client.stream("GET", OPEN_METEO_GFS_WAVE_URL, params=params,
                                     headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    raise OpenMeteoGfsWaveUnavailable(f"Open-Meteo GFS-Wave returned HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > OPEN_METEO_GFS_WAVE_MAX_RESPONSE_BYTES):
                    raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response exceeds its byte ceiling")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes(1024):
                    size += len(chunk)
                    if size > OPEN_METEO_GFS_WAVE_MAX_RESPONSE_BYTES:
                        raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response exceeds its byte ceiling")
                    chunks.append(chunk)
                body = b"".join(chunks)
                completed_at = self._utcnow()
                effective_url = str(response.request.url)
                headers = {
                    name.lower(): value for name, value in response.headers.items()
                    if name.lower() in {"cache-control", "age", "date"}
                }
        except httpx.HTTPError as error:
            raise OpenMeteoGfsWaveUnavailable(f"Open-Meteo GFS-Wave transport failed: {type(error).__name__}") from error
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave returned malformed JSON") from error
        if not isinstance(payload, dict) or payload.get("error") is True:
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave rejected the canonical request")
        allowed_top_level = {
            "latitude", "longitude", "generationtime_ms", "utc_offset_seconds", "timezone",
            "timezone_abbreviation", "elevation", "hourly", "hourly_units",
        }
        if set(payload) - allowed_top_level or not {"latitude", "longitude", "hourly", "hourly_units"} <= set(payload):
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response has an unexpected structure")
        hourly, units = payload.get("hourly"), payload.get("hourly_units")
        if not isinstance(hourly, dict) or not isinstance(units, dict):
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response has no hourly arrays")
        expected_hourly_keys = {"time", *key.fields}
        if (
            "time" not in hourly or "time" not in units
            or set(hourly) - expected_hourly_keys or set(units) - expected_hourly_keys
        ):
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response has an unexpected field inventory")
        times = hourly.get("time")
        if not isinstance(times, list) or len(times) != 1 or _native_timestamp(times[0]) != key.valid_time:
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave did not return the exact selected native hour")
        values: dict[str, float | None] = {}
        missing_fields: list[str] = []
        for field in key.fields:
            raw_values = hourly.get(field)
            original, _normalized = OPEN_METEO_GFS_WAVE_UNITS[field]
            # A provider may leave one optional native series out of a model
            # response.  Preserve that absence for this field without erasing
            # siblings that did validate; malformed values below still fail the
            # particular field rather than becoming a fabricated number.
            if units.get(field) != original or not isinstance(raw_values, list) or len(raw_values) != 1:
                values[field] = None
                missing_fields.append(field)
                continue
            value = raw_values[0]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))):
                values[field] = None
                missing_fields.append(field)
                continue
            values[field] = None if value is None else float(value)
        if not any(value is not None for value in values.values()):
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave returned no sea-cell values")
        lat, lon = payload.get("latitude"), payload.get("longitude")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in (lat, lon)):
            raise OpenMeteoGfsWaveUnavailable("Open-Meteo GFS-Wave response has invalid sampled coordinates")
        return OpenMeteoGfsWaveEntry(
            key, values, float(lat), float(lon), completed_at, hashlib.sha256(body).hexdigest(), len(body), effective_url, headers,
            tuple(missing_fields), _cache_ttl_seconds(headers),
        )

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime) -> list[EvidenceField]:
        entry = self.query(latitude, longitude, selected_time)
        distance = _distance_km(latitude, longitude, entry.sampled_latitude, entry.sampled_longitude)
        fields: list[EvidenceField] = []
        # The response is already the selected native hour.  There is no
        # documented producer-run field, so run time and run staleness remain
        # unknown instead of importing atmospheric meta.json as false identity.
        for field, value in entry.values.items():
            original_units, normalized_units = OPEN_METEO_GFS_WAVE_UNITS[field]
            api_field, catalogue_key = OPEN_METEO_GFS_WAVE_API_FIELDS[field]
            flags = ["exact_native_hour", "cell_selection:sea"]
            if field in entry.missing_fields:
                flags.append("native_field_unavailable")
            fields.append(EvidenceField(
                field=api_field, key=catalogue_key, value=value,
                provenance=Provenance(
                    data_mode=DataMode.LIVE, evidence_class="reprocessed", source_id="openmeteo-gfs-wave",
                    artifact_revision=f"demand:{entry.body_sha256}", provider="NOAA NCEP",
                    product="GFS-Wave 0.16 degree via Open-Meteo", forecast_centre="NOAA NCEP",
                    run_time=None, valid_time=entry.key.valid_time, retrieval_time=entry.completed_at,
                    vertical_level="sea surface", original_units=original_units, normalized_units=normalized_units,
                    native_resolution="0.16 degree", native_crs="EPSG:4326",
                    quality=Quality(status="unknown" if value is None else "passed", flags=flags),
                    coverage=Coverage(status="complete", fraction=1.0),
                    freshness=Freshness.evaluate(
                        max(0, int((self._utcnow() - entry.completed_at).total_seconds())),
                        entry.cache_ttl_seconds,
                    ),
                    licence="CC BY 4.0", attribution="NOAA NCEP GFS-Wave forecast via Open-Meteo",
                    delivery_kind="reprocessed", source_display_primary=False, intermediary="Open-Meteo",
                    intermediary_method="Open-Meteo marine point response; provider run identity is not exposed",
                    adapter_version="openmeteo-gfs-wave-demand-v1", sampled_latitude=entry.sampled_latitude,
                    sampled_longitude=entry.sampled_longitude, sample_distance_km=distance, sample_method="rectilinear",
                    run_stale=None, run_stale_reason="Open-Meteo Marine API response does not declare a GFS-Wave run identifier",
                ),
            ))
        return fields


def _distance_km(latitude: float, longitude: float, sampled_latitude: float, sampled_longitude: float) -> float:
    lat_radians = math.radians((latitude + sampled_latitude) / 2)
    return math.hypot(sampled_latitude - latitude, (sampled_longitude - longitude) * math.cos(lat_radians)) * 111.32


def _cache_ttl_seconds(headers: Mapping[str, str]) -> int:
    """Use a finite provider freshness directive when it is supplied.

    The free endpoint does not promise one, so its absence leaves the measured
    five-minute source-local ceiling in force.  An invalid, expired or broader
    directive never extends that ceiling.
    """
    match = _MAX_AGE.search(headers.get("cache-control", ""))
    if match is None:
        return OPEN_METEO_GFS_WAVE_CACHE_TTL_SECONDS
    age_text = headers.get("age", "0").strip()
    age = int(age_text) if age_text.isdigit() else 0
    return max(1, min(OPEN_METEO_GFS_WAVE_CACHE_TTL_SECONDS, int(match.group(1)) - age))


_SERVICE: OpenMeteoGfsWaveQueryService | None = None


def openmeteo_gfs_wave_query_service() -> OpenMeteoGfsWaveQueryService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = OpenMeteoGfsWaveQueryService()
    return _SERVICE
