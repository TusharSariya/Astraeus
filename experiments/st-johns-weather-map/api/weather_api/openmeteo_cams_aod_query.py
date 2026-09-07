"""Isolated finite CAMS-global AOD delivery over the existing experimental adapter.

Hourly timestamps belong to Open-Meteo's reprocessed series, not the producer's
three-hour grid. This service is not registered, scheduled, or operational.
"""
from __future__ import annotations

import json
import math
import tempfile
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import xarray
import zarr

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.openmeteo import OpenMeteoCompositionAdapter, _times
from ingest.http import PoliteClient
from .models import Coverage, DataMode, EvidenceField, Freshness, Provenance, Quality

SOURCE_ID = "openmeteo-cams-aod"
FIELD_KEY = "aerosol_optical_depth_550nm"
MAX_HOURS = 24
MAX_RESPONSE_BYTES = 16 * 1024
MAX_CACHE_ENTRIES = 32
MAX_CACHE_BYTES = 256 * 1024
MAX_INFLIGHT = 2
TTL_SECONDS = 300


class OpenMeteoCamsAodUnavailable(RuntimeError):
    """The named finite selection has no fresh validated delivery."""


@dataclass(frozen=True)
class CamsAodSelection:
    latitude: float
    longitude: float
    start: datetime
    end: datetime


@dataclass(frozen=True)
class CamsAodEntry:
    selection: CamsAodSelection
    times: tuple[datetime, ...]
    values: tuple[float | None, ...]
    sampled_latitude: float
    sampled_longitude: float
    retrieved_at: datetime
    expires_at: datetime
    expires_at_monotonic: float
    response_sha256: str
    request_url: str
    latest_model_initialisation_context: str
    transformations: tuple[str, ...]

    @property
    def backing_bytes(self) -> int:
        return len(json.dumps(self.__dict__, default=str).encode()) + 1024


class _FiniteClient:
    """Keep the adapter's bounded download seam, with a smaller point ceiling."""

    def __init__(self, client: PoliteClient):
        self.client = client

    def download(self, url: str, path: Path, *, max_bytes: int):
        return self.client.download(url, path, max_bytes=min(max_bytes, MAX_RESPONSE_BYTES),
                                    headers={"Accept-Encoding": "identity"}, chunk_size=1024)


def _hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("CAMS AOD selection requires an offset")
    value = value.astimezone(UTC)
    if value.minute or value.second or value.microsecond:
        raise ValueError("CAMS AOD requires exact intermediary hourly timestamps")
    return value


class OpenMeteoCamsAodQueryService:
    """Coalesce identical bounded windows; retain no artifacts or raw responses."""

    def __init__(self, *, client: PoliteClient | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self._client = _FiniteClient(client or PoliteClient(attempts=1))
        self._clock, self._utcnow = clock, utcnow
        self._lock = threading.Lock()
        self._entries: dict[CamsAodSelection, CamsAodEntry] = {}
        self._inflight: dict[CamsAodSelection, Future[CamsAodEntry]] = {}

    def query(self, latitude: float, longitude: float, start: datetime,
              end: datetime | None = None, *, refresh: bool = False) -> CamsAodEntry:
        if (isinstance(latitude, bool) or isinstance(longitude, bool)
                or not math.isfinite(latitude) or not -90 <= latitude <= 90
                or not math.isfinite(longitude) or not -180 <= longitude <= 180):
            raise ValueError("CAMS AOD coordinates must be finite and in range")
        start, end = _hour(start), _hour(end if end is not None else start)
        if not timedelta(0) <= end - start < timedelta(hours=MAX_HOURS):
            raise ValueError("CAMS AOD selection must contain 1 to 24 hours")
        key = CamsAodSelection(float(latitude), float(longitude), start, end)
        with self._lock:
            self._entries = {k: v for k, v in self._entries.items() if self._clock() < v.expires_at_monotonic}
            cached = self._entries.get(key)
            if not refresh and cached is not None:
                return cached
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                if len(self._inflight) >= MAX_INFLIGHT:
                    raise OpenMeteoCamsAodUnavailable("CAMS AOD concurrent acquisition bound reached")
                future = Future()
                self._inflight[key] = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            entry = self._fetch(key)
            with self._lock:
                self._entries[key] = entry
                while len(self._entries) > MAX_CACHE_ENTRIES or sum(v.backing_bytes for v in self._entries.values()) > MAX_CACHE_BYTES:
                    self._entries.pop(next(iter(self._entries)))
            future.set_result(entry)
            return entry
        except BaseException as error:
            # A failed refresh never changes the old entry's fixed deadline.
            # The next read removes it if the deadline elapsed during failure.
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def _fetch(self, key: CamsAodSelection) -> CamsAodEntry:
        window = FetchWindow(key.start, back_hours=0, forward_hours=(key.end-key.start).total_seconds()/3600)
        adapter = OpenMeteoCompositionAdapter(SOURCE_ID, client=self._client,
                                              latitude=key.latitude, longitude=key.longitude)
        try:
            candidate = adapter.discover(window)[0]
            acquired = self._utcnow()
            deadline = self._clock() + TTL_SECONDS
            payload = candidate.detail["payload"]
            # The existing adapter permits full-day slicing for archive proof;
            # this demand path permits only the requested finite hourly shape.
            if any(isinstance(payload.get(name), bool) for name in ("latitude", "longitude")):
                raise AdapterUnavailable("invalid returned AOD coordinates")
            hourly, units = payload.get("hourly", {}), payload.get("hourly_units", {})
            if set(hourly) != {"time", "aerosol_optical_depth"} or set(units) != set(hourly):
                raise AdapterUnavailable("unexpected named AOD field inventory")
            if units["time"] != "iso8601" or len(hourly["time"]) > MAX_HOURS:
                raise AdapterUnavailable("invalid bounded AOD time axis")
            times = tuple(_hour(t) for t in _times(hourly["time"]))
            if (not times or times != tuple(sorted(set(times)))
                    or any(t < key.start or t > key.end for t in times)):
                raise AdapterUnavailable("AOD time axis is duplicated, unordered, or outside selection")
            with tempfile.TemporaryDirectory(prefix="astraeus-cams-aod-") as directory:
                result = adapter.fetch(candidate, window, Path(directory))
                if not result.complete or not result.qc_passed:
                    raise AdapterUnavailable("AOD adapter completeness/QC gate refused publication")
                artifact = result.artifacts[0]
                with zarr.storage.ZipStore(artifact.payload_path, mode="r") as store:
                    with xarray.open_zarr(store, consolidated=False) as dataset:
                        raw = dataset[FIELD_KEY].values[:, 0, 0]
                        values = tuple(float(v) if math.isfinite(float(v)) else None for v in raw)
                provenance = artifact.provenance
            if self._clock() >= deadline:
                raise AdapterUnavailable("AOD acquisition expired during validation")
            entry = CamsAodEntry(key, times, values, *provenance["returned_coordinates"],
                                 acquired, acquired + timedelta(seconds=TTL_SECONDS), deadline,
                                 candidate.detail["sha256"], candidate.urls[0],
                                 candidate.detail["latest_model_initialisation"],
                                 tuple(provenance["intermediary_transformations"]))
            if entry.backing_bytes > MAX_CACHE_BYTES:
                raise AdapterUnavailable("AOD cache entry exceeds byte ceiling")
            return entry
        except Exception as error:
            raise OpenMeteoCamsAodUnavailable(f"CAMS AOD acquisition failed: {type(error).__name__}: {error}") from error

    def point_fields(self, latitude: float, longitude: float, selected: datetime,
                     *, refresh: bool = False) -> list[EvidenceField]:
        entry = self.query(latitude, longitude, selected, refresh=refresh)
        if selected.astimezone(UTC) not in entry.times:
            raise OpenMeteoCamsAodUnavailable("CAMS AOD has no exact returned hour")
        value = entry.values[entry.times.index(selected.astimezone(UTC))]
        distance = math.hypot(entry.sampled_latitude-latitude,
                              (entry.sampled_longitude-longitude)*math.cos(math.radians(latitude))) * 111.32
        return [EvidenceField(field=FIELD_KEY, key=FIELD_KEY, value=value, provenance=Provenance(
            data_mode=DataMode.LIVE, evidence_class="reprocessed", source_id=SOURCE_ID,
            artifact_revision=f"demand:{entry.response_sha256}",
            provider="ECMWF Copernicus Atmosphere Monitoring Service (CAMS)",
            product="CAMS global atmospheric composition forecast", forecast_centre="ECMWF",
            run_time=None, valid_time=selected.astimezone(UTC), retrieval_time=entry.retrieved_at,
            vertical_level="total atmosphere", original_units="", normalized_units="1",
            native_resolution="0.4 degree served at 0.1 degree cell centres", native_crs="EPSG:4326",
            quality=Quality(status="unknown" if value is None else "passed", flags=["exact_intermediary_hour"]),
            coverage=Coverage(status="complete", fraction=1.0),
            freshness=Freshness.evaluate(max(0, int((self._utcnow()-entry.retrieved_at).total_seconds())), TTL_SECONDS),
            licence="Open-Meteo CC BY 4.0 plus upstream terms",
            attribution="CAMS global atmospheric composition via Open-Meteo",
            delivery_kind="reprocessed", intermediary="Open-Meteo", source_display_primary=False,
            intermediary_method="; ".join(entry.transformations), adapter_version="openmeteo-cams-aod-demand-v1",
            sampled_latitude=entry.sampled_latitude, sampled_longitude=entry.sampled_longitude,
            sample_distance_km=distance, sample_method="rectilinear", run_stale=None,
            run_stale_reason="Rolling intermediary series has no per-value producer run reference",
        ))]
