"""Experimental retained-summary workspace. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
import math
import secrets
import threading
import time
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field, model_validator
from registry.weathernext import BY_NATIVE, surface_key
from .models import StrictModel, Provenance
from .desktop_series import fail
from .forecast_comparison import ComparisonService, source_failure
from .series_budget import reserve, release

PAGE_DEADLINE = 95
SELECTION_TTL = 3600

STATS = ('mean', 'p10', 'p25', 'p50', 'p75', 'p90')
QUANTILES = (('p10',10),('p25',25),('p50',50),('p75',75),('p90',90))
Section = Literal['clouds','temperature','wind','precipitation','solar','pressure_sea']
Product = Literal['default','gridded','station','model','imerg','experimental']
BASES = {
 'clouds': ('total_cloud_cover','low_cloud_cover','medium_cloud_cover','high_cloud_cover'),
 'temperature': ('temperature_2m','dewpoint_temperature_2m'),
 'wind': ('wind_speed_10m','wind_speed_100m','u_component_of_wind_10m','v_component_of_wind_10m','u_component_of_wind_100m','v_component_of_wind_100m'),
 'precipitation': ('total_precipitation_1hr',),
 'solar': ('surface_solar_radiation_downwards_1hr','total_sky_direct_solar_radiation_at_surface_1hr'),
 'pressure_sea': ('mean_sea_level_pressure','sea_surface_temperature'),
}

class WeatherNextSelectionRequest(StrictModel):
    latitude: float = Field(ge=-90,le=90,allow_inf_nan=False)
    longitude: float = Field(ge=-180,le=180,allow_inf_nan=False)
    start: AwareDatetime
    end: AwareDatetime
    run_time: AwareDatetime | None = None
    section: Section = 'clouds'
    product: Product = 'default'

    @model_validator(mode='after')
    def valid_selection(self):
        if self.start >= self.end: raise ValueError('Positive shared range required')
        allowed = {'temperature': ('default','gridded','station'), 'precipitation': ('default','model','imerg','experimental')}
        if self.product not in allowed.get(self.section, ('default',)): raise ValueError('Product does not belong to section')
        if self.run_time and (self.run_time.minute or self.run_time.second or self.run_time.microsecond): raise ValueError('Exact run hour required')
        return self

    def bases(self):
        if self.section == 'temperature' and self.product == 'station': return tuple('station_head_'+b for b in BASES[self.section])
        if self.section == 'precipitation': return ({'imerg':'imerg_tp_1hr','experimental':'experimental_tp_1hr'}.get(self.product,'total_precipitation_1hr'),)
        return BASES[self.section]

class Threshold(StrictModel):
    quantity: str = Field(max_length=100)
    unit: str = Field(max_length=20)
    value: float = Field(allow_inf_nan=False)
    event: Literal['above','below'] = 'above'

class ProbabilityBounds(StrictModel):
    lower: float | None = None
    upper: float | None = None
    basis: str
    approximate: Literal[True] = True


def probability_bounds(values, threshold, event):
    """Strict neighbors deliberately skip all ties, including at zero."""
    available = [(name,rank,values.get(name)) for name,rank in QUANTILES if values.get(name) is not None]
    if not available or any(not math.isfinite(v) for _,_,v in available):
        return ProbabilityBounds(basis='No usable published percentiles')
    if any(a[2]>b[2] for a,b in zip(available,available[1:])):
        return ProbabilityBounds(basis='Non-monotonic published percentiles; estimate withheld')
    lo = next(((n,q) for n,q,v in reversed(available) if v<threshold), ('lower tail',0))
    hi = next(((n,q) for n,q,v in available if v>threshold), ('upper tail',100))
    lower,upper = (100-hi[1],100-lo[1]) if event=='above' else (lo[1],hi[1])
    tied = any(v==threshold for _,_,v in available)
    return ProbabilityBounds(lower=lower,upper=upper,basis=f'Threshold bracketed by {lo[0].upper()} and {hi[0].upper()}; estimate from published percentiles'+('; equal percentiles widen the range' if tied else ''))

class WeatherNextSummary(StrictModel):
    quantity: str
    unit: str
    values: dict[str,float | None]
    state: Literal['available','missing','failed','expired']
    reason: str | None = None
    sampled_latitude: float | None = None
    sampled_longitude: float | None = None
    provenance: Provenance | None = None
    native_fields: list[str]
    grid: str
    original_unit: str
    level: str
    conversion_scale: float
    conversion_offset: float
    interval_start: AwareDatetime | None = None
    interval_end: AwareDatetime | None = None

class WeatherNextSample(StrictModel):
    time: AwareDatetime
    summaries: list[WeatherNextSummary]
    provenance: Provenance | None = None
    expires_at: AwareDatetime | None = None

class WeatherNextPage(StrictModel):
    completed_pages: int = 0
    total_pages: int = 0
    id: str
    selection: WeatherNextSelectionRequest
    run_time: AwareDatetime | None
    run_id: str | None
    native_times: list[AwareDatetime]
    samples: list[WeatherNextSample]
    next_offset: int | None
    expires_at: AwareDatetime
    state: Literal['available','unsupported','failed','credentials_required','missing']
    reason: str | None = None

class WeatherNextEstimates(StrictModel):
    id: str
    threshold: Threshold
    estimates: dict[str,ProbabilityBounds]
    run_time: AwareDatetime | None
    basis: Literal['retained_published_percentiles'] = 'retained_published_percentiles'

@dataclass
class Retained:
    id: str
    selection: WeatherNextSelectionRequest
    service: object
    times: tuple
    expires: float
    expires_at: datetime
    pages: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancelled: threading.Event = field(default_factory=threading.Event)

class WeatherNextWorkspaceService(ComparisonService):
    def __init__(self, service_for=None, axis_for=None, *, utcnow=lambda: datetime.now(UTC), clock=time.monotonic):
        from .source_grid import selected_service
        from .source_times import run_axis
        self.service_for, self.axis_for = service_for or selected_service, axis_for or run_axis
        # Inherit selection coalescing, subscriber cancellation and the bounded
        # executor from the existing comparison service.
        super().__init__(clock=clock,utcnow=utcnow,deadline=PAGE_DEADLINE+45)
        self.jobs = self

    def _initial(self, selection, stop=lambda:False):
        deadline=self.clock()+45
        anchor = selection.run_time+timedelta(hours=1) if selection.run_time else min(selection.start+timedelta(hours=1),self.utcnow())
        try:
            service=self.jobs._bounded(lambda:self.service_for('WeatherNext 3 local',anchor),deadline,stop).result(timeout=max(.001,deadline-self.clock()))
            if selection.run_time and service.config.initialization != selection.run_time: raise ValueError('Requested run unavailable')
            times,_,_=self.jobs._bounded(lambda:self.axis_for(service),deadline,stop).result(timeout=max(.001,deadline-self.clock()))
        except Exception as error:
            state,reason=source_failure(error)
            return WeatherNextPage(id=secrets.token_urlsafe(18),selection=selection,run_time=selection.run_time,run_id=None,native_times=[],samples=[],next_offset=None,expires_at=self.utcnow(),state='credentials_required' if state=='credentials_required' else 'failed',reason=reason)
        key=secrets.token_urlsafe(18)
        entry=Retained(key,selection,service,tuple(t for t in times if selection.start<=t<selection.end),self.clock()+SELECTION_TTL,self.utcnow()+timedelta(seconds=SELECTION_TTL))
        if len(entry.times)>360: fail('query_limit_exceeded','Native run exceeds existing horizon')
        with self.lock:
            for old_id,old in list(self.entries.items()):
                if old.expires<=self.clock(): self.entries.pop(old_id); release(old_id)
            if len(self.entries)>=16 or not reserve(key,4096+len(entry.times)*100,time.monotonic()+SELECTION_TTL): fail('snapshot_capacity_unavailable','Shared finite response budget full',status=503)
            self.entries[key]=entry
        try: return self.page(key,0,stop)
        except Exception:
            self.cancel(key)
            raise

    def get(self,key):
        with self.lock: entry=self.entries.get(key)
        if not entry or entry.cancelled.is_set() or self.clock()>=entry.expires:
            fail('snapshot_expired','WeatherNext selection expired; refresh explicitly',status=410)
        return entry

    def fresh(self,page):
        page=page.model_copy(deep=True)
        for sample in page.samples:
            if sample.expires_at and sample.expires_at<=self.utcnow():
                for summary in sample.summaries:
                    summary.values={s:None for s in STATS}; summary.state='expired'; summary.reason='Source evidence expired'
        return page

    def page(self,key,offset,stop=lambda:False):
        entry=self.get(key)
        if not entry.lock.acquire(timeout=PAGE_DEADLINE): fail('page_busy','Page still loading',status=503)
        try:
            self.get(key)
            if stop(): fail('comparison_cancelled','Selection cancelled',status=409)
            if offset in entry.pages:return self.fresh(entry.pages[offset])
            total_pages=len(entry.times)*len(entry.selection.bases())
            if offset!=len(entry.pages) or offset<0 or (entry.times and offset>=total_pages):fail('invalid_cursor','Invalid page offset')
            samples=[]
            if entry.times:
                quantity_index,time_index=divmod(offset,len(entry.times))
                t=entry.times[time_index]; bases=(entry.selection.bases()[quantity_index],)
                keys=tuple(surface_key(b,s) for b in bases for s in STATS)
                evidence,failures=(),{}
                try:
                    deadline=self.clock()+PAGE_DEADLINE
                    evidence,failures=self.jobs._bounded(lambda:entry.service.read_batch(entry.selection.latitude,entry.selection.longitude,t,fields=keys,run=entry.service.config.run_id,report_failures=True,retention_until=entry.expires_at),deadline,lambda:stop() or entry.cancelled.is_set()).result(timeout=max(.001,deadline-self.clock()))
                except Exception as error:
                    reason='Native acquisition deadline exceeded' if isinstance(error,TimeoutError) else source_failure(error)[1]
                    failures={k:reason for k in keys}
                if stop() or entry.cancelled.is_set():fail('comparison_cancelled','Selection cancelled',status=409)
                by_key={e.key:e for e in evidence}
                summaries=[]
                for b in bases:
                    mapping=BY_NATIVE[b+'_mean']; readings=[by_key.get(surface_key(b,s)) for s in STATS]
                    first=next((r for r in readings if r),None)
                    values={s:float(r.value) if r and isinstance(r.value,(float,int)) and math.isfinite(r.value) else None for s,r in zip(STATS,readings)}
                    failed=any(surface_key(b,s) in failures for s in STATS)
                    summaries.append(WeatherNextSummary(quantity=b,unit=mapping.unit,values=values,
                        state='available' if any(v is not None for v in values.values()) else 'failed' if failed else 'missing',
                        reason='; '.join(dict.fromkeys(failures[surface_key(b,s)] for s in STATS if surface_key(b,s) in failures)) if failed else None,
                        provenance=first.provenance if first else None,
                        sampled_latitude=first.provenance.sampled_latitude if first else None,sampled_longitude=first.provenance.sampled_longitude if first else None,
                        native_fields=[b+'_'+s for s in STATS],grid=mapping.grid,original_unit=mapping.native_unit,level=mapping.level,conversion_scale=mapping.scale,conversion_offset=mapping.offset,interval_start=t-timedelta(hours=1) if b.endswith('1hr') else None,interval_end=t if b.endswith('1hr') else None))
                expiry=min((e.provenance.source_acquisition.expires_at for e in evidence if e.provenance.source_acquisition),default=None)
                samples=[WeatherNextSample(time=t,summaries=summaries,provenance=evidence[0].provenance if evidence else None,expires_at=expiry)]
            page=WeatherNextPage(completed_pages=offset+1,total_pages=total_pages,id=key,selection=entry.selection,run_time=entry.service.config.initialization,run_id=entry.service.config.run_id,native_times=list(entry.times),samples=samples,next_offset=offset+1 if offset+1<total_pages else None,expires_at=entry.expires_at,state='available' if entry.times else 'missing',reason=None if entry.times else 'Pinned run has no native times in the shared range')
            size=len(page.model_dump_json().encode())
            if size>512*1024 or not reserve(key,4096+size+sum(len(p.model_dump_json().encode()) for p in entry.pages.values()),time.monotonic()+max(0,entry.expires-self.clock())):fail('snapshot_capacity_unavailable','Retained page budget reached',status=503)
            entry.pages[offset]=page
            return self.fresh(page)
        finally:entry.lock.release()

    def estimate(self,key,threshold):
        entry=self.get(key)
        estimates={}
        # Completed pages are immutable and published atomically. Snapshot the map
        # without waiting on the page acquisition lock; thresholds never queue
        # behind provider work.
        for page in entry.pages.copy().values():
            for sample in self.fresh(page).samples:
                for summary in sample.summaries:
                    if summary.quantity==threshold.quantity and summary.unit==threshold.unit:
                        estimates[sample.time.isoformat()]=probability_bounds(summary.values,threshold.value,threshold.event)
        return WeatherNextEstimates(id=key,threshold=threshold,estimates=estimates,run_time=entry.service.config.initialization)

    def cancel(self,key):
        with self.lock:entry=self.entries.pop(key,None)
        if entry:entry.cancelled.set();release(key)

@lru_cache(maxsize=1)
def workspace_service():return WeatherNextWorkspaceService()
router=APIRouter()

async def work(request,fn):
    stopped=threading.Event()
    task=asyncio.create_task(asyncio.to_thread(fn,stopped.is_set))
    try:
        while not task.done():
            if await request.is_disconnected():stopped.set()
            await asyncio.wait({task},timeout=.1)
        return await task
    finally:stopped.set()

@router.post('/weathernext/selection',response_model=WeatherNextPage)
async def initial(body:WeatherNextSelectionRequest,request:Request):
    from .store import configured_mode,LIVE_MODE
    if configured_mode()!=LIVE_MODE:fail('unsupported','WeatherNext requires the configured experimental runtime',status=503)
    return await work(request,lambda stop:workspace_service().initial(body,stop))

@router.get('/weathernext/selection/{identity}',response_model=WeatherNextPage)
async def page(identity:str,request:Request,offset:int=0):return await work(request,lambda stop:workspace_service().page(identity,offset,stop))

@router.post('/weathernext/selection/{identity}/threshold',response_model=WeatherNextEstimates)
def estimate(identity:str,body:Threshold):return workspace_service().estimate(identity,body)

@router.delete('/weathernext/selection/{identity}',status_code=204)
def cancel(identity:str):workspace_service().cancel(identity)
