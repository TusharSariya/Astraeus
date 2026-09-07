"""Exact-time, MSC-only SWOB station demand query with a finite local cache."""
from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlencode

import httpx

from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from .models import (
    Coverage, DataMode, EvidenceField, Freshness, NativeReportIdentity, Provenance,
    Quality, SWOBAcquisition, SWOBDemandRequest, SWOBDemandUnavailable,
)

SWOB_BODY_MAX_BYTES = 256 * 1024
SWOB_CACHE_MAX_BYTES = 256 * 1024
SWOB_CACHE_MAX_ENTRIES = 32
SWOB_MAX_FEATURES = 64
SWOB_POLICY_TTL_SECONDS = 60
SWOB_MAX_CACHE_AGE_SECONDS = 300
SWOB_MAX_DISTANCE_DEGREES = 0.75
SWOB_DECODE_LIMITS = ProcessAllocationLimits(128 * 1024 * 1024, 1, SWOB_BODY_MAX_BYTES, 96 * 1024, 32 * 1024)
SWOB_ENDPOINT = "https://api.weather.gc.ca/collections/swob-realtime/items"

_FIELDS = {
    "temperature_2m": ("temperature_2m", "degC", "2 m"),
    "dew_point_2m": ("dew_point_2m", "degC", "2 m"),
    "relative_humidity_2m": ("relative_humidity_2m", "percent", "2 m"),
    "mean_sea_level_pressure": ("mean_sea_level_pressure", "hPa", "mean sea level"),
    "wind_speed_10m": ("wind_speed_10m", "m s-1", "10 m"),
    "wind_direction_10m": ("wind_direction_10m", "degree", "10 m"),
}


class SwobQueryUnavailable(RuntimeError):
    def __init__(self, message: str, *, reason: str = "query_failed", outcome: SWOBDemandUnavailable | None = None) -> None:
        super().__init__(message)
        self.outcome = outcome or SWOBDemandUnavailable(reason=reason, error_type=type(self).__name__)


@dataclass(frozen=True)
class SWOBStationObservation:
    station_id: str
    station_name: str | None
    observation_time: datetime
    latitude: float
    longitude: float
    dataset: str
    provider_report_id: str | None
    field_quality_tokens: Mapping[str, str]
    station_metadata: Mapping[str, str]
    values: Mapping[str, float | None]


@dataclass(frozen=True)
class SWOBCacheEntry:
    observations: tuple[SWOBStationObservation, ...]
    acquisition: SWOBAcquisition
    expires_at_monotonic: float

    @property
    def backing_bytes(self) -> int:
        return len(json.dumps({
            "observations": [{
                "station_id": item.station_id, "station_name": item.station_name,
                "observation_time": item.observation_time.isoformat(), "latitude": item.latitude,
                "longitude": item.longitude, "dataset": item.dataset, "provider_report_id": item.provider_report_id,
                "field_quality_tokens": dict(item.field_quality_tokens),
                "station_metadata": dict(item.station_metadata), "values": dict(item.values),
            } for item in self.observations],
            "acquisition": self.acquisition.model_dump(mode="json"),
        }, separators=(",", ":")).encode())


def _safe_headers(headers: Mapping[str, str], allowed: set[str], ceiling: int) -> dict[str, str]:
    retained = {key.lower(): value for key, value in headers.items() if key.lower() in allowed}
    if any(len(key.encode()) > 128 or len(value.encode()) > 2048 for key, value in retained.items()):
        raise SwobQueryUnavailable("SWOB transport metadata exceeds a field ceiling")
    if sum(len(key.encode()) + len(value.encode()) for key, value in retained.items()) > ceiling:
        raise SwobQueryUnavailable("SWOB transport metadata exceeds its retained-header ceiling")
    return retained


def _ttl(headers: Mapping[str, str], completed: datetime) -> int:
    max_age = None
    for token in headers.get("cache-control", "").split(","):
        name, separator, value = token.strip().partition("=")
        if separator and name.lower() == "max-age" and value.isdigit():
            max_age = int(value)
            break
    if max_age is None:
        return SWOB_POLICY_TTL_SECONDS
    if not 1 <= max_age <= SWOB_MAX_CACHE_AGE_SECONDS:
        raise SwobQueryUnavailable("SWOB max-age exceeds the supported finite bound")
    age_text = headers.get("age", "0").strip()
    if not age_text.isdigit():
        raise SwobQueryUnavailable("SWOB response has invalid Age metadata")
    apparent_age = 0
    if headers.get("date"):
        try:
            provider_date = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError) as error:
            raise SwobQueryUnavailable("SWOB response has invalid Date metadata") from error
        if provider_date.tzinfo is None:
            raise SwobQueryUnavailable("SWOB response Date has no offset")
        apparent_age = max(0, math.floor((completed - provider_date.astimezone(UTC)).total_seconds()))
    remaining = max_age - max(int(age_text), apparent_age)
    if remaining <= 0:
        raise SwobQueryUnavailable("SWOB response is already expired")
    return remaining


def _decode(body: bytes) -> tuple[SWOBStationObservation, ...]:
    result = run_bounded_process(
        command=[sys.executable, str(Path(__file__).with_name("swob_query_worker.py")), "{output}"],
        stdin=body, destination=None, limits=SWOB_DECODE_LIMITS, require_output=False,
    )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, list) or len(parsed) > SWOB_MAX_FEATURES:
        raise ValueError("SWOB decoder output has an invalid observation list")
    return tuple(SWOBStationObservation(
        station_id=str(item["station_id"]), station_name=item.get("station_name"),
        observation_time=datetime.fromisoformat(str(item["observation_time"])).astimezone(UTC),
        latitude=float(item["latitude"]), longitude=float(item["longitude"]), dataset=str(item["dataset"]),
        provider_report_id=None if item.get("provider_report_id") is None else str(item["provider_report_id"]),
        field_quality_tokens={str(key): str(value) for key, value in dict(item.get("field_quality_tokens", {})).items()},
        station_metadata={str(key): str(value) for key, value in dict(item.get("station_metadata", {})).items()},
        values={str(key): (None if value is None else float(value)) for key, value in dict(item["values"]).items()},
    ) for item in parsed)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request_url(latitude: float, longitude: float, selected: datetime) -> str:
    latitude_half = SWOB_MAX_DISTANCE_DEGREES
    # Selection measures longitude in latitude-corrected degrees. Make the
    # request envelope at least that wide at every permitted station latitude.
    furthest_latitude = min(89.999, abs(latitude) + latitude_half)
    longitude_half = min(180.0, latitude_half / max(math.cos(math.radians(furthest_latitude)), 1e-6))
    params = {
        "bbox": f"{longitude-longitude_half:.6f},{latitude-latitude_half:.6f},{longitude+longitude_half:.6f},{latitude+latitude_half:.6f}",
        "datetime": _stamp(selected), "limit": str(SWOB_MAX_FEATURES), "f": "json",
    }
    return f"{SWOB_ENDPOINT}?{urlencode(params)}"


def _distance_km(latitude: float, longitude: float, station: SWOBStationObservation) -> float:
    scale = math.cos(math.radians((latitude + station.latitude) / 2))
    return math.hypot(station.latitude - latitude, (station.longitude - longitude) * scale) * 111.32


class SWOBQueryService:
    def __init__(self, *, client: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
                 decode: Callable[[bytes], tuple[SWOBStationObservation, ...]] = _decode) -> None:
        self._client = client or httpx.Client(headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"}, timeout=30, follow_redirects=False)
        self._clock, self._utcnow, self._decode = clock, utcnow, decode
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, float, float], SWOBCacheEntry] = OrderedDict()
        self._expired: OrderedDict[tuple[str, float, float], SWOBAcquisition] = OrderedDict()
        self._inflight: dict[tuple[str, float, float], Future[SWOBCacheEntry]] = {}

    @staticmethod
    def _key(latitude: float, longitude: float, selected: datetime) -> tuple[str, float, float]:
        if selected.tzinfo is None:
            raise ValueError("SWOB selected time must include an offset")
        return selected.astimezone(UTC).isoformat(), round(latitude, 6), round(longitude, 6)

    def _prune_locked(self) -> None:
        def resident() -> int:
            return sum(item.backing_bytes for item in self._entries.values()) + sum(len(item.model_dump_json().encode()) for item in self._expired.values())
        while len(self._entries) + len(self._expired) > SWOB_CACHE_MAX_ENTRIES or resident() > SWOB_CACHE_MAX_BYTES:
            if self._expired:
                self._expired.popitem(last=False)
            elif len(self._entries) > 1:
                self._entries.popitem(last=False)
            else:
                raise SwobQueryUnavailable("SWOB cache residency exceeds its ceiling")

    def _fetch(self, latitude: float, longitude: float, selected: datetime) -> SWOBCacheEntry:
        instant = selected.astimezone(UTC)
        request_url = _request_url(latitude, longitude, instant)
        try:
            with self._client.stream("GET", request_url, headers={"Accept": "application/geo+json, application/json", "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    raise SwobQueryUnavailable(f"SWOB returned HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > SWOB_BODY_MAX_BYTES):
                    raise SwobQueryUnavailable("SWOB exceeds the received-body ceiling")
                chunks, size = [], 0
                for chunk in response.iter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > SWOB_BODY_MAX_BYTES:
                        raise SwobQueryUnavailable("SWOB exceeds the received-body ceiling")
                    chunks.append(chunk)
                body = b"".join(chunks)
                completed = self._utcnow()
                effective_url = str(response.request.url)
                request_headers = _safe_headers(response.request.headers, {"accept", "accept-encoding", "user-agent"}, 4 * 1024)
                response_headers = _safe_headers(response.headers, {"age", "cache-control", "content-type", "date", "etag", "last-modified"}, 8 * 1024)
        except httpx.HTTPError as error:
            raise SwobQueryUnavailable(f"SWOB transport failed: {type(error).__name__}") from error
        if effective_url != request_url:
            raise SwobQueryUnavailable("SWOB effective URL differs from the canonical request")
        if not body:
            raise SwobQueryUnavailable("SWOB returned an empty body")
        try:
            observations = self._decode(body)
        except Exception as error:
            raise SwobQueryUnavailable(f"SWOB validation failed: {type(error).__name__}") from error
        # Time is a source boundary as well: no earlier/later report is eligible.
        observations = tuple(item for item in observations if item.observation_time == instant)
        if not observations:
            raise SwobQueryUnavailable("SWOB has no canonical MSC station report at the exact selected time", reason="unsupported_time")
        ttl = _ttl(response_headers, completed)
        acquisition = SWOBAcquisition(
            request=SWOBDemandRequest(selected_time=instant, latitude=latitude, longitude=longitude, provider_url=request_url),
            effective_url=effective_url, request_headers=request_headers, response_headers=response_headers,
            transport_completed_at=completed, body_bytes=len(body), body_sha256=hashlib.sha256(body).hexdigest(),
            cached_at=completed, expires_at=completed + timedelta(seconds=ttl),
        )
        entry = SWOBCacheEntry(observations, acquisition, self._clock() + ttl)
        if entry.backing_bytes > SWOB_CACHE_MAX_BYTES:
            raise SwobQueryUnavailable("SWOB normalized cache entry exceeds its ceiling")
        return entry

    def entry_for(self, latitude: float, longitude: float, selected: datetime, *, refresh: bool = False) -> SWOBCacheEntry:
        key = self._key(latitude, longitude, selected)
        with self._lock:
            cached = self._entries.get(key)
            if not refresh and cached is not None and self._clock() < cached.expires_at_monotonic:
                self._entries.move_to_end(key)
                return cached
            if cached is not None and self._clock() >= cached.expires_at_monotonic:
                self._expired[key] = cached.acquisition
                self._expired.move_to_end(key)
                del self._entries[key]
                self._prune_locked()
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            replacement = self._fetch(latitude, longitude, selected)
            with self._lock:
                self._entries[key] = replacement
                self._entries.move_to_end(key)
                self._expired.pop(key, None)
                self._prune_locked()
            future.set_result(replacement)
            return replacement
        except BaseException as error:
            with self._lock:
                # An explicit refresh can fail after the retained entry expires.
                cached = self._entries.get(key)
                if cached is not None and self._clock() >= cached.expires_at_monotonic:
                    self._expired[key] = cached.acquisition
                    del self._entries[key]
                    self._prune_locked()
                expired = self._expired.get(key)
            if isinstance(error, SwobQueryUnavailable) and expired is not None:
                error.outcome = SWOBDemandUnavailable(reason="refresh_failed", error_type=type(error).__name__, expired_acquisition=expired)
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def point_fields(self, latitude: float, longitude: float, selected: datetime, *, refresh: bool = False) -> list[EvidenceField]:
        entry = self.entry_for(latitude, longitude, selected, refresh=refresh)
        return self.point_fields_from_entry(entry, latitude, longitude, selected)

    def point_fields_from_entry(self, entry: SWOBCacheEntry, latitude: float, longitude: float,
                                selected: datetime) -> list[EvidenceField]:
        """Read one finite acquired snapshot without acquisition or time substitution."""
        request = entry.acquisition.request
        if self._key(latitude, longitude, selected) != self._key(request.latitude, request.longitude, request.selected_time):
            raise SwobQueryUnavailable("SWOB snapshot does not match the exact selected request", reason="unsupported_time")
        if self._clock() >= entry.expires_at_monotonic:
            raise SwobQueryUnavailable("SWOB snapshot has expired", outcome=SWOBDemandUnavailable(
                reason="refresh_failed", error_type="SwobQueryUnavailable", expired_acquisition=entry.acquisition,
            ))
        station = min(entry.observations, key=lambda item: (_distance_km(latitude, longitude, item), item.station_id))
        distance = _distance_km(latitude, longitude, station)
        if distance / 111.32 > SWOB_MAX_DISTANCE_DEGREES:
            raise SwobQueryUnavailable("SWOB has no applicable canonical MSC station near the requested coordinate")
        report = NativeReportIdentity(
            station_id=station.station_id, provider_report_id=station.provider_report_id,
            observation_time=station.observation_time, provider_station_name=station.station_name, provider_latitude=station.latitude, provider_longitude=station.longitude,
            native_metadata={"dataset": station.dataset, **dict(station.station_metadata)},
        )
        age = max(0, int((self._utcnow() - entry.acquisition.transport_completed_at).total_seconds()))
        ttl = max(1, int((entry.acquisition.expires_at - entry.acquisition.cached_at).total_seconds()))
        fields: list[EvidenceField] = []
        for field, (key, units, level) in _FIELDS.items():
            value = station.values.get(field)
            token = station.field_quality_tokens.get(field)
            flags = ["native_swob", *( [f"provider_quality:{token}"] if token else [])]
            fields.append(EvidenceField(
                field=field, key=key, value=value, storage="available-not-stored",
                provenance=Provenance(
                    data_mode=DataMode.LIVE, evidence_class="retrieved", source_id="eccc-swob",
                    artifact_revision=f"demand:{entry.acquisition.body_sha256}", provider="Environment and Climate Change Canada",
                    product="MSC SWOB real-time surface observation via GeoMet OGC API Features",
                    forecast_centre="Environment and Climate Change Canada", run_time=None,
                    valid_time=station.observation_time, retrieval_time=entry.acquisition.transport_completed_at,
                    vertical_level=level, original_units=units, normalized_units=units,
                    native_resolution="station point", native_crs="EPSG:4326",
                    quality=Quality(status="unknown", flags=flags), coverage=Coverage(status="complete", fraction=1.0),
                    freshness=Freshness.evaluate(age, ttl), licence="MSC Open Data licence",
                    attribution="Credit Environment and Climate Change Canada; MSC SWOB observation via GeoMet",
                    delivery_kind="published_cell", source_display_primary=False, adapter_version="eccc-swob-demand-v1",
                    native_report=report, swob_acquisition=entry.acquisition,
                    sampled_latitude=station.latitude, sampled_longitude=station.longitude,
                    sample_distance_km=distance, sample_method="nearest_published_cell",
                    run_stale=None, run_stale_reason="SWOB is a station observation and has no model run",
                ),
            ))
        return fields

    def cached_entries_for(self, latitude: float, longitude: float) -> tuple[SWOBCacheEntry, ...]:
        """Finite native-time planning snapshot for this exact request location.

        The returned times are actual reports already retrieved, never a cadence
        or an assertion that uncached hours have station coverage.
        """
        location = round(latitude, 6), round(longitude, 6)
        with self._lock:
            return tuple(sorted((entry for key, entry in self._entries.items()
                                 if key[1:] == location and self._clock() < entry.expires_at_monotonic),
                                key=lambda entry: entry.acquisition.request.selected_time))

    def cached_entries(self) -> tuple[SWOBCacheEntry, ...]:
        with self._lock:
            return tuple(item for item in self._entries.values() if self._clock() < item.expires_at_monotonic)


_service: SWOBQueryService | None = None


def swob_query_service() -> SWOBQueryService:
    global _service
    if _service is None:
        _service = SWOBQueryService()
    return _service


def demand_layer(layer_type, *, z_index: int):
    """Describe cached SWOB station capability without making a provider request."""
    entries = swob_query_service().cached_entries()
    times = sorted({observation.observation_time for entry in entries for observation in entry.observations})
    from .layer_identity import imagery, mappings
    from datetime import UTC
    return layer_type(
        **mappings([('eccc-swob', key) for key in _FIELDS]),
        imagery_availability=imagery("unavailable", datetime.now(UTC), "non_raster_layer", "This source exposes station features, not raster imagery"),
        id="eccc-swob-demand-observations",
        title="ECCC MSC SWOB station observations (selected-time demand points)",
        kind="point", field="temperature_2m", product="ECCC MSC SWOB", units="mixed native units",
        semantics="Native MSC SWOB station readings at the exact selected report time; nearest published station only, no interpolation, stale fallback, or partner observations",
        evidence_class="retrieved", family="surface_observation", field_key="temperature_2m",
        times=times, cadence_seconds=None, staleness_tolerance_seconds=SWOB_POLICY_TTL_SECONDS,
        z_index=z_index, evidence_basis="demand_query", group="observation",
        raster_available=False, legend_available=False,
        run_time=None, run_stale=None,
        run_stale_reason="SWOB is a station observation and has no model run",
    )
