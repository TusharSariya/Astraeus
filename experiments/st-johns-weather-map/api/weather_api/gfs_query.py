"""Source-local coalescing cache for selected-timestamp NOAA GFS queries."""

from __future__ import annotations

import threading
import time
import json
import hashlib
import tempfile
import sys
import zipfile
import re
import xml.etree.ElementTree as ElementTree
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from ingest.adapters.noaa_s3 import (
    GFS_IDX_SELECTORS,
    MAX_IDX_BYTES,
    NOAAS3Adapter,
    cap_open_range,
    gfs_native_lead,
    gfs_native_time_at_or_before,
    select_gfs_ranges,
)
from ingest.contract import FetchWindow, RunCandidate
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

GFS_OBJECT_CACHE_TTL_SECONDS = 600.0
GFS_TIMELINE_LISTING_MAX_BYTES = 1024 * 1024
GFS_TIMELINE_LISTING_MAX_KEYS = 1000
_GFS_LISTED_LEAD = re.compile(r"\.f(\d{3})\.idx$")
GFS_CACHE_MAX_ENTRIES = 4
GFS_CACHE_MAX_BYTES = 256 * 1024 * 1024
GFS_DEMAND_WORKSPACE_BYTES = 192 * 1024 * 1024
GFS_DEMAND_LIMITS = ProcessAllocationLimits(
    address_space_bytes=1 * 1024 * 1024 * 1024,
    output_bytes=64 * 1024 * 1024,
    # A 2 MiB sidecar can expand six-fold when control bytes are JSON escaped.
    stdin_bytes=16 * 1024 * 1024,
    stdout_bytes=64 * 1024,
    stderr_bytes=256 * 1024,
)
_COORDINATOR: GFSQueryCoordinator | None = None

@dataclass(frozen=True)
class GFSRequestKey:
    """Canonical provider request identity known before payload retrieval."""

    index_url: str
    grib_url: str
    ranges: tuple[tuple[int, int], ...]
    fields: tuple[str, ...]
    bounds: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class GFSQueryEntry:
    key: GFSRequestKey
    run_time: datetime
    valid_time: datetime
    fetched_at: datetime
    content_digest: str
    values: Mapping[str, object]
    provenance: Mapping[str, object]
    payloads: tuple[bytes, ...] = ()

    def __post_init__(self) -> None:
        if any(value.tzinfo is None for value in (self.run_time, self.valid_time, self.fetched_at)):
            raise ValueError("GFS cache entry times must be timezone-aware")
        if len(self.content_digest) != 64 or any(char not in "0123456789abcdef" for char in self.content_digest):
            raise ValueError("GFS content digest must be lowercase SHA-256")

    @property
    def backing_bytes(self) -> int:
        metadata = json.dumps(
            {"values": self.values, "provenance": self.provenance},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return len(metadata) + sum(len(payload) for payload in self.payloads)


class GFSQueryService:
    """Cache exact immutable GFS object ranges and coalesce identical misses."""

    def __init__(
        self,
        loader: Callable[[GFSRequestKey], GFSQueryEntry],
        *,
        ttl_seconds: float = GFS_OBJECT_CACHE_TTL_SECONDS,
        max_entries: int = GFS_CACHE_MAX_ENTRIES,
        max_bytes: int = GFS_CACHE_MAX_BYTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0 or max_bytes <= 0:
            raise ValueError("GFS cache TTL, entry count and byte ceiling must be positive")
        if max_entries > GFS_CACHE_MAX_ENTRIES or max_bytes > GFS_CACHE_MAX_BYTES:
            raise ValueError("GFS cache configuration exceeds its source-local ceiling")
        self._loader = loader
        self._ttl = ttl_seconds
        self._clock = clock
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        self._entries: OrderedDict[GFSRequestKey, tuple[float, GFSQueryEntry]] = OrderedDict()
        self._inflight: dict[GFSRequestKey, Future[GFSQueryEntry]] = {}

    def query(self, key: GFSRequestKey) -> GFSQueryEntry:
        while True:
            with self._lock:
                now = self._clock()
                cached = self._entries.get(key)
                if cached is not None and now < cached[0]:
                    self._entries.move_to_end(key)
                    return cached[1]
                if cached is not None:
                    self._entries.pop(key)
                future = self._inflight.get(key)
                if future is None:
                    future = Future()
                    self._inflight[key] = future
                    owner = True
                else:
                    owner = False
            if owner:
                try:
                    entry = self._loader(key)
                    if entry.key != key:
                        raise ValueError("GFS loader returned a different provider request identity")
                    if entry.backing_bytes <= 0 or entry.backing_bytes > self._max_bytes:
                        raise ValueError("GFS normalized cache entry exceeds its finite byte ceiling")
                    with self._lock:
                        self._entries[key] = (self._clock() + self._ttl, entry)
                        self._entries.move_to_end(key)
                        while (
                            len(self._entries) > self._max_entries
                            or sum(item.backing_bytes for _, item in self._entries.values()) > self._max_bytes
                        ):
                            self._entries.popitem(last=False)
                    future.set_result(entry)
                    return entry
                except BaseException as error:
                    with self._lock:
                        self._entries.pop(key, None)
                    future.set_exception(error)
                    raise
                finally:
                    with self._lock:
                        self._inflight.pop(key, None)
            return future.result()


class GFSQueryCoordinator:
    """Resolve one selection and load one exact GFS object-range request."""

    def __init__(
        self,
        adapter: NOAAS3Adapter | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime],
        bounded_fetch: Callable[[GFSRequestKey, RunCandidate, datetime], GFSQueryEntry] | None = None,
    ) -> None:
        self._adapter = adapter or NOAAS3Adapter()
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._candidate: tuple[float, RunCandidate] | None = None
        self._indices: OrderedDict[str, tuple[float, str, Mapping[str, object] | None]] = OrderedDict()
        self._timeline: tuple[float, str, tuple[datetime, ...], Mapping[str, object]] | None = None
        self._timeline_inflight: Future[tuple[tuple[datetime, ...], Mapping[str, object]]] | None = None
        self._prepared: dict[GFSRequestKey, RunCandidate] = {}
        self._bounded_fetch = bounded_fetch
        self._cache = GFSQueryService(self._load, clock=clock)

    def query(self, selected_time: datetime) -> GFSQueryEntry:
        with self._lock:
            candidate = self._discover()
            if candidate.run_time is None:
                raise ValueError("GFS discovery returned no producer run time")
            native_time = gfs_native_time_at_or_before(candidate.run_time, selected_time)
            lead = gfs_native_lead(candidate.run_time, native_time)
            date_str = str(candidate.detail["date_str"])
            cycle = str(candidate.detail["cycle"])
            stem = f"gfs.t{cycle}z.pgrb2.0p25.f{lead:03d}"
            grib_url = f"{self._adapter._base_url}/gfs.{date_str}/{cycle}/atmos/{stem}"
            idx_url = f"{grib_url}.idx"
            idx_text, idx_receipt = self._index(idx_url)
            ranges, _present = select_gfs_ranges(idx_text)
            ranges = cap_open_range(ranges)
            key = GFSRequestKey(
                index_url=idx_url,
                grib_url=grib_url,
                ranges=tuple((item.start, int(item.end)) for item in ranges if item.end is not None),
                fields=tuple(f"{parameter}:{level}" for parameter, level in sorted(GFS_IDX_SELECTORS)),
                bounds=tuple(sorted((str(name), float(value)) for name, value in self._adapter._bounds.items())),
            )
            self._prepared[key] = RunCandidate(
                candidate.provider_run_id,
                candidate.run_time,
                list(candidate.urls),
                {**candidate.detail, "idx_text_by_lead": {lead: idx_text}, "idx_receipts_by_lead": {lead: idx_receipt}},
            )
            try:
                return self._cache.query(key)
            finally:
                self._prepared.pop(key, None)

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime) -> tuple[list[Any], Any, list[str]]:
        """Answer one point through the existing evidence/provenance builder.

        Demand payloads remain memory-resident cache entries.  They are opened
        only for this request and presented to the existing sampler as native
        retrieved artifacts; no ArtifactStore row or current revision is
        invented for the live-query path.
        """
        from .store import LiveStore, live_point_fields  # noqa: PLC0415

        entry = self.query(selected_time)
        samples = []
        with tempfile.TemporaryDirectory(prefix="gfs-demand-read-") as directory:
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped = []
            sampler.unmodelled = []
            for index, logical_name in enumerate(entry.values["logical_names"]):
                path = Path(directory) / f"{logical_name}.zarr.zip"
                path.write_bytes(entry.payloads[index])
                import xarray  # noqa: PLC0415
                import zarr  # noqa: PLC0415

                zipped = zarr.storage.ZipStore(str(path), mode="r")
                dataset = xarray.open_zarr(zipped, consolidated=False)
                try:
                    provenance = dict(entry.provenance[logical_name])
                    provenance.setdefault("run_time", entry.run_time.isoformat())
                    artifact = SimpleNamespace(
                        source_id="noaa-gfs",
                        logical_name=logical_name,
                        revision_id=f"demand:{entry.content_digest}:{logical_name}",
                        provenance=provenance,
                        run_time=entry.run_time,
                        retrieved_at=entry.fetched_at,
                        native_crs=provenance.get("native_crs", "EPSG:4326"),
                    )
                    samples.extend(
                        sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time)
                    )
                finally:
                    dataset.close()
                    zipped.close()

        class _Samples:
            skipped = sampler.skipped
            unmodelled = sampler.unmodelled

            @staticmethod
            def sample_point(*_args: object, **_kwargs: object) -> list[Any]:
                return samples

        return live_point_fields(_Samples(), latitude, longitude, entry.valid_time)

    def profile_levels(self, latitude: float, longitude: float, selected_time: datetime, pressures: tuple[int, ...]) -> list[Any]:
        """Answer the existing pressure-level profile from one cached frame."""
        from .store import (  # noqa: PLC0415
            WIND_METHOD,
            LiveStore,
            _derived_evidence_field,
            _registered_wind,
            live_profile_levels,
        )
        from .science import WIND_DIRECTION_UNITS, WIND_SPEED_UNITS  # noqa: PLC0415

        entry = self.query(selected_time)
        by_pressure: dict[int, list[Any]] = {}
        with tempfile.TemporaryDirectory(prefix="gfs-demand-profile-") as directory:
            sampler = LiveStore.__new__(LiveStore)
            sampler.skipped = []
            sampler.unmodelled = []
            for index, logical_name in enumerate(entry.values["logical_names"]):
                path = Path(directory) / f"{logical_name}.zarr.zip"
                path.write_bytes(entry.payloads[index])
                import xarray  # noqa: PLC0415
                import zarr  # noqa: PLC0415

                zipped = zarr.storage.ZipStore(str(path), mode="r")
                dataset = xarray.open_zarr(zipped, consolidated=False)
                try:
                    provenance = dict(entry.provenance[logical_name])
                    provenance.setdefault("run_time", entry.run_time.isoformat())
                    artifact = SimpleNamespace(
                        source_id="noaa-gfs",
                        logical_name=logical_name,
                        revision_id=f"demand:{entry.content_digest}:{logical_name}",
                        provenance=provenance,
                        run_time=entry.run_time,
                        retrieved_at=entry.fetched_at,
                        native_crs=provenance.get("native_crs", "EPSG:4326"),
                    )
                    for pressure in pressures:
                        found = sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time, pressure=pressure)
                        if found:
                            by_pressure.setdefault(pressure, []).extend(found)
                finally:
                    dataset.close()
                    zipped.close()

        class _Samples:
            skipped = sampler.skipped
            unmodelled = sampler.unmodelled

            @staticmethod
            def sample_profile(*_args: object, **_kwargs: object) -> dict[int, list[Any]]:
                return by_pressure

        levels = live_profile_levels(_Samples(), latitude, longitude, entry.valid_time, pressures)
        for level in levels:
            samples = {sample.variable: sample for sample in by_pressure.get(level.pressure_hpa, [])}
            suffix = f"_{level.pressure_hpa}hPa"
            u_name, v_name = f"wind_u{suffix}", f"wind_v{suffix}"
            u, v = samples.get(u_name), samples.get(v_name)
            # Pressure-level components are derivation inputs, not standalone
            # profile readings. The profile exposes the same registered wind
            # representation as its existing fixture and UI contract.
            level.fields = [
                field.model_copy(update={"field": "temperature"}) if field.key == "temperature_pressure"
                else field.model_copy(update={"field": "relative_humidity"}) if field.key == "relative_humidity_pressure"
                else field
                for field in level.fields
                if field.field not in {u_name, v_name}
            ]
            if u is not None and v is not None and u.value is not None and v.value is not None:
                speed, direction = _registered_wind(u.value, v.value)
                for name, derived, units in (
                    ("wind_speed", speed, WIND_SPEED_UNITS),
                    ("wind_direction", direction, WIND_DIRECTION_UNITS),
                ):
                    level.fields.append(
                        _derived_evidence_field(
                            _Samples(),
                            field_name=name,
                            basis=replace(u, variable=name, value=derived.value, units=units),
                            inputs=[(u_name, u), (v_name, v)],
                            method=WIND_METHOD,
                            value=derived.value,
                            derivation=derived.derivation,
                            derivation_version=derived.version,
                            reference=datetime.now(UTC),
                        )
                    )
        return levels

    def timeline_times(self, reference: datetime) -> tuple[tuple[datetime, ...], Mapping[str, object]]:
        """Return actual native frame keys from one bounded, coalesced S3 listing."""
        if reference.tzinfo is None:
            raise ValueError("reference must be timezone-aware")
        with self._lock:
            candidate = self._discover()
            current = self._clock()
            if self._timeline is not None and current < self._timeline[0] and self._timeline[1] == candidate.provider_run_id:
                return self._timeline[2], self._timeline[3]
            future = self._timeline_inflight
            owner = future is None
            if owner:
                future = Future()
                self._timeline_inflight = future
        assert future is not None
        if not owner:
            return future.result()
        try:
            if candidate.run_time is None:
                raise ValueError("GFS candidate has no producer run time")
            date_str, cycle = str(candidate.detail["date_str"]), str(candidate.detail["cycle"])
            prefix = f"gfs.{date_str}/{cycle}/atmos/gfs.t{cycle}z.pgrb2.0p25.f"
            query = urlencode({"list-type": "2", "max-keys": GFS_TIMELINE_LISTING_MAX_KEYS, "prefix": prefix})
            body, receipt = self._adapter._get_client().get_bytes_with_receipt(
                f"{self._adapter._base_url}?{query}", max_bytes=GFS_TIMELINE_LISTING_MAX_BYTES
            )
            upper = body.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ValueError("GFS listing declarations are unsupported")
            root = ElementTree.fromstring(body)
            if root.tag.rsplit("}", 1)[-1] != "ListBucketResult":
                raise ValueError("GFS listing has an unexpected root")
            nodes = list(root.iter())
            if len(nodes) > 3 * GFS_TIMELINE_LISTING_MAX_KEYS + 32:
                raise ValueError("GFS listing exceeds structural node bound")
            truncated = next((node.text for node in nodes if node.tag.rsplit("}", 1)[-1] == "IsTruncated"), "false")
            if str(truncated).lower() != "false":
                raise ValueError("GFS listing was truncated")
            leads: set[int] = set()
            for node in nodes:
                if node.tag.rsplit("}", 1)[-1] != "Key" or not isinstance(node.text, str) or not node.text.startswith(prefix):
                    continue
                match = _GFS_LISTED_LEAD.search(node.text)
                if match:
                    lead = int(match.group(1))
                    if lead <= 384 and (lead <= 120 or lead % 3 == 0):
                        leads.add(lead)
            start = reference.astimezone(UTC) - timedelta(hours=24)
            end = reference.astimezone(UTC) + timedelta(days=14)
            times = tuple(
                candidate.run_time + timedelta(hours=lead)
                for lead in sorted(leads)
                if start <= candidate.run_time + timedelta(hours=lead) <= end
            )
            result = (times, receipt)
            with self._lock:
                self._timeline = (current + GFS_OBJECT_CACHE_TTL_SECONDS, candidate.provider_run_id, times, receipt)
            future.set_result(result)
            return result
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._timeline_inflight = None

    def _discover(self) -> RunCandidate:
        current = self._clock()
        if self._candidate is not None and current < self._candidate[0]:
            return self._candidate[1]
        candidate = self._adapter.discover(FetchWindow(now=self._now()))[0]
        self._candidate = (current + GFS_OBJECT_CACHE_TTL_SECONDS, candidate)
        return candidate

    def _index(self, url: str) -> tuple[str, Mapping[str, object] | None]:
        current = self._clock()
        cached = self._indices.get(url)
        if cached is not None and current < cached[0]:
            self._indices.move_to_end(url)
            return cached[1], cached[2]
        client = self._adapter._get_client()
        if hasattr(client, "get_bytes_with_receipt"):
            raw, receipt = client.get_bytes_with_receipt(url, max_bytes=MAX_IDX_BYTES)
        else:
            raw, receipt = client.get_bytes(url, max_bytes=MAX_IDX_BYTES), None
        text = raw.decode("utf-8")
        self._indices[url] = (current + GFS_OBJECT_CACHE_TTL_SECONDS, text, receipt)
        while len(self._indices) > GFS_CACHE_MAX_ENTRIES:
            self._indices.popitem(last=False)
        return text, receipt

    def _load(self, key: GFSRequestKey) -> GFSQueryEntry:
        candidate = self._prepared[key]
        if self._bounded_fetch is not None:
            return self._bounded_fetch(key, candidate, self._selected_time(key, candidate))
        with tempfile.TemporaryDirectory(prefix="gfs-demand-") as directory:
            bundle_path = Path(directory) / "gfs-demand-result.zip"
            request = json.dumps(
                {
                    "provider_run_id": candidate.provider_run_id,
                    "run_time": candidate.run_time.isoformat() if candidate.run_time else None,
                    "selected_time": self._selected_time(key, candidate).isoformat(),
                    "urls": candidate.urls,
                    "detail": candidate.detail,
                    "base_url": self._adapter._base_url,
                    "bounds": self._adapter._bounds,
                },
                default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
                sort_keys=True,
            ).encode()
            run_bounded_process(
                command=[sys.executable, "-m", "weather_api.gfs_query_worker", "{output}"],
                stdin=request,
                destination=bundle_path,
                limits=GFS_DEMAND_LIMITS,
                timeout_seconds=180,
            )
            with zipfile.ZipFile(bundle_path) as bundle:
                info = json.loads(bundle.read("result.json"))
                if info.get("source_id") != "noaa-gfs" or not info.get("complete") or not info.get("qc_passed"):
                    raise ValueError("GFS bounded child returned an incomplete or failed-QC selection")
                if info.get("provider_run_id") != candidate.provider_run_id:
                    raise ValueError("GFS bounded child returned a different provider run")
                if datetime.fromisoformat(info["run_time"]) != candidate.run_time:
                    raise ValueError("GFS bounded child returned a different producer run time")
                if datetime.fromisoformat(info["valid_time"]) != self._selected_time(key, candidate):
                    raise ValueError("GFS bounded child returned a different native valid time")
                artifacts = info["artifacts"]
                if not artifacts or len(artifacts) > 2:
                    raise ValueError("GFS bounded child returned an invalid artifact set")
                logical_names = [artifact["logical_name"] for artifact in artifacts]
                if len(set(logical_names)) != len(logical_names) or set(logical_names) - {"surface", "upper_air"}:
                    raise ValueError("GFS bounded child returned invalid logical artifact names")
                expected_members = {"result.json", *(f"artifacts/{artifact['name']}" for artifact in artifacts)}
                if set(bundle.namelist()) != expected_members:
                    raise ValueError("GFS bounded child bundle contains unexpected members")
                if sum(member.file_size for member in bundle.infolist()) > GFS_DEMAND_LIMITS.output_bytes:
                    raise ValueError("GFS bounded child bundle expands beyond its output ceiling")
                payloads = tuple(bundle.read(f"artifacts/{artifact['name']}") for artifact in artifacts)
            digest = hashlib.sha256(b"".join(payloads)).hexdigest()
            provenance = {artifact["logical_name"]: artifact["provenance"] for artifact in artifacts}
        return GFSQueryEntry(
            key=key,
            run_time=datetime.fromisoformat(info["run_time"]),
            valid_time=self._selected_time(key, candidate),
            fetched_at=datetime.fromisoformat(info["retrieved_at"]),
            content_digest=digest,
            values={"logical_names": [artifact["logical_name"] for artifact in artifacts]},
            provenance=provenance,
            payloads=payloads,
        )

    @staticmethod
    def _selected_time(key: GFSRequestKey, candidate: RunCandidate) -> datetime:
        lead = int(key.grib_url.rsplit(".f", 1)[1])
        assert candidate.run_time is not None
        return candidate.run_time + timedelta(hours=lead)


def gfs_query_coordinator() -> GFSQueryCoordinator:
    """Process-local demand cache used by the public point route."""
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = GFSQueryCoordinator(now=lambda: datetime.now(UTC))
    return _COORDINATOR
