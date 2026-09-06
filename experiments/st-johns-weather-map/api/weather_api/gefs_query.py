"""Bounded cache for one selected GEFS member-family lead."""
from __future__ import annotations
import json, math, os, re, tempfile, threading, time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES, NOAA_GEFS_S3_BASE, _gefs_keys_by_upstream, gefs_member_identifiers, gefs_member_url
from ingest.adapters.noaa_s3 import NOAAGEFSEnsembleAdapter
from ingest.contract import FetchWindow, ResourceBounds, RunCandidate
from ingest.registry import get_config
GEFS_FIELDS=("temperature_2m","dew_point_2m","relative_humidity_2m","wind_u_10m","wind_v_10m","mean_sea_level_pressure","total_cloud_mean_6h")
GEFS_MEMBER_COUNT=31; GEFS_IDX_BYTES=1024*1024; GEFS_CACHE_MAX_BYTES=704*1024**2
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
    run_id:str; run_time:datetime; lead:int; product_set:str; members:tuple[str,...]; fields:tuple[str,...]; bounds:tuple[tuple[str,float],...]; endpoint:str=NOAA_GEFS_S3_BASE
    def validate(self):
        if self.run_time.tzinfo is None or self.run_time.utcoffset()!=timedelta(0): raise ValueError("GEFS run time must be aware UTC")
        if self.run_id!=self.run_time.strftime("%Y%m%d%H"): raise ValueError("GEFS run identity must match run time")
        if self.endpoint.rstrip("/")!=NOAA_GEFS_S3_BASE: raise ValueError("GEFS endpoint is not the approved NOAA origin")
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
        receipts=self.provenance.get("transport_receipts")
        if not isinstance(receipts,list): raise ValueError("GEFS transport receipts are required")
        upstream_by_field={field:upstream for upstream,field in _gefs_keys_by_upstream("noaa-gefs").items()}
        expected_ranges={(member,upstream_by_field[field]) for member in self.members_present for field in GEFS_FIELDS if field=="temperature_2m" or field not in self.optional_absences.get(member,())}
        seen_idx=set(); seen_ranges=set()
        for receipt in receipts:
            if not isinstance(receipt,dict) or receipt.get("member") not in self.key.members: raise ValueError("GEFS receipt has invalid member identity")
            member=str(receipt["member"]); stem=gefs_member_url(date_str=self.key.run_time.strftime("%Y%m%d"),cycle=self.key.run_time.strftime("%H"),lead=self.key.lead,member=member)
            if receipt.get("kind")=="index":
                if receipt.get("url")!=stem+".idx" or receipt.get("http_status")!=200: raise ValueError("GEFS index receipt has invalid request identity")
                if not 0<receipt.get("byte_size",0)<=GEFS_IDX_BYTES: raise ValueError("GEFS index receipt exceeds its byte ceiling")
                seen_idx.add(member)
            elif receipt.get("kind")=="range":
                field=receipt.get("field"); start=receipt.get("range_start"); end=receipt.get("range_end")
                if (member,field) not in expected_ranges or receipt.get("url")!=stem or receipt.get("http_status")!=206 or not isinstance(start,int) or not isinstance(end,int) or end<start: raise ValueError("GEFS range receipt has invalid request identity")
                if receipt.get("effective_url")!=stem: raise ValueError("GEFS range request redirected from its canonical URL")
                header={str(k).lower():str(v) for k,v in receipt.get("request_headers",{}).items()}.get("range")
                if header!=f"bytes={start}-{end}": raise ValueError("GEFS range receipt does not match the requested bytes")
                if receipt.get("byte_size")!=end-start+1 or receipt["byte_size"]>MAX_GEFS_MEMBER_BYTES: raise ValueError("GEFS range receipt byte count is invalid")
                content_range={str(k).lower():str(v) for k,v in receipt.get("response_headers",{}).items()}.get("content-range")
                match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)",content_range or "")
                if match is None or tuple(map(int,match.groups()[:2]))!=(start,end) or (match.group(3)!="*" and int(match.group(3))<=end): raise ValueError("GEFS response Content-Range does not match request")
                seen_ranges.add((member,field))
            else: raise ValueError("GEFS receipt has invalid kind")
            completed=datetime.fromisoformat(str(receipt.get("completed_at")))
            if not isinstance(receipt.get("request_headers"),dict) or not isinstance(receipt.get("response_headers"),dict) or any(not isinstance(k,str) or not isinstance(v,str) for mapping in (receipt["request_headers"],receipt["response_headers"]) for k,v in mapping.items()): raise ValueError("GEFS transport headers must be string mappings")
            if completed.tzinfo is None or completed.utcoffset()!=timedelta(0) or not isinstance(receipt.get("byte_size"),int) or receipt["byte_size"]<=0 or not re.fullmatch(r"[0-9a-f]{64}",str(receipt.get("sha256"))): raise ValueError("GEFS receipt has invalid completion or body identity")
        if seen_idx!=set(self.key.members) or seen_ranges!=expected_ranges or len(receipts)!=len(seen_idx)+len(seen_ranges): raise ValueError("GEFS receipts do not correspond exactly to represented requests")
        if self.fetched_at!=max(datetime.fromisoformat(str(item["completed_at"])) for item in receipts): raise ValueError("GEFS fetched time must equal final transport completion")
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
        if not getattr(adapter, "_capture_transport_receipts", False):
            raise ValueError("GEFS selected demand requires receipt capture before provider I/O")
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

GEFS_CHILD_LIMITS = __import__("ingest.isolation",fromlist=["ProcessAllocationLimits"]).ProcessAllocationLimits(
    address_space_bytes=GEFS_MEMORY_LIMIT_BYTES, output_bytes=GEFS_OUTPUT_ALLOWANCE_BYTES,
    stdin_bytes=64*1024, stdout_bytes=64*1024, stderr_bytes=1024*1024,
)

class GEFSBoundedLoader:
    """Execute provider transport and decode in a limited child; validate one bundle."""
    def __init__(self, workspace: Path, *, runner=None, validator=None):
        from ingest.isolation import run_bounded_process
        self.workspace, self.runner, self.validator = workspace, runner or run_bounded_process, validator or validate_normalized_payload
    def __call__(self,key:GEFSRequestKey)->GEFSQueryEntry:
        import sys, zipfile
        request=json.dumps({"run_id":key.run_id,"run_time":key.run_time.isoformat(),"lead":key.lead,"product_set":key.product_set,"members":key.members,"fields":key.fields,"bounds":key.bounds,"endpoint":key.endpoint},sort_keys=True).encode()
        with tempfile.TemporaryDirectory(prefix="gefs-parent-",dir=self.workspace) as directory:
            bundle_path=Path(directory)/"gefs-result.zip"
            self.runner(command=[sys.executable,"-m","weather_api.gefs_query_worker","{output}"],stdin=request,destination=bundle_path,limits=GEFS_CHILD_LIMITS,timeout_seconds=600)
            with zipfile.ZipFile(bundle_path) as bundle:
                if set(bundle.namelist())!={"result.json","artifacts/noaa_gefs_members.zarr.zip"}: raise ValueError("GEFS child returned unexpected bundle members")
                infos=bundle.infolist()
                if len(infos)!=2 or any(item.flag_bits&1 or item.compress_type!=zipfile.ZIP_STORED or item.file_size!=item.compress_size for item in infos): raise ValueError("GEFS child bundle must contain two unencrypted stored members")
                if sum(item.file_size for item in infos)>GEFS_CHILD_LIMITS.output_bytes: raise ValueError("GEFS child bundle exceeds output allowance")
                if bundle.testzip() is not None: raise ValueError("GEFS child bundle failed CRC validation")
                info=json.loads(bundle.read("result.json")); payload=bundle.read("artifacts/noaa_gefs_members.zarr.zip")
            if not isinstance(info,dict) or not isinstance(info.get("members_present"),list) or not isinstance(info.get("mandatory_failures"),dict) or not isinstance(info.get("optional_absences"),dict) or not isinstance(info.get("cloud_intervals"),dict) or not isinstance(info.get("provenance"),dict): raise ValueError("GEFS child manifest has invalid types")
            if info["run_id"]!=key.run_id or datetime.fromisoformat(info["run_time"])!=key.run_time or int(info["lead"])!=key.lead: raise ValueError("GEFS child returned different run identity")
            if info["provenance"].get("source_id")!="noaa-gefs": raise ValueError("GEFS child returned a different source identity")
            intervals={member:(datetime.fromisoformat(pair[0]),datetime.fromisoformat(pair[1])) for member,pair in info["cloud_intervals"].items()}
            entry=GEFSQueryEntry(key,datetime.fromisoformat(info["valid_time"]),datetime.fromisoformat(info["fetched_at"]),tuple(info["members_present"]),info["mandatory_failures"],{m:tuple(v) for m,v in info["optional_absences"].items()},payload,info["provenance"],intervals)
            self.validator(payload,entry,self.workspace)
            return entry

def validate_normalized_payload(payload:bytes,entry:GEFSQueryEntry,workspace:Path)->None:
    """Open the returned Zarr and verify its native member-field contract."""
    import xarray, zarr
    from registry import fields as catalogue
    with tempfile.TemporaryDirectory(dir=workspace) as directory:
        path=Path(directory)/"gefs.zarr.zip"; path.write_bytes(payload)
        store=zarr.storage.ZipStore(str(path),mode="r")
        try:
            dataset=xarray.open_zarr(store,consolidated=False)
            names=set(dataset.data_vars)
            if "temperature_2m" not in names or names-set(GEFS_FIELDS): raise ValueError("GEFS normalized fields violate the seven-field contract")
            for name in names:
                field=dataset[name]
                if "member" not in field.dims or not {"latitude","longitude"}<=set(field.dims): raise ValueError("GEFS normalized field has invalid dimensions")
                if "valid_time" not in field.coords or tuple(__import__("numpy").asarray(field.coords["valid_time"].values).astype("datetime64[ns]").reshape(-1))!=(__import__("numpy").datetime64(entry.valid_time.replace(tzinfo=None),"ns"),): raise ValueError("GEFS normalized field has invalid native valid time")
                lat=field.coords["latitude"].values; lon=field.coords["longitude"].values
                if lat.size==0 or lon.size==0 or not __import__("numpy").isfinite(lat).all() or not __import__("numpy").isfinite(lon).all(): raise ValueError("GEFS normalized grid coordinates are invalid")
                area=dict(entry.key.bounds)
                if float(lat.min())<area["south"] or float(lat.max())>area["north"] or float(lon.min())<area["west"] or float(lon.max())>area["east"]: raise ValueError("GEFS normalized grid exceeds requested bounds")
                expected=catalogue.resolve(name).field.units
                if field.attrs.get("units")!=expected: raise ValueError("GEFS normalized field has invalid units")
                if members_with_values(field)!=tuple(member for member in entry.members_present if name=="temperature_2m" or name not in entry.optional_absences.get(member,())): raise ValueError("GEFS normalized member masks disagree with manifest")
            members=tuple(str(value) for value in dataset["temperature_2m"].coords["member"].values)
            if members!=entry.members_present: raise ValueError("GEFS normalized member order disagrees with manifest")
            control=dataset["temperature_2m"].coords.get("control")
            if not members or members[0]!="gec00" or control is None or not bool(control.values[0]) or any(bool(value) for value in control.values[1:]): raise ValueError("GEFS normalized control identity is invalid")
            if entry.provenance.get("source_id")!="noaa-gefs" or entry.provenance.get("provider_run_id")!=entry.key.run_id or datetime.fromisoformat(str(entry.provenance.get("run_time")))!=entry.key.run_time or entry.provenance.get("product")!=f"Global Ensemble Forecast System ({entry.key.product_set})" or entry.provenance.get("quality",{}).get("status") not in {"passed","suspect"}: raise ValueError("GEFS normalized provenance or QC is invalid")
        finally:
            store.close()
