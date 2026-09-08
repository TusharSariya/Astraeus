"""Experimental bounded WeatherNext statistics manifest queries; no network default.

The acquisition callback is an injected seam for the existing bounded collector.
This module does not authenticate, publish, or establish consumer field mappings.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from ingest.adapters.weathernext3_statistics import (
    CLOUD_FIELDS, EXPECTED_FIELDS, PRODUCT, SOURCE_ID, validate_acquisition,
)

MANIFEST_MAX_BYTES = 16 * 1024 * 1024
CACHE_MAX_ENTRIES = 8
CACHE_MAX_BYTES = 2 * 1024 * 1024
TTL_SECONDS = 60
HISTORICAL_DELAY = timedelta(hours=48)


class WeatherNextQueryUnavailable(RuntimeError):
    """A safe source-local failure, containing no acquisition exception text."""


@dataclass(frozen=True)
class WeatherNextSelection:
    initialization: datetime
    valid_time: datetime
    latitude: float
    longitude: float
    fields: tuple[str, ...] = CLOUD_FIELDS

    def __post_init__(self) -> None:
        for stamp in (self.initialization, self.valid_time):
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("WeatherNext times require an explicit offset")
        object.__setattr__(self, "initialization", self.initialization.astimezone(UTC))
        object.__setattr__(self, "valid_time", self.valid_time.astimezone(UTC))
        lead = (self.valid_time - self.initialization).total_seconds() / 3600
        horizon = 360 if self.initialization.astimezone(UTC).hour % 6 == 0 else 48
        if self.initialization.minute or self.initialization.second or self.initialization.microsecond:
            raise ValueError("WeatherNext initialization must be an exact UTC hour")
        if not 0 <= lead <= horizon or not lead.is_integer():
            raise ValueError("WeatherNext requires an exact native hourly lead within the run horizon")
        if not math.isfinite(self.latitude) or not math.isfinite(self.longitude):
            raise ValueError("WeatherNext location must be finite")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("WeatherNext location is outside geographic bounds")
        if not self.fields or len(self.fields) != len(set(self.fields)) or not set(self.fields) <= set(EXPECTED_FIELDS):
            raise ValueError("WeatherNext fields must be unique documented statistics")
        object.__setattr__(self, "initialization", self.initialization.astimezone(UTC))
        object.__setattr__(self, "valid_time", self.valid_time.astimezone(UTC))
        object.__setattr__(self, "fields", tuple(sorted(self.fields)))


@dataclass(frozen=True)
class WeatherNextValue:
    field: str
    value: float | None
    unit: str
    statistic: str
    grid: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class WeatherNextReceipt:
    identity: str
    source_id: str
    product: str
    initialization: datetime
    valid_time: datetime
    manifest_sha256: str
    manifest_bytes: int
    source_retrieved_at: datetime
    completed_at: datetime
    expires_at: datetime
    evidence_class: str = "retained_acquisition_manifest_replay"
    terms_class: str = "historical_conservative_48_hour_valid_time_gate"


@dataclass(frozen=True)
class WeatherNextReading:
    values: tuple[WeatherNextValue, ...]
    receipt: WeatherNextReceipt


@dataclass(frozen=True)
class _Entry:
    reading: WeatherNextReading
    expiry: float
    size: int


def _stamp(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("manifest timestamp lacks offset")
    return stamp.astimezone(UTC)


def _decode(body: bytes, selection: WeatherNextSelection) -> tuple[tuple[WeatherNextValue, ...], datetime]:
    manifest = json.loads(body)
    validate_acquisition(manifest)
    if _stamp(manifest["times"]["initialization"]) != selection.initialization:
        raise ValueError("manifest initialization differs from requested run")
    lead = int((selection.valid_time - selection.initialization).total_seconds() / 3600)
    leads = manifest["sample"]["lead_hours"]
    if lead not in leads:
        raise ValueError("manifest has no exact requested native lead")
    index = leads.index(lead)
    samples = {item["field"]: item for item in manifest["sample"]["fields"]}
    box = manifest.get("avalon_box_sample")
    if box:
        samples = {item["field"]: item for item in box.get("fields", manifest["sample"]["fields"])}
    values = []
    for field in selection.fields:
        if field not in samples:
            raise ValueError("selected field was not retrieved")
        sample = samples[field]
        grid = sample.get("grid", "0p1")
        if box:
            coordinates = box["grids"][grid] if "grids" in box else box
            lats, lons = coordinates["latitudes"], coordinates["longitudes"]
            yi = min(range(len(lats)), key=lambda i: abs(lats[i] - selection.latitude))
            xi = min(range(len(lons)), key=lambda i: abs(lons[i] - selection.longitude))
            latitude, longitude = lats[yi], lons[xi]
            value = sample["leads"][index]["values"][yi][xi]
        else:
            latitude, longitude = sample["latitude"], sample["longitude"]
            value = sample["values"][index]
        # Only the retained native cell footprint is answerable. No distant
        # point substitution, interpolation or synthetic spatial coverage.
        tolerance = (0.05 if grid == "0p1" else 0.025) + 0.00005
        if abs(latitude - selection.latitude) > tolerance or abs(longitude - selection.longitude) > tolerance:
            raise ValueError("requested point is outside retained native cell coverage")
        values.append(WeatherNextValue(field, value, sample["unit"], field.rsplit("_", 1)[1],
                                       grid, latitude, longitude))
    return tuple(values), _stamp(manifest["times"]["retrieval"])


class WeatherNextStatisticsQueryService:
    """Finite source-local replay cache using the established manifest decoder.

    acquire(selection) must return bounded manifest bytes from the existing
    collector or retained evidence. No environment, account, API key or provider
    client is consulted. Acquisition failures never fall back to stale values.
    """

    def __init__(self, *, acquire: Callable[[WeatherNextSelection], bytes],
                 clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._acquire, self._clock, self._utcnow = acquire, clock, utcnow
        self._lock = threading.Lock()
        self._entries: OrderedDict[WeatherNextSelection, _Entry] = OrderedDict()
        self._inflight: dict[WeatherNextSelection, Future[_Entry]] = {}

    def read_point(self, selection: WeatherNextSelection, *, refresh: bool = False) -> WeatherNextReading:
        now = self._utcnow()
        if now.tzinfo is None or now.utcoffset() is None:
            raise WeatherNextQueryUnavailable("WeatherNext clock requires an explicit offset")
        if selection.valid_time >= now - HISTORICAL_DELAY:
            raise WeatherNextQueryUnavailable("WeatherNext terms permission is not established for this valid time")
        with self._lock:
            entry = self._entries.get(selection)
            if entry and self._clock() >= entry.expiry:
                del self._entries[selection]
                entry = None
            if entry and not refresh:
                self._entries.move_to_end(selection)
                return entry.reading
            future = self._inflight.get(selection)
            owner = future is None
            if owner:
                if len(self._inflight) >= CACHE_MAX_ENTRIES:
                    raise WeatherNextQueryUnavailable("WeatherNext concurrent acquisition bound exceeded")
                future = Future()
                self._inflight[selection] = future
        assert future is not None
        if not owner:
            return future.result().reading
        try:
            body = self._acquire(selection)
            if not isinstance(body, bytes) or not 0 < len(body) <= MANIFEST_MAX_BYTES:
                raise ValueError("WeatherNext manifest body bound exceeded")
            completed, completed_monotonic = self._utcnow(), self._clock()
            if completed.tzinfo is None or completed.utcoffset() is None or selection.valid_time >= completed - HISTORICAL_DELAY:
                raise ValueError("WeatherNext valid time is no longer historical under the conservative gate")
            values, source_retrieved = _decode(body, selection)
            digest = hashlib.sha256(body).hexdigest()
            identity = hashlib.sha256((repr(selection) + digest).encode()).hexdigest()
            receipt = WeatherNextReceipt(identity, SOURCE_ID, PRODUCT, selection.initialization,
                selection.valid_time, digest, len(body), source_retrieved, completed,
                completed + timedelta(seconds=TTL_SECONDS))
            reading = WeatherNextReading(values, receipt)
            size = len(repr(reading).encode())
            if size > CACHE_MAX_BYTES or self._clock() >= completed_monotonic + TTL_SECONDS:
                raise ValueError("WeatherNext cache bounds exceeded")
            replacement = _Entry(reading, completed_monotonic + TTL_SECONDS, size)
            with self._lock:
                previous = self._entries.get(selection)
                if previous and previous.expiry > self._clock() and previous.reading.receipt.identity == identity:
                    replacement = previous
                    reading = previous.reading
                self._entries[selection] = replacement
                self._entries.move_to_end(selection)
                while len(self._entries) > CACHE_MAX_ENTRIES or sum(e.size for e in self._entries.values()) > CACHE_MAX_BYTES:
                    self._entries.popitem(last=False)
            future.set_result(replacement)
            return reading
        except Exception:
            error = WeatherNextQueryUnavailable("WeatherNext bounded acquisition or manifest validation failed")
            future.set_exception(error)
            raise error from None
        finally:
            with self._lock:
                self._inflight.pop(selection, None)
