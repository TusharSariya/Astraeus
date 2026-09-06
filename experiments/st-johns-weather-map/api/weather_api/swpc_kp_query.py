"""Selected-time NOAA SWPC Kp query with a small process-local cache."""
from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Callable, Mapping

import httpx

from ingest.adapters.swpc import KP_DOCUMENT_BYTES, KP_FORECAST_URL, KP_OBSERVED_URL, SWPCKpAdapter
from ingest.kp3h_isolated import decode
from ingest.contract import FetchWindow
from .models import Freshness, KpAcquisition, SpaceWeatherReading, SpaceWeatherSeries
from .taf_query import TafQueryUnavailable, _freshness

KP_CACHE_SECONDS = 60


class SWPCKpUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class KpDocument:
    mode: str
    readings: tuple[SpaceWeatherReading, ...]
    body_bytes: int
    body_sha256: str
    provider_url: str
    effective_url: str
    request_headers: Mapping[str, str]
    response_headers: Mapping[str, str]
    completed_at: datetime
    expires_at_monotonic: float
    expires_at: datetime
    max_age: int
    etag: str | None
    last_revalidation: Mapping[str, object] | None = None


@dataclass(frozen=True)
class KpEntry:
    observed: KpDocument
    forecast: KpDocument | None
    forecast_error: str | None
    expires_at: float


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {"accept", "accept-encoding", "user-agent", "if-none-match"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


class SWPCKpQueryService:
    """One canonical pair of feeds, coalesced across selected timestamps."""

    def __init__(self, *, client: httpx.Client | None = None,
                 adapter: SWPCKpAdapter | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=60, follow_redirects=False,
        )
        self._adapter = adapter or SWPCKpAdapter()
        self._clock = clock
        self._entry: KpEntry | None = None
        self._inflight: Future[KpEntry] | None = None
        self._failure: tuple[float, SWPCKpUnavailable] | None = None
        self._lock = threading.Lock()

    def _document(self, url: str, mode: str, prior: KpDocument | None = None) -> KpDocument:
        sent = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if prior and prior.etag:
            sent["If-None-Match"] = prior.etag
        with self._client.stream("GET", url, headers=sent) as response:
            if response.status_code == 304:
                if next(response.iter_bytes(1), b""):
                    raise SWPCKpUnavailable(f"SWPC {mode} Kp 304 carried a body")
                if prior is None:
                    raise SWPCKpUnavailable(f"SWPC {mode} Kp returned 304 without cached content")
                headers = {key.lower(): value for key, value in response.headers.items()}
                if headers.get("etag") and headers["etag"] != prior.etag:
                    raise SWPCKpUnavailable(f"SWPC {mode} Kp 304 changed ETag")
                freshness_headers = dict(headers)
                freshness_headers.setdefault("cache-control", prior.response_headers.get("cache-control", ""))
                completed = datetime.now(UTC)
                try:
                    max_age, ttl = _freshness(freshness_headers, completed)
                except TafQueryUnavailable as error:
                    raise SWPCKpUnavailable(f"SWPC {mode} Kp freshness invalid: {error}") from error
                event = {"http_status": 304, "effective_url": str(response.request.url),
                         "request_headers": _safe_headers(response.request.headers),
                         "response_headers": headers, "transport_completed_at": completed.isoformat()}
                return replace(prior, expires_at_monotonic=self._clock() + ttl,
                               expires_at=completed + timedelta(seconds=ttl), max_age=max_age,
                               last_revalidation=event)
            if response.status_code != 200:
                raise SWPCKpUnavailable(f"SWPC {mode} Kp returned HTTP {response.status_code}")
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > KP_DOCUMENT_BYTES):
                raise SWPCKpUnavailable(f"SWPC {mode} Kp exceeds the {KP_DOCUMENT_BYTES}-byte ceiling")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(8192):
                size += len(chunk)
                if size > KP_DOCUMENT_BYTES:
                    raise SWPCKpUnavailable(f"SWPC {mode} Kp exceeds the {KP_DOCUMENT_BYTES}-byte ceiling")
                chunks.append(chunk)
            body = b"".join(chunks)
            completed = datetime.now(UTC)
            effective_url = str(response.request.url)
            request_headers = _safe_headers(response.request.headers)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
        try:
            rows = decode(body, mode)
        except Exception as error:
            raise SWPCKpUnavailable(f"SWPC {mode} Kp validation failed: {error}") from error
        statuses = {0: "observed", 1: "estimated", 2: "predicted"}
        readings = tuple(SpaceWeatherReading(
            time=stamp, value=value,
            status=statuses[int(context)] if mode == "forecast" else None,
        ) for stamp, value, context in rows)
        try:
            max_age, ttl = _freshness(response_headers, completed)
        except TafQueryUnavailable as error:
            raise SWPCKpUnavailable(f"SWPC {mode} Kp freshness invalid: {error}") from error
        return KpDocument(mode, readings, len(body), hashlib.sha256(body).hexdigest(), url,
                          effective_url, request_headers, response_headers, completed,
                          self._clock() + ttl, completed + timedelta(seconds=ttl), max_age,
                          response_headers.get("etag"))

    def entry(self) -> KpEntry:
        with self._lock:
            current = self._clock()
            if self._entry is not None and current < self._entry.expires_at:
                return self._entry
            if self._failure is not None and current < self._failure[0]:
                raise self._failure[1]
            self._failure = None
            future = self._inflight
            owner = future is None
            if owner:
                future = Future()
                self._inflight = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            # The historical bound charges both documents and both outputs.
            # Enforce that aggregate envelope before the first provider byte.
            self._adapter.demand_operation_bounds()
            observed = self._document(KP_OBSERVED_URL, "observed", self._entry.observed if self._entry else None)
            try:
                forecast = self._document(KP_FORECAST_URL, "forecast", self._entry.forecast if self._entry else None)
                forecast_error = None
            except SWPCKpUnavailable as error:
                forecast = None
                forecast_error = str(error)
            expiries = [observed.expires_at_monotonic, *( [forecast.expires_at_monotonic] if forecast else [])]
            result = KpEntry(observed, forecast, forecast_error, min(expiries))
            with self._lock:
                self._entry = result
                self._failure = None
            future.set_result(result)
            return result
        except Exception as error:
            unavailable = error if isinstance(error, SWPCKpUnavailable) else SWPCKpUnavailable(str(error))
            with self._lock:
                self._failure = (self._clock() + KP_CACHE_SECONDS, unavailable)
            future.set_exception(unavailable)
            raise unavailable
        finally:
            with self._lock:
                self._inflight = None

    @staticmethod
    def _series(document: KpDocument | None, at: datetime, *, forecast: bool,
                unavailable: str | None = None) -> SpaceWeatherSeries:
        if document is None:
            return SpaceWeatherSeries(available=False, source_id="noaa-swpc-kp", product="unavailable",
                readings=[], freshness=Freshness.evaluate(None, 21600), notices=[unavailable or "Kp feed unavailable"])
        # Observations never use a future record. Forecast preserves provider
        # status and exposes entries from the selected instant onward; it does
        # not substitute the nearest entry for a gap.
        native_start = min(row.time for row in document.readings)
        native_end = max(row.time for row in document.readings)
        if not native_start <= at <= native_end:
            selected = []
        elif forecast:
            selected = [row for row in document.readings if at <= row.time <= at + timedelta(days=14)]
        else:
            selected = [row for row in document.readings if at - timedelta(hours=24) <= row.time <= at]
        anchor = max((row.time for row in document.readings if row.time <= at), default=None)
        age = int((at - anchor).total_seconds()) if anchor else None
        return SpaceWeatherSeries(
            available=bool(selected), source_id="noaa-swpc-kp",
            product="Planetary K index (3-day outlook, per-value status)" if forecast else "Planetary K index (observed)",
            readings=selected, freshness=Freshness.evaluate(age, 21600),
            acquisition=KpAcquisition(
                provider_url=document.provider_url,
                effective_url=document.effective_url,
                request_headers=dict(document.request_headers),
                response_headers=dict(document.response_headers),
                transport_completed_at=document.completed_at,
                body_bytes=document.body_bytes,
                body_sha256=document.body_sha256,
                expires_at=document.expires_at,
                last_revalidation=dict(document.last_revalidation) if document.last_revalidation else None,
            ),
            notices=[] if selected else ["no native Kp row is applicable to the selected instant"],
        )

    def series(self, at: datetime) -> tuple[SpaceWeatherSeries, SpaceWeatherSeries]:
        if at.tzinfo is None:
            raise ValueError("space-weather selected time must include an offset")
        instant = at.astimezone(UTC)
        entry = self.entry()
        return (self._series(entry.observed, instant, forecast=False),
                self._series(entry.forecast, instant, forecast=True, unavailable=entry.forecast_error))


@lru_cache(maxsize=1)
def swpc_kp_query_service() -> SWPCKpQueryService:
    return SWPCKpQueryService()
