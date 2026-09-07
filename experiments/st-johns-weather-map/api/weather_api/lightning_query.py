"""Exact-frame demand query and finite cache for ECCC lightning density."""
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

import httpx

from ingest.adapters.eccc_geomet import GEOMET_BASE_URL, LIGHTNING_LAYER, GeoMetClient
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from .models import (
    Coverage, DataMode, EvidenceField, Freshness, LightningAcquisition,
    LightningDemandRequest, LightningDemandUnavailable, LightningTransportReceipt,
    Provenance, Quality,
)

CAPABILITIES_MAX_BYTES = 256 * 1024
SAMPLE_MAX_BYTES = 64 * 1024
CACHE_MAX_BYTES = 256 * 1024
CACHE_MAX_ENTRIES = 32
POLICY_TTL_SECONDS = 60
MAX_TTL_SECONDS = 600
MAX_GRID_DISTANCE_DEGREES = 0.75
DECODE_LIMITS = ProcessAllocationLimits(96 * 1024 * 1024, 1, CAPABILITIES_MAX_BYTES, 64 * 1024, 32 * 1024)


class LightningQueryUnavailable(RuntimeError):
    def __init__(self, message: str, *, reason: str = "query_failed", outcome: LightningDemandUnavailable | None = None) -> None:
        super().__init__(message)
        self.outcome = outcome or LightningDemandUnavailable(reason=reason, error_type=type(self).__name__)


@dataclass(frozen=True)
class LightningSample:
    value: float | None
    latitude: float | None
    longitude: float | None
    title: str | None
    native_units: str | None


@dataclass(frozen=True)
class LightningCacheEntry:
    sample: LightningSample
    acquisition: LightningAcquisition
    expires_at_monotonic: float

    @property
    def backing_bytes(self) -> int:
        return len(json.dumps({
            "sample": self.sample.__dict__,
            "acquisition": self.acquisition.model_dump(mode="json"),
        }, separators=(",", ":")).encode())


def _safe_headers(headers: Mapping[str, str], allowed: set[str], ceiling: int) -> dict[str, str]:
    retained = {key.lower(): value for key, value in headers.items() if key.lower() in allowed}
    if any(len(key.encode()) > 128 or len(value.encode()) > 2048 for key, value in retained.items()):
        raise LightningQueryUnavailable("ECCC lightning transport metadata exceeds a field ceiling")
    if sum(len(key.encode()) + len(value.encode()) for key, value in retained.items()) > ceiling:
        raise LightningQueryUnavailable("ECCC lightning transport metadata exceeds its header ceiling")
    return retained


def _ttl(headers: Mapping[str, str], completed: datetime) -> int:
    max_age = None
    for token in headers.get("cache-control", "").split(","):
        name, separator, value = token.strip().partition("=")
        if separator and name.lower() == "max-age" and value.isdigit():
            max_age = int(value)
            break
    if max_age is None:
        return POLICY_TTL_SECONDS
    if max_age < 1:
        raise LightningQueryUnavailable("ECCC lightning response is already expired")
    age_text = headers.get("age", "0").strip()
    if not age_text.isdigit():
        raise LightningQueryUnavailable("ECCC lightning response has invalid Age metadata")
    apparent_age = 0
    if headers.get("date"):
        try:
            provider_date = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError) as error:
            raise LightningQueryUnavailable("ECCC lightning response has invalid Date metadata") from error
        if provider_date.tzinfo is None:
            raise LightningQueryUnavailable("ECCC lightning response Date has no offset")
        apparent_age = max(0, math.floor((completed - provider_date.astimezone(UTC)).total_seconds()))
    remaining = min(max_age, MAX_TTL_SECONDS) - max(int(age_text), apparent_age)
    if remaining <= 0:
        raise LightningQueryUnavailable("ECCC lightning response is already expired")
    return remaining


def _decode(kind: str, body: bytes) -> dict[str, object]:
    result = run_bounded_process(
        command=[sys.executable, str(Path(__file__).with_name("lightning_query_worker.py")), kind, "{output}"],
        stdin=body, destination=None, limits=DECODE_LIMITS, require_output=False,
    )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("lightning decoder output is not an object")
    return parsed


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request_urls(latitude: float, longitude: float, selected: datetime) -> tuple[str, str]:
    geomet = GeoMetClient()
    capabilities = geomet.url({"request": "GetCapabilities", "LAYERS": LIGHTNING_LAYER})
    half, pixels = 0.1, 20
    sample = geomet.url({
        "request": "GetFeatureInfo", "layers": LIGHTNING_LAYER,
        "query_layers": LIGHTNING_LAYER, "info_format": "application/json",
        "feature_count": 1, "crs": "EPSG:4326",
        "bbox": f"{latitude-half},{longitude-half},{latitude+half},{longitude+half}",
        "width": pixels, "height": pixels, "i": pixels // 2, "j": pixels // 2,
        "TIME": _stamp(selected),
    })
    return capabilities, sample


class LightningQueryService:
    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
                 decode: Callable[[str, bytes], dict[str, object]] = _decode) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=30, follow_redirects=False,
        )
        self._clock, self._utcnow, self._decode = clock, utcnow, decode
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, float, float], LightningCacheEntry] = OrderedDict()
        self._expired: OrderedDict[tuple[str, float, float], LightningAcquisition] = OrderedDict()
        self._inflight: dict[tuple[str, float, float], Future[LightningCacheEntry]] = {}

    @staticmethod
    def _key(latitude: float, longitude: float, selected: datetime) -> tuple[str, float, float]:
        if selected.tzinfo is None:
            raise ValueError("lightning selected time must include an offset")
        return selected.astimezone(UTC).isoformat(), round(latitude, 6), round(longitude, 6)

    def _get(self, url: str, kind: str, maximum: int) -> tuple[bytes, LightningTransportReceipt, int]:
        try:
            with self._client.stream("GET", url, headers={"Accept": "application/json" if kind == "sample" else "application/xml", "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200:
                    raise LightningQueryUnavailable(f"ECCC lightning {kind} returned HTTP {response.status_code}")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > maximum):
                    raise LightningQueryUnavailable(f"ECCC lightning {kind} exceeds its received-body ceiling")
                chunks, size = [], 0
                for chunk in response.iter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > maximum:
                        raise LightningQueryUnavailable(f"ECCC lightning {kind} exceeds its received-body ceiling")
                    chunks.append(chunk)
                body = b"".join(chunks)
                completed = self._utcnow()
                effective_url = str(response.request.url)
                request_headers = _safe_headers(response.request.headers, {"accept", "accept-encoding", "user-agent"}, 4 * 1024)
                response_headers = _safe_headers(response.headers, {"age", "cache-control", "content-type", "date", "etag", "last-modified"}, 8 * 1024)
        except httpx.HTTPError as error:
            raise LightningQueryUnavailable(f"ECCC lightning {kind} transport failed: {type(error).__name__}") from error
        if effective_url != url:
            raise LightningQueryUnavailable(f"ECCC lightning {kind} effective URL differs from the canonical request")
        if not body:
            raise LightningQueryUnavailable(f"ECCC lightning {kind} returned an empty body")
        receipt = LightningTransportReceipt(
            kind=kind, url=url, request_headers=request_headers, response_headers=response_headers,
            body_bytes=len(body), body_sha256=hashlib.sha256(body).hexdigest(), completed_at=completed,
        )
        return body, receipt, _ttl(response_headers, completed)

    def _prune_locked(self) -> None:
        def resident_bytes() -> int:
            return sum(item.backing_bytes for item in self._entries.values()) + sum(
                len(item.model_dump_json().encode()) for item in self._expired.values()
            )

        while len(self._entries) + len(self._expired) > CACHE_MAX_ENTRIES or resident_bytes() > CACHE_MAX_BYTES:
            if self._expired:
                self._expired.popitem(last=False)
            elif len(self._entries) > 1:
                self._entries.popitem(last=False)
            else:
                raise LightningQueryUnavailable("ECCC lightning cache residency exceeds its ceiling")

    def _fetch(self, latitude: float, longitude: float, selected: datetime) -> LightningCacheEntry:
        instant = selected.astimezone(UTC)
        capabilities_url, sample_url = _request_urls(latitude, longitude, instant)
        cap_body, cap_receipt, cap_ttl = self._get(capabilities_url, "capabilities", CAPABILITIES_MAX_BYTES)
        try:
            capability = self._decode("capabilities", cap_body)
            advertised = {datetime.fromisoformat(str(item)).astimezone(UTC) for item in capability["times"]}
        except Exception as error:
            raise LightningQueryUnavailable(f"ECCC lightning capabilities validation failed: {type(error).__name__}") from error
        if instant not in advertised:
            raise LightningQueryUnavailable(
                "selected lightning time is not an exact provider-advertised native frame", reason="unsupported_time",
            )
        sample_body, sample_receipt, sample_ttl = self._get(sample_url, "sample", SAMPLE_MAX_BYTES)
        try:
            decoded = self._decode("sample", sample_body)
            native_time = decoded.get("valid_time")
            if native_time is not None and datetime.fromisoformat(str(native_time)).astimezone(UTC) != instant:
                raise ValueError("sample native time differs from the requested advertised frame")
            sample = LightningSample(
                value=None if decoded.get("value") is None else float(decoded["value"]),
                latitude=None if decoded.get("latitude") is None else float(decoded["latitude"]),
                longitude=None if decoded.get("longitude") is None else float(decoded["longitude"]),
                title=None if decoded.get("title") is None else str(decoded["title"]),
                native_units=None if decoded.get("native_units") is None else str(decoded["native_units"]),
            )
        except Exception as error:
            raise LightningQueryUnavailable(f"ECCC lightning sample validation failed: {type(error).__name__}") from error
        completed = max(cap_receipt.completed_at, sample_receipt.completed_at)
        ttl = min(cap_ttl, sample_ttl)
        acquisition = LightningAcquisition(
            request=LightningDemandRequest(
                selected_time=instant, latitude=latitude, longitude=longitude,
                capabilities_url=capabilities_url, sample_url=sample_url,
            ),
            native_valid_time=instant,
            transport_receipts=(cap_receipt, sample_receipt), cached_at=completed,
            expires_at=completed + timedelta(seconds=ttl),
        )
        entry = LightningCacheEntry(sample, acquisition, self._clock() + ttl)
        if entry.backing_bytes > CACHE_MAX_BYTES:
            raise LightningQueryUnavailable("ECCC lightning normalized cache entry exceeds its ceiling")
        return entry

    def entry_for(self, latitude: float, longitude: float, selected: datetime) -> LightningCacheEntry:
        key = self._key(latitude, longitude, selected)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and self._clock() < cached.expires_at_monotonic:
                self._entries.move_to_end(key)
                return cached
            if cached is not None:
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
            expired = self._expired.get(key)
            if isinstance(error, LightningQueryUnavailable) and expired is not None:
                error.outcome = LightningDemandUnavailable(
                    reason="refresh_failed", error_type=type(error).__name__, expired_acquisition=expired,
                )
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def cached_entries(self) -> tuple[LightningCacheEntry, ...]:
        with self._lock:
            return tuple(item for item in self._entries.values() if self._clock() < item.expires_at_monotonic)

    def point_fields(self, latitude: float, longitude: float, selected: datetime) -> list[EvidenceField]:
        entry = self.entry_for(latitude, longitude, selected)
        sample = entry.sample
        sampled_latitude, sampled_longitude = sample.latitude, sample.longitude
        corrected_degrees = distance_km = None
        if sampled_latitude is not None and sampled_longitude is not None:
            latitude_scale = math.cos(math.radians((latitude + sampled_latitude) / 2))
            corrected_degrees = math.hypot(sampled_latitude - latitude, (sampled_longitude - longitude) * latitude_scale)
            if corrected_degrees > MAX_GRID_DISTANCE_DEGREES:
                raise LightningQueryUnavailable("ECCC lightning published cell is too far from the requested coordinate")
            distance_km = corrected_degrees * 111.32
        cache_age = max(0, int((self._utcnow() - entry.acquisition.transport_receipts[1].completed_at).total_seconds()))
        cache_ttl = max(1, int((entry.acquisition.expires_at - entry.acquisition.cached_at).total_seconds()))
        quality_flags = ["native_lightning"]
        sample_method = "wms_getfeatureinfo_pixel"
        if sampled_latitude is None or sampled_longitude is None:
            quality_flags.append("published_cell_coordinate_unavailable")
            sample_method = "wms_getfeatureinfo_pixel_identity_unavailable"
        common = dict(
            data_mode=DataMode.LIVE, evidence_class="retrieved", source_id="eccc-lightning",
            artifact_revision=f"demand:{entry.acquisition.transport_receipts[1].body_sha256}",
            provider="Environment and Climate Change Canada",
            product="Lightning flash density 2.5 km via GeoMet WMS",
            forecast_centre="Environment and Climate Change Canada", run_time=None,
            valid_time=entry.acquisition.native_valid_time,
            retrieval_time=entry.acquisition.transport_receipts[1].completed_at,
            vertical_level="10-minute gridded interval", native_resolution="2.5 km gridded density",
            native_crs="EPSG:4326", quality=Quality(status="unknown", flags=quality_flags),
            coverage=Coverage(status="complete", fraction=1.0), freshness=Freshness.evaluate(cache_age, cache_ttl),
            licence="MSC Open Data licence",
            attribution="Credit Environment and Climate Change Canada; lightning density via MSC GeoMet",
            delivery_kind="published_cell", source_display_primary=True,
            adapter_version="eccc-geomet-lightning-demand-v1", lightning_acquisition=entry.acquisition,
            sampled_latitude=sampled_latitude, sampled_longitude=sampled_longitude,
            sample_distance_km=distance_km, sample_method=sample_method,
            run_stale=None, run_stale_reason="lightning is an observation and has no model run",
        )
        observed = EvidenceField(
            field="lightning_observed", key="lightning_observed", value=1 if sample.value is not None and sample.value > 0 else 0,
            storage="available-not-stored",
            provenance=Provenance(original_units="flag", normalized_units="flag", **common),
        )
        fields = [observed]
        if sample.value is not None:
            fields.append(EvidenceField(
                field="lightning_strike", key="lightning_strike", value=sample.value,
                storage="available-not-stored",
                provenance=Provenance(original_units=sample.native_units or "flash/km²/min", normalized_units="flash km-2 min-1", **common),
            ))
        return fields


_service: LightningQueryService | None = None


def lightning_query_service() -> LightningQueryService:
    global _service
    if _service is None:
        _service = LightningQueryService()
    return _service


def demand_layer(layer_type, *, z_index: int):
    entries = lightning_query_service().cached_entries()
    times = sorted({item.acquisition.native_valid_time for item in entries})
    return layer_type(
        id="eccc-lightning-demand-observations",
        title="ECCC lightning flash density (exact-frame demand points)",
        kind="point", field="lightning_strike", product="ECCC lightning",
        units="flash km-2 min-1",
        semantics="Native 10-minute gridded flash density; exact advertised point frame only, with zero detection distinguished from unavailable retrieval",
        evidence_class="retrieved", family="lightning", field_key="lightning_strike",
        times=times, cadence_seconds=600, staleness_tolerance_seconds=600,
        z_index=z_index, evidence_basis="demand_query", group="observation",
        raster_available=False, legend_available=False, run_time=None, run_stale=None,
        run_stale_reason="lightning is an observation and has no model run",
    )
