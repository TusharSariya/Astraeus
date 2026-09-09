"""Finite resumable IFS source selections; pages never renew the deadline.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass,field
from datetime import UTC,datetime,timedelta
import json
import secrets
import threading
import time
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import AwareDatetime,Field,model_validator
from registry.ifs import MANIFEST,PRODUCTS,field_selection
from .source_contract import ContractModel,SourceTransferReceipt
from .ifs_native import native_service,IFSUnavailable
from .ifs_budget import SelectionBudget,SelectionStopped


class IFSFieldSelection(ContractModel):
    product: str
    field: str
    level: int = 0
    run: str = 'latest'
    times: list[AwareDatetime] = Field(min_length=1,max_length=144)

    @model_validator(mode='after')
    def known(self):
        field_selection(self.product,self.field,self.level)
        if len(set(self.times))!=len(self.times):raise ValueError('duplicate_times')
        return self


class IFSSelection(ContractModel):
    fields: list[IFSFieldSelection] = Field(min_length=1,max_length=8)


class IFSGrid(ContractModel):
    source_id: Literal['ecmwf-ifs'] = 'ecmwf-ifs'
    product: str
    selection_product: str
    run_id: str
    run_time: AwareDatetime
    native_time: AwareDatetime
    field: str
    level: int
    member: str|None
    statistic: str|None = None
    quantile: float|None = None
    threshold: float|None = None
    comparison: str|None = None
    member_counts: list[list[int]]|None = None
    missing_member_bits: list[list[int]]|None = None
    refusal_reasons: list[str] = Field(default_factory=list)
    missing_members: list[str] = Field(default_factory=list)
    method: dict[str,str]|None = None
    units: str
    temporal: str
    interval_start: AwareDatetime
    interval_end: AwareDatetime
    region: tuple[float,float,float,float]
    latitudes: list[float] = Field(min_length=2,max_length=61)
    longitudes: list[float] = Field(min_length=2,max_length=121)
    latitude_edges: list[float] = Field(min_length=3,max_length=62)
    longitude_edges: list[float] = Field(min_length=3,max_length=122)
    values: list[list[float|None]] = Field(max_length=61)
    native_metadata: dict[str,str|int|float]
    retrieved_at: AwareDatetime
    expires_at: AwareDatetime
    digest: str
    control_mapping: dict[str,str]|None = None
    receipt_ids: list[int]
    receipt_manifest: str

    @model_validator(mode='after')
    def shape(self):
        import math
        if self.region!=(-70.,40.,-40.,55.) or self.interval_end!=self.native_time or self.interval_start>self.interval_end:
            raise ValueError('grid_interval_or_region')
        for axis,edges,step in ((self.latitudes,self.latitude_edges,-.25),(self.longitudes,self.longitude_edges,.25)):
            if len(edges)!=len(axis)+1 or not all(math.isfinite(v) for v in axis+edges):raise ValueError('grid_axis')
            if any(abs(b-a-step)>1e-8 for a,b in zip(axis,axis[1:])):raise ValueError('grid_spacing')
            if any(abs(edges[i]-(axis[i-1]+axis[i])/2)>1e-8 for i in range(1,len(axis))):raise ValueError('grid_edges')
        if len(self.values)!=len(self.latitudes) or any(len(r)!=len(self.longitudes) for r in self.values):raise ValueError('grid_shape')
        if any(v is not None and not math.isfinite(v) for r in self.values for v in r):raise ValueError('grid_nonfinite')
        return self


class IFSItem(ContractModel):
    index: int
    product: str
    field: str
    level: int
    run_id: str
    time: AwareDatetime
    member: str
    grid: IFSGrid|None = None
    reason: str|None = None


class IFSPage(ContractModel):
    id: str
    selected_at: AwareDatetime
    expires_at: AwareDatetime
    completed: int
    total: int
    input_bytes: int
    record_acquisitions: int
    items: list[IFSItem]
    next_cursor: int|None
    receipt_manifest: str


class IFSReceipts(ContractModel):
    id: str
    offset: int
    receipts: list[SourceTransferReceipt] = Field(max_length=12)
    next_offset: int|None


@dataclass
class Job:
    id:str
    selected_at:datetime
    budget:SelectionBudget
    tasks:list
    receipts:list=field(default_factory=list)
    receipt_keys:dict=field(default_factory=dict)
    digests: set=field(default_factory=set)
    completed:int=0
    pending:object=None
    lock:threading.Lock=field(default_factory=threading.Lock)
    last_page:IFSPage|None=None
    last_cursor:int|None=None


class IFSSelections:
    def __init__(self,native=None,clock=time.monotonic,now=lambda:datetime.now(UTC)):
        self.native=native or native_service();self.clock,self.now=clock,now
        self.lock=threading.Lock();self.jobs={};self.executor=ThreadPoolExecutor(2,thread_name_prefix='ifs-selection')

    def start(self,selection):
        budget=SelectionBudget(clock=self.clock);now=self.now();tasks=[]
        # Discovery itself consumes the selection's input and lifetime budgets.
        for selected in selection.fields:
            runs=self.native.inventory(selected.product,budget)
            run=next((r for r in runs if selected.run in ('latest',r['id'])),None)
            if run is None:raise IFSUnavailable('run_expired' if selected.run!='latest' else 'product_unpublished')
            for stamp in selected.times:
                hours=(stamp-datetime.fromisoformat(run['run_time'])).total_seconds()/3600
                lead=int(hours) if hours.is_integer() else -2
                for member in PRODUCTS[selected.product]['members'] or ['0']:
                    tasks.append((selected,run,lead,member,stamp))
        if len(tasks)>4096:raise IFSUnavailable('selection_exceeds_4096_records')
        with self.lock:
            for key,job in list(self.jobs.items()):
                if self.clock()>=job.budget.expires:
                    job.budget.cancelled.set();del self.jobs[key]
            if len(self.jobs)>=8:raise IFSUnavailable('selection_capacity')
            job=Job(secrets.token_urlsafe(18),now,budget,tasks);self.jobs[job.id]=job
        return IFSPage(id=job.id,selected_at=now,expires_at=now+timedelta(seconds=900),completed=0,
            total=len(tasks),input_bytes=budget.bytes,record_acquisitions=0,items=[],next_cursor=0,
            receipt_manifest=f'/api/experiments/weather/v0/ifs/selections/{job.id}/receipts')

    def _job(self,id):
        with self.lock:job=self.jobs.get(id)
        if job is None:raise IFSUnavailable('selection_unavailable')
        job.budget.check()
        return job

    def _read(self,job,index):
        selected,run,lead,member,stamp=job.tasks[index]
        item=dict(index=index,product=selected.product,field=selected.field,level=selected.level,run_id=run['id'],time=stamp,member=member)
        try:
            result=self.native.record(selected.product,run,lead,selected.field,selected.level,member,job.budget)
            job.digests.add(result['digest'])
            receipt_ids=[]
            for receipt in [*run['receipts'],*result['receipts']]:
                key=json.dumps(receipt,sort_keys=True)
                if key not in job.receipt_keys:
                    job.receipt_keys[key]=len(job.receipts);job.receipts.append(receipt)
                receipt_ids.append(job.receipt_keys[key])
            grid=IFSGrid(**{k:v for k,v in result.items() if k!='receipts'},receipt_ids=receipt_ids,
                         receipt_manifest=f'/api/experiments/weather/v0/ifs/selections/{job.id}/receipts')
            return IFSItem(**item,grid=grid)
        except Exception as error:
            return IFSItem(**item,reason=str(error) if isinstance(error,(IFSUnavailable,SelectionStopped)) else type(error).__name__)

    def page(self,id,cursor):
        job=self._job(id);deadline=self.clock()+45
        if not job.lock.acquire(timeout=max(.001,deadline-self.clock())):raise IFSUnavailable('page_busy')
        try:
            if job.last_cursor==cursor:
                return job.last_page.model_copy(update={'items':[item.model_copy(update={'grid':None,'reason':'native_evidence_expired'}) if item.grid and item.grid.expires_at<=self.now() else item for item in job.last_page.items]})
            if cursor!=job.completed:raise IFSUnavailable('invalid_cursor')
            items=[]
            while job.completed<len(job.tasks) and len(items)<2:
                job.budget.check()
                if job.pending is None:job.pending=self.executor.submit(self._read,job,job.completed)
                try:item=job.pending.result(timeout=max(.001,deadline-self.clock()))
                except TimeoutError:break
                job.budget.check();items.append(item);job.completed+=1;job.pending=None
                if self.clock()>=deadline:break
            page=IFSPage(id=id,selected_at=job.selected_at,expires_at=job.selected_at+timedelta(seconds=900),
                         completed=job.completed,total=len(job.tasks),input_bytes=job.budget.bytes,record_acquisitions=job.budget.records,
                         items=items,next_cursor=job.completed if job.completed<len(job.tasks) else None,
                         receipt_manifest=f'/api/experiments/weather/v0/ifs/selections/{id}/receipts')
            if len(page.model_dump_json().encode())>512*1024:raise IFSUnavailable('page_bytes_exceeded')
            # A pending page has no stable result yet; the same cursor resumes its Future.
            if items:job.last_page,job.last_cursor=page,cursor
            return page
        finally:job.lock.release()

    def receipts(self,id,offset):
        job=self._job(id)
        with job.lock:
            return IFSReceipts(id=id,offset=offset,receipts=job.receipts[offset:offset+12],
                               next_offset=offset+12 if offset+12<len(job.receipts) else None)

    def loaded_grid(self,id,statistic,member,quantile,threshold,comparison):
        job=self._job(id)
        selected,run,lead,_,stamp=job.tasks[0]
        if any((s.product,s.field,s.level,r['id'],l)!=(selected.product,selected.field,selected.level,run['id'],lead) for s,r,l,m,t in job.tasks):
            raise IFSUnavailable('grid_requires_one_field_level_time')
        grids={}
        for m in PRODUCTS[selected.product]['members'] or ['0']:
            grid=self.native.loaded_record(selected.product,run['run_time'],lead,selected.field,selected.level,m)
            if grid is not None and grid['digest'] in job.digests:grids[m]=grid
        if statistic:
            from .ifs_statistics import summarize
            grid=summarize(grids,selected.product,selected.field,statistic,quantile=quantile,threshold=threshold,comparison=comparison)
        else:
            grid=grids.get(member)
            if grid is None:raise IFSUnavailable('loaded_member_unavailable_or_expired')
        receipt_ids=sorted({job.receipt_keys[json.dumps(r,sort_keys=True)] for g in grids.values() for r in g['receipts'] if json.dumps(r,sort_keys=True) in job.receipt_keys})
        return IFSGrid(**{k:v for k,v in grid.items() if k!='receipts'},receipt_ids=receipt_ids,
                       receipt_manifest=f'/api/experiments/weather/v0/ifs/selections/{id}/receipts')

    def cancel(self,id):
        with self.lock:job=self.jobs.pop(id,None)
        if job:
            job.budget.cancelled.set()
            if job.pending:job.pending.cancel()


router=APIRouter(prefix='/ifs')
_jobs=None

def selection_service():
    global _jobs
    if _jobs is None:_jobs=IFSSelections()
    return _jobs


def respond(action):
    try:return action()
    except (IFSUnavailable,SelectionStopped,ValueError) as error:
        raise HTTPException(status_code=410 if 'expired' in str(error) else 422,detail=str(error)) from None


@router.get('/catalogue')
def catalogue():return MANIFEST


@router.get('/runs/{product}')
def inventory(product:str):
    return respond(lambda:[{k:v for k,v in r.items() if k!='receipts'} for r in native_service().inventory(product,SelectionBudget())])


@router.post('/selections',response_model=IFSPage)
def select(body:IFSSelection):return respond(lambda:selection_service().start(body))


@router.get('/selections/{id}',response_model=IFSPage)
def page(id:str,cursor:int=0):return respond(lambda:selection_service().page(id,cursor))


@router.get('/selections/{id}/receipts',response_model=IFSReceipts)
def receipts(id:str,offset:int=0):
    if offset<0:raise HTTPException(422,'invalid_offset')
    return respond(lambda:selection_service().receipts(id,offset))


@router.delete('/selections/{id}',status_code=204)
def cancel(id:str):selection_service().cancel(id)


@router.get('/selections/{id}/grid',response_model=IFSGrid)
def loaded_grid(id:str,statistic:str|None=None,member:str='0',quantile:float|None=None,threshold:float|None=None,comparison:str|None=None):
    return respond(lambda:selection_service().loaded_grid(id,statistic,member,quantile,threshold,comparison))


class IFSTrackPoint(ContractModel):
    time: AwareDatetime
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)


class IFSTrack(ContractModel):
    storm_id: str
    member: str
    points: list[IFSTrackPoint] = Field(max_length=122)


class IFSTracks(ContractModel):
    product: str
    run_id: str
    run_time: AwareDatetime
    tracks: list[IFSTrack] = Field(max_length=256*51)
    decoded_members: list[str] = Field(max_length=256)
    expires_at: AwareDatetime
    receipts: list[SourceTransferReceipt]


_track_cache={}
_track_lock=threading.Lock()


from contextlib import contextmanager

@contextmanager
def _cancellable_track_lock(budget):
    while not _track_lock.acquire(timeout=.1):budget.check()
    try:
        budget.check()
        yield
    finally:_track_lock.release()


@router.get('/tracks/{product}',response_model=IFSTracks)
def tracks(product:str,run:str='latest'):
    if product not in ('cyclone-control','cyclone-ensemble'):raise HTTPException(422,'unsupported_track_product')
    return respond(lambda:_acquire_tracks(product,run,SelectionBudget()))


def _acquire_tracks(product,run,budget):
    import sys,tempfile
    from pathlib import Path
    from ingest.isolation import run_bounded_process
    from .ecmwf_query import DECODE_LIMITS
    service=native_service();budget.check()
    runs=service.inventory(product,budget)
    selected=next((r for r in runs if run in ('latest',r['id'])),None)
    if selected is None:raise IFSUnavailable('track_product_unpublished_or_expired')
    identity=selected['id']
    with _cancellable_track_lock(budget):
        previous=_track_cache.get(identity)
        if previous and previous.expires_at>datetime.now(UTC):return previous
        transport=service.transport(budget)
        try:
            if len(selected['files'])!=1:raise IFSUnavailable('track_file_identity_ambiguous')
            budget.start_record()
            body=transport.read(next(iter(selected['files'].values())),limit=8*1024**2)
            with tempfile.TemporaryDirectory(prefix='ifs-track-') as directory:
                path=Path(directory)/'track.bufr';path.write_bytes(body);destination=Path(directory)/'tracks.json'
                run_bounded_process(command=[sys.executable,'-m','weather_api.ifs_track_worker','{output}'],
                    stdin=json.dumps({'path':str(path),'run_time':selected['run_time']}).encode(),destination=destination,limits=DECODE_LIMITS,timeout_seconds=120)
                budget.check()
                result=IFSTracks(product=product,run_id=identity,**json.loads(destination.read_bytes()),
                    expires_at=datetime.fromisoformat(transport.receipts[-1]['completed_at'])+timedelta(seconds=600),receipts=transport.receipts)
            if len(result.model_dump_json().encode())>512*1024:raise IFSUnavailable('track_response_bound')
            _track_cache[identity]=result
            while len(_track_cache)>4:del _track_cache[next(iter(_track_cache))]
            return result
        finally:
            if service.client is None:transport.client.close()



@router.get('/transfers/{id}',response_model=IFSReceipts)
def transfers(id:str,offset:int=0):
    if offset<0:raise HTTPException(422,'invalid_offset')
    from .ifs_budget import receipt_page
    def read():
        receipts,next_offset=receipt_page(id,offset)
        return IFSReceipts(id=id,offset=offset,receipts=receipts,next_offset=next_offset)
    return respond(read)


class IFSTrackSelection(ContractModel):
    product: Literal['cyclone-control','cyclone-ensemble']
    run: str = 'latest'


class IFSTrackPage(ContractModel):
    id: str
    expires_at: AwareDatetime
    complete: bool
    result: IFSTracks | None = None
    reason: str | None = None
    bytes_received: int

    @model_validator(mode='after')
    def bounded(self):
        if len(self.model_dump_json().encode())>512*1024:raise ValueError('track_page_bound')
        return self


_track_jobs={}
_track_jobs_lock=threading.Lock()


def track_page(id):
    with _track_jobs_lock:
        job=_track_jobs.get(id)
    if job is None:raise SelectionStopped('selection_expired')
    budget,future,expires=job;budget.check()
    try:
        result=future.result(timeout=min(45,max(.001,budget.expires-budget.clock())))
        budget.check()
        if result.expires_at<=datetime.now(UTC):raise SelectionStopped('native_evidence_expired')
        return IFSTrackPage(id=id,expires_at=expires,complete=True,result=result,bytes_received=budget.bytes)
    except TimeoutError:return IFSTrackPage(id=id,expires_at=expires,complete=False,bytes_received=budget.bytes)
    except Exception as error:
        return IFSTrackPage(id=id,expires_at=expires,complete=True,reason=str(error),bytes_received=budget.bytes)


@router.post('/track-selections',response_model=IFSTrackPage)
def select_tracks(body:IFSTrackSelection):
    def start():
        budget=SelectionBudget();id=secrets.token_urlsafe(18);expires=datetime.now(UTC)+timedelta(seconds=900)
        with _track_jobs_lock:
            for old,(ledger,future,_) in list(_track_jobs.items()):
                if ledger.cancelled.is_set() or ledger.clock()>=ledger.expires:
                    ledger.cancelled.set();future.cancel();del _track_jobs[old]
            if len(_track_jobs)>=8:raise IFSUnavailable('selection_capacity')
            future=selection_service().executor.submit(_acquire_tracks,body.product,body.run,budget)
            _track_jobs[id]=(budget,future,expires)
        return IFSTrackPage(id=id,expires_at=expires,complete=False,bytes_received=budget.bytes)
    return respond(start)


@router.get('/track-selections/{id}',response_model=IFSTrackPage)
def continue_tracks(id:str):return respond(lambda:track_page(id))


@router.delete('/track-selections/{id}',status_code=204)
def cancel_tracks(id:str):
    with _track_jobs_lock:job=_track_jobs.pop(id,None)
    if job:job[0].cancelled.set();job[1].cancel()
