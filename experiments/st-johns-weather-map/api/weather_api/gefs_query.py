"""Bounded cache for one selected GEFS member-family lead."""
from __future__ import annotations
import json, math, os, tempfile, threading, time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES, gefs_member_identifiers
from ingest.adapters.noaa_s3 import NOAAGEFSEnsembleAdapter
from ingest.contract import FetchWindow, ResourceBounds, RunCandidate
from ingest.registry import get_config
GEFS_FIELDS=("temperature_2m","dew_point_2m","relative_humidity_2m","wind_u_10m","wind_v_10m","mean_sea_level_pressure","total_cloud_mean_6h")
GEFS_MEMBER_COUNT=31; GEFS_IDX_BYTES=1024*1024; GEFS_CACHE_MAX_BYTES=1024**3
GEFS_OUTPUT_ALLOWANCE_BYTES=GEFS_CACHE_MAX_BYTES; GEFS_MARGIN_BYTES=128*1024**2
GEFS_PRODUCT_SET="pgrb2ap5"; GEFS_MAX_LEAD=384

def members_with_values(field) -> tuple[str, ...]:
    """Member labels with at least one finite, unmasked native cell."""
    import numpy
    if "member" not in field.dims:
        return ()
    values = numpy.ma.masked_invalid(numpy.asarray(field.values, dtype=float))
    axis = field.get_axis_num("member")
    moved = numpy.moveaxis(values, axis, 0).reshape((field.sizes["member"], -1))
    labels = [str(value) for value in field.coords["member"].values]
    return tuple(label for label, row in zip(labels, moved, strict=True) if row.count() > 0)
GEFS_MEMORY_LIMIT_BYTES=4*1024**3; GEFS_TEMP_LIMIT_BYTES=3*1024**3

def declared_members(): return gefs_member_identifiers(get_config("noaa-gefs").ensemble)
def demand_operation_bounds():
    raw=GEFS_MEMBER_COUNT*len(GEFS_FIELDS)*MAX_GEFS_MEMBER_BYTES; idx=GEFS_MEMBER_COUNT*GEFS_IDX_BYTES
    return ResourceBounds(GEFS_CACHE_MAX_BYTES,raw+idx+GEFS_OUTPUT_ALLOWANCE_BYTES,GEFS_MARGIN_BYTES,raw+idx)
def enforce_platform_bounds(workspace: Path):
    bounds=demand_operation_bounds(); bounds.validate()
    try: memory=int(Path("/sys/fs/cgroup/memory.max").read_text().strip())
    except (OSError,ValueError) as error: raise RuntimeError("GEFS demand requires a finite Linux cgroup memory limit") from error
    if memory!=GEFS_MEMORY_LIMIT_BYTES: raise RuntimeError("GEFS demand requires the measured 4 GiB cgroup limit")
    workspace=workspace.resolve()
    if not workspace.is_dir(): raise RuntimeError("GEFS dedicated workspace is unavailable")
    geometry=os.statvfs(workspace); capacity=geometry.f_blocks*geometry.f_frsize
    if capacity>GEFS_TEMP_LIMIT_BYTES: raise RuntimeError("GEFS demand requires the enforced 3 GiB temporary filesystem")
    if geometry.f_bavail*geometry.f_frsize<bounds.filesystem_bytes+bounds.margin_bytes: raise RuntimeError("GEFS demand temporary capacity is below the complete-operation bound")
    return bounds
@dataclass(frozen=True)
class GEFSRequestKey:
    run_id:str; run_time:datetime; lead:int; product_set:str; members:tuple[str,...]; fields:tuple[str,...]; bounds:tuple[tuple[str,float],...]
    def validate(self):
        if self.run_time.tzinfo is None or self.run_time.utcoffset()!=timedelta(0): raise ValueError("GEFS run time must be aware UTC")
        if self.run_id!=self.run_time.strftime("%Y%m%d%H"): raise ValueError("GEFS run identity must match run time")
        if self.product_set!=GEFS_PRODUCT_SET: raise ValueError("GEFS product set is not declared")
        if self.members!=declared_members(): raise ValueError("GEFS request must preserve all 31 declared member identities")
        if self.fields!=GEFS_FIELDS: raise ValueError("GEFS request must use the seven registered fields")
        if not 0<=self.lead<=GEFS_MAX_LEAD or self.lead%3: raise ValueError("GEFS selected lead must use native three-hour cadence")
        area=dict(self.bounds)
        if self.bounds!=tuple(sorted(self.bounds)) or len(area)!=4 or set(area)!={"west","east","south","north"} or not all(math.isfinite(value) for value in area.values()) or not area["west"]<area["east"] or not area["south"]<area["north"]: raise ValueError("GEFS bounds must name a finite ordered box")
@dataclass(frozen=True)
class GEFSQueryEntry:
    key:GEFSRequestKey; valid_time:datetime; fetched_at:datetime; members_present:tuple[str,...]; mandatory_failures:Mapping[str,str]; optional_absences:Mapping[str,tuple[str,...]]; payload:bytes; provenance:Mapping[str,object]; cloud_intervals:Mapping[str,tuple[datetime,datetime]]
    @property
    def backing_bytes(self): return len(self.payload)+len(json.dumps({"key":self.key,"present":self.members_present,"mandatory":self.mandatory_failures,"optional":self.optional_absences,"cloud_intervals":self.cloud_intervals,"provenance":self.provenance},sort_keys=True,default=str).encode())
    @property
    def complete(self): return self.members_present==self.key.members and not self.mandatory_failures
    def validate(self):
        declared=self.key.members
        if tuple(member for member in declared if member in self.members_present)!=self.members_present or len(set(self.members_present))!=len(self.members_present): raise ValueError("GEFS present members must be a unique declared-order subset")
        absent=set(declared)-set(self.members_present)
        if set(self.mandatory_failures)!=absent: raise ValueError("GEFS mandatory failures must exactly name absent members")
        optional=set(GEFS_FIELDS)-{"temperature_2m"}
        if not set(self.optional_absences)<=set(self.members_present) or any(not set(fields)<=optional for fields in self.optional_absences.values()): raise ValueError("GEFS optional absences must name admitted members and optional fields")
        if self.valid_time!=self.key.run_time+timedelta(hours=self.key.lead): raise ValueError("GEFS valid time must match run and lead")
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset()!=timedelta(0): raise ValueError("GEFS fetch completion must be aware UTC")
        if any(not reason for reason in self.mandatory_failures.values()): raise ValueError("GEFS failure reasons must be nonempty")
        if any(not fields or len(fields)!=len(set(fields)) for fields in self.optional_absences.values()): raise ValueError("GEFS optional absences must be unique and nonempty")
        expected_cloud=set(self.members_present)-{member for member,fields in self.optional_absences.items() if "total_cloud_mean_6h" in fields}
        if set(self.cloud_intervals)!=expected_cloud: raise ValueError("GEFS cloud intervals must exactly match members with cloud records")
        for member,interval in self.cloud_intervals.items():
            if member not in self.members_present or len(interval)!=2 or not interval[0]<interval[1] or interval[1]!=self.valid_time or interval[1]-interval[0]>timedelta(hours=6): raise ValueError("GEFS cloud interval must preserve the native positive window ending at valid time")
            if self.key.lead==3 and interval!=(self.key.run_time,self.valid_time): raise ValueError("GEFS f003 cloud interval must be exactly 0-3 hours")
            if self.key.lead>=6 and interval[1]-interval[0]!=timedelta(hours=6): raise ValueError("GEFS cloud interval at f006 and later must be exactly six hours")
        if self.key.lead==0 and self.cloud_intervals: raise ValueError("GEFS f000 has no declared averaged-cloud interval")
class GEFSQueryService:
    def __init__(self,loader:Callable[[GEFSRequestKey],GEFSQueryEntry],*,workspace:Path=Path("/work"),preflight=enforce_platform_bounds,clock=time.monotonic):
        self.loader,self.workspace,self.preflight,self.clock=loader,workspace,preflight,clock; self.lock=threading.Lock(); self.entries=OrderedDict(); self.inflight={}; self.failures={}
    def query(self,key):
        key.validate()
        with self.lock:
            now=self.clock(); cached=self.entries.get(key); failure=self.failures.get(key); future=self.inflight.get(key); owner=future is None
            if cached and now<cached[0]: return cached[1]
            if failure and now<failure[0]: raise failure[1]
            if owner: future=Future(); self.inflight[key]=future
        if not owner:return future.result()
        try:
            bounds=self.preflight(self.workspace); bounds.validate(); entry=self.loader(key)
            if entry.key!=key: raise ValueError("GEFS loader changed request identity")
            entry.validate()
            if not 0<entry.backing_bytes<=GEFS_CACHE_MAX_BYTES: raise ValueError("GEFS cache entry exceeds finite byte ceiling")
            with self.lock:
                self.entries[key]=(self.clock()+600,entry); self.entries.move_to_end(key); self.failures.pop(key,None)
                while len(self.entries)>1 or sum(item.backing_bytes for _,item in self.entries.values())>GEFS_CACHE_MAX_BYTES:self.entries.popitem(last=False)
            future.set_result(entry); return entry
        except BaseException as error:
            with self.lock:self.failures[key]=(self.clock()+60,error)
            future.set_exception(error); raise
        finally:
            with self.lock:self.inflight.pop(key,None)


class GEFSSelectedLoader:
    """Run the existing bounded member decoder for one canonical run/lead."""

    def __init__(self, adapter: NOAAGEFSEnsembleAdapter, workspace: Path) -> None:
        self.adapter, self.workspace = adapter, workspace

    def __call__(self, key: GEFSRequestKey) -> GEFSQueryEntry:
        import xarray
        import zarr
        valid_time = key.run_time + timedelta(hours=key.lead)
        candidate = RunCandidate(key.run_id, key.run_time, detail={
            "date_str": key.run_time.strftime("%Y%m%d"),
            "cycle": key.run_time.strftime("%H"),
            "lead_hours": key.lead,
        })
        with tempfile.TemporaryDirectory(dir=self.workspace) as directory:
            result = self.adapter.assemble(candidate, FetchWindow(valid_time), Path(directory))
            artifact = result.artifacts[0]
            payload = artifact.payload_path.read_bytes()
            store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
            try:
                dataset = xarray.open_zarr(store, consolidated=False)
                temperature = dataset["temperature_2m"]
                present = members_with_values(temperature)
                mandatory = {member: "temperature_2m unavailable after bounded decode" for member in key.members if member not in present}
                optional: dict[str, tuple[str, ...]] = {}
                for member in present:
                    absent = []
                    for field in GEFS_FIELDS[1:]:
                        if field not in dataset or member not in members_with_values(dataset[field]):
                            absent.append(field)
                    if absent:
                        optional[member] = tuple(absent)
                intervals = {}
                if "total_cloud_mean_6h" in dataset:
                    cloud = dataset["total_cloud_mean_6h"]
                    hours = float(cloud.attrs["averaging_window_hours"])
                    for member in members_with_values(cloud):
                        intervals[member] = (valid_time - timedelta(hours=hours), valid_time)
            finally:
                store.close()
            receipts = tuple(artifact.provenance.get("transport_receipts", ()))
            if not receipts:
                raise ValueError("GEFS selected loader requires final-byte transport receipts")
            fetched_at = max(datetime.fromisoformat(str(item["completed_at"])) for item in receipts)
            return GEFSQueryEntry(key, valid_time, fetched_at, present, mandatory, optional,
                                  payload, artifact.provenance, intervals)
