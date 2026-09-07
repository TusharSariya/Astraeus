"""Isolated GOES-19 ACTPF native evidence delivery; no public activation.

One retained cropped NetCDF revision, exact producer phase codes and DQF.
Retention is a memory policy, not a claim that a scan is current.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from ingest.adapters.goes_abi import GOES_S3_BASE, _hour_prefix, parse_bucket_keys, parse_scan_stamp
from ingest.adapters.goes_abi_l2 import DISCOVERY_HOURS, MAX_GRANULE_BYTES, parse_product_key
from ingest.http import USER_AGENT
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

PRODUCT_ID = "ABI-L2-ACTPF"
MAX_LISTING_BYTES = 512 * 1024
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
RETENTION_SECONDS = 300
DECODE_LIMITS = ProcessAllocationLimits(768 * 1024 * 1024, MAX_GRANULE_BYTES, MAX_GRANULE_BYTES, 16384, 16384)
_KEY = re.compile(r"ABI-L2-ACTPF/\d{4}/\d{3}/\d{2}/OR_ABI-L2-ACTPF-M6_G19_s\d{14}_e\d{14}_c\d{14}\.nc")


class GOESPhaseUnavailable(RuntimeError):
    """No complete native phase revision; never substitute cloud or fog."""


@dataclass(frozen=True)
class PhaseReceipt:
    url: str
    body_bytes: int
    sha256: str
    completed_at: datetime


@dataclass(frozen=True)
class PhaseEvidence:
    artifact: bytes
    metadata_json: str
    receipt: PhaseReceipt
    listing_receipts: tuple[PhaseReceipt, ...]
    retained_until: datetime
    artifact_sha256: str
    cache_status: str = "miss"
    source_id: str = "noaa-goes-east"
    product_id: str = PRODUCT_ID
    operational: bool = False



@dataclass(frozen=True)
class NativePhasePoint:
    """One native pixel and its receipt; no shared categorical conversion.

    Quality is producer readability only. It never establishes source admission
    or local scientific QC, which remains unknown.
    """
    phase_code: int | None
    dqf_code: int | None
    sampled_latitude: float
    sampled_longitude: float
    sample_distance_km: float
    scan_start: datetime
    scan_end: datetime
    native_projection_json: str
    evidence: PhaseEvidence
    requested_latitude: float
    requested_longitude: float
    selected_time: datetime
    flags: tuple[str, ...] = ()
    sample_method: str = "curvilinear_nearest_cell"
    quality_state: str = "unknown"
    units: str = "code"
    operational: bool = False


def native_point_from_entry(entry: PhaseEvidence, latitude: float, longitude: float,
                            selected_time: datetime) -> NativePhasePoint:
    """Read an already retained crop without acquiring or renewing anything.

    Reuses the experiment's one-cell spatial metric and one-hour time ceiling.
    Native flag meanings stay in the artifact; codes do not become labels.
    """
    import xarray
    from .store import (KM_PER_DEGREE, MAX_GRID_DISTANCE_DEGREES,
                        _nearest_curvilinear_cell, _nearest_time_index)

    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("ACTPF requires finite geographic coordinates")
    if selected_time.tzinfo is None:
        raise ValueError("ACTPF selected time must be timezone-aware")
    if (entry.product_id != PRODUCT_ID or entry.source_id != "noaa-goes-east"
            or len(entry.artifact) > MAX_ARTIFACT_BYTES
            or hashlib.sha256(entry.artifact).hexdigest() != entry.artifact_sha256):
        raise GOESPhaseUnavailable("ACTPF retained artifact identity mismatch")
    with tempfile.TemporaryDirectory(prefix="goes-phase-point-") as directory:
        path = Path(directory) / "phase.nc"
        path.write_bytes(entry.artifact)
        with xarray.open_dataset(path) as dataset:
            metadata = json.loads(entry.metadata_json)
            if dataset.attrs.get("product_id") != PRODUCT_ID or dataset.attrs.get("source_dataset_name") != metadata.get("source_dataset_name"):
                raise GOESPhaseUnavailable("ACTPF crop identity mismatch")
            try:
                projection_json = dataset.attrs["native_projection_json"]
                projection = json.loads(projection_json)
                if projection != metadata["native_projection"]:
                    raise ValueError("projection mismatch")
                start = datetime.fromisoformat(dataset.attrs["scan_start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(dataset.attrs["scan_end"].replace("Z", "+00:00"))
                if start.tzinfo is None or end.tzinfo is None or end < start:
                    raise ValueError("invalid scan interval")
                instant = _nearest_time_index(dataset, "valid_time", selected_time)
            except (KeyError, ValueError, LookupError) as cause:
                raise GOESPhaseUnavailable("ACTPF scan or native projection unavailable for request") from cause
            nearest = _nearest_curvilinear_cell(dataset, "latitude", "longitude", latitude, longitude)
            if nearest is None:
                raise GOESPhaseUnavailable("ACTPF has no native coordinate cell")
            indexers, cell_lat, cell_lon, distance = nearest
            cell = dataset.isel(indexers).sel(valid_time=instant)
            phase = float(cell.cloud_top_phase.values)
            quality = float(cell.quality_flag.values)
            dqf = int(quality) if math.isfinite(quality) and quality.is_integer() else None
            flags = []
            if distance > MAX_GRID_DISTANCE_DEGREES:
                flags.append("sample_distance_exceeded")
            if dqf != 0:
                flags.append("native_quality_unreadable")
            if not math.isfinite(phase):
                flags.append("native_phase_missing")
            elif phase not in (0, 1, 2, 3, 4, 5):
                raise GOESPhaseUnavailable("ACTPF phase is outside the exact native categorical domain")
            return NativePhasePoint(
                None if flags else int(phase), dqf, cell_lat, cell_lon,
                round(distance * KM_PER_DEGREE, 3), start, end, projection_json,
                entry, latitude, longitude, selected_time, tuple(flags),
            )


def decode_phase(body: bytes, key: str) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory(prefix="goes-phase-") as directory:
        output = Path(directory) / "phase.nc"
        result = run_bounded_process(
            command=[sys.executable, str(Path(__file__).with_name("goes_phase_query_worker.py")), "{output}", key],
            stdin=body, destination=output, limits=DECODE_LIMITS,
        )
        if output.stat().st_size > MAX_ARTIFACT_BYTES:
            raise GOESPhaseUnavailable("ACTPF crop exceeds artifact ceiling")
        metadata = json.loads(result.stdout)
        if metadata.get("product_id") != PRODUCT_ID or metadata.get("source_dataset_name") != key.rsplit("/", 1)[-1]:
            raise GOESPhaseUnavailable("ACTPF decoded identity mismatch")
        return output.read_bytes(), json.dumps(metadata, sort_keys=True)


class GOESPhaseQueryService:
    """At most six listings and one granule per coalesced acquisition.

    Failed refresh raises to its callers and preserves a still-valid prior
    revision for ordinary reads. Expired revisions are never returned.
    """
    def __init__(self, *, client: httpx.Client | None = None,
                 clock: Callable[[], datetime] | None = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 decoder: Callable[[bytes, str], tuple[bytes, str]] = decode_phase) -> None:
        self._client = client or httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": USER_AGENT})
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic = monotonic
        self._decoder = decoder
        self._lock = threading.Lock()
        self._cached: PhaseEvidence | None = None
        self._deadline = 0.0
        self._inflight: Future[PhaseEvidence] | None = None

    def _fetch(self, url: str, cap: int) -> tuple[bytes, PhaseReceipt]:
        request_deadline = self._monotonic() + 60
        with self._client.stream("GET", url, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200 or response.headers.get("content-encoding", "identity") != "identity":
                raise GOESPhaseUnavailable("ACTPF provider response refused")
            body = bytearray()
            for chunk in response.iter_bytes():
                if self._monotonic() >= request_deadline:
                    raise GOESPhaseUnavailable("ACTPF provider request exceeded time ceiling")
                if len(body) + len(chunk) > cap:
                    raise GOESPhaseUnavailable("ACTPF response exceeds byte ceiling")
                body.extend(chunk)
        payload = bytes(body)
        return payload, PhaseReceipt(url, len(payload), hashlib.sha256(payload).hexdigest(), self._clock())

    def _valid_cache(self) -> bool:
        return (self._cached is not None and self._clock() < self._cached.retained_until
                and self._monotonic() < self._deadline)

    def read_native(self, *, refresh: bool = False) -> PhaseEvidence:
        with self._lock:
            if not self._valid_cache():
                self._cached = None
            if self._cached is not None and not refresh:
                return replace(self._cached, cache_status="hit")
            future = self._inflight
            leader = future is None
            if leader:
                future = Future()
                self._inflight = future
        assert future is not None
        if not leader:
            return replace(future.result(), cache_status="hit")
        try:
            evidence, deadline = self._acquire(refresh)
        except Exception as cause:
            error = cause if isinstance(cause, GOESPhaseUnavailable) else GOESPhaseUnavailable("ACTPF native evidence unavailable")
            with self._lock:
                if not self._valid_cache():
                    self._cached = None
                future.set_exception(error)
                self._inflight = None
            raise error from (cause if cause is not error else None)
        with self._lock:
            self._cached, self._deadline = evidence, deadline
            future.set_result(evidence)
            self._inflight = None
        return evidence

    def read_point_native(self, latitude: float, longitude: float, selected_time: datetime,
                          *, refresh: bool = False) -> NativePhasePoint:
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("ACTPF requires finite geographic coordinates")
        if selected_time.tzinfo is None:
            raise ValueError("ACTPF selected time must be timezone-aware")
        return native_point_from_entry(self.read_native(refresh=refresh), latitude, longitude, selected_time)

    def _acquire(self, refresh: bool) -> tuple[PhaseEvidence, float]:
        started = self._clock()
        deadline = self._monotonic() + RETENTION_SECONDS
        expiry = started + timedelta(seconds=RETENTION_SECONDS)
        found: list[tuple[datetime, str]] = []
        receipts = []
        for hours_back in range(DISCOVERY_HOURS):
            prefix = _hour_prefix(PRODUCT_ID, started - timedelta(hours=hours_back))
            listing, receipt = self._fetch(f"{GOES_S3_BASE}/?list-type=2&max-keys=1000&prefix={prefix}", MAX_LISTING_BYTES)
            receipts.append(receipt)
            for key in parse_bucket_keys(listing.decode("utf-8")):
                if not _KEY.fullmatch(key) or not key.startswith(prefix):
                    continue
                stamp = parse_product_key(key, PRODUCT_ID)
                if stamp is not None:
                    observed = parse_scan_stamp(stamp)
                    if started - timedelta(hours=DISCOVERY_HOURS) <= observed <= started:
                        found.append((observed, key))
        if not found:
            raise GOESPhaseUnavailable("ACTPF has no native scan in bounded discovery window")
        _, key = max(found)
        body, receipt = self._fetch(f"{GOES_S3_BASE}/{key}", MAX_GRANULE_BYTES)
        artifact, metadata = self._decoder(body, key)
        if not artifact or len(artifact) > MAX_ARTIFACT_BYTES or len(metadata.encode()) > 16384:
            raise GOESPhaseUnavailable("ACTPF decoded output exceeds bounds or is empty")
        if self._clock() >= expiry or self._monotonic() >= deadline:
            raise GOESPhaseUnavailable("ACTPF acquisition exceeded retention window")
        return PhaseEvidence(artifact, metadata, receipt, tuple(receipts), expiry,
                             hashlib.sha256(artifact).hexdigest(), "refresh" if refresh else "miss"), deadline
