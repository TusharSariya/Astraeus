"""GOV-SPEC-001/004/006: September 9 comparison verification."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import threading
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from weather_api.app import app
from weather_api.forecast_comparison import ComparisonSelection, ComparisonService, ComparisonSource, DEFAULT_SOURCES
from weather_api.source_delivery import NativeFrame, NativePlan
from weather_api.fixtures import point_fields
NOW = datetime(2026,9,9,12,tzinfo=UTC)

def selection(**updates):
    return ComparisonSelection(**dict(latitude=47.5,longitude=-52.7,start=NOW,end=NOW+timedelta(hours=24),**updates))

class Reader:
    product_id='test-native'
    def __init__(self, source, *, cadence=1, failure=None):
        self.source_id,self.cadence,self.failure=source,cadence,failure
        self.calls=[]
        self.fields=['temperature_2m','relative_humidity_2m','total_cloud_opacity','wind_speed_10m']
    def descriptors(self):
        return [SimpleNamespace(field=f,product_id=self.product_id) for f in self.fields]
    def plan_series(self,start,end,*,run='latest'):
        times=tuple(NOW+timedelta(hours=h) for h in range(0,25,self.cadence))
        return NativePlan(tuple(NativeFrame(t,'actual-run',NOW) for t in times if start<=t<end),available_times=times)
    def read_point(self,latitude,longitude,selected,*,run):
        self.calls.append((selected,run))
        if self.failure:raise self.failure
        result=[]
        for key in self.fields:
            value=point_fields(selected)[0][0].model_copy(deep=True)
            value.key=value.field=key
            value.provenance.source_id=self.source_id
            value.provenance.run_time=NOW
            value.provenance.valid_time=selected
            value.value=0 if selected==NOW else 4
            value.provenance.normalized_units='degC' if key=='temperature_2m' else 'percent'
            result.append(value)
        return result

def test_five_models_native_day_progressive_coalesced_fields_and_half_open():
    readers={s:Reader(s,cadence=3 if s=='noaa-gfs' else 1) for s in DEFAULT_SOURCES}
    service=ComparisonService(readers,utcnow=lambda:NOW)
    first=service.initial(selection())
    assert 0 < first.completed_positions <= 12 and sum(len(r.calls) for r in readers.values())==first.completed_positions
    assert first.total_positions==104 and first.expires_at==NOW+timedelta(minutes=15)
    pages=[first]
    while pages[-1].next_cursor:pages.append(service.continuation(pages[-1].next_cursor))
    assert sum(len(r.calls) for r in readers.values())==104
    assert all(len(r.calls)==len(set(r.calls)) for r in readers.values())
    assert len(readers['noaa-gfs'].calls)==8
    assert all(run=='actual-run' and t<NOW+timedelta(hours=24) for r in readers.values() for t,run in r.calls)
    assert all(len(p.model_dump_json().encode())<=512*1024 and p.expires_at==first.expires_at for p in pages)
    assert any(c.reason for c in first.curves if c.group=='precipitation')

def test_concurrent_cursor_coalesces_fixed_page_and_expiry():
    clock=[0.];reader=Reader('eccc-hrdps')
    service=ComparisonService({reader.source_id:reader},utcnow=lambda:NOW,clock=lambda:clock[0])
    first=service.initial(selection(sources=[ComparisonSource(source_id=reader.source_id)]))
    with ThreadPoolExecutor(2) as pool:a,b=list(pool.map(service.continuation,[first.next_cursor]*2))
    assert a==b and len(reader.calls)==24
    a.curves[0].samples.clear()
    assert service.continuation(first.next_cursor).curves[0].samples
    clock[0]=900
    with pytest.raises(HTTPException) as caught:service.continuation(first.next_cursor)
    assert caught.value.detail['code']=='snapshot_expired'

def test_credentials_and_inventory_failures_are_source_local():
    error=RuntimeError('secret must not be exposed');error.http_status=403
    readers={s:Reader(s,failure=error if s=='eccc-hrdps' else None) for s in DEFAULT_SOURCES}
    readers['eccc-rdps'].plan_series=lambda *a,**k: (_ for _ in ()).throw(ValueError('unreadable inventory'))
    service=ComparisonService(readers);pages=[service.initial(selection())]
    while pages[-1].next_cursor:pages.append(service.continuation(pages[-1].next_cursor))
    assert pages[0].coverage[0].state=='credentials_required' and pages[0].coverage[1].state=='unknown'
    assert 'secret' not in pages[0].model_dump_json()
    assert any(s.evidence for p in pages for c in p.curves if c.source_id=='noaa-gfs' for s in c.samples)

def test_empty_window_suggests_available_without_shifting():
    r=Reader('eccc-hrdps')
    request=selection(sources=[ComparisonSource(source_id=r.source_id)]).model_copy(update={'start':NOW-timedelta(days=2),'end':NOW-timedelta(days=1)})
    page=ComparisonService({r.source_id:r}).initial(request)
    assert page.selection==request and not r.calls and page.complete
    assert page.coverage[0].state=='empty' and page.coverage[0].available_start==NOW

def test_cancel_stops_continuations_without_acquiring():
    r=Reader('eccc-hrdps');service=ComparisonService({r.source_id:r})
    first=service.initial(selection(sources=[ComparisonSource(source_id=r.source_id)]))
    service.cancel(first.id)
    with pytest.raises(HTTPException):service.continuation(first.next_cursor)
    assert len(r.calls)==12

def test_page_deadline_keeps_two_acquisitions_and_marks_gaps():
    r=Reader('eccc-hrdps');hold=threading.Event();calls=[]
    def slow(*a,**k):calls.append(1);hold.wait(2);return []
    r.read_point=slow
    service=ComparisonService({r.source_id:r},deadline=.08)
    try:
        page=service.initial(selection(sources=[ComparisonSource(source_id=r.source_id)]))
        assert len(calls)==2 and page.curves[0].samples[0].evidence is None and page.coverage[0].state=='unknown'
    finally:hold.set()

def test_typed_route_rejects_altered_cursor_and_bounds(monkeypatch):
    monkeypatch.setattr('weather_api.forecast_comparison.comparison_service',lambda:ComparisonService({}))
    client=TestClient(app);path='/api/experiments/weather/v0/point/comparison'
    assert client.post(path,json={'cursor':'invalid','latitude':1}).status_code==422
    payload=selection().model_dump(mode='json')
    assert client.post(path,json=payload).status_code==200
    payload['end']=(NOW+timedelta(hours=25)).isoformat()
    assert client.post(path,json=payload).status_code==422
    payload=selection().model_dump(mode='json');payload['sources']*=2
    assert client.post(path,json=payload).status_code==422

def test_hrdps_inventory_needs_no_decode_cgroup():
    from weather_api.hrdps_query import HRDPSQueryCoordinator
    from ingest.contract import RunCandidate
    adapter=SimpleNamespace(discover=lambda _: [RunCandidate('advertised',NOW,detail={'available_hours':['001','004']})],
        demand_operation_bounds=lambda *_: (_ for _ in ()).throw(AssertionError('decode during inventory')))
    coordinator=HRDPSQueryCoordinator(adapter,now=lambda:NOW)
    assert coordinator.run_inventory()[0].provider_run_id=='advertised'
    assert coordinator.run_times('advertised')==(NOW+timedelta(hours=1),NOW+timedelta(hours=4))

def test_hrdps_discovery_names_run_from_advertised_nonzero_lead():
    from ingest.adapters.eccc_datamart import HRDPS_ADAPTER
    listings={'root/':['12/'],'root/12/':['001/','003/'],'root/12/001/':['20260909T12Z_MSC_HRDPS_TMP_AGL-2_RLatLon0.0225_PT001H.grib2']}
    client=SimpleNamespace(list_directory=lambda url,**k:listings[url])
    runs=HRDPS_ADAPTER._candidates_under_root(client,'root/','20260909')
    assert runs[0].run_time==NOW and runs[0].detail['available_hours']==['001','003']


def test_same_initial_request_coalesces_and_refresh_creates_new_identity():
    r=Reader('eccc-hrdps');entered=threading.Event();release=threading.Event()
    original=r.plan_series
    def plan(*a,**kw):entered.set();release.wait(2);return original(*a,**kw)
    r.plan_series=plan
    service=ComparisonService({r.source_id:r});request=selection(sources=[ComparisonSource(source_id=r.source_id)])
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(service.initial,request);assert entered.wait(1)
        b=pool.submit(service.initial,request)
        release.set();a,b=a.result(),b.result()
    assert a.id==b.id and len(r.calls)==12
    assert service.initial(request).id!=a.id


def test_published_quantiles_and_precipitation_interval_remain_source_specific():
    from registry.weathernext import BY_NATIVE
    source='google-weathernext-3-statistics';r=Reader(source)
    r.fields=[BY_NATIVE['total_precipitation_1hr_mean'].key]
    r.plan_series=lambda start,end,**k:NativePlan((NativeFrame(NOW,'actual-run',NOW),))
    calls=[]
    def batch(lat,lon,frame,fields,*,spread):
        calls.append((fields,spread));result=[]
        from weather_api.models import EnsembleProvenance
        for stat,number in [('mean',2),('p10',1),('p90',3)]:
            evidence=point_fields(NOW)[0][0].model_copy(deep=True)
            evidence.key=evidence.field=BY_NATIVE[f'total_precipitation_1hr_{stat}'].key
            evidence.value=number
            evidence.provenance.source_id=source;evidence.provenance.run_time=NOW;evidence.provenance.valid_time=NOW
            evidence.provenance.normalized_units='mm'
            evidence.provenance.ensemble=EnsembleProvenance(family='google-weathernext-3',statistic='ensemble_mean' if stat=='mean' else 'ensemble_quantile',quantile=None if stat=='mean' else .1 if stat=='p10' else .9,computed_here=False,member_set=None)
            result.append(evidence)
        return result
    r.read_comparison=batch
    page=ComparisonService({source:r}).initial(selection(sources=[ComparisonSource(source_id=source)],variables=['precipitation'],ensemble_spread=True))
    sample=page.curves[0].samples[0]
    assert calls==[(tuple(r.fields),True)]
    assert (sample.evidence.value,sample.lower.value,sample.upper.value)==(2,1,3)
    assert sample.interval_start==NOW-timedelta(hours=1) and sample.interval_end==NOW
    assert page.curves[0].units=='mm'


def test_position_and_shared_cache_limits(monkeypatch):
    r=Reader('eccc-hrdps')
    r.plan_series=lambda *a,**k:NativePlan(tuple(NativeFrame(NOW+timedelta(minutes=i),'run',NOW) for i in range(145)))
    service=ComparisonService({r.source_id:r})
    with pytest.raises(HTTPException) as caught:service.initial(selection(sources=[ComparisonSource(source_id=r.source_id)]))
    assert caught.value.detail['code']=='query_limit_exceeded' and not r.calls
    r.plan_series=lambda *a,**k:NativePlan(())
    monkeypatch.setattr('weather_api.forecast_comparison.reserve',lambda *a:False)
    with pytest.raises(HTTPException) as caught:service.initial(selection(sources=[ComparisonSource(source_id=r.source_id)]))
    assert caught.value.detail['code']=='snapshot_capacity_unavailable'


def test_aborted_initial_subscriber_does_not_cancel_active_replacement():
    import time
    r=Reader('eccc-hrdps');entered=threading.Event();release=threading.Event();cancelled=threading.Event()
    original=r.plan_series
    def plan(*a,**kw):entered.set();release.wait(2);return original(*a,**kw)
    r.plan_series=plan
    service=ComparisonService({r.source_id:r});request=selection(sources=[ComparisonSource(source_id=r.source_id)])
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(service.initial,request,cancelled.is_set);assert entered.wait(1)
        second=pool.submit(service.initial,request)
        deadline=time.monotonic()+1
        while len(service.pending[request.model_dump_json()][1])<2 and time.monotonic()<deadline:time.sleep(.001)
        cancelled.set();release.set()
        assert first.result().id==second.result().id
    assert len(r.calls)==12
