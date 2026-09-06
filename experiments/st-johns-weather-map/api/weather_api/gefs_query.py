"""Bounded cache for one selected GEFS member-family lead."""
from __future__ import annotations
import json, threading, time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping
from ingest.adapters.noaa_s3 import MAX_GEFS_MEMBER_BYTES, gefs_member_identifiers
from ingest.contract import ResourceBounds
from ingest.registry import get_config
GEFS_FIELDS=("temperature_2m","dew_point_2m","relative_humidity_2m","wind_u_10m","wind_v_10m","mean_sea_level_pressure","total_cloud_mean_6h")
GEFS_MEMBER_COUNT=31; GEFS_IDX_BYTES=1024*1024; GEFS_CACHE_MAX_BYTES=1024**3
GEFS_OUTPUT_ALLOWANCE_BYTES=GEFS_CACHE_MAX_BYTES; GEFS_MARGIN_BYTES=128*1024**2

def declared_members(): return gefs_member_identifiers(get_config("noaa-gefs").ensemble)
def demand_operation_bounds():
    raw=GEFS_MEMBER_COUNT*len(GEFS_FIELDS)*MAX_GEFS_MEMBER_BYTES; idx=GEFS_MEMBER_COUNT*GEFS_IDX_BYTES
    return ResourceBounds(GEFS_CACHE_MAX_BYTES,raw+idx+GEFS_OUTPUT_ALLOWANCE_BYTES,GEFS_MARGIN_BYTES,raw+idx)
@dataclass(frozen=True)
class GEFSRequestKey:
    run_id:str; run_time:datetime; lead:int; product_set:str; members:tuple[str,...]; fields:tuple[str,...]; bounds:tuple[tuple[str,float],...]
    def validate(self):
        if self.members!=declared_members(): raise ValueError("GEFS request must preserve all 31 declared member identities")
        if self.fields!=GEFS_FIELDS: raise ValueError("GEFS request must use the seven registered fields")
        if self.lead<0 or self.lead%3: raise ValueError("GEFS selected lead must use native three-hour cadence")
@dataclass(frozen=True)
class GEFSQueryEntry:
    key:GEFSRequestKey; valid_time:datetime; fetched_at:datetime; members_present:tuple[str,...]; mandatory_failures:Mapping[str,str]; optional_absences:Mapping[str,tuple[str,...]]; payload:bytes; provenance:Mapping[str,object]; cloud_interval_hours:int=6
    @property
    def backing_bytes(self): return len(self.payload)+len(json.dumps(self.provenance,sort_keys=True,default=str).encode())
    @property
    def complete(self): return self.members_present==self.key.members and not self.mandatory_failures
class GEFSQueryService:
    def __init__(self,loader:Callable[[GEFSRequestKey],GEFSQueryEntry],*,preflight=demand_operation_bounds,clock=time.monotonic):
        self.loader,self.preflight,self.clock=loader,preflight,clock; self.lock=threading.Lock(); self.entries=OrderedDict(); self.inflight={}; self.failures={}
    def query(self,key):
        key.validate()
        with self.lock:
            now=self.clock(); cached=self.entries.get(key); failure=self.failures.get(key); future=self.inflight.get(key); owner=future is None
            if cached and now<cached[0]: return cached[1]
            if failure and now<failure[0]: raise failure[1]
            if owner: future=Future(); self.inflight[key]=future
        if not owner:return future.result()
        try:
            bounds=self.preflight(); bounds.validate(); entry=self.loader(key)
            if entry.key!=key or entry.cloud_interval_hours!=6: raise ValueError("GEFS loader changed request identity or native cloud interval")
            if not 0<entry.backing_bytes<=GEFS_CACHE_MAX_BYTES: raise ValueError("GEFS cache entry exceeds finite byte ceiling")
            with self.lock:self.entries[key]=(self.clock()+600,entry); self.failures.pop(key,None)
            future.set_result(entry); return entry
        except BaseException as error:
            with self.lock:self.failures[key]=(self.clock()+60,error)
            future.set_exception(error); raise
        finally:
            with self.lock:self.inflight.pop(key,None)
