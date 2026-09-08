"""Experimental exact-time demand for the five verified GEPS reductions.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
This source-local experiment does not register or activate GEPS. The 527 other
advertised reductions and native members/levels remain unresolved. WCS time
parameters establish requested identity, never independently verified run identity.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from ingest.adapters.eccc_geomet import GeoMetClient, TimeExtent, _service_exception
from ingest.adapters.eccc_geomet_ensemble import MAX_WCS_TIFF_BYTES, REPS_EVIDENCE_BOX, coverage_url
from ingest.adapters.eccc_geomet_reductions import GEPS_SCALESIZE, SELECTED_REDUCTIONS, fetch_geps_reductions
from ingest.isolation import ProcessAllocationLimits, run_bounded_process

GEPS_COVERAGES = tuple(item.coverage_id for item in SELECTED_REDUCTIONS)
GEPS_CAPABILITY_BYTES = 2 * 1024**2
GEPS_OUTPUT_BYTES = 4 * 1024**2
GEPS_WIRE_BYTES = 5 * (GEPS_CAPABILITY_BYTES + MAX_WCS_TIFF_BYTES)
GEPS_CHILD_LIMITS = ProcessAllocationLimits(2 * 1024**3, GEPS_OUTPUT_BYTES, 8192, 4096, 65536)


@dataclass(frozen=True)
class GEPSRequestKey:
    reference_time: datetime
    valid_time: datetime
    coverages: tuple[str, ...] = GEPS_COVERAGES
    bounds: tuple[tuple[str, float], ...] = tuple(sorted(REPS_EVIDENCE_BOX.items()))

    def validate(self) -> None:
        for moment in (self.reference_time, self.valid_time):
            if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
                raise ValueError("GEPS times must be aware UTC")
            if moment.minute or moment.second or moment.microsecond:
                raise ValueError("GEPS adapter run and lead identity requires whole-hour times")
        if self.valid_time < self.reference_time:
            raise ValueError("GEPS valid time precedes reference time")
        if self.coverages != GEPS_COVERAGES:
            raise ValueError("GEPS requires all five supported provider reductions")
        if self.bounds != tuple(sorted(REPS_EVIDENCE_BOX.items())):
            raise ValueError("GEPS query supports only the verified bounded output geometry")

    def as_dict(self) -> dict:
        self.validate()
        return {"reference_time": self.reference_time.astimezone(UTC).isoformat(),
                "valid_time": self.valid_time.astimezone(UTC).isoformat()}

    @classmethod
    def from_dict(cls, value: dict) -> GEPSRequestKey:
        if set(value) != {"reference_time", "valid_time"}:
            raise ValueError("unexpected GEPS request keys")
        key = cls(datetime.fromisoformat(value["reference_time"]), datetime.fromisoformat(value["valid_time"]))
        key.validate()
        return key


def exact_advertised(extent: TimeExtent | None, moment: datetime) -> bool:
    """Check cadence arithmetically without materializing an unbounded axis."""
    if extent is None or not extent.contains(moment):
        return False
    if extent.values:
        return moment in extent.values
    if extent.period is None:
        return moment in (extent.start, extent.end)
    return extent.period.total_seconds() > 0 and (moment - extent.start) % extent.period == extent.period * 0


class _ReceiptClient:
    """Ten bounded public requests; adapter and capabilities share one budget."""
    def __init__(self, client):
        self.client = client
        self.receipts = []
        self.retrieved_at = datetime.now(UTC)

    def get_bytes_with_headers(self, url, *, max_bytes):
        query = {key.lower(): value for key, value in parse_qs(urlsplit(url).query).items()}
        capabilities = query.get("request") == ["GetCapabilities"]
        ceiling = GEPS_CAPABILITY_BYTES if capabilities else MAX_WCS_TIFF_BYTES
        if len(self.receipts) >= 10:
            raise ValueError("GEPS request count exceeded")
        payload, receipt = self.client.get_bytes_with_receipt(url, max_bytes=min(max_bytes, ceiling))
        problem = _service_exception(payload[:4096].decode("utf-8", "replace"))
        if problem:
            raise ValueError(f"GEPS GeoMet service exception: {problem}")
        if not payload or len(payload) > ceiling:
            raise ValueError("GEPS empty or oversized response")
        if receipt.get("byte_size") != len(payload) or receipt.get("sha256") != hashlib.sha256(payload).hexdigest():
            raise ValueError("GEPS transport receipt does not identify response")
        self.receipts.append({**receipt, "kind": "capabilities" if capabilities else "coverage"})
        self.retrieved_at = datetime.fromisoformat(receipt["completed_at"])
        return payload, {**receipt["response_headers"], "x-astraeus-original-retrieved-at": receipt["completed_at"]}

    get_bytes = get_bytes_with_headers

    def download(self, url, destination, *, max_bytes):
        payload, _ = self.get_bytes_with_headers(url, max_bytes=max_bytes)
        destination.write_bytes(payload)
        return len(payload)


@dataclass(frozen=True)
class GEPSQueryEntry:
    key: GEPSRequestKey
    payload: bytes
    provenance: dict

    def validate(self) -> None:
        self.key.validate()
        p = self.provenance
        if not 0 < len(self.payload) <= GEPS_OUTPUT_BYTES or p.get("sha256") != hashlib.sha256(self.payload).hexdigest():
            raise ValueError("GEPS artifact bytes or checksum invalid")
        if p.get("source_id") != "eccc-geps" or p.get("operational") is not False or p.get("computed_here") is not False or p.get("members_published") is not False:
            raise ValueError("GEPS provider reduction identity invalid")
        if p.get("run_identity_status") != "requested_unverified" or p.get("quality", {}).get("status") != "unknown":
            raise ValueError("GEPS experimental identity or QC was promoted")
        if datetime.fromisoformat(p["run_time"]) != self.key.reference_time or datetime.fromisoformat(p["valid_time"]) != self.key.valid_time:
            raise ValueError("GEPS artifact time differs from request")
        for reduction, receipt in zip(SELECTED_REDUCTIONS, p["reductions"], strict=True):
            expected = {"coverage_id": reduction.coverage_id, "variable": reduction.variable,
                "field": reduction.field, "provider_statistic": reduction.statistic,
                "quantile": reduction.quantile, "threshold": reduction.threshold}
            if any(receipt.get(name) != value for name, value in expected.items()):
                raise ValueError("GEPS reduction receipt changed provider statistic identity")
        if tuple(item["coverage_id"] for item in p["reductions"]) != GEPS_COVERAGES:
            raise ValueError("GEPS reductions were thinned or substituted")
        if p["field_accounting"].get("whole_family_complete") is not False:
            raise ValueError("GEPS whole-family completion is not supported")
        receipts = p.get("transport_receipts", [])
        if len(receipts) != 10 or sum(item["byte_size"] for item in receipts) > GEPS_WIRE_BYTES:
            raise ValueError("GEPS transport accounting invalid")
        for kind in ("capabilities", "coverage"):
            selected = [item for item in receipts if item["kind"] == kind]
            names = []
            for item in selected:
                parsed = urlsplit(item["url"])
                if (parsed.scheme, parsed.netloc, parsed.path) != ("https", "geo.weather.gc.ca", "/geomet/"):
                    raise ValueError("GEPS receipt is not from the approved public GeoMet origin")
                ceiling = GEPS_CAPABILITY_BYTES if kind == "capabilities" else MAX_WCS_TIFF_BYTES
                if type(item.get("byte_size")) is not int or not 0 < item["byte_size"] <= ceiling or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256"))):
                    raise ValueError("GEPS receipt byte size or digest invalid")
                completed = datetime.fromisoformat(item["completed_at"])
                if completed.utcoffset() is None:
                    raise ValueError("GEPS receipt completion must be offset-aware")
                query = {key.lower(): value for key, value in parse_qs(parsed.query).items()}
                names.append(query["layers" if kind == "capabilities" else "coverageid"][0])
                if kind == "coverage" and (datetime.fromisoformat(query["time"][0]) != self.key.valid_time or datetime.fromisoformat(query["dim_reference_time"][0]) != self.key.reference_time):
                    raise ValueError("GEPS coverage receipt time differs from request")
                if kind == "coverage":
                    expected_url = coverage_url(names[-1], dict(self.key.bounds),
                        scalesize=GEPS_SCALESIZE, valid_time=self.key.valid_time,
                        reference_time=self.key.reference_time)
                    if parse_qs(parsed.query) != parse_qs(urlsplit(expected_url).query):
                        raise ValueError("GEPS coverage request changed bounded geometry or format")
                    reduction_receipt = p["reductions"][len(names) - 1]
                    if reduction_receipt["sha256"] != item["sha256"] or reduction_receipt["bytes"] != item["byte_size"]:
                        raise ValueError("GEPS reduction and transport receipts disagree")
            if tuple(names) != GEPS_COVERAGES:
                raise ValueError("GEPS receipts do not cover exact selected reductions")


class GEPSSelectedLoader:
    def __init__(self, workspace: Path, client):
        self.workspace, self.client = workspace, client

    def __call__(self, key: GEPSRequestKey) -> GEPSQueryEntry:
        key.validate()
        http = _ReceiptClient(self.client)
        with tempfile.TemporaryDirectory(prefix="geps-selected-", dir=self.workspace) as directory:
            scratch = Path(directory)
            capabilities = GeoMetClient(client=http, scratch_dir=scratch)
            for coverage in key.coverages:
                layer = capabilities.capabilities(coverage)
                if not exact_advertised(layer.time, key.valid_time) or not exact_advertised(layer.reference_time, key.reference_time):
                    raise ValueError(f"{coverage}: exact requested valid/reference time is not advertised")
            artifact = fetch_geps_reductions(valid_time=key.valid_time, reference_time=key.reference_time,
                workdir=scratch, bounds=dict(key.bounds), client=http)
            provenance = {**artifact.provenance, "run_identity_status": "requested_unverified",
                "transport_receipts": http.receipts,
                "residual": "527 other advertised reductions deferred; no GEPS.MEM coverages; native vertical and temporal windows not established by this adapter"}
            entry = GEPSQueryEntry(key, artifact.payload_path.read_bytes(), provenance)
            entry.validate()
            validate_normalized_payload(entry, scratch)
            return entry


def validate_normalized_payload(entry: GEPSQueryEntry, workspace: Path) -> None:
    import numpy as np
    import xarray as xr
    import zarr
    with tempfile.TemporaryDirectory(prefix="geps-validate-", dir=workspace) as directory:
        path = Path(directory) / "artifact.zip"
        path.write_bytes(entry.payload)
        with zarr.storage.ZipStore(str(path), mode="r") as store:
            with xr.open_zarr(store, consolidated=False) as dataset:
                if set(dataset.data_vars) != {r.variable for r in SELECTED_REDUCTIONS} or dict(dataset.sizes) != {"valid_time": 1, "latitude": 11, "longitude": 24}:
                    raise ValueError("GEPS normalized fields or geometry invalid")
                expected_time = np.datetime64(entry.key.valid_time.astimezone(UTC).replace(tzinfo=None), "ns")
                if tuple(dataset.valid_time.values) != (expected_time,):
                    raise ValueError("GEPS normalized time differs from request")
                area = dict(entry.key.bounds)
                expected_lon = area["west"] + (np.arange(24) + .5) * ((area["east"] - area["west"]) / 24)
                expected_lat = area["north"] - (np.arange(11) + .5) * ((area["north"] - area["south"]) / 11)
                if not np.allclose(dataset.longitude.values, expected_lon) or not np.allclose(dataset.latitude.values, expected_lat):
                    raise ValueError("GEPS normalized geometry differs from request")
                for reduction in SELECTED_REDUCTIONS:
                    field = dataset[reduction.variable]
                    wanted = {"units": reduction.units, "field": reduction.field,
                        "provider_statistic": reduction.statistic, "quantile": reduction.quantile,
                        "threshold": reduction.threshold, "computed_here": False}
                    if any(field.attrs.get(k) != v for k, v in wanted.items()) or field.dims != ("valid_time", "latitude", "longitude"):
                        raise ValueError("GEPS normalized provider statistic identity invalid")
                    if np.isinf(field.values).any() or not np.isfinite(field.values).any():
                        raise ValueError("GEPS selected reduction has no usable finite values")


class GEPSBoundedLoader:
    def __init__(self, workspace: Path, runner=run_bounded_process):
        self.workspace, self.runner = workspace, runner

    def __call__(self, key: GEPSRequestKey) -> GEPSQueryEntry:
        import sys
        import zipfile
        key.validate()
        with tempfile.TemporaryDirectory(prefix="geps-parent-", dir=self.workspace) as directory:
            output = Path(directory) / "result.zip"
            self.runner(command=[sys.executable, "-m", "weather_api.geps_query_worker", "{output}"],
                stdin=json.dumps(key.as_dict()).encode(), destination=output,
                limits=GEPS_CHILD_LIMITS, timeout_seconds=180)
            with zipfile.ZipFile(output) as bundle:
                items = bundle.infolist()
                if len(items) != 2 or {i.filename for i in items} != {"result.json", "artifact.zip"} or any(i.flag_bits & 1 or i.compress_type != zipfile.ZIP_STORED for i in items) or sum(i.file_size for i in items) > GEPS_OUTPUT_BYTES:
                    raise ValueError("GEPS child bundle violates bounded shape")
                metadata = json.loads(bundle.read("result.json"))
                if GEPSRequestKey.from_dict(metadata["request"]) != key:
                    raise ValueError("GEPS child changed request identity")
                entry = GEPSQueryEntry(key, bundle.read("artifact.zip"), metadata["provenance"])
            entry.validate()
            validate_normalized_payload(entry, Path(directory))
            return entry


class GEPSQueryService:
    """One admitted operation, shared concurrent outcome and bounded caches."""
    def __init__(self, loader: Callable, *, clock=time.monotonic):
        self.loader, self.clock = loader, clock
        self.lock = threading.Lock()
        self.cached = None
        self.failure = None
        self.inflight = None

    def query(self, key: GEPSRequestKey, *, refresh=False) -> GEPSQueryEntry:
        key.validate()
        with self.lock:
            now = self.clock()
            if self.cached is not None:
                deadline, cached = self.cached
                if not refresh and deadline > now and cached.key == key:
                    return copy.deepcopy(cached)
            if self.inflight is not None:
                active_key, future = self.inflight
                if active_key != key:
                    raise RuntimeError("GEPS query capacity is occupied by another request")
                owner = False
            else:
                if self.failure is not None:
                    deadline, failed_key, reason = self.failure
                    if deadline > now and failed_key == key:
                        raise RuntimeError(reason)
                future = Future()
                self.inflight = (key, future)
                owner = True
        if not owner:
            return copy.deepcopy(future.result())
        try:
            entry = self.loader(key)
            if entry.key != key:
                raise ValueError("GEPS loader changed request identity")
            entry.validate()
            if len(entry.payload) + len(json.dumps(entry.provenance).encode()) > GEPS_OUTPUT_BYTES:
                raise ValueError("GEPS cache exceeds byte ceiling")
            retained = copy.deepcopy(entry)
            with self.lock:
                self.cached = (self.clock() + 300, retained)
                self.failure = None
            future.set_result(retained)
            return copy.deepcopy(retained)
        except BaseException as error:
            with self.lock:
                self.failure = (self.clock() + 30, key, str(error)[:4096])
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.inflight = None
