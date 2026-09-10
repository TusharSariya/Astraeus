"""GOV-SPEC-001/004/006: retained summaries only, synthetic data, no provider I/O."""
from datetime import UTC,datetime,timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from weather_api.weathernext_workspace import WeatherNextWorkspaceService,WeatherNextSelectionRequest,Threshold,probability_bounds,STATS
from weather_api.fixtures import point_fields
from registry.weathernext import BY_KEY

@pytest.mark.parametrize('values,threshold,event,expected',[
 ({'p10':10,'p25':25,'p50':50,'p75':75,'p90':90},80,'above',(10,25)),
 ({'p10':10,'p25':25,'p50':50,'p75':75,'p90':90},80,'below',(75,90)),
 ({'p10':10,'p25':25,'p50':50,'p75':75,'p90':90},50,'below',(25,75)),
 ({'p10':0,'p25':0,'p50':0,'p75':0,'p90':8},0,'above',(10,100)),
 ({'p10':0,'p25':0,'p50':0,'p75':0,'p90':0},0,'below',(0,100)),
 ({'p10':10,'p90':90},0,'above',(90,100)),
 ({'p10':10,'p90':90},100,'above',(0,10)),
 ({'p10':None,'p25':20,'p75':60},40,'below',(25,75)),
 ({'p10':80,'p25':20},40,'below',(None,None)),
 ({'p50':None},0,'above',(None,None)),
 ({'p10':float('nan')},0,'above',(None,None)),
])
def test_strict_quantile_bounds(values,threshold,event,expected):
    result=probability_bounds(values,threshold,event)
    assert (result.lower,result.upper)==expected
    assert result.approximate

@pytest.fixture
def runtime():
    now=[datetime(2026,9,9,tzinfo=UTC)]
    calls=[]
    config=SimpleNamespace(initialization=now[0],run_id='fixed-run')
    def read(lat,lon,t,*,fields,run,report_failures,retention_until=None):
        calls.append((t,fields,run))
        evidence=[]
        for key in fields:
            value=point_fields(t)[0][0].model_copy(deep=True)
            value.key=value.field=key;value.value=0 if key.endswith('p10') else 50
            value.provenance.source_id='google-weathernext-3-statistics'
            value.provenance.native_variable=BY_KEY[key].native
            value.provenance.normalized_units=BY_KEY[key].unit
            value.provenance.run_time=config.initialization
            value.provenance.valid_time=t
            evidence.append(value)
        return tuple(evidence),{}
    source=SimpleNamespace(config=config,read_batch=read)
    times=tuple(now[0]+timedelta(hours=h) for h in (1,2,72))
    runtime=WeatherNextWorkspaceService(service_for=lambda *args:source,axis_for=lambda _: (times,[],now[0]+timedelta(seconds=60)),utcnow=lambda:now[0])
    yield runtime,now,calls
    for key in list(runtime.entries):runtime.cancel(key)
    runtime.jobs.executor.shutdown(wait=True)

def test_paged_section_only_long_range_retained_threshold_no_downloads(runtime):
    service,now,calls=runtime
    selection=WeatherNextSelectionRequest(latitude=47.5,longitude=-52.7,start=now[0],end=now[0]+timedelta(days=10))
    first=service.initial(selection)
    assert len(calls)==1 and len(calls[0][1])==6
    assert all('cloud' in k for k in calls[0][1])
    assert first.next_offset==1 and len(first.native_times)==3
    assert first.total_pages==12 and first.completed_pages==1
    assert all('total_cloud' in k for k in calls[0][1])
    assert first.run_id=='fixed-run' and first.run_time==now[0]
    assert service.page(first.id,0)==first and len(calls)==1
    service.estimate(first.id,Threshold(quantity='total_cloud_cover',unit='percent',value=80))
    assert len(calls)==1
    second=service.page(first.id,1)
    assert second.samples[0].time==now[0]+timedelta(hours=2)
    assert len(service.entries[first.id].pages)==2
    service.cancel(first.id)
    with pytest.raises(HTTPException):service.page(first.id,2)
    assert len(calls)==2

def test_expiry_withholds_summaries_and_thresholds(runtime):
    service,now,calls=runtime
    first=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4)))
    retained=service.entries[first.id].pages[0]
    retained.samples[0].expires_at=now[0]+timedelta(seconds=60)
    now[0]+=timedelta(seconds=61)
    page=service.page(first.id,0)
    assert all(s.state=='expired' and all(v is None for v in s.values.values()) for s in page.samples[0].summaries)
    estimate=service.estimate(first.id,Threshold(quantity='total_cloud_cover',unit='percent',value=80))
    assert all(e.lower is None and e.upper is None for e in estimate.estimates.values())
    assert len(calls)==1

@pytest.mark.parametrize('section,product,base',[('temperature','station','station_head_temperature_2m'),('precipitation','imerg','imerg_tp_1hr'),('precipitation','experimental','experimental_tp_1hr')])
def test_explicit_products(runtime,section,product,base):
    service,now,calls=runtime
    first=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=2),section=section,product=product))
    assert first.samples[0].summaries[0].quantity==base
    assert len(calls)==1
    if section=='precipitation':assert first.samples[0].summaries[0].interval_end-first.samples[0].summaries[0].interval_start==timedelta(hours=1)

def test_failed_later_page_preserves_first(runtime):
    service,now,calls=runtime
    first=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4)))
    service.entries[first.id].service.read_batch=lambda *a,**kw:(_ for _ in ()).throw(ValueError())
    second=service.page(first.id,1)
    assert all(s.state=='failed' for s in second.samples[0].summaries)
    assert service.page(first.id,0)==first

def test_duplicate_initial_requests_coalesce_existing_executor(runtime):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    service,now,calls=runtime
    entered,release_read=threading.Event(),threading.Event()
    source=service.service_for(None,None)
    original=source.read_batch
    def read(*args,**kwargs):
        entered.set()
        assert release_read.wait(5)
        return original(*args,**kwargs)
    source.read_batch=read
    selection=WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(service.initial,selection)
        assert entered.wait(5)
        second=pool.submit(service.initial,selection)
        # Ensure both subscribers joined the inherited coalescing seam.
        import time
        deadline=time.monotonic()+5
        while len(service.pending[selection.model_dump_json()][1])<2 and time.monotonic()<deadline:time.sleep(.001)
        assert len(service.pending[selection.model_dump_json()][1])==2
        release_read.set()
        assert first.result().id==second.result().id
    assert len(calls)==1

def test_threshold_reads_completed_pages_while_next_page_lock_is_held(runtime):
    service,now,calls=runtime
    first=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4)))
    entry=service.entries[first.id]
    with entry.lock:
        estimates=service.estimate(first.id,Threshold(quantity='total_cloud_cover',unit='percent',value=80))
    assert estimates.estimates and len(calls)==1

def test_requested_run_is_not_silently_substituted(runtime):
    service,now,calls=runtime
    result=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4),run_time=now[0]-timedelta(hours=6)))
    assert result.state=='failed' and not result.samples and not calls

def test_public_selection_page_and_retained_estimate_contract(runtime,monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from weather_api.app import app,PREFIX
    service,now,calls=runtime
    module=importlib.import_module('weather_api.weathernext_workspace')
    store=importlib.import_module('weather_api.store')
    monkeypatch.setattr(module,'workspace_service',lambda:service)
    monkeypatch.setattr(store,'configured_mode',lambda:store.LIVE_MODE)
    client=TestClient(app)
    response=client.post(PREFIX+'/weathernext/selection',json={'latitude':47.5,'longitude':-52.7,'start':now[0].isoformat(),'end':(now[0]+timedelta(days=10)).isoformat(),'section':'clouds'})
    assert response.status_code==200,response.text
    page=response.json();assert page['run_id']=='fixed-run'
    assert page['samples'][0]['summaries'][0]['unit']=='percent'
    base=PREFIX+'/weathernext/selection/'+page['id']
    assert client.get(base+'?offset=0').status_code==200
    estimate=client.post(base+'/threshold',json={'quantity':'total_cloud_cover','unit':'percent','value':80,'event':'above'})
    assert estimate.status_code==200 and estimate.json()['basis']=='retained_published_percentiles'
    assert len(calls)==1
    assert client.post(base+'/threshold',json={'quantity':'total_cloud_cover','unit':'percent','value':80,'event':'at_any_time'}).status_code==422
    assert client.delete(base).status_code==204
    assert client.get(base+'?offset=1').status_code==410


def test_quantity_pages_and_deadline_alignment(runtime):
    from weather_api.weathernext_workspace import PAGE_DEADLINE
    service,now,calls=runtime
    assert PAGE_DEADLINE > 90
    first=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4)))
    for offset in range(1,12):
        result=service.page(first.id,offset)
        assert len(result.samples[0].summaries)==1
        assert result.completed_pages==offset+1
    assert result.next_offset is None
    assert [c[0] for c in calls[:3]]==list(first.native_times)
    assert all('low_cloud' in key for key in calls[3][1])
    assert all(len(c[1])==6 for c in calls)
    assert len(service.entries[first.id].pages)==12
    assert first.expires_at==now[0]+timedelta(hours=1)


def test_page_wait_accepts_completion_after_old_deadline(runtime):
    from concurrent.futures import Future
    service,now,calls=runtime
    elapsed=[0.]
    service.clock=lambda:elapsed[0]
    def bounded(work,deadline,stop):
        f=Future()
        value=work()
        if calls: elapsed[0]+=46
        assert elapsed[0]<deadline
        f.set_result(value)
        return f
    service._bounded=bounded
    first=service.initial(WeatherNextSelectionRequest(latitude=0,longitude=0,start=now[0],end=now[0]+timedelta(days=4)))
    assert first.samples[0].summaries[0].state=='available'
