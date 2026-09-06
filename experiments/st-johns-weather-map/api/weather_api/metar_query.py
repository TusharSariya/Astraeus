"""Bounded timestamp-demand query and anti-hammering cache for CYYT METAR."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Mapping

import httpx

from ingest.adapters.awc import AWCMetarAdapter, AWC_METAR_DOCUMENT_BYTES
from ingest.awc_metar_isolated import _decode
from ingest.contract import FetchWindow, RunCandidate
from .taf_query import TafQueryUnavailable, _freshness as _taf_freshness, _safe_request_headers

AWC_METAR_URL = "https://aviationweather.gov/api/data/metar"
METAR_MAX_AGE_SECONDS = 3600
METAR_CACHE_MAX_ENTRIES = 64
METAR_CACHE_MAX_BYTES = METAR_CACHE_MAX_ENTRIES * AWC_METAR_DOCUMENT_BYTES


def _freshness(headers: Mapping[str, str], completed: datetime) -> tuple[int, int]:
    try:
        return _taf_freshness(headers, completed)
    except TafQueryUnavailable as error:
        raise TafQueryUnavailable(str(error).replace("AWC TAF", "AWC METAR")) from error


@dataclass(frozen=True)
class MetarCacheEntry:
    records: tuple[dict, ...]
    body: bytes
    body_sha256: str
    body_bytes: int
    provider_url: str
    effective_url: str
    cache_key: tuple[str, str, str, str]
    request_headers: Mapping[str, str]
    response_headers: Mapping[str, str]
    transport_completed_at: datetime
    expires_at_monotonic: float
    expires_at: datetime
    max_age: int
    etag: str | None
    last_revalidation: Mapping[str, object] | None = None


class MetarQueryService:
    """Process-local LRU keyed by one canonical hourly CYYT request."""

    def __init__(self, *, client: httpx.Client | None = None,
                 adapter: AWCMetarAdapter | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"},
            timeout=60, follow_redirects=False,
        )
        self._adapter = adapter or AWCMetarAdapter()
        self._clock = clock
        self._entries: OrderedDict[tuple[str, str, str, str], MetarCacheEntry] = OrderedDict()
        self._inflight: dict[tuple[str, str, str, str], Future[MetarCacheEntry]] = {}
        self._failures: dict[tuple[str, str, str, str], tuple[float, TafQueryUnavailable]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def request_identity(at: datetime) -> tuple[str, tuple[str, str, str, str], datetime]:
        if at.tzinfo is None:
            raise ValueError("METAR selected time must include an offset")
        instant = at.astimezone(UTC).replace(microsecond=0)
        end = instant.replace(minute=0, second=0)
        if instant != end:
            end += timedelta(hours=1)
        stamp = end.isoformat().replace("+00:00", "Z")
        url = str(httpx.URL(AWC_METAR_URL, params={"ids":"CYYT", "format":"json", "hours":"2", "date":stamp}))
        return url, ("aviationweather.gov", "metar-json", "CYYT", f"two-hours-ending:{stamp}"), end

    def _fetch(self, prior: MetarCacheEntry | None, request_url: str,
               cache_key: tuple[str, str, str, str], at: datetime) -> MetarCacheEntry:
        # The existing measured METAR allocation probe runs before any provider byte.
        self._adapter.demand_operation_bounds()
        sent = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if prior and prior.etag:
            sent["If-None-Match"] = prior.etag
        with self._client.stream("GET", request_url, headers=sent) as response:
            if response.status_code == 304:
                if next(response.iter_bytes(1), b""):
                    raise TafQueryUnavailable("AWC METAR 304 unexpectedly carried a response body")
                completed = datetime.now(UTC)
                if prior is None:
                    raise TafQueryUnavailable("AWC returned 304 without a cached METAR response")
                headers = {k.lower(): v for k, v in response.headers.items()}
                if headers.get("etag") and headers["etag"] != prior.etag:
                    raise TafQueryUnavailable("AWC METAR 304 changed the retained ETag")
                freshness_headers = dict(headers)
                freshness_headers.setdefault("cache-control", prior.response_headers.get("cache-control", ""))
                max_age, ttl = _freshness(freshness_headers, completed)
                event = {"status": 304, "request_headers": _safe_request_headers(response.request.headers),
                         "response_headers": headers, "transport_completed_at": completed}
                return MetarCacheEntry(**{**prior.__dict__, "expires_at_monotonic": self._clock() + ttl,
                                          "expires_at": completed + timedelta(seconds=ttl),
                                          "max_age": max_age, "last_revalidation": event})
            if 300 <= response.status_code < 400:
                raise TafQueryUnavailable("AWC METAR redirect refused because it changes the canonical request")
            if response.status_code == 204:
                raise TafQueryUnavailable("AWC METAR has no observation in the requested native window")
            if response.status_code != 200:
                retry = response.headers.get("retry-after", "").strip()
                seconds = int(retry) if retry.isdigit() and 1 <= int(retry) <= 300 else 60
                raise TafQueryUnavailable(f"AWC METAR returned HTTP {response.status_code}", retry_after_seconds=seconds)
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > AWC_METAR_DOCUMENT_BYTES):
                raise TafQueryUnavailable("AWC METAR response exceeds the 65536-byte ceiling")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes(8192):
                size += len(chunk)
                if size > AWC_METAR_DOCUMENT_BYTES:
                    raise TafQueryUnavailable("AWC METAR response exceeds the 65536-byte ceiling")
                chunks.append(chunk)
            body = b"".join(chunks)
            completed = datetime.now(UTC)
            headers = {k.lower(): v for k, v in response.headers.items()}
            effective_url = str(response.request.url)
            effective_headers = _safe_request_headers(response.request.headers)
        records = tuple(_decode(body, FetchWindow(at, back_hours=2, forward_hours=0)))
        max_age, ttl = _freshness(headers, completed)
        return MetarCacheEntry(records, body, hashlib.sha256(body).hexdigest(), len(body),
                               request_url, effective_url, cache_key,
                               effective_headers, headers, completed,
                               self._clock() + ttl, completed + timedelta(seconds=ttl),
                               max_age, headers.get("etag"))

    def entry(self, at: datetime) -> MetarCacheEntry:
        request_url, cache_key, window_end = self.request_identity(at)
        at = at.astimezone(UTC).replace(microsecond=0)
        with self._lock:
            now = self._clock()
            current = self._entries.get(cache_key)
            if current and now < current.expires_at_monotonic:
                self._entries.move_to_end(cache_key)
                return current
            failure = self._failures.get(cache_key)
            if failure and now < failure[0]:
                raise failure[1]
            self._failures.pop(cache_key, None)
            future = self._inflight.get(cache_key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[cache_key] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            replacement = self._fetch(current, request_url, cache_key, window_end)
        except Exception as error:
            unavailable = TafQueryUnavailable(str(error), cached=current,
                                               retry_after_seconds=getattr(error, "retry_after_seconds", 60))
            with self._lock:
                self._failures[cache_key] = (self._clock() + unavailable.retry_after_seconds, unavailable)
            future.set_exception(unavailable)
            raise unavailable
        finally:
            with self._lock:
                self._inflight.pop(cache_key, None)
        with self._lock:
            self._entries[cache_key] = replacement
            self._entries.move_to_end(cache_key)
            while len(self._entries) > METAR_CACHE_MAX_ENTRIES or sum(item.body_bytes for item in self._entries.values()) > METAR_CACHE_MAX_BYTES:
                self._entries.popitem(last=False)
            self._failures.pop(cache_key, None)
        future.set_result(replacement)
        return replacement

    def point_fields(self, latitude: float, longitude: float, at: datetime):
        if at.tzinfo is None:
            raise ValueError("METAR selected time must include an offset")
        at = at.astimezone(UTC)
        entry = self.entry(at)
        row, observed = self.select_record(entry, at)
        return self._sample_record(row, observed, entry, latitude, longitude)

    @staticmethod
    def select_record(entry: MetarCacheEntry, at: datetime) -> tuple[dict, datetime]:
        at = at.astimezone(UTC)
        eligible = [row for row in entry.records if datetime.fromtimestamp(int(row["obsTime"]), UTC) <= at]
        if not eligible:
            raise ValueError("AWC METAR has no observation at or before the selected timestamp")
        row = max(eligible, key=lambda item: int(item["obsTime"]))
        observed = datetime.fromtimestamp(int(row["obsTime"]), UTC)
        if at - observed >= timedelta(hours=1):
            raise ValueError("latest AWC METAR observation is one hour old or older")
        return row, observed

    def _sample_record(self, row: dict, observed: datetime, entry: MetarCacheEntry,
                       latitude: float, longitude: float):
        from .store import LiveStore, live_point_fields
        raw = json.dumps([row], separators=(",", ":")).encode()
        with TemporaryDirectory(prefix="metar-demand-") as directory:
            root = Path(directory)
            window = FetchWindow(observed, back_hours=0, forward_hours=0)
            candidate = RunCandidate(f"cyyt-metar-{int(row['obsTime'])}", observed, [AWC_METAR_URL], {
                "bounded_raw": raw,
                "transport_completed_at": entry.transport_completed_at.isoformat(),
                "transport_headers": dict(entry.response_headers),
            })
            result = self._adapter.fetch(candidate, window, root)
            result.artifacts[0].provenance["acquisition"] = {
                "provider_url": entry.provider_url,
                "effective_url": entry.effective_url,
                "cache_key": list(entry.cache_key),
                "http_status": 200,
                "request_headers": dict(entry.request_headers),
                "response_headers": dict(entry.response_headers),
                "transport_completed_at": entry.transport_completed_at.isoformat(),
                "body_sha256": entry.body_sha256,
                "body_bytes": entry.body_bytes,
                "expires_at": entry.expires_at.isoformat(),
                "max_age": entry.max_age,
                "last_revalidation": entry.last_revalidation,
            }
            payload = result.artifacts[0].payload_path.read_bytes()
            path = root / "read.zarr.zip"
            path.write_bytes(payload)
            import xarray
            import zarr
            zipped = zarr.storage.ZipStore(str(path), mode="r")
            dataset = xarray.open_zarr(zipped, consolidated=False)
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped, sampler.unmodelled = [], []
            try:
                artifact = type("Artifact", (), {"source_id": "awc-metar-speci", "logical_name": "surface",
                    "revision_id": f"demand:{entry.body_sha256}", "provenance": result.artifacts[0].provenance,
                    "run_time": observed, "retrieved_at": entry.transport_completed_at, "native_crs": "EPSG:4326"})()
                samples = sampler._sample_dataset(dataset, artifact, latitude, longitude, observed)
            finally:
                dataset.close(); zipped.close()
        class Samples:
            skipped, unmodelled = sampler.skipped, sampler.unmodelled
            @staticmethod
            def sample_point(*_args, **_kwargs): return samples
        fields, _consensus, _sources = live_point_fields(Samples(), latitude, longitude, observed)
        return fields, observed, entry


_service: MetarQueryService | None = None


def metar_query_service() -> MetarQueryService:
    global _service
    if _service is None:
        _service = MetarQueryService()
    return _service
