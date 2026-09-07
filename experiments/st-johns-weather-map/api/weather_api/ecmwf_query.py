"""Unregistered bounded ECMWF deterministic demand experiment for #270.

No registry, scheduler or public route imports this module. Runtime exposure
requires the verified-demand exception in the ECMWF source contract.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Callable
from urllib.parse import urljoin
import zipfile

import httpx

from ingest.adapters.ecmwf_opendata import (
    ECMWF_OPEN_DATA_BASE, ECMWF_ENSEMBLE_BOUNDS, MAX_MEMBER_BYTES,
    _download_verified_range, _get_bounded_metadata,
)
from ingest.contract import RunCandidate
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

TTL_SECONDS = 600
MAX_ENTRIES = 4
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_INDEX_RECORDS = 10000
MAX_DISCOVERY_REQUESTS = 7
MAX_ACQUISITION_SECONDS = 120
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_WORKSPACE_BYTES = 64 * 1024 * 1024
DECODE_LIMITS = ProcessAllocationLimits(address_space_bytes=1024**3, output_bytes=MAX_OUTPUT_BYTES,
    stdin_bytes=128 * 1024, stdout_bytes=64 * 1024, stderr_bytes=256 * 1024)
FIELDS = {"2t": ("temperature_2m", "degC"), "2d": ("dew_point_2m", "degC"),
          "msl": ("mean_sea_level_pressure", "hPa"), "tcc": ("total_cloud_geometric", "percent")}
PRODUCTS = {"ecmwf-ifs": ("ifs", "IFS Cycle 50r1", "https://www.ecmwf.int/en/forecasts/datasets/open-data"),
    "ecmwf-aifs-single": ("aifs-single", "AIFS Single v2", "https://www.ecmwf.int/en/forecasts/datasets/aifs-machine-learning-data")}


class ECMWFQueryUnavailable(ValueError):
    """The exact source selection could not be verified within its bounds."""


class ECMWFHTTP:
    """Source-local bounded receipt transport reused by Open Data range helpers."""
    def __init__(self, client=None, *, now=lambda: datetime.now(UTC), clock=time.monotonic):
        self.client = client or httpx.Client(timeout=30, follow_redirects=False,
            headers={"User-Agent": "astraeus-weather-experiment/0.1", "Accept-Encoding": "identity"})
        self.now, self.clock = now, clock
        self.receipts = []
        self.completed_monotonic = None
        self.deadline = self.clock() + MAX_ACQUISITION_SECONDS

    def read(self, url, *, limit, byte_range=None):
        if self.clock() >= self.deadline:
            raise ECMWFQueryUnavailable("ECMWF acquisition deadline exceeded")
        headers = {"Accept-Encoding": "identity"}
        if byte_range is not None:
            headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
        with self.client.stream("GET", url, headers=headers, follow_redirects=False) as response:
            expected_status = 200 if byte_range is None else 206
            if response.status_code != expected_status:
                response.raise_for_status()
                raise ECMWFQueryUnavailable("ECMWF response did not honor its request")
            if str(response.url) != url:
                raise ECMWFQueryUnavailable("ECMWF effective endpoint changed")
            if response.headers.get("content-encoding", "identity") != "identity":
                raise ECMWFQueryUnavailable("ECMWF encoded range/body is unsupported")
            declared = response.headers.get("content-length")
            if declared is not None and (not declared.isdigit() or int(declared) > limit):
                raise ECMWFQueryUnavailable("ECMWF declared body exceeds bound")
            if byte_range is not None:
                match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", ""))
                if not match or tuple(map(int, match.groups()[:2])) != byte_range or int(match[3]) <= byte_range[1]:
                    raise ECMWFQueryUnavailable("ECMWF range identity mismatch")
            body = bytearray()
            for chunk in response.iter_bytes(65536):
                if self.clock() >= self.deadline:
                    raise ECMWFQueryUnavailable("ECMWF acquisition deadline exceeded")
                body.extend(chunk)
                if len(body) > limit:
                    raise ECMWFQueryUnavailable("ECMWF received body exceeds bound")
            completed = self.now()
            self.completed_monotonic = self.clock()
            if declared is not None and len(body) != int(declared):
                raise ECMWFQueryUnavailable("ECMWF truncated declared body")
            if byte_range is not None and len(body) != byte_range[1] - byte_range[0] + 1:
                raise ECMWFQueryUnavailable("ECMWF truncated range")
            safe = {"content-length", "content-range", "content-type", "etag", "last-modified", "cache-control", "date", "expires"}
            receipt = {"url": url, "effective_url": str(response.url), "http_status": response.status_code,
                "request_headers": headers, "response_headers": {k: v for k, v in response.headers.items() if k in safe},
                "completed_at": completed.isoformat(), "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        if len(self.receipts) >= MAX_DISCOVERY_REQUESTS + 1 + len(FIELDS):
            raise ECMWFQueryUnavailable("ECMWF request budget exhausted")
        self.receipts.append(receipt)
        return bytes(body)

    def get_text(self, url):
        return self.read(url, limit=MAX_METADATA_BYTES).decode("utf-8")

    def download_ranges(self, url, destination, ranges, *, max_bytes):
        if len(ranges) != 1:
            raise ECMWFQueryUnavailable("ECMWF requires one exact record range")
        body = self.read(url, limit=min(max_bytes, MAX_MEMBER_BYTES), byte_range=ranges[0])
        destination.write_bytes(body)
        self.last_response_evidence = self.receipts[-1]
        return len(body)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for name, value in attrs if name == "href" and value is not None)


def native_lead(source_id, run, selected):
    seconds = (selected - run).total_seconds()
    if seconds < 0 or seconds % 3600:
        raise ECMWFQueryUnavailable("ECMWF requires an exact native selected time")
    lead = int(seconds // 3600)
    version_start = datetime(2026, 5, 13 if source_id == "ecmwf-ifs" else 12, tzinfo=UTC)
    if run < version_start:
        raise ECMWFQueryUnavailable("ECMWF run predates the verified model-version basis")
    if source_id == "ecmwf-aifs-single":
        valid = lead <= 360 and lead % 6 == 0
    else:
        valid = lead <= (360 if run.hour in (0, 12) else 144) and (lead % (3 if lead <= 144 else 6) == 0)
    if not valid:
        raise ECMWFQueryUnavailable("ECMWF selected time is outside native cycle/lead support")
    return lead


def select_records(text, source_id, run, lead):
    if len(text.encode()) > MAX_METADATA_BYTES:
        raise ECMWFQueryUnavailable("ECMWF index exceeds metadata bound")
    lines = text.splitlines()
    if len(lines) > MAX_INDEX_RECORDS:
        raise ECMWFQueryUnavailable("ECMWF index exceeds record bound")
    selected = {}
    model = PRODUCTS[source_id][0]
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ECMWFQueryUnavailable("ECMWF index record is not an object")
        required = {"param", "levtype", "date", "time", "step", "stream", "type", "_offset", "_length", "class"}
        if not required <= row.keys():
            raise ECMWFQueryUnavailable("ECMWF index omits native identity")
        if row["param"] not in FIELDS or row["levtype"] != "sfc":
            continue
        if (str(row["date"]) != run.strftime("%Y%m%d") or str(row["time"]).zfill(4) != run.strftime("%H%M")
            or str(row["step"]) != str(lead) or row.get("model", model) != model
            or row["class"] != ("od" if source_id == "ecmwf-ifs" else "ai") or row["stream"] != "oper" or row["type"] != "fc"):
            raise ECMWFQueryUnavailable("ECMWF index product/run/lead identity mismatch")
        start, length = row["_offset"], row["_length"]
        if type(start) is not int or type(length) is not int or start < 0 or not 0 < length <= MAX_MEMBER_BYTES:
            raise ECMWFQueryUnavailable("ECMWF record range is invalid or oversized")
        if row.get("number") not in (None, "0", 0):
            raise ECMWFQueryUnavailable("ECMWF deterministic record has a perturbed member")
        if row["param"] in selected:
            raise ECMWFQueryUnavailable("ECMWF deterministic field identity is duplicated")
        selected[row["param"]] = row
    if set(selected) != set(FIELDS):
        raise ECMWFQueryUnavailable("ECMWF selected native fields are absent")
    ordered = sorted(selected.values(), key=lambda row: row["_offset"])
    if any(a["_offset"] + a["_length"] > b["_offset"] for a, b in zip(ordered, ordered[1:])):
        raise ECMWFQueryUnavailable("ECMWF selected ranges overlap")
    return tuple(ordered)


@dataclass(frozen=True)
class ECMWFQueryEntry:
    source_id: str
    run_time: datetime
    valid_time: datetime
    fetched_at: datetime
    expires_at: datetime
    content_digest: str
    provenance: dict
    payload: bytes

    @property
    def backing_bytes(self):
        return len(self.payload) + len(json.dumps(self.provenance).encode())


class ECMWFQueryCoordinator:
    """One deterministic product, four selected native grids, no admission side effects."""
    def __init__(self, source_id, *, now=lambda: datetime.now(UTC), clock=time.monotonic,
                 client=None, base_url=ECMWF_OPEN_DATA_BASE, decoder=None):
        if source_id not in PRODUCTS:
            raise ValueError("Only IFS and AIFS Single deterministic products are supported")
        self.source_id, self.now, self.clock = source_id, now, clock
        self.client, self.base_url, self.decoder = client, base_url.rstrip("/"), decoder
        self._lock = threading.Lock()
        self._entries = OrderedDict()
        self._inflight = {}
        self._inventory = None
        self._inventory_lock = threading.Lock()

    def _discover(self, transport, *, refresh=False):
        with self._inventory_lock:
            if not refresh and self._inventory and self.clock() < self._inventory[0]:
                return self._inventory[1]
            ref = self.now().astimezone(UTC).replace(minute=0, second=0, microsecond=0)
            ref -= timedelta(hours=ref.hour % 6)
            candidates = []
            for age in range(MAX_DISCOVERY_REQUESTS):
                run = ref - timedelta(hours=6 * age)
                directory = f"{self.base_url}/{run:%Y%m%d}/{run:%H}z/{PRODUCTS[self.source_id][0]}/0p25/oper/"
                try:
                    listing = _get_bounded_metadata(transport, directory)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 404:
                        continue
                    raise
                parser = _Links(); parser.feed(listing)
                files = {}
                for href in parser.links:
                    match = re.fullmatch(r"(\d{14})-(\d+)h-oper-fc\.grib2", href.rsplit("/", 1)[-1])
                    if not match or match[1] != run.strftime("%Y%m%d%H%M%S"):
                        continue
                    lead = int(match[2])
                    try:
                        native_lead(self.source_id, run, run + timedelta(hours=lead))
                    except ECMWFQueryUnavailable:
                        continue
                    url = urljoin(directory, href)
                    if url != directory + match[0]:
                        continue
                    files[lead] = url
                if files:
                    candidates.append(RunCandidate(f"{self.source_id}-{run:%Y%m%d%H}", run,
                        list(files.values()), {"files": files, "discovery_receipt": transport.receipts[-1]}))
                if len(candidates) == 2:
                    break
            if not candidates:
                raise ECMWFQueryUnavailable("ECMWF has no verified run in bounded discovery")
            self._inventory = (transport.completed_monotonic + TTL_SECONDS, tuple(candidates))
            return self._inventory[1]

    def query(self, selected_time, *, run_id=None, refresh=False):
        if selected_time.tzinfo is None:
            raise ECMWFQueryUnavailable("ECMWF requires a timezone-aware selected time")
        selected_time = selected_time.astimezone(UTC)
        key = (selected_time, run_id)
        flight_key = (key, refresh)
        with self._lock:
            cached = self._entries.get(key)
            if not refresh and cached and self.clock() < cached[0]:
                self._entries.move_to_end(key); return cached[1]
            future = self._inflight.get(flight_key)
            owner = future is None
            if owner:
                if len(self._inflight) >= MAX_ENTRIES:
                    raise ECMWFQueryUnavailable("ECMWF concurrent selection bound reached")
                future = Future(); self._inflight[flight_key] = future
        if not owner:
            return future.result()
        try:
            transport = ECMWFHTTP(self.client, now=self.now, clock=self.clock)
            try:
                candidates = self._discover(transport, refresh=refresh)
                candidate = next((run for run in candidates if run.provider_run_id == run_id), None) if run_id else candidates[0]
                if candidate is None:
                    raise ECMWFQueryUnavailable("ECMWF named run is no longer available")
                lead = native_lead(self.source_id, candidate.run_time, selected_time)
                url = candidate.detail["files"].get(lead)
                if url is None:
                    raise ECMWFQueryUnavailable("ECMWF run has no published exact selected frame")
                index_url = url.removesuffix(".grib2") + ".index"
                records = select_records(_get_bounded_metadata(transport, index_url), self.source_id, candidate.run_time, lead)
                with tempfile.TemporaryDirectory(prefix="ecmwf-demand-") as directory:
                    request = {"source_id": self.source_id, "run_time": candidate.run_time.isoformat(),
                        "valid_time": selected_time.isoformat(), "lead": lead, "records": records,
                        "bounds": ECMWF_ENSEMBLE_BOUNDS, "directory": directory}
                    for row in records:
                        _download_verified_range(transport, url, Path(directory) / f'{row["param"]}.grib2',
                            (row["_offset"], row["_offset"] + row["_length"] - 1))
                    manifest, payload = (self.decoder(request) if self.decoder else self._decode(request))
                if (manifest.get("source_id") != self.source_id or manifest.get("run_time") != candidate.run_time.isoformat()
                    or manifest.get("valid_time") != selected_time.isoformat() or not manifest.get("complete") or not manifest.get("qc_passed")
                    or set(manifest.get("fields", ())) != {value[0] for value in FIELDS.values()}):
                    raise ECMWFQueryUnavailable("ECMWF decoder identity or validation failed")
                completion = datetime.fromisoformat(transport.receipts[-1]["completed_at"])
                provenance = {**manifest, "source_id": self.source_id, "producer": "ECMWF",
                    "product": PRODUCTS[self.source_id][1], "model_version_basis": PRODUCTS[self.source_id][2],
                    "model_version_verified_on": "2026-09-07", "distributed_grid": "regular latitude-longitude 0.25 degrees",
                    "provider_run_id": candidate.provider_run_id, "lead_hours": lead, "native_crs": "EPSG:4326",
                    "bounds": ECMWF_ENSEMBLE_BOUNDS, "index_records": records,
                    "request_identity": {"source_id": self.source_id, "model_version": PRODUCTS[self.source_id][1],
                        "run_id": candidate.provider_run_id, "lead": lead, "member": None,
                        "fields": sorted(FIELDS), "bounds": ECMWF_ENSEMBLE_BOUNDS, "index_url": index_url,
                        "ranges": [[row["_offset"], row["_offset"] + row["_length"] - 1] for row in records]},
                    "discovery_receipt": candidate.detail["discovery_receipt"], "transport_receipts": transport.receipts,
                    "licence": "CC BY 4.0", "attribution": "ECMWF", "operational": False}
                entry = ECMWFQueryEntry(self.source_id, candidate.run_time, selected_time, completion,
                    completion + timedelta(seconds=TTL_SECONDS), hashlib.sha256(payload).hexdigest(), provenance, payload)
                if entry.backing_bytes > MAX_OUTPUT_BYTES:
                    raise ECMWFQueryUnavailable("ECMWF normalized cache entry exceeds bound")
                # Wall time can jump during decoding. The original final-byte
                # monotonic deadline must cap admission independently of UTC.
                remaining = min(TTL_SECONDS - max(0.0, (self.now() - completion).total_seconds()),
                    transport.completed_monotonic + TTL_SECONDS - self.clock())
                if remaining <= 0:
                    raise ECMWFQueryUnavailable("ECMWF response expired during normalization")
                with self._lock:
                    self._entries[key] = (self.clock() + remaining, entry)
                    self._entries.move_to_end(key)
                    while len(self._entries) > MAX_ENTRIES or sum(value[1].backing_bytes for value in self._entries.values()) > MAX_CACHE_BYTES:
                        self._entries.popitem(last=False)
                future.set_result(entry)
                return entry
            finally:
                if self.client is None:
                    transport.client.close()
        except BaseException as error:
            failure = (ECMWFQueryUnavailable(f"ECMWF exact native query failed: {type(error).__name__}")
                       if isinstance(error, Exception) and not isinstance(error, ECMWFQueryUnavailable) else error)
            future.set_exception(failure)
            if failure is error:
                raise
            raise failure from error
        finally:
            with self._lock:
                self._inflight.pop(flight_key, None)

    def _decode(self, request):
        destination = Path(request["directory"]) / "result.zip"
        run_bounded_process(command=[sys.executable, "-m", "weather_api.ecmwf_query_worker", "{output}"],
            stdin=json.dumps(request).encode(), destination=destination, limits=DECODE_LIMITS, timeout_seconds=120)
        with zipfile.ZipFile(destination) as bundle:
            if sorted(bundle.namelist()) != ["manifest.json", "surface.zarr.zip"] or sum(i.file_size for i in bundle.infolist()) > MAX_OUTPUT_BYTES:
                raise ECMWFQueryUnavailable("ECMWF decoder bundle violates output bound")
            return json.loads(bundle.read("manifest.json")), bundle.read("surface.zarr.zip")

    def point_fields(self, latitude, longitude, selected_time, *, run_id=None, refresh=False):
        from .store import LiveStore, live_point_fields
        bounds = ECMWF_ENSEMBLE_BOUNDS
        if not bounds["south"] <= latitude <= bounds["north"] or not bounds["west"] <= longitude <= bounds["east"]:
            raise ECMWFQueryUnavailable("ECMWF point is outside the bounded native query domain")
        entry = self.query(selected_time, run_id=run_id, refresh=refresh)
        import xarray
        import zarr
        with tempfile.TemporaryDirectory(prefix="ecmwf-point-") as directory:
            path = Path(directory) / "surface.zip"; path.write_bytes(entry.payload)
            store = zarr.storage.ZipStore(str(path), mode="r")
            dataset = xarray.open_zarr(store, consolidated=False)
            provenance = dict(entry.provenance)
            provenance["original_units"] = {
                str(name): str(variable.attrs.get("original_units", variable.attrs.get("units", "")))
                for name, variable in dataset.data_vars.items()
            }
            sampler = LiveStore.__new__(LiveStore); sampler.skipped = []; sampler.unmodelled = []
            artifact = SimpleNamespace(source_id=self.source_id, logical_name="surface", revision_id=f"demand:{entry.content_digest}",
                provenance=provenance, run_time=entry.run_time, retrieved_at=entry.fetched_at, native_crs="EPSG:4326")
            try:
                samples = sampler._sample_dataset(dataset, artifact, latitude, longitude, entry.valid_time)
            finally:
                dataset.close(); store.close()
        class Samples:
            skipped, unmodelled = sampler.skipped, sampler.unmodelled
            def sample_point(self, *args, **kwargs): return samples
        return live_point_fields(Samples(), latitude, longitude, entry.valid_time)
