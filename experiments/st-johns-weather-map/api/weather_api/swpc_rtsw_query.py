"""Bounded selected-time cache for SWPC real-time solar-wind magnetometer rows."""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Callable, Mapping

import httpx

from ingest.adapters.swpc import RTSW_MAG_FIELDS, RTSW_MAG_URL, _parse_platform_records, _records
from ingest.resources import acquisition_budget
from ingest.space_weather import MAX_LARGE_FEED_BYTES, parse_time
from .models import Freshness, KpAcquisition, SolarWindLatest
from .taf_query import TafQueryUnavailable, _freshness

RTSW_FAILURE_BACKOFF_SECONDS = 60
RTSW_FRESHNESS_SECONDS = 900
RTSW_CACHE_MAX_BYTES = 16 * 1024 * 1024
RTSW_OPERATION_MAX_BYTES = 4 * MAX_LARGE_FEED_BYTES


class SWPCRTSWUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RTSWDocument:
    rows: tuple[Mapping[str, object], ...]
    acquisition: KpAcquisition
    expires_at_monotonic: float
    backing_bytes: int


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"accept", "accept-encoding", "user-agent"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


class SWPCRTSWQueryService:
    """One canonical mutable RTSW request shared by all selected instants."""

    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=60, follow_redirects=False,
        )
        self._clock, self._utcnow = clock, utcnow
        self._lock = threading.Lock()
        self._entry: RTSWDocument | None = None
        self._inflight: Future[RTSWDocument] | None = None
        self._failure: tuple[float, SWPCRTSWUnavailable] | None = None

    def _fetch(self) -> RTSWDocument:
        sent = {"Accept": "application/json", "Accept-Encoding": "identity"}
        with acquisition_budget(MAX_LARGE_FEED_BYTES) as received, self._client.stream("GET", RTSW_MAG_URL, headers=sent) as response:
            if response.status_code != 200:
                raise SWPCRTSWUnavailable(f"SWPC RTSW returned HTTP {response.status_code}")
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_LARGE_FEED_BYTES):
                raise SWPCRTSWUnavailable("SWPC RTSW exceeds the bounded document ceiling")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(8192):
                size += len(chunk)
                received.charge(len(chunk))
                if size > MAX_LARGE_FEED_BYTES:
                    raise SWPCRTSWUnavailable("SWPC RTSW exceeds the bounded document ceiling")
                chunks.append(chunk)
            body = b"".join(chunks)
            completed = self._utcnow()
            effective_url = str(response.request.url)
            request_headers = _safe_headers(response.request.headers)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
        try:
            payload = json.loads(body)
            if not isinstance(payload, list):
                raise ValueError("document is not a native row list")
            expected = {"time_tag", "source", *(field.name for field in RTSW_MAG_FIELDS)}
            seen: set[tuple[str, str]] = set()
            for index, row in enumerate(payload):
                if not isinstance(row, Mapping):
                    raise ValueError(f"row {index} is not an object")
                missing = expected - set(row)
                if missing:
                    raise ValueError(f"row {index} is missing native fields: {', '.join(sorted(missing))}")
                if not isinstance(row["time_tag"], str) or not isinstance(row["source"], str) or not row["source"]:
                    raise ValueError(f"row {index} has invalid time_tag or source")
                parse_time(row["time_tag"])
                identity = (row["time_tag"], row["source"])
                if identity in seen:
                    raise ValueError(f"row {index} duplicates native time/source identity")
                seen.add(identity)
                for field in RTSW_MAG_FIELDS:
                    value = row[field.name]
                    if field.name in {"active", "manual_mode"}:
                        if value is not None and not isinstance(value, bool):
                            raise ValueError(f"row {index} native {field.name} is not boolean or null")
                    elif value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))):
                        raise ValueError(f"row {index} native {field.name} is not finite numeric or null")
            rows = _records(payload, required=("time_tag", "source", "bz_gsm"))
            if not rows:
                raise ValueError("no row carries time_tag, source and bz_gsm")
            # This validates timestamps, spacecraft labels, all numeric magnetic
            # fields and every native quality flag while the cache retains each
            # original row and explicit null unchanged.
            _parse_platform_records(rows, RTSW_MAG_FIELDS)
        except Exception as error:
            raise SWPCRTSWUnavailable(f"SWPC RTSW validation failed: {error}") from error
        try:
            _max_age, ttl = _freshness(response_headers, completed)
        except TafQueryUnavailable as error:
            raise SWPCRTSWUnavailable(f"SWPC RTSW freshness invalid: {error}") from error
        expires = completed + timedelta(seconds=ttl)
        acquisition = KpAcquisition(
            provider_url=RTSW_MAG_URL, effective_url=effective_url,
            request_headers=request_headers, response_headers=response_headers,
            transport_completed_at=completed, body_bytes=len(body),
            body_sha256=hashlib.sha256(body).hexdigest(), expires_at=expires,
        )
        normalized_bytes = len(json.dumps(rows, separators=(",", ":")).encode())
        if normalized_bytes > RTSW_CACHE_MAX_BYTES:
            raise SWPCRTSWUnavailable("SWPC RTSW normalized cache entry exceeds its byte ceiling")
        backing_bytes = len(body) + normalized_bytes
        if backing_bytes > RTSW_OPERATION_MAX_BYTES:
            raise SWPCRTSWUnavailable("SWPC RTSW operation exceeds its combined memory envelope")
        return RTSWDocument(tuple(dict(row) for row in rows), acquisition, self._clock() + ttl, backing_bytes)

    def entry(self) -> RTSWDocument:
        with self._lock:
            now = self._clock()
            if self._entry is not None and now < self._entry.expires_at_monotonic:
                return self._entry
            if self._failure is not None and now < self._failure[0]:
                raise self._failure[1]
            future = self._inflight
            owner = future is None
            if owner:
                future = Future()
                self._inflight = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            result = self._fetch()
            with self._lock:
                self._entry = result
                self._failure = None
            future.set_result(result)
            return result
        except Exception as error:
            unavailable = error if isinstance(error, SWPCRTSWUnavailable) else SWPCRTSWUnavailable(str(error))
            with self._lock:
                self._failure = (self._clock() + RTSW_FAILURE_BACKOFF_SECONDS, unavailable)
            future.set_exception(unavailable)
            raise unavailable
        finally:
            with self._lock:
                self._inflight = None

    def latest(self, at: datetime) -> SolarWindLatest:
        if at.tzinfo is None:
            raise ValueError("solar-wind selected time must include an offset")
        instant = at.astimezone(UTC)
        document = self.entry()
        acquired = document.acquisition.transport_completed_at
        if not acquired - timedelta(seconds=RTSW_FRESHNESS_SECONDS) < instant <= document.acquisition.expires_at:
            raise SWPCRTSWUnavailable("selected timestamp is outside the mutable RTSW acquisition context")
        candidates: list[tuple[datetime, str, Mapping[str, object]]] = []
        for row in document.rows:
            stamp = parse_time(row.get("time_tag"))
            raw_bz = row.get("bz_gsm")
            source = row.get("source")
            if stamp <= instant and isinstance(source, str) and source and isinstance(raw_bz, (int, float)) and not isinstance(raw_bz, bool) and math.isfinite(float(raw_bz)):
                candidates.append((stamp, source, row))
        if not candidates:
            raise SWPCRTSWUnavailable("no finite native Bz row applies to the selected timestamp")
        newest = max(stamp for stamp, _source, _row in candidates)
        rows = [(source, row) for stamp, source, row in candidates if stamp == newest]
        active = [(source, row) for source, row in rows if row.get("active") is True]
        source, row = sorted(active if len(active) == 1 else rows, key=lambda item: item[0])[0]
        age = int((instant - newest).total_seconds())
        if age >= RTSW_FRESHNESS_SECONDS:
            raise SWPCRTSWUnavailable(f"newest native Bz is {age} s old, past the {RTSW_FRESHNESS_SECONDS} s freshness threshold")
        notices = [] if len(active) == 1 else [
            f"{'multiple spacecraft carried' if active else 'no spacecraft carried'} the feed active flag at {newest.isoformat()}; "
            f"{source} is the first native source label alphabetically"
        ]
        bt = row.get("bt")
        quality = row.get("overall_quality")
        return SolarWindLatest(
            available=True, source_id="noaa-swpc-rtsw",
            product="Real-time solar wind magnetic field (1-minute, per spacecraft)",
            bz_gsm_nt=float(row["bz_gsm"]),
            bt_nt=float(bt) if isinstance(bt, (int, float)) and not isinstance(bt, bool) and math.isfinite(float(bt)) else None,
            measured_at=newest, feed_declared_spacecraft=source,
            active=True if row.get("active") == 1 else False if row.get("active") == 0 else None,
            overall_quality=float(quality) if isinstance(quality, (int, float)) and not isinstance(quality, bool) and math.isfinite(float(quality)) else None,
            freshness=Freshness.evaluate(age, RTSW_FRESHNESS_SECONDS),
            acquisition=document.acquisition, notices=notices,
        )


@lru_cache(maxsize=1)
def swpc_rtsw_query_service() -> SWPCRTSWQueryService:
    return SWPCRTSWQueryService()
