"""Bounded selected-time cache for SWPC real-time solar-wind magnetometer rows."""
from __future__ import annotations

import hashlib
import math
import json
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Callable, Mapping

import httpx

from ingest.adapters.swpc import RTSW_MAG_URL
from ingest.isolation import ProcessAllocationLimits, run_bounded_process
from ingest.resources import acquisition_budget
from ingest.space_weather import MAX_LARGE_FEED_BYTES
from .models import Freshness, KpAcquisition, SolarWindLatest
from .taf_query import TafQueryUnavailable, _freshness

RTSW_FAILURE_BACKOFF_SECONDS = 60
RTSW_FRESHNESS_SECONDS = 900


class SWPCRTSWUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RTSWDocument:
    body: bytes
    acquisition: KpAcquisition
    expires_at_monotonic: float
    backing_bytes: int

RTSW_DECODE_LIMITS = ProcessAllocationLimits(512*1024*1024, 1024, MAX_LARGE_FEED_BYTES, 64*1024, 64*1024)


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"accept", "accept-encoding", "user-agent", "if-none-match", "if-modified-since"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


class SWPCRTSWQueryService:
    """One canonical mutable RTSW request shared by all selected instants."""

    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
                 bounded_decode: Callable[[bytes, datetime | None], Mapping[str, object]] | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=60, follow_redirects=False,
        )
        self._clock, self._utcnow = clock, utcnow
        self._decode = bounded_decode or self._bounded
        self._lock = threading.Lock()
        self._entry: RTSWDocument | None = None
        self._inflight: Future[RTSWDocument] | None = None
        self._failure: tuple[float, SWPCRTSWUnavailable] | None = None

    @staticmethod
    def _bounded(body: bytes, at: datetime | None = None) -> Mapping[str, object]:
        selected = at.isoformat() if at else "validate"
        result=run_bounded_process(command=[sys.executable,"-m","weather_api.swpc_rtsw_worker","{output}",selected],stdin=body,destination=None,limits=RTSW_DECODE_LIMITS,require_output=False)
        return json.loads(result.stdout)

    def _fetch(self, prior: RTSWDocument | None = None) -> RTSWDocument:
        sent = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if prior is not None:
            etag = prior.acquisition.response_headers.get("etag")
            modified = prior.acquisition.response_headers.get("last-modified")
            if etag:
                sent["If-None-Match"] = etag
            if modified:
                sent["If-Modified-Since"] = modified
        with acquisition_budget(MAX_LARGE_FEED_BYTES) as received, self._client.stream("GET", RTSW_MAG_URL, headers=sent) as response:
            if response.status_code == 304:
                if next(response.iter_bytes(1), b""):
                    raise SWPCRTSWUnavailable("SWPC RTSW 304 carried a body")
                if prior is None:
                    raise SWPCRTSWUnavailable("SWPC RTSW returned 304 without cached content")
                response_headers = {key.lower(): value for key, value in response.headers.items()}
                if str(response.request.url) != RTSW_MAG_URL:
                    raise SWPCRTSWUnavailable("SWPC RTSW 304 effective URL differs from its canonical request identity")
                if response_headers.get("etag") and response_headers["etag"] != prior.acquisition.response_headers.get("etag"):
                    raise SWPCRTSWUnavailable("SWPC RTSW 304 changed ETag")
                prior_modified = prior.acquisition.response_headers.get("last-modified")
                if prior_modified and response_headers.get("last-modified") and response_headers["last-modified"] != prior_modified:
                    raise SWPCRTSWUnavailable("SWPC RTSW 304 changed Last-Modified")
                freshness_headers = dict(response_headers)
                freshness_headers.setdefault("cache-control", prior.acquisition.response_headers.get("cache-control", ""))
                completed = self._utcnow()
                try:
                    _max_age, ttl = _freshness(freshness_headers, completed)
                except TafQueryUnavailable as error:
                    raise SWPCRTSWUnavailable(f"SWPC RTSW freshness invalid: {error}") from error
                event = {
                    "http_status": 304,
                    "effective_url": str(response.request.url),
                    "request_headers": _safe_headers(response.request.headers),
                    "response_headers": response_headers,
                    "transport_completed_at": completed.isoformat(),
                }
                acquisition = prior.acquisition.model_copy(update={
                    "expires_at": completed + timedelta(seconds=ttl),
                    "last_revalidation": event,
                })
                return RTSWDocument(prior.body, acquisition, self._clock() + ttl, prior.backing_bytes)
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
            if effective_url != RTSW_MAG_URL:
                raise SWPCRTSWUnavailable("SWPC RTSW effective URL differs from its canonical request identity")
            request_headers = _safe_headers(response.request.headers)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
        try:
            self._decode(body, None)
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
        return RTSWDocument(body, acquisition, self._clock() + ttl, len(body))

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
            with self._lock:
                prior = self._entry
            result = self._fetch(prior)
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
        if document.acquisition.last_revalidation:
            revalidated = document.acquisition.last_revalidation.get("transport_completed_at")
            if isinstance(revalidated, str):
                parsed = datetime.fromisoformat(revalidated)
                if parsed.tzinfo is None:
                    raise SWPCRTSWUnavailable("SWPC RTSW revalidation completion is not offset-aware")
                acquired = parsed.astimezone(UTC)
        if not acquired - timedelta(seconds=RTSW_FRESHNESS_SECONDS) < instant <= document.acquisition.expires_at:
            raise SWPCRTSWUnavailable("selected timestamp is outside the mutable RTSW acquisition context")
        selected=self._decode(document.body,instant)
        newest=datetime.fromisoformat(str(selected["time"])); source=str(selected["source"]); row=selected["row"]
        assert isinstance(row,Mapping)
        active_count=int(selected["active_count"])
        age = int((instant - newest).total_seconds())
        if age >= RTSW_FRESHNESS_SECONDS:
            raise SWPCRTSWUnavailable(f"newest native Bz is {age} s old, past the {RTSW_FRESHNESS_SECONDS} s freshness threshold")
        notices = [] if active_count == 1 else [
            f"{'multiple spacecraft carried' if active_count else 'no spacecraft carried'} the feed active flag at {newest.isoformat()}; "
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
