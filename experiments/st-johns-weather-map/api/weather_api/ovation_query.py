"""Selected-time, bounded current-grid query for NOAA SWPC OVATION."""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Mapping

import httpx

from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from .models import KpAcquisition
from .taf_query import TafQueryUnavailable, _freshness

OVATION_URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
OVATION_MAX_BODY_BYTES = 1024 * 1024
OVATION_MAX_CACHE_BYTES = 256 * 1024
OVATION_NATIVE_CADENCE_SECONDS = 600
OVATION_DECODE_LIMITS = ProcessAllocationLimits(128 * 1024 * 1024, 1, OVATION_MAX_BODY_BYTES, 128 * 1024, 64 * 1024)


class OvationUnavailable(RuntimeError):
    """No fresh OVATION grid can answer the selected instant."""

    def __init__(self, message: str, *, cached: KpAcquisition | None = None) -> None:
        super().__init__(message)
        self.cached = cached
        self.detail = {
            "reason": message,
            "cached_identity": cached.body_sha256 if cached else None,
            "cached_expires_at": cached.expires_at.isoformat() if cached else None,
            "values_withheld": True,
        }


class OvationFrameUnavailable(OvationUnavailable):
    """The fresh document has no native Forecast Time for this selection."""


@dataclass(frozen=True)
class OvationEntry:
    observation_time: datetime
    forecast_time: datetime
    cells: tuple[tuple[float, float, float], ...]
    acquisition: KpAcquisition
    expires_at_monotonic: float

    @property
    def backing_bytes(self) -> int:
        return len(json.dumps({"cells": self.cells, "headers": self.acquisition.response_headers}, separators=(",", ":")).encode()) + 1024

    def supports(self, selected: datetime) -> bool:
        return abs((selected - self.forecast_time).total_seconds()) <= OVATION_NATIVE_CADENCE_SECONDS


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"accept", "accept-encoding", "user-agent", "if-none-match", "if-modified-since"}
    retained = {key.lower(): value for key, value in headers.items() if key.lower() in allowed}
    if any(len(value.encode()) > 1024 for value in retained.values()) or sum(len(key.encode()) + len(value.encode()) for key, value in retained.items()) > 2 * 1024:
        raise OvationUnavailable("SWPC OVATION request metadata exceeds the retained-header ceiling")
    return retained


def public_acquisition(acquisition: KpAcquisition) -> str:
    """ASCII, bounded receipt that a map consumer can retain with its image."""
    value = json.dumps({
        "provider_url": acquisition.provider_url,
        "effective_url": acquisition.effective_url,
        "request_headers": acquisition.request_headers,
        "response_headers": acquisition.response_headers,
        "transport_completed_at": acquisition.transport_completed_at.isoformat(),
        "body_bytes": acquisition.body_bytes,
        "body_sha256": acquisition.body_sha256,
        "expires_at": acquisition.expires_at.isoformat(),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(value.encode()) > 12 * 1024:
        raise OvationUnavailable("SWPC OVATION public receipt exceeds its ceiling")
    return value


def _retained_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Keep only finite freshness/identity metadata, never arbitrary headers."""
    allowed = {"age", "cache-control", "content-type", "date", "etag", "last-modified"}
    retained = {key.lower(): value for key, value in headers.items() if key.lower() in allowed}
    if any(len(value.encode()) > 1024 for value in retained.values()):
        raise OvationUnavailable("SWPC OVATION response metadata exceeds the retained-header ceiling")
    if sum(len(key.encode()) + len(value.encode()) for key, value in retained.items()) > 8 * 1024:
        raise OvationUnavailable("SWPC OVATION response metadata exceeds the retained-header ceiling")
    return retained


def _decode(body: bytes) -> Mapping[str, object]:
    result = run_bounded_process(
        command=[sys.executable, "-m", "weather_api.ovation_query_worker", "{output}"],
        stdin=body, destination=None, limits=OVATION_DECODE_LIMITS, require_output=False,
    )
    parsed = json.loads(result.stdout)
    if not isinstance(parsed, dict):
        raise ValueError("OVATION decoder output is not an object")
    return parsed


class OvationQueryService:
    """One canonical, coalesced current-grid cache; never an evidence archive."""

    def __init__(self, *, client: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
                 decode: Callable[[bytes], Mapping[str, object]] = _decode) -> None:
        self._client = client or httpx.Client(headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"}, timeout=30, follow_redirects=False)
        self._clock, self._utcnow, self._decode = clock, utcnow, decode
        self._lock = threading.Lock()
        self._entry: OvationEntry | None = None
        # A failed refresh keeps only this receipt, never cells or body bytes.
        self._expired_acquisition: KpAcquisition | None = None
        self._inflight: Future[OvationEntry] | None = None

    def _fetch(self) -> OvationEntry:
        try:
            return self._fetch_response()
        except httpx.HTTPError as error:
            raise OvationUnavailable(f"SWPC OVATION transport failed: {type(error).__name__}") from error

    def _fetch_response(self) -> OvationEntry:
        with self._client.stream("GET", OVATION_URL, headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as response:
            if response.status_code != 200:
                raise OvationUnavailable(f"SWPC OVATION returned HTTP {response.status_code}")
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > OVATION_MAX_BODY_BYTES):
                raise OvationUnavailable("SWPC OVATION exceeds the received-body ceiling")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(64 * 1024):
                size += len(chunk)
                if size > OVATION_MAX_BODY_BYTES:
                    raise OvationUnavailable("SWPC OVATION exceeds the received-body ceiling")
                chunks.append(chunk)
            body = b"".join(chunks)
            completed = self._utcnow()
            effective_url = str(response.request.url)
            headers = _retained_response_headers(response.headers)
            request_headers = _safe_headers(response.request.headers)
        if effective_url != OVATION_URL:
            raise OvationUnavailable("SWPC OVATION effective URL differs from the canonical request")
        try:
            decoded = self._decode(body)
            observation = datetime.fromisoformat(str(decoded["observation_time"])).astimezone(UTC)
            forecast = datetime.fromisoformat(str(decoded["forecast_time"])).astimezone(UTC)
            raw_cells = decoded["cells"]
            if not isinstance(raw_cells, list):
                raise ValueError("cells missing")
            cells = tuple((float(item[0]), float(item[1]), float(item[2])) for item in raw_cells if isinstance(item, list) and len(item) == 3)
            if len(cells) != len(raw_cells):
                raise ValueError("decoder returned malformed cells")
        except Exception as error:
            raise OvationUnavailable(f"SWPC OVATION validation failed: {error}") from error
        try:
            _maximum, ttl = _freshness(headers, completed)
        except TafQueryUnavailable as error:
            raise OvationUnavailable(f"SWPC OVATION freshness invalid: {error}") from error
        acquisition = KpAcquisition(provider_url=OVATION_URL, effective_url=effective_url, request_headers=request_headers, response_headers=headers, transport_completed_at=completed, body_bytes=len(body), body_sha256=hashlib.sha256(body).hexdigest(), expires_at=completed + timedelta(seconds=ttl))
        # Validate the public receipt before retaining any values it describes.
        public_acquisition(acquisition)
        entry = OvationEntry(observation, forecast, cells, acquisition, self._clock() + ttl)
        if entry.backing_bytes > OVATION_MAX_CACHE_BYTES:
            raise OvationUnavailable("SWPC OVATION normalized cache entry exceeds its ceiling")
        return entry

    def entry_for(self, selected: datetime) -> OvationEntry:
        if selected.tzinfo is None:
            raise ValueError("OVATION selected time must include an offset")
        instant = selected.astimezone(UTC)
        with self._lock:
            cached = self._entry
            if cached is not None and self._clock() < cached.expires_at_monotonic:
                if cached.supports(instant):
                    return cached
                raise OvationFrameUnavailable("selected time is outside the native OVATION Forecast Time tolerance")
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
            entry = future.result()
        else:
            try:
                entry = self._fetch()
                with self._lock:
                    self._entry = entry
                    self._expired_acquisition = None
                future.set_result(entry)
            except BaseException as error:
                if isinstance(error, OvationUnavailable) and self._expired_acquisition is not None:
                    error = OvationUnavailable(str(error), cached=self._expired_acquisition)
                future.set_exception(error)
                raise error
            finally:
                with self._lock:
                    self._inflight = None
        if not entry.supports(instant):
            raise OvationFrameUnavailable("selected time is outside the native OVATION Forecast Time tolerance")
        return entry


_service: OvationQueryService | None = None

def ovation_query_service() -> OvationQueryService:
    global _service
    if _service is None:
        _service = OvationQueryService()
    return _service
