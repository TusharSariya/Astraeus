"""Isolated NL provincial station acquisition prerequisite; no public point API.

The exact production station/time applicability, native-field delivery schema,
QC eligibility and restricted-rights contract still require owner acceptance.
This handle retains only the existing experimental adapter's native selection.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from ingest.experimental.nl_air_quality import CSV_URL, MAX_CSV_BYTES
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

STATION_ID = "010102"
CACHE_TTL_SECONDS = 60
CACHE_MAX_ENTRIES = 4
CACHE_MAX_BYTES = 2 * 1024 * 1024
DECODE_LIMITS = ProcessAllocationLimits(2 * 1024**3, 1, MAX_CSV_BYTES, MAX_CSV_BYTES, 64 * 1024)
MISSING_CONTRACT = "Accepted production station/time applicability, native-field delivery and restricted-rights contract"


class NLAirQualityUnavailable(RuntimeError):
    """No fresh, validated experimental station evidence is available."""


@dataclass(frozen=True)
class NativeObservation:
    observation_time: datetime
    local_time: str
    pm2_5_24h_mean_ug_m3: float | None
    ozone_ppb: float | None
    station_id: str = STATION_ID
    quality_status: str = "unknown"
    quality_flags: tuple[str, ...] = ("provisional", "not_quality_controlled")
    evidence_class: str = "uncalibrated_observation"
    operational: bool = False
    redistribution: bool = False


@dataclass(frozen=True)
class Acquisition:
    provider_url: str
    effective_url: str
    transport_completed_at: datetime
    body_bytes: int
    body_sha256: str
    expires_at: datetime


@dataclass(frozen=True)
class CacheEntry:
    observations: tuple[NativeObservation, ...]
    acquisition: Acquisition
    expires_at_monotonic: float
    backing_bytes: int
    window_start: datetime
    window_end: datetime
    source_id: str = "nl-air-quality-csv"
    licence: str = "Copyright Government of Newfoundland and Labrador, all rights reserved"

    @property
    def complete(self) -> bool:
        return all(row.pm2_5_24h_mean_ug_m3 is not None and row.ozone_ppb is not None for row in self.observations)


def _decode(body: bytes, start: datetime, end: datetime) -> tuple[NativeObservation, ...]:
    result = run_bounded_process(
        command=[sys.executable, str(Path(__file__).with_name("nl_airquality_worker.py")), start.isoformat(), end.isoformat(), "{output}"],
        stdin=body, destination=None, limits=DECODE_LIMITS, require_output=False,
    )
    rows = json.loads(result.stdout)
    if not isinstance(rows, list) or not rows or len(rows) > 10000:
        raise ValueError("NL decoder returned an invalid row count")
    return tuple(NativeObservation(
        observation_time=datetime.fromisoformat(row["time"]), local_time=row["local_time"],
        pm2_5_24h_mean_ug_m3=row["values"]["PM2_5_RUN_AVG"], ozone_ppb=row["values"]["O3"],
    ) for row in rows)


class NLAirQualityQueryService:
    """Finite exact-window cache for local experimental use only.

    All network activity is serialized, with identical window requests sharing
    a Future. Refresh failure never extends a retained entry's fixed deadline.
    No latest/nearest fallback, station mapping, aggregation or AQHI derivation.
    """

    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
                 decode: Callable = _decode) -> None:
        self._client = client or httpx.Client(timeout=30, follow_redirects=False)
        self._clock, self._utcnow, self._decode = clock, utcnow, decode
        self._lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._cache: OrderedDict[tuple[datetime, datetime], CacheEntry] = OrderedDict()
        self._inflight: dict[tuple[datetime, datetime], Future] = {}

    def _fetch(self, start: datetime, end: datetime) -> CacheEntry:
        try:
            with self._client.stream("GET", CSV_URL, follow_redirects=False,
                                     headers={"Accept": "text/csv", "Accept-Encoding": "identity"}) as response:
                if response.status_code != 200 or str(response.request.url) != CSV_URL:
                    raise NLAirQualityUnavailable("NL CSV canonical request did not return HTTP 200")
                declared = response.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or len(declared) > 10 or int(declared) > MAX_CSV_BYTES):
                    raise NLAirQualityUnavailable("NL CSV exceeds its body ceiling")
                body = bytearray()
                for chunk in response.iter_bytes(64 * 1024):
                    if len(body) + len(chunk) > MAX_CSV_BYTES:
                        raise NLAirQualityUnavailable("NL CSV exceeds its body ceiling")
                    body.extend(chunk)
                completed, monotonic = self._utcnow(), self._clock()
                if completed.tzinfo is None:
                    raise NLAirQualityUnavailable("NL acquisition clock must have an offset")
                completed = completed.astimezone(UTC)
            observations = self._decode(bytes(body), start, end)
        except Exception as error:
            if isinstance(error, NLAirQualityUnavailable):
                raise
            raise NLAirQualityUnavailable(f"NL CSV acquisition failed: {type(error).__name__}") from error
        if not observations:
            raise NLAirQualityUnavailable("NL CSV has no observations in the exact window")
        size = len(json.dumps([item.__dict__ for item in observations], default=str).encode()) + 1024
        if size > CACHE_MAX_BYTES:
            raise NLAirQualityUnavailable("NL decoded evidence exceeds cache ceiling")
        expires = monotonic + CACHE_TTL_SECONDS
        if self._clock() >= expires:
            raise NLAirQualityUnavailable("NL CSV expired during validation")
        return CacheEntry(observations, Acquisition(CSV_URL, CSV_URL, completed, len(body),
                          hashlib.sha256(body).hexdigest(), completed + timedelta(seconds=CACHE_TTL_SECONDS)), expires, size, start, end)

    def _expire(self) -> None:
        for key in list(self._cache):
            if self._clock() >= self._cache[key].expires_at_monotonic:
                del self._cache[key]

    def query(self, station_id: str, start: datetime, end: datetime, *, refresh: bool = False) -> CacheEntry:
        if station_id != STATION_ID:
            raise ValueError("Only the exact St. John's NAPS 010102 station is supported")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("NL query times must include offsets")
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        if not 0 <= (end - start).total_seconds() <= 35 * 86400:
            raise ValueError("NL exact window must be ordered and at most 35 days")
        key = start, end
        with self._lock:
            self._expire()
            if not refresh and key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                if len(self._inflight) >= CACHE_MAX_ENTRIES:
                    raise NLAirQualityUnavailable("NL acquisition queue is full")
                future = Future()
                self._inflight[key] = future
        if not owner:
            return future.result()
        try:
            with self._fetch_lock:
                replacement = self._fetch(start, end)
            with self._lock:
                self._expire()
                self._cache.pop(key, None)
                while self._cache and (len(self._cache) >= CACHE_MAX_ENTRIES or
                       sum(entry.backing_bytes for entry in self._cache.values()) + replacement.backing_bytes > CACHE_MAX_BYTES):
                    self._cache.popitem(last=False)
                self._cache[key] = replacement
            future.set_result(replacement)
            return replacement
        except BaseException as error:
            with self._lock:
                self._expire()
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)
