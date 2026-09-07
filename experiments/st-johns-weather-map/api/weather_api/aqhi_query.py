"""Bounded selected-time query cache for native ECCC AQHI observations."""
from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping

import httpx

from ingest.adapters.eccc_geomet import AQHI_LAYER, GEOMET_BASE_URL, GeoMetClient, avalon_probe_boxes
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from .models import (
    AQHIAcquisition, AQHIDemandUnavailable, Coverage, DataMode, EvidenceField,
    Freshness, NativeReportIdentity, Provenance, Quality,
)

AQHI_BODY_MAX_BYTES = 2 * 1024 * 1024
AQHI_CACHE_MAX_BYTES = 256 * 1024
AQHI_MAX_FEATURES = 50
AQHI_POLICY_TTL_SECONDS = 60
AQHI_MAX_CACHE_AGE_SECONDS = 300
AQHI_NATIVE_MAX_AGE_SECONDS = 3600
AQHI_MAX_DISTANCE_DEGREES = 0.75
AQHI_DECODE_LIMITS = ProcessAllocationLimits(128 * 1024 * 1024, 1, AQHI_BODY_MAX_BYTES, 192 * 1024, 64 * 1024)


class AqhiQueryUnavailable(RuntimeError):
    """A fresh current document cannot truthfully answer the selected point."""

    def __init__(self, message: str, *, outcome: AQHIDemandUnavailable | None = None) -> None:
        super().__init__(message)
        self.outcome = outcome or AQHIDemandUnavailable(reason="query_failed", error_type=type(self).__name__)


@dataclass(frozen=True)
class AQHIStationObservation:
    station_id: str
    station_name: str | None
    observation_time: datetime
    latitude: float
    longitude: float
    value: float
    quality: str | None


@dataclass(frozen=True)
class AQHICacheEntry:
    observations: tuple[AQHIStationObservation, ...]
    acquisition: AQHIAcquisition
    expires_at_monotonic: float

    @property
    def backing_bytes(self) -> int:
        return len(json.dumps({
            "observations": [item.__dict__ | {"observation_time": item.observation_time.isoformat()} for item in self.observations],
            "acquisition": self.acquisition.model_dump(mode="json"),
        }, separators=(",", ":")).encode())


def _safe_headers(headers: Mapping[str, str], allowed: set[str], ceiling: int) -> dict[str, str]:
    retained = {key.lower(): value for key, value in headers.items() if key.lower() in allowed}
    if any(len(key.encode()) > 128 or len(value.encode()) > 2048 for key, value in retained.items()):
        raise AqhiQueryUnavailable("ECCC AQHI transport metadata exceeds a field ceiling")
    if sum(len(key.encode()) + len(value.encode()) for key, value in retained.items()) > ceiling:
        raise AqhiQueryUnavailable("ECCC AQHI transport metadata exceeds its retained-header ceiling")
    return retained


def _ttl(headers: Mapping[str, str], completed: datetime) -> int:
    cache_control = headers.get("cache-control", "")
    max_age: int | None = None
    for token in cache_control.split(","):
        name, separator, value = token.strip().partition("=")
        if separator and name.lower() == "max-age" and value.isdigit():
            max_age = int(value)
            break
    if max_age is None:
        return AQHI_POLICY_TTL_SECONDS
    if not 1 <= max_age <= AQHI_MAX_CACHE_AGE_SECONDS:
        raise AqhiQueryUnavailable("ECCC AQHI max-age exceeds the supported finite bound")
    age_text = headers.get("age", "0").strip()
    if not age_text.isdigit():
        raise AqhiQueryUnavailable("ECCC AQHI response has invalid Age metadata")
    apparent_age = 0
    if headers.get("date"):
        try:
            provider_date = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError) as error:
            raise AqhiQueryUnavailable("ECCC AQHI response has invalid Date metadata") from error
        if provider_date.tzinfo is None:
            raise AqhiQueryUnavailable("ECCC AQHI response Date has no offset")
        apparent_age = max(0, math.floor((completed - provider_date.astimezone(UTC)).total_seconds()))
    remaining = max_age - max(int(age_text), apparent_age)
    if remaining <= 0:
        raise AqhiQueryUnavailable("ECCC AQHI response is already expired")
    return remaining


def _decode(body: bytes) -> tuple[AQHIStationObservation, ...]:
    result = run_bounded_process(
        command=[sys.executable, "-m", "weather_api.aqhi_query_worker"], stdin=body,
        destination=None, limits=AQHI_DECODE_LIMITS, require_output=False,
    )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, list) or len(parsed) > AQHI_MAX_FEATURES:
        raise ValueError("AQHI decoder output has an invalid observation list")
    return tuple(AQHIStationObservation(
        station_id=str(item["station_id"]), station_name=item.get("station_name"),
        observation_time=datetime.fromisoformat(str(item["observation_time"])).astimezone(UTC),
        latitude=float(item["latitude"]), longitude=float(item["longitude"]),
        value=float(item["value"]), quality=str(item["quality"]) if item.get("quality") is not None else None,
    ) for item in parsed)


def _distance_km(latitude: float, longitude: float, station: AQHIStationObservation) -> float:
    latitude_scale = math.cos(math.radians((latitude + station.latitude) / 2))
    return math.hypot(station.latitude - latitude, (station.longitude - longitude) * latitude_scale) * 111.32


def _request_url() -> str:
    box = avalon_probe_boxes()[0]
    latitude = round((box["south"] + box["north"]) / 2, 6)
    longitude = round((box["west"] + box["east"]) / 2, 6)
    geomet = GeoMetClient()
    return geomet.url({
        "request": "GetFeatureInfo", "layers": AQHI_LAYER, "query_layers": AQHI_LAYER,
        "info_format": "application/json", "feature_count": AQHI_MAX_FEATURES,
        **geomet._probe_params(latitude, longitude, box),
    })


class AQHIQueryService:
    """One coalesced current-document cache retaining normalized station rows."""

    def __init__(self, *, client: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
                 decode: Callable[[bytes], tuple[AQHIStationObservation, ...]] = _decode) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=30, follow_redirects=False,
        )
        self._clock, self._utcnow, self._decode = clock, utcnow, decode
        self.request_url = _request_url()
        self._lock = threading.Lock()
        self._entry: AQHICacheEntry | None = None
        self._expired_acquisition: AQHIAcquisition | None = None
        self._inflight: Future[AQHICacheEntry] | None = None

    def _fetch(self) -> AQHICacheEntry:
        try:
            with self._client.stream("GET", self.request_url, headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    raise AqhiQueryUnavailable(f"ECCC AQHI returned HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > AQHI_BODY_MAX_BYTES):
                    raise AqhiQueryUnavailable("ECCC AQHI exceeds the received-body ceiling")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > AQHI_BODY_MAX_BYTES:
                        raise AqhiQueryUnavailable("ECCC AQHI exceeds the received-body ceiling")
                    chunks.append(chunk)
                body = b"".join(chunks)
                completed = self._utcnow()
                effective_url = str(response.request.url)
                request_headers = _safe_headers(response.request.headers, {"accept", "accept-encoding", "user-agent"}, 4 * 1024)
                response_headers = _safe_headers(response.headers, {"age", "cache-control", "content-type", "date", "etag", "last-modified"}, 8 * 1024)
        except httpx.HTTPError as error:
            raise AqhiQueryUnavailable(f"ECCC AQHI transport failed: {type(error).__name__}") from error
        if effective_url != self.request_url:
            raise AqhiQueryUnavailable("ECCC AQHI effective URL differs from the canonical request")
        try:
            observations = self._decode(body)
        except Exception as error:
            raise AqhiQueryUnavailable(f"ECCC AQHI validation failed: {type(error).__name__}") from error
        if not observations:
            raise AqhiQueryUnavailable("ECCC AQHI returned no station observations")
        ttl = _ttl(response_headers, completed)
        acquisition = AQHIAcquisition(
            provider_url=self.request_url, effective_url=effective_url,
            request_headers=request_headers, response_headers=response_headers,
            transport_completed_at=completed, body_bytes=len(body),
            body_sha256=hashlib.sha256(body).hexdigest(), cached_at=completed,
            expires_at=completed + timedelta(seconds=ttl),
        )
        entry = AQHICacheEntry(observations, acquisition, self._clock() + ttl)
        if entry.backing_bytes > AQHI_CACHE_MAX_BYTES:
            raise AqhiQueryUnavailable("ECCC AQHI normalized cache entry exceeds its ceiling")
        return entry

    def entry(self) -> AQHICacheEntry:
        with self._lock:
            cached = self._entry
            if cached is not None and self._clock() < cached.expires_at_monotonic:
                return cached
            self._entry = None
            if cached is not None:
                self._expired_acquisition = cached.acquisition
            future = self._inflight
            owner = future is None
            if owner:
                future = Future()
                self._inflight = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            replacement = self._fetch()
            with self._lock:
                self._entry = replacement
                self._expired_acquisition = None
            future.set_result(replacement)
            return replacement
        except BaseException as error:
            if isinstance(error, AqhiQueryUnavailable):
                error.outcome = AQHIDemandUnavailable(
                    reason="refresh_failed", error_type=type(error).__name__,
                    expired_acquisition=self._expired_acquisition,
                )
            future.set_exception(error)
            raise error
        finally:
            with self._lock:
                self._inflight = None

    def cached_entry(self) -> AQHICacheEntry | None:
        with self._lock:
            return self._entry if self._entry is not None and self._clock() < self._entry.expires_at_monotonic else None

    def point_field(self, latitude: float, longitude: float, selected: datetime) -> EvidenceField:
        if selected.tzinfo is None:
            raise ValueError("AQHI selected time must include an offset")
        instant = selected.astimezone(UTC)
        entry = self.entry()
        eligible = [item for item in entry.observations if item.observation_time <= instant and instant - item.observation_time < timedelta(hours=1)]
        if not eligible:
            raise AqhiQueryUnavailable("ECCC AQHI has no station observation less than one hour old at or before the selection")
        station = min(eligible, key=lambda item: (_distance_km(latitude, longitude, item), -item.observation_time.timestamp(), item.station_id))
        corrected_degrees = _distance_km(latitude, longitude, station) / 111.32
        if corrected_degrees > AQHI_MAX_DISTANCE_DEGREES:
            raise AqhiQueryUnavailable("ECCC AQHI has no applicable published station near the requested coordinate")
        distance = _distance_km(latitude, longitude, station)
        report = NativeReportIdentity(
            station_id=station.station_id, observation_time=station.observation_time,
            provider_station_name=station.station_name, provider_latitude=station.latitude,
            provider_longitude=station.longitude,
            native_metadata={"provider_quality": station.quality} if station.quality is not None else {},
        )
        return EvidenceField(
            field="aqhi", key="air_quality_health_index", value=station.value,
            storage="available-not-stored",
            provenance=Provenance(
                data_mode=DataMode.LIVE, evidence_class="retrieved", source_id="eccc-aqhi",
                artifact_revision=f"demand:{entry.acquisition.body_sha256}",
                provider="Environment and Climate Change Canada",
                product="Air Quality Health Index observations via GeoMet WMS",
                forecast_centre="Environment and Climate Change Canada", run_time=None,
                valid_time=station.observation_time, retrieval_time=entry.acquisition.transport_completed_at,
                vertical_level="station", original_units="index", normalized_units="index",
                native_resolution="station point", native_crs="EPSG:4326",
                # No accepted mapping declares any provider token a passing QC
                # code. Preserve the native token while keeping our verdict
                # unknown rather than silently certifying it.
                quality=Quality(status="unknown", flags=["native_aqhi", *( [f"provider_quality:{station.quality}"] if station.quality else [])]),
                coverage=Coverage(status="complete", fraction=1.0),
                freshness=Freshness.evaluate(max(0, int((instant - station.observation_time).total_seconds())), AQHI_NATIVE_MAX_AGE_SECONDS),
                licence="MSC Open Data licence",
                attribution="Credit Environment and Climate Change Canada; AQHI observation via MSC GeoMet",
                delivery_kind="published_cell", source_display_primary=False,
                adapter_version="eccc-geomet-aqhi-demand-v1", native_report=report,
                aqhi_acquisition=entry.acquisition,
                sampled_latitude=station.latitude, sampled_longitude=station.longitude,
                sample_distance_km=distance, sample_method="nearest_published_cell",
                run_stale=None, run_stale_reason="AQHI is a station observation and has no model run",
            ),
        )


_service: AQHIQueryService | None = None


def aqhi_query_service() -> AQHIQueryService:
    global _service
    if _service is None:
        _service = AQHIQueryService()
    return _service


def demand_layer(layer_type, *, z_index: int):
    """Describe the local demand capability from cache metadata only."""
    entry = aqhi_query_service().cached_entry()
    times = sorted({item.observation_time for item in entry.observations}) if entry else []
    return layer_type(
        id="eccc-aqhi-demand-observations",
        title="ECCC AQHI station observations (selected-time demand points)",
        kind="point", field="aqhi", product="ECCC AQHI", units="index",
        semantics="Native station AQHI index; nearest published station, no interpolation and never substituted for particulate matter or aerosol fields",
        evidence_class="retrieved", family="air_quality", field_key="air_quality_health_index",
        times=times, cadence_seconds=3600, staleness_tolerance_seconds=3600,
        z_index=z_index, evidence_basis="demand_query", group="observation",
        raster_available=False, legend_available=False,
        run_time=None, run_stale=None,
        run_stale_reason="AQHI is a station observation and has no model run",
    )
