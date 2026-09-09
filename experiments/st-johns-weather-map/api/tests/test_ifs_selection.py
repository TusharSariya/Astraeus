"""IFS Atlantic experiment verification: GOV-SPEC-001/004/006."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime
import json
from threading import Event
import httpx
import pytest
from registry.ifs import FIELDS,PRODUCTS,field_selection
from weather_api.ifs_budget import SelectionBudget,SelectionStopped
from weather_api.ifs_native import IFSNative,IFSUnavailable,index_records

RUN=datetime(2026,9,9,tzinfo=UTC)
BASE='https://data.ecmwf.int/forecasts/'
URL=BASE+'20260909/00z/ifs/0p25/oper/20260909000000-0h-oper-fc.grib2'


def row():
    return dict(param='2t',levtype='sfc',date='20260909',time='0000',step='0',stream='oper',type='fc',
                _offset=0,_length=4,**{'class':'od'})


class Fixture:
    def __init__(self):self.calls=[];self.record=row();self.failed=False
    def handle(self,request):
        url=str(request.url);self.calls.append((url,request.headers.get('range')))
        pages={BASE:'20260909/',BASE+'20260909/':'00z/',BASE+'20260909/00z/ifs/0p25/oper/':URL.rsplit('/',1)[-1]}
        if url in pages:return httpx.Response(200,text=f'<a href="{pages[url]}">fixture</a>')
        if url==URL.replace('.grib2','.index'):return httpx.Response(200,text=json.dumps(self.record))
        if url==URL:
            return httpx.Response(503) if self.failed else httpx.Response(206,content=b'GRIB',headers={'Content-Range':'bytes 0-3/4'})
        return httpx.Response(404)
    def service(self,decoder=None,clock=lambda:0):
        return IFSNative(client=httpx.Client(transport=httpx.MockTransport(self.handle)),now=lambda:RUN,clock=clock,
                         decoder=decoder or (lambda r:dict(values=[[1.]],units='K',native_time=RUN.isoformat(),run_time=RUN.isoformat())))


def test_catalogue_shapes_and_exclusions():
    assert len(FIELDS)==87 and len(PRODUCTS)==11
    assert FIELDS['t:pl']['levels']==[1000,925,850,700,600,500,400,300,250,200,150,100,50,10]
    assert FIELDS['sot:sol']['levels']==[1,2,3,4]
    assert FIELDS['ptype:sfc']['rendering']=='categorical'
    assert FIELDS['mwd:sfc']['rendering']=='direction'
    assert FIELDS['tpg1:sfc']['threshold']=={'comparison':'>=','value':1.,'units':'mm'}
    assert not any(f['parameter'] in ('t20d','sav300','sst') for f in FIELDS.values())
    assert PRODUCTS['cyclone-ensemble']['format']=='bufr'
    for f in FIELDS.values():
        assert f['units'] and f['temporal'] and f['param_ids']
        for product in f['products']:
            for level in f.get('product_levels',{}).get(product,f['levels']):
                assert field_selection(product,f['id'],level) is f
    with pytest.raises(ValueError):field_selection('ensemble-mean','t:pl',1000)


def test_metadata_only_discovery_and_pinned_cached_record():
    fixture=Fixture();service=fixture.service();budget=SelectionBudget()
    runs=service.inventory('atmosphere-control',budget)
    assert len(runs)==1 and not any(r for _,r in fixture.calls)
    first=service.record('atmosphere-control',runs[0],0,'2t:sfc',0,'0',budget)
    n=len(fixture.calls);charged=budget.bytes
    second=service.record('atmosphere-control',runs[0],0,'2t:sfc',0,'0',budget)
    assert second==first and len(fixture.calls)==n and budget.bytes==charged
    assert budget.records==1
    assert fixture.calls[-1]==(URL,'bytes=0-3')


@pytest.mark.parametrize('change',[{'step':'3'},{'_offset':True},{'_length':8*1024**2+1},{'stream':'enfo'},{'date':'20260908'},{'model':'aifs-single'}])
def test_index_identity_fails_closed(change):
    record=row();record.update(change)
    with pytest.raises(IFSUnavailable):index_records(json.dumps(record),product='atmosphere-control',run=RUN,lead=0,definition=FIELDS['2t:sfc'],level=0,member='0')


def test_missing_field_and_duplicate_are_distinct():
    for records,reason in [([], 'field_unpublished'),([row(),row()],'record_identity_ambiguous')]:
        with pytest.raises(IFSUnavailable,match=reason):
            index_records('\n'.join(map(json.dumps,records)),product='atmosphere-control',run=RUN,lead=0,definition=FIELDS['2t:sfc'],level=0,member='0')


def test_budget_expiry_cancellation_records_and_bytes():
    clock=[0];budget=SelectionBudget(byte_limit=4,record_limit=1,clock=lambda:clock[0])
    budget.start_record()
    with pytest.raises(SelectionStopped,match='record_budget'):budget.start_record()
    budget.charge(4)
    with pytest.raises(SelectionStopped,match='byte_budget'):budget.allowance(1)
    clock[0]=900
    with pytest.raises(SelectionStopped,match='expired'):budget.check()
    budget.cancelled.set()
    with pytest.raises(SelectionStopped,match='cancelled'):budget.check()


def test_native_cache_coalesces():
    entered,release=Event(),Event();calls=[]
    def decode(r):
        calls.append(r);entered.set();assert release.wait(5)
        return {'values':[[1]],'units':'K'}
    fixture=Fixture();service=fixture.service(decode);budget=SelectionBudget()
    run=service.inventory('atmosphere-control',budget)[0]
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(service.record,'atmosphere-control',run,0,'2t:sfc',0,'0',budget)
        assert entered.wait(5)
        b=pool.submit(service.record,'atmosphere-control',run,0,'2t:sfc',0,'0',budget)
        release.set();assert a.result()==b.result()
    assert len(calls)==1 and budget.records==1


def native_fixture_bytes(param_id=167):
    import eccodes as ec
    import numpy as np
    g=ec.codes_grib_new_from_samples('regular_ll_sfc_grib2')
    try:
        settings={'centre':'ecmf','setLocalDefinition':1,'localDefinitionNumber':1,'class':'od','stream':'oper','type':'fc','dataDate':20260909,'dataTime':0,'paramId':param_id,'Ni':1440,'Nj':721,
                  'latitudeOfFirstGridPointInDegrees':90.,'latitudeOfLastGridPointInDegrees':-90.,
                  'longitudeOfFirstGridPointInDegrees':0.,'longitudeOfLastGridPointInDegrees':359.75,
                  'iDirectionIncrementInDegrees':.25,'jDirectionIncrementInDegrees':.25,'step':0}
        for k,v in settings.items():ec.codes_set(g,k,v)
        ec.codes_set_values(g,np.full(1440*721,280.))
        return ec.codes_get_message(g)
    finally:ec.codes_release(g)


def test_default_bounded_child_fixture_transport():
    import sys
    if sys.platform!='linux':pytest.skip('Locked RLIMIT_AS proof runs on Linux')
    body=native_fixture_bytes();fixture=Fixture();fixture.record['_length']=len(body)
    calls=[]
    def handle(request):
        if str(request.url)==URL:
            calls.append(request.headers['range'])
            return httpx.Response(206,content=body,headers={'Content-Range':f'bytes 0-{len(body)-1}/{len(body)}'})
        return fixture.handle(request)
    service=IFSNative(client=httpx.Client(transport=httpx.MockTransport(handle)),now=lambda:RUN)
    budget=SelectionBudget();run=service.inventory('atmosphere-control',budget)[0]
    result=service.record('atmosphere-control',run,0,'2t:sfc',0,'0',budget)
    assert len(result['latitudes'])==61 and len(result['longitudes'])==121
    assert result['values'][0][0]==280.
    assert service.record('atmosphere-control',run,0,'2t:sfc',0,'0',budget)==result
    assert calls==[f'bytes=0-{len(body)-1}']


def test_precipitation_intervals_and_resets():
    from weather_api.ifs_delivery import interval_amount
    g=dict(product='atmosphere-control',run_time=RUN.isoformat(),field='tp:sfc',level=0,member='0',units='m',
           digest='fixture',expires_at='2026-09-09T00:10:00+00:00',latitudes=[55,54.75],longitudes=[-70,-69.75],interval_start=RUN.isoformat(),temporal='accum',receipts=[])
    previous={**g,'interval_end':'2026-09-09T03:00:00+00:00','values':[[.01,.02],[None,0]]}
    current={**g,'interval_end':'2026-09-09T06:00:00+00:00','values':[[.02,.01],[.01,0]]}
    result=interval_amount(current,previous)
    assert result['values']==[[.01,None],[None,0]]
    assert result['interval_start']==previous['interval_end']
    with pytest.raises(IFSUnavailable):interval_amount(current,{**previous,'member':'1'})
    with pytest.raises(IFSUnavailable):interval_amount(current,None)


def grid(value=280.,member='0',field='2t:sfc'):
    return dict(product='atmosphere-control',selection_product='atmosphere-control',run_id='ifs:atmosphere-control:2026090900',
        run_time=RUN.isoformat(),native_time=RUN.isoformat(),field=field,level=0,member=member,units='K',temporal='instant',
        interval_start=RUN.isoformat(),interval_end=RUN.isoformat(),region=[-70,40,-40,55],
        latitudes=[55.,54.75],longitudes=[-70.,-69.75],latitude_edges=[55.125,54.875,54.625],longitude_edges=[-70.125,-69.875,-69.625],
        values=[[value,value],[value,value]],native_metadata={},retrieved_at=RUN.isoformat(),expires_at='2026-09-09T00:10:00+00:00',
        digest=('a' if member=='0' else 'b')*64,receipts=[],control_mapping=None)


def test_summary_identity_partial_counts_and_expiry():
    from weather_api.ifs_statistics import summarize
    a=grid(0);b=grid(10,'1');b['values'][0][0]=None;b['expires_at']='2026-09-09T00:09:00+00:00'
    mean=summarize({'0':a,'1':b},'atmosphere-ensemble','2t:sfc')
    spread=summarize({'0':a,'1':b},'atmosphere-ensemble','2t:sfc','ensemble_spread')
    assert mean['values'][0]==[0,5] and mean['member_counts'][0]==[1,2]
    assert spread['values'][0][0] is None
    assert mean['digest']!=a['digest'] and mean['digest']!=spread['digest']
    assert mean['expires_at']==b['expires_at']
    with pytest.raises(IFSUnavailable):summarize({'0':grid(field='mwd:sfc')},'wave-ensemble','mwd:sfc')


def test_selection_pages_pin_results_and_withhold_expired_evidence():
    from weather_api.ifs_selection import IFSSelections,IFSSelection
    from datetime import timedelta
    fixture=Fixture();clock=[0.];service=fixture.service(lambda _:grid(),clock=lambda:clock[0])
    jobs=IFSSelections(service,clock=lambda:clock[0],now=lambda:RUN+timedelta(seconds=clock[0]))
    page=jobs.start(IFSSelection(fields=[dict(product='atmosphere-control',field='2t:sfc',times=[RUN])]))
    assert page.completed==0 and page.next_cursor==0 and not any(r for _,r in fixture.calls)
    page=jobs.page(page.id,0)
    assert page.completed==page.total==1 and page.items[0].grid is not None
    assert page.items[0].grid.receipt_ids
    n=len(fixture.calls);assert jobs.page(page.id,0)==page;assert len(fixture.calls)==n
    clock[0]=601
    expired=jobs.page(page.id,0)
    assert expired.items[0].grid is None and expired.items[0].reason=='native_evidence_expired'
    clock[0]=900
    with pytest.raises(SelectionStopped,match='expired'):jobs.page(page.id,0)


def test_control_point_uses_same_native_cell_and_registered_wind():
    from weather_api.ifs_delivery import IFSSource
    from weather_api.source_delivery import NativeFrame
    class Native:
        def inventory(self,*args,**kwargs):return [dict(id='run',run_time=RUN.isoformat(),files={0:'fixture'},receipts=[])]
        def record(self,product,run,lead,field,level,member,budget):
            g=grid({'10u:sfc':3.,'10v:sfc':4.,'2t:sfc':280.,'2d:sfc':279.}.get(field,0),field=field)
            g['units']='m s**-1' if field.startswith('10') else 'K'
            return g
    reading=IFSSource(Native()).read_comparison(55,-70,NativeFrame(RUN,'run',RUN),('wind_speed_10m','relative_humidity_2m'))
    assert not reading.failures
    fields={f.key:f for f in reading.fields}
    assert fields['wind_speed_10m'].value==5
    assert fields['wind_speed_10m'].provenance.sampled_latitude==55
    assert len(fields['wind_speed_10m'].provenance.derivation_inputs)==2
    assert fields['relative_humidity_2m'].phase=='liquid'

@pytest.mark.parametrize('statistic,units,expected',[
    ('ensemble_spread','degC',25.5**.5),
    ('ensemble_member_count','members',51),
    ('ensemble_threshold_probability','1',1),
])
def test_point_summary_uses_statistic_units(statistic,units,expected):
    from weather_api.ifs_delivery import IFSSource
    from weather_api.source_delivery import NativeFrame
    from weather_api.source_contract import SourceVariant
    class Native:
        def inventory(self,*args,**kwargs):return [dict(id='run',run_time=RUN.isoformat(),files={0:'fixture'},receipts=[])]
        def record(self,product,run,lead,field,level,member,budget):return grid(280+int(member)%2*10,member,field)
    variant=SourceVariant(kind='derived_statistic',statistic=statistic,**({'threshold':270,'comparison':'gt'} if statistic=='ensemble_threshold_probability' else {}))
    result=IFSSource(Native(),'atmosphere-ensemble',variant=variant).read_comparison(55,-70,NativeFrame(RUN,'run',RUN),('temperature_2m',))
    assert not result.failures
    value=result.fields[0]
    assert value.provenance.normalized_units==units
    if statistic=='ensemble_spread':assert 5<value.value<5.1
    else:assert value.value==expected

@pytest.mark.parametrize('product,expected_tracks,control',[('cyclone-control',0,'51'),('cyclone-ensemble',1,'51')])
def test_bounded_bufr_fixture_without_network(tmp_path,product,expected_tracks,control):
    import sys,hashlib
    from pathlib import Path
    from ingest.isolation import run_bounded_process
    from weather_api.ecmwf_query import DECODE_LIMITS
    if sys.platform!='linux':pytest.skip('Kernel decoder limits require Linux')
    root=Path(__file__).parent/'fixtures'/'ifs'
    receipt=json.loads((root/f'{product}.json').read_text())
    path=root/f'{product}.bufr'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==receipt['receipts'][0]['sha256']
    output=tmp_path/'decoded.json'
    run_bounded_process(command=[sys.executable,'-m','weather_api.ifs_track_worker','{output}'],
        stdin=json.dumps({'path':str(path),'run_time':'2026-09-09T06:00:00+00:00'}).encode(),
        destination=output,limits=DECODE_LIMITS,timeout_seconds=45)
    result=json.loads(output.read_bytes())
    assert len(result['tracks'])==expected_tracks
    assert control in result['decoded_members']
    assert result['decoded_members']==receipt['members']

@pytest.mark.parametrize('field',sorted(FIELDS))
def test_each_catalogue_field_has_exact_index_identity(field):
    definition=FIELDS[field]
    for product in definition['products']:
        p=PRODUCTS[product]
        for level in definition.get('product_levels',{}).get(product,definition['levels']):
            record={**row(),'param':definition['parameter'],'levtype':definition['level_type'],'stream':p['stream'],'type':p['record_type']}
            if definition['level_type']!='sfc':record['levelist']=str(level)
            member='1' if p['members'] else '0'
            if p['members']:record['number']=member
            actual=index_records(json.dumps(record),product=product,run=RUN,lead=0,definition=definition,level=level,member=member)
            assert actual==record


def test_point_precipitation_uses_registered_interval_field():
    from datetime import timedelta
    from weather_api.ifs_delivery import IFSSource
    from weather_api.source_delivery import NativeFrame
    class Native:
        def inventory(self,*args,**kwargs):return [dict(id='run',run_time=RUN.isoformat(),files={0:'a',3:'b'},receipts=[])]
        def record(self,product,run,lead,field,level,member,budget):
            return {**grid(.001*lead,field='tp:sfc'),'units':'m','temporal':'accum','interval_end':(RUN+timedelta(hours=lead)).isoformat()}
    reading=IFSSource(Native()).read_comparison(55,-70,NativeFrame(RUN+timedelta(hours=3),'run',RUN),('precipitation_accumulation',))
    assert not reading.failures
    assert reading.fields[0].value==3
    assert reading.intervals['precipitation_accumulation']==(RUN,RUN+timedelta(hours=3))

@pytest.mark.parametrize('field,product,level',[
    ('t:pl','atmosphere-control',850),('sot:sol','atmosphere-control',1),
    ('ptype:sfc','atmosphere-control',0),('lsm:sfc','atmosphere-control',0),
    ('swh:sfc','wave-control',0),('tpg1:sfc','daily-probability',0),
    ('10fg:sfc','atmosphere-control',0),
])
def test_native_shapes_in_bounded_decoder(tmp_path,field,product,level):
    import sys
    if sys.platform!='linux':pytest.skip('Kernel decoder limits require Linux')
    import eccodes as ec
    from ingest.isolation import run_bounded_process
    from weather_api.ecmwf_query import DECODE_LIMITS
    definition=FIELDS[field];p=PRODUCTS[product]
    g=ec.codes_new_from_message(native_fixture_bytes(definition['param_ids'][0]))
    try:
        ec.codes_set(g,'stream',p['stream']);ec.codes_set(g,'type',p['record_type'])
        if definition['level_type']=='pl':ec.codes_set(g,'typeOfLevel','isobaricInhPa');ec.codes_set(g,'level',level)
        if definition['level_type']=='sol':ec.codes_set(g,'typeOfLevel','soilLayer');ec.codes_set(g,'level',level)
        step=3 if definition['temporal']=='maximum' else 0
        if step:ec.codes_set(g,'stepType','max');ec.codes_set(g,'stepRange','0-3')
        # A real bitmap distinguishes missing sea cells from valid zeros.
        if field=='swh:sfc':
            values=ec.codes_get_values(g);values[:]=0;values[140*1440+1160]=9999
            ec.codes_set(g,'missingValue',9999);ec.codes_set(g,'bitmapPresent',1);ec.codes_set_values(g,values)
        body=ec.codes_get_message(g)
    finally:ec.codes_release(g)
    path=tmp_path/'one.grib2';path.write_bytes(body);output=tmp_path/'grid.json'
    request=dict(path=str(path),product=product,field=field,level=level,member='0',lead=step,run_time=RUN.isoformat(),
        record={'_length':len(body),'step':f'0-{step}' if step else '0'},bounds={'west':-70,'east':-40,'south':40,'north':55})
    run_bounded_process(command=[sys.executable,'-m','weather_api.ifs_native_worker','{output}'],stdin=json.dumps(request).encode(),destination=output,limits=DECODE_LIMITS,timeout_seconds=45)
    result=json.loads(output.read_bytes());assert result['units']==definition['units']
    assert len(result['values'])==61 and len(result['values'][0])==121
    if field=='swh:sfc':assert result['values'][0][0] is None and result['values'][0][1]==0


def test_coalesced_waiter_recovers_after_owner_cancellation():
    entered=Event();release=Event();waiting=Event();count=[]
    def decode(request):
        count.append(1)
        if len(count)==1:entered.set();assert release.wait(5)
        return grid()
    fixture=Fixture();service=fixture.service(decode)
    owner_budget=SelectionBudget();waiter_budget=SelectionBudget()
    run=service.inventory('atmosphere-control',owner_budget)[0]
    def second():
        waiting.set()
        return service.record('atmosphere-control',run,0,'2t:sfc',0,'0',waiter_budget)
    with ThreadPoolExecutor(2) as pool:
        owner=pool.submit(service.record,'atmosphere-control',run,0,'2t:sfc',0,'0',owner_budget)
        assert entered.wait(5)
        waiter=pool.submit(second);assert waiting.wait(5)
        owner_budget.cancelled.set();release.set()
        with pytest.raises(SelectionStopped):owner.result()
        assert waiter.result()['values'][0][0]==280
    assert len(count)==2 and waiter_budget.records==1


def test_track_selection_returns_cancellable_identity_before_completion(monkeypatch):
    import weather_api.ifs_selection as module
    entered=Event();release=Event()
    def acquire(product,run,budget):
        entered.set();assert release.wait(5);budget.check()
    monkeypatch.setattr(module,'_acquire_tracks',acquire)
    page=module.select_tracks(module.IFSTrackSelection(product='cyclone-ensemble'))
    assert not page.complete and entered.wait(5)
    module.cancel_tracks(page.id);release.set()
    with pytest.raises(SelectionStopped):module.track_page(page.id)
