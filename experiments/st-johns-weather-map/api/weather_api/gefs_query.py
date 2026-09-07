"""Bounded cache for one selected GEFS member-family lead."""
from __future__ import annotations
import json, math, os, re, tempfile, threading, time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Mapping
from types import SimpleNamespace
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES, NOAA_GEFS_S3_BASE, _gefs_keys_by_upstream, gefs_member_identifiers, gefs_member_url
from ingest.adapters.noaa_s3 import NOAAGEFSEnsembleAdapter
from ingest.contract import FetchWindow, ResourceBounds, RunCandidate
from ingest.registry import get_config
GEFS_FIELDS=("temperature_2m","dew_point_2m","relative_humidity_2m","wind_u_10m","wind_v_10m","mean_sea_level_pressure","total_cloud_mean_6h")
GEFS_MEMBER_COUNT=31; GEFS_IDX_BYTES=1024*1024; GEFS_CACHE_MAX_BYTES=704*1024**2
GEFS_OUTPUT_ALLOWANCE_BYTES=GEFS_CACHE_MAX_BYTES; GEFS_MARGIN_BYTES=128*1024**2
GEFS_PRODUCT_SET="pgrb2ap5"; GEFS_MAX_LEAD=384
GEFS_DISCOVERY_ATTEMPTS = 2
GEFS_DISCOVERY_BYTES = GEFS_DISCOVERY_ATTEMPTS * GEFS_IDX_BYTES
_COORDINATOR = None

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
    return ResourceBounds(GEFS_CACHE_MAX_BYTES,raw+idx+GEFS_DISCOVERY_BYTES+GEFS_OUTPUT_ALLOWANCE_BYTES,GEFS_MARGIN_BYTES,raw+idx+GEFS_DISCOVERY_BYTES)
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
    availability_sha256: str | None = None
    def validate(self):
        if self.run_time.tzinfo is None or self.run_time.utcoffset()!=timedelta(0): raise ValueError("GEFS run time must be aware UTC")
        if self.run_id!=self.run_time.strftime("%Y%m%d%H"): raise ValueError("GEFS run identity must match run time")
        if self.endpoint.rstrip("/")!=NOAA_GEFS_S3_BASE: raise ValueError("GEFS endpoint is not the approved NOAA origin")
        if self.availability_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}",self.availability_sha256): raise ValueError("GEFS availability digest is invalid")
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
                field=receipt.get("field"); start=receipt.get("range_start"); requested_end=receipt.get("range_end")
                if field not in upstream_by_field.values() or receipt.get("url")!=stem or receipt.get("http_status")!=206 or not isinstance(start,int) or (requested_end is not None and (not isinstance(requested_end,int) or requested_end<start)): raise ValueError("GEFS range receipt has invalid request identity")
                if receipt.get("effective_url")!=stem: raise ValueError("GEFS range request redirected from its canonical URL")
                header={str(k).lower():str(v) for k,v in receipt.get("request_headers",{}).items()}.get("range")
                expected_header=f"bytes={start}-" if requested_end is None else f"bytes={start}-{requested_end}"
                if header!=expected_header: raise ValueError("GEFS range receipt does not match the requested bytes")
                content_range={str(k).lower():str(v) for k,v in receipt.get("response_headers",{}).items()}.get("content-range")
                match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)",content_range or "")
                returned_end=-1 if match is None else int(match.group(2))
                if match is None or int(match.group(1))!=start or (requested_end is not None and returned_end!=requested_end) or (match.group(3)!="*" and int(match.group(3))<=returned_end): raise ValueError("GEFS response Content-Range does not match request")
                if receipt.get("byte_size")!=returned_end-start+1 or receipt["byte_size"]>MAX_GEFS_MEMBER_BYTES: raise ValueError("GEFS range receipt byte count is invalid")
                seen_ranges.add((member,field))
            else: raise ValueError("GEFS receipt has invalid kind")
            completed=datetime.fromisoformat(str(receipt.get("completed_at")))
            if not isinstance(receipt.get("request_headers"),dict) or not isinstance(receipt.get("response_headers"),dict) or any(not isinstance(k,str) or not isinstance(v,str) for mapping in (receipt["request_headers"],receipt["response_headers"]) for k,v in mapping.items()): raise ValueError("GEFS transport headers must be string mappings")
            if completed.tzinfo is None or completed.utcoffset()!=timedelta(0) or not isinstance(receipt.get("byte_size"),int) or receipt["byte_size"]<=0 or not re.fullmatch(r"[0-9a-f]{64}",str(receipt.get("sha256"))): raise ValueError("GEFS receipt has invalid completion or body identity")
        failed_indices=set()
        failures=self.provenance.get("transport_failures",[])
        if not isinstance(failures,list): raise ValueError("GEFS transport failures must be a list")
        for failure in failures:
            if not isinstance(failure,dict): raise ValueError("GEFS transport failure is invalid")
            member=failure.get("member")
            stem=gefs_member_url(date_str=self.key.run_time.strftime("%Y%m%d"),cycle=self.key.run_time.strftime("%H"),lead=self.key.lead,member=member) if member in self.key.members else None
            finished=datetime.fromisoformat(str(failure.get("attempt_finished_at")))
            status=failure.get("http_status")
            if failure.get("kind")!="index" or member not in absent or member in failed_indices or member in seen_idx or failure.get("url")!=stem+".idx" or failure.get("body_retained") is not False or not failure.get("error_type") or (status is not None and (type(status) is not int or not 400<=status<=599)) or finished.tzinfo is None or finished.utcoffset()!=timedelta(0):
                raise ValueError("GEFS failed index attempt does not match an absent member")
            failed_indices.add(member)
        if seen_idx|failed_indices!=set(self.key.members) or not expected_ranges<=seen_ranges or any(member not in seen_idx for member,_ in seen_ranges) or len(receipts)!=len(seen_idx)+len(seen_ranges): raise ValueError("GEFS receipts do not correspond exactly to represented requests")
        if self.fetched_at!=max(datetime.fromisoformat(str(item["completed_at"])) for item in receipts): raise ValueError("GEFS fetched time must equal final transport completion")
        if self.key.availability_sha256 is not None:
            receipt = self.provenance.get("availability_receipt")
            url = gefs_member_url(date_str=self.key.run_time.strftime("%Y%m%d"),cycle=self.key.run_time.strftime("%H"),lead=self.key.lead,member="gec00")+".idx"
            validate_availability_receipt(receipt, url, self.key.availability_sha256)
            if next(item for item in receipts if item["kind"]=="index" and item["member"]=="gec00")["sha256"] != self.key.availability_sha256:
                raise ValueError("GEFS selected control index changed since discovery")
class GEFSQueryService:
    def __init__(self,loader:Callable[[GEFSRequestKey],GEFSQueryEntry],*,workspace:Path=Path("/work"),preflight=enforce_platform_bounds,clock=time.monotonic):
        self.loader,self.workspace,self.preflight,self.clock=loader,workspace,preflight,clock; self.lock=threading.Lock(); self.entries=OrderedDict(); self.inflight={}; self.failures={}
    def query(self,key, *, availability_receipt=None, refresh: bool = False):
        key.validate()
        with self.lock:
            now=self.clock(); cached=self.entries.get(key); failure=self.failures.get(key); future=self.inflight.get(key); owner=future is None
            if cached and now<cached[0] and not refresh: return cached[1]
            if failure and now<failure[0]: raise failure[1]
            if owner: future=Future(); self.inflight[key]=future
        if not owner:return future.result()
        try:
            bounds=self.preflight(self.workspace); bounds.validate(); entry=self.loader(key)
            if availability_receipt is not None:
                entry=replace(entry,provenance={**entry.provenance,"availability_receipt":availability_receipt})
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
            store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
            try:
                dataset = xarray.open_zarr(store, consolidated=False)
                temperature = dataset["temperature_2m"]
                present = members_with_values(temperature)
                omitted = tuple(str(value) for value in temperature.coords["member"].values) != present
                if omitted:
                    dataset=dataset.sel(member=list(present)).load()
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
            provenance=artifact.provenance
            if omitted:
                from ingest.grib import write_zarr
                # The closed input is fully materialized above. Remove it
                # before writing so the one-output disk allowance also holds
                # for a partial family; never retain an original payload copy.
                artifact.payload_path.unlink()
                write_zarr(dataset, artifact.payload_path)
                provenance={**provenance,"members":{**provenance.get("members",{}),"present":list(present),"missing":list(mandatory)}}
            dataset.close()
            del dataset, temperature
            cloud = None
            payload = artifact.payload_path.read_bytes()
            receipts = tuple(artifact.provenance.get("transport_receipts", ()))
            if not receipts:
                raise ValueError("GEFS selected loader requires final-byte transport receipts")
            fetched_at = max(datetime.fromisoformat(str(item["completed_at"])) for item in receipts)
            return GEFSQueryEntry(key, valid_time, fetched_at, present, mandatory, optional,
                                  payload, provenance, intervals)

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
            if not members or control is None or tuple(bool(value) for value in control.values) != tuple(member == "gec00" for member in members): raise ValueError("GEFS normalized control identity is invalid")
            if entry.provenance.get("source_id")!="noaa-gefs" or entry.provenance.get("provider_run_id")!=entry.key.run_id or datetime.fromisoformat(str(entry.provenance.get("run_time")))!=entry.key.run_time or entry.provenance.get("product")!=f"Global Ensemble Forecast System ({entry.key.product_set})" or entry.provenance.get("quality",{}).get("status") not in {"passed","suspect"}: raise ValueError("GEFS normalized provenance or QC is invalid")
        finally:
            store.close()


def validate_availability_receipt(receipt, url: str, digest: str):
    if not isinstance(receipt,dict) or receipt.get("url")!=url or receipt.get("effective_url")!=url or receipt.get("http_status")!=200 or receipt.get("sha256")!=digest:
        raise ValueError("GEFS availability receipt has invalid transport identity")
    if type(receipt.get("byte_size")) is not int or not 0<receipt["byte_size"]<=GEFS_IDX_BYTES:
        raise ValueError("GEFS availability receipt exceeds the byte bound")
    for name in ("request_headers","response_headers"):
        headers=receipt.get(name)
        if not isinstance(headers,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in headers.items()):
            raise ValueError("GEFS availability receipt headers are invalid")
    completed=datetime.fromisoformat(str(receipt.get("completed_at")))
    if completed.tzinfo is None or completed.utcoffset()!=timedelta(0):
        raise ValueError("GEFS availability completion must be aware UTC")


def fetch_discovery_index(url: str):
    """One bounded GET, no redirect or retry hidden inside the request count."""
    import hashlib
    import httpx
    try:
        with httpx.Client(timeout=30, follow_redirects=False, headers={"Accept-Encoding": "identity"}) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200 or str(response.url) != url:
                    raise ValueError("GEFS discovery did not return the canonical index")
                size = response.headers.get("content-length")
                if size is not None and (not size.isdigit() or int(size) > GEFS_IDX_BYTES):
                    raise ValueError("GEFS discovery content length exceeds its bound")
                body = bytearray()
                for chunk in response.iter_raw(64*1024):
                    if len(body)+len(chunk) > GEFS_IDX_BYTES:
                        raise ValueError("GEFS discovery index exceeds its bound")
                    body.extend(chunk)
                completed = datetime.now(UTC)
                return bytes(body), {"url": url, "effective_url":str(response.url), "http_status": 200,
                    "request_headers": dict(response.request.headers),
                    "response_headers": dict(response.headers),
                    "completed_at": completed.isoformat(), "byte_size": len(body),
                    "sha256": hashlib.sha256(body).hexdigest()}
    except httpx.HTTPError as error:
        raise OSError("GEFS discovery transport failed") from error


class GEFSQueryCoordinator:
    """Resolve selected time and expose the cached native member family."""
    def __init__(self, service: GEFSQueryService | None = None, *, workspace: Path = Path("/tmp"),
                 now=lambda: datetime.now(UTC), clock=time.monotonic, discover_index=None):
        self.service = service or GEFSQueryService(GEFSBoundedLoader(workspace), workspace=workspace)
        self._now, self._clock = now, clock
        self._discover_index = discover_index or fetch_discovery_index
        self._discovery_lock = threading.RLock()
        self._discovery = None
        self._discovery_failure = None
        self._query_lock = threading.Lock()
        self._query_inflight = None

    def selected_lead_run(self, selected_time: datetime, *, refresh: bool = False) -> RunCandidate:
        """Describe only the control-index-proven run and selected native lead.

        This is deliberately not a run inventory: discovery stops at its first
        success, and a predecessor is a fallback, not a separately selectable
        run. No family payload or other lead is acquired by this operation.
        """
        from copy import deepcopy

        with self._discovery_lock:
            key = self.request_key(selected_time, refresh=refresh)
            receipt = deepcopy(self._discovery[3])
        valid_time = key.run_time + timedelta(hours=key.lead)
        return RunCandidate(key.run_id, key.run_time, urls=[receipt["url"]], detail={
            "date_str": key.run_time.strftime("%Y%m%d"),
            "cycle": key.run_time.strftime("%H"),
            "lead_hours": key.lead,
            "valid_times": (valid_time,),
            "product_set": key.product_set,
            "members_declared": key.members,
            "fields": key.fields,
            "bounds": dict(key.bounds),
            "availability_sha256": key.availability_sha256,
            "availability_receipt": receipt,
            "availability_scope": "selected_lead_control_index_only",
        })

    def request_key(self, selected_time: datetime, *, refresh: bool = False) -> GEFSRequestKey:
        if selected_time.tzinfo is None:
            raise ValueError("GEFS selected time must be aware")
        selected = selected_time.astimezone(UTC)
        available = min(selected, self._now().astimezone(UTC))
        cycle = (available.hour // 6) * 6
        run = available.replace(hour=cycle, minute=0, second=0, microsecond=0)
        lead = int((selected-run).total_seconds() // (3*3600))*3
        identity = (run, lead)
        with self._discovery_lock:
            current = self._clock()
            if self._discovery and self._discovery[0] == identity and current < self._discovery[1] and not refresh:
                return self._discovery[2]
            if self._discovery_failure and self._discovery_failure[0] == identity and current < self._discovery_failure[1]:
                raise ValueError("GEFS control-index discovery is in failure backoff")
            # Reserve the complete operation before even the first control index.
            self.service.preflight(self.service.workspace).validate()
            for offset in range(GEFS_DISCOVERY_ATTEMPTS):
                candidate_run = run-timedelta(hours=6*offset)
                candidate_lead = lead+6*offset
                if not 0 <= candidate_lead <= GEFS_MAX_LEAD:
                    break
                key = GEFSRequestKey(candidate_run.strftime("%Y%m%d%H"), candidate_run,
                    candidate_lead, GEFS_PRODUCT_SET, declared_members(), GEFS_FIELDS,
                    (("east",-46.0),("north",50.5),("south",45.0),("west",-58.0)))
                key.validate()
                url = gefs_member_url(date_str=candidate_run.strftime("%Y%m%d"),
                    cycle=candidate_run.strftime("%H"), lead=candidate_lead, member="gec00")+".idx"
                try:
                    body, receipt = self._discover_index(url)
                    import hashlib
                    from ingest.adapters.noaa_s3 import select_gefs_member_records
                    if not 0 < len(body) <= GEFS_IDX_BYTES or receipt.get("url") != url or receipt.get("byte_size") != len(body) or receipt.get("sha256") != hashlib.sha256(body).hexdigest():
                        raise ValueError("GEFS discovery body identity is invalid")
                    validate_availability_receipt(receipt,url,hashlib.sha256(body).hexdigest())
                    selection = select_gefs_member_records(body.decode("utf-8"))
                    if not any(upstream == "TMP:2 m above ground" for _, upstream, _ in selection.wanted):
                        raise ValueError("GEFS control index lacks mandatory temperature")
                except (OSError, ValueError):
                    continue
                key=replace(key,availability_sha256=receipt["sha256"])
                self._discovery = (identity, self._clock()+600, key, receipt)
                self._discovery_failure = None
                return key
            self._discovery_failure = (identity, self._clock()+60)
            raise ValueError("GEFS has no available eligible control index within bounded discovery")

    def query(self, selected_time: datetime, *, refresh: bool = False) -> GEFSQueryEntry:
        if selected_time.tzinfo is None:
            raise ValueError("GEFS selected time must be aware")
        selection = (selected_time.astimezone(UTC), refresh)
        # Keep one complete acquisition in flight. Same-selection callers share
        # its result; other selections wait without retaining another bundle.
        while True:
            with self._query_lock:
                pending = self._query_inflight
                if pending is None:
                    future = Future()
                    self._query_inflight = (selection, future)
                    break
            if pending[0] == selection:
                return pending[1].result()
            try:
                pending[1].result()
            except Exception:
                pass  # A different selection's failure is not this one's result.
        try:
            with self._discovery_lock:
                previous_discovery = self._discovery
                try:
                    key = self.request_key(selected_time, refresh=refresh)
                    receipt = self._discovery[3] if self._discovery is not None else None
                    result = self.service.query(key, availability_receipt=receipt, refresh=refresh)
                except BaseException:
                    # A new index digest must not hide an unexpired family if
                    # refreshing its payload fails. Keep the original deadline.
                    if refresh and previous_discovery and self._clock() < previous_discovery[1]:
                        self._discovery = previous_discovery
                    raise
            future.set_result(result)
            return result
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._query_lock:
                self._query_inflight = None

    def point_fields(self, latitude: float, longitude: float, selected_time: datetime, *,
                     member: str | None = None, statistic: str | None = None,
                     quantile: float | None = None, threshold: float | None = None,
                     comparison: str | None = None, refresh: bool = False):
        from .store import LiveStore, _ensemble_point_fields
        entry = self.query(selected_time, refresh=refresh)
        with tempfile.TemporaryDirectory(prefix="gefs-demand-read-") as directory:
            path=Path(directory)/"noaa_gefs_members.zarr.zip"; path.write_bytes(entry.payload)
            import xarray, zarr
            zipped=zarr.storage.ZipStore(str(path),mode="r"); dataset=xarray.open_zarr(zipped,consolidated=False)
            sampler=LiveStore.__new__(LiveStore); sampler.skipped=[]; sampler.unmodelled=[]
            try:
                artifact=SimpleNamespace(source_id="noaa-gefs",logical_name="noaa_gefs_members",
                    revision_id=f"demand:{__import__('hashlib').sha256(entry.payload).hexdigest()}",
                    provenance=entry.provenance,run_time=entry.key.run_time,retrieved_at=entry.fetched_at,native_crs="EPSG:4326")
                samples=sampler._sample_dataset(dataset,artifact,latitude,longitude,entry.valid_time,
                                                member=member,statistic=statistic)
            finally:
                dataset.close(); zipped.close()
        if member is not None:
            samples=[sample for sample in samples if sample.member==member]
        fields=_ensemble_point_fields(sampler,samples,valid_time=entry.valid_time,reference=selected_time,
            statistic=statistic,quantile=quantile,threshold=threshold,comparison=comparison,reader_disabled=())
        return fields, None, ["noaa-gefs"]


def gefs_query_coordinator() -> GEFSQueryCoordinator:
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR=GEFSQueryCoordinator()
    return _COORDINATOR
