"""WN3 grid experiment verification: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Synthetic Zarr objects, never provider captures or network requests.
"""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import zarr
from fastapi.testclient import TestClient

from weather_api import source_grid as grids
from weather_api.weathernext_native import NativeStatisticsReader, NativeUnavailable, NativeLimits, ObjectIdentity, BUCKET
from weather_api.weathernext_query import WeatherNextSelection
from weather_api.weathernext_delivery import HistoricalConfiguration, WeatherNextHistoricalDelivery, WeatherNextLocalExperimentalDelivery

INIT=datetime(2026,8,1,tzinfo=UTC)
VALID=INIT+timedelta(hours=6)
NOW=datetime(2026,9,8,tzinfo=UTC)
FIELD='total_cloud_cover_mean'
PREFIX='weathernext_3_0_0_statistics/zarr/2026_to_present/20260801_00hr_01_preds/predictions.zarr/'

@pytest.fixture
def transport(tmp_path,request):
    reverse=getattr(request,'param',False)
    lat=np.round(np.arange(48.7,46.29,-.1),1).astype('float32')
    lon=np.round(np.arange(304.8,309.21,.1),1).astype('float32')
    if reverse=='atlantic':
        lat=np.round(np.arange(55.2,39.79,-.1),1).astype('float32')
        lon=np.round(np.arange(289.8,320.21,.1),1).astype('float32')
    elif reverse: lat=lat[::-1];lon=lon[::-1]
    values=np.full((3,len(lat),len(lon)),.5,dtype='float32')
    values[:,5,5]=0; values[:,6,6]=-9999; values[:,7,7]=1
    arrays={'init_time':(np.array(0,dtype='int64'),(),[],'days since 2026-08-01 00:00:00'),
        'lead_time':(np.array([5,6,7],dtype='int64'),(3,),['lead_time'],'hours'),
        'lat_0p1':(lat,(len(lat),),['lat_0p1'],'degrees_north'),
        'lon_0p1':(lon,(len(lon),),['lon_0p1'],'degrees_east'),
        FIELD:(values,((1,90,180) if reverse=='atlantic' else (1,13,23)),['lead_time','lat_0p1','lon_0p1'],'(0 - 1)')}
    nodes={}
    for name,(data,chunks,dims,unit) in arrays.items():
        zarr.create_array(tmp_path/name,data=data,chunks=chunks,dimension_names=dims,attributes={'units':unit},fill_value=-9999 if name==FIELD else None,config={'write_empty_chunks':True})
        nodes[name]=json.loads((tmp_path/name/'zarr.json').read_bytes())
    class Transport:
        def __init__(self):
            self.calls=[];self.nodes=nodes
            self.bodies={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
        def body(self,name):
            return json.dumps({'zarr_format':3,'node_type':'group','consolidated_metadata':{'metadata':nodes}}).encode() if name=='zarr.json' else self.bodies[name]
        def describe(self,bucket,name,*,timeout):
            self.calls.append(('describe',name));return ObjectIdentity(bucket,name,'42','etag',len(self.body(name.removeprefix(PREFIX))))
        def read(self,identity,*,max_bytes,timeout):
            self.calls.append(('read',identity.name));return self.body(identity.name.removeprefix(PREFIX))
    return Transport()

def selection(lat=47.5,lon=-53):return WeatherNextSelection(INIT,VALID,lat,lon,(FIELD,))

@pytest.fixture(autouse=True)
def reset():
    grids._entries.clear();grids._inflight.clear()

@pytest.mark.parametrize('transport',[False,True],indirect=True)
def test_complete_native_grid_order_boundaries_masks_and_point_agreement(transport):
    reader=NativeStatisticsReader(transport)
    reading=reader.read_grid(selection(),now=NOW)
    grid=reading.grid
    assert len(grid['latitudes'])==21 and len(grid['longitudes'])==41
    cells=[v for row in grid['percentages'] for v in row]
    assert len(cells)==861 and {0,50,100,None}<=set(cells)
    chunks=[name for op,name in transport.calls if op=='read' and '/'+FIELD+'/' in name]
    assert len(chunks)==len(set(chunks))==4
    assert min(grid['latitude_edges'])<=46.5 and max(grid['latitude_edges'])>=48.5
    assert min(grid['longitude_edges'])<=-55 and max(grid['longitude_edges'])>=-51
    for y,x in [(0,0),(20,40),(10,20),(3,3),(4,4),(5,5)]:
        point=reader.read_point(selection(grid['latitudes'][y],grid['longitudes'][x]),now=NOW).values[0].value
        assert grid['percentages'][y][x] == (None if point is None else pytest.approx(point*100))

@pytest.mark.parametrize('fault',['lead','spacing','coverage','chunk','missing','field','historical'])
def test_grid_refuses_incomplete_or_unsupported_native_evidence(transport,fault):
    s=selection();now=NOW
    if fault=='lead':s=WeatherNextSelection(INIT,INIT+timedelta(hours=8),47.5,-53,(FIELD,))
    if fault=='spacing':transport.nodes['lat_0p1']['attributes']['units']='radians'
    if fault=='coverage':transport.nodes[FIELD]['shape'][1]-=1
    if fault=='chunk':transport.nodes[FIELD]['chunk_grid']['configuration']['chunk_shape']=[1,100000,100000]
    if fault=='missing':del transport.bodies[FIELD+'/c/1/0/0']
    if fault=='field':s=WeatherNextSelection(INIT,VALID,47.5,-53,('low_cloud_cover_mean',))
    if fault=='historical':now=VALID+timedelta(hours=48)
    with pytest.raises(NativeUnavailable):NativeStatisticsReader(transport).read_grid(s,now=now)

def service(transport,clock=lambda:0,local=False):
    root=transport.describe(BUCKET,PREFIX+'zarr.json',timeout=1)
    config=HistoricalConfiguration(INIT,root,'astraeus')
    reader=(WeatherNextLocalExperimentalDelivery if local else WeatherNextHistoricalDelivery)(config,clock=clock,utcnow=lambda:NOW)
    def acquire(sel,regional=False):
        native=NativeStatisticsReader(transport)
        result=(native.read_grid if regional else native.read_point)(sel,now=NOW,**({"region":"atlantic"} if regional=="atlantic" else {}))
        raw=asdict(result);raw['initialization']=INIT.isoformat();raw['valid_time']=sel.valid_time.isoformat()
        operations=[{'name':o.name,'kind':'media','generation':o.generation,'bytes':o.size,'sha256':hashlib.sha256(transport.body(o.name.removeprefix(PREFIX))).hexdigest(),'completed_at':NOW.isoformat()} for o in result.objects]
        return {'reading':raw,'receipt':{'acquisition_scope':'internal_experimental_forecast' if local else 'historical','http_objects':operations,'http_response_bytes':sum(o.size for o in result.objects)}}
    reader._native_acquire=acquire;reader._acquire=acquire
    return reader

def test_frame_cache_point_reuse_scope_expiry_and_native_selection(transport):
    clock=[0];reader=service(transport,lambda:clock[0])
    grid=grids.frame(reader,VALID-timedelta(minutes=20))
    count=len(transport.calls)
    assert grid.selected_time==VALID-timedelta(minutes=20) and grid.native_time==VALID
    for y,x in [(0,0),(20,40),(10,20),(3,3),(4,4),(5,5)]:
        point=reader.read_point(grid.latitudes[y],grid.longitudes[x],VALID,field=grids.FIELD)[0]
        assert point.value==grid.percentages[y][x]
        assert point.provenance.source_acquisition==grid.provenance.source_acquisition
    assert len(transport.calls)==count
    assert grids.frame(reader,VALID).selected_time==VALID and len(transport.calls)==count
    other=grids.frame(service(transport,local=True),VALID)
    assert other.product=='WeatherNext 3 local' and len(transport.calls)>count
    count=len(transport.calls);clock[0]=60
    grids.frame(reader,VALID)
    assert len(transport.calls)>count

def test_duplicate_frames_and_point_coalesce(transport):
    reader=service(transport);original=reader._native_acquire
    started=threading.Event();release=threading.Event();calls=[]
    def acquire(*args,**kwargs):
        calls.append(1);started.set();assert release.wait(5);return original(*args,**kwargs)
    reader._native_acquire=acquire
    with ThreadPoolExecutor(3) as pool:
        a=pool.submit(grids.frame,reader,VALID);assert started.wait(5)
        b=pool.submit(grids.frame,reader,VALID)
        c=pool.submit(reader.read_point,47.5,-53,VALID,field=grids.FIELD)
        release.set()
        assert a.result()==b.result()
        assert c.result()[0].value==50
    assert len(calls)==1

def test_api_typed_grid_and_refusals(transport,monkeypatch):
    from weather_api.app import app,PREFIX as API
    monkeypatch.setenv('WEATHER_DATA_MODE','live')
    import importlib
    module=importlib.import_module("weather_api.app")
    monkeypatch.setattr(module,'configured_mode',lambda:module.LIVE_MODE)
    monkeypatch.setattr(grids,'selected_service',lambda *args:service(transport))
    client=TestClient(app);url=f'{API}/sources/{grids.SOURCE}/grid'
    params={'product':'WeatherNext 3 historical','field':grids.FIELD,'selected_time':VALID.isoformat()}
    response=client.get(url,params=params)
    assert response.status_code==200,response.text
    assert len(response.content)<1024**2 and response.json()['percentages'][10][20]==50
    assert client.get(url,params={**params,'field':'temperature_2m'}).status_code==422
    assert client.get(url,params={**params,'selected_time':'2026-08-01T06:00:00'}).status_code==422

def test_linux_default_worker_grid(transport):
    if sys.platform!='linux':pytest.skip('Linux bounded native decoder proof')
    from weather_api.weathernext_gcs_bridge import read_historical_point
    root=transport.describe(BUCKET,PREFIX+'zarr.json',timeout=1)
    result=read_historical_point(selection(),root_identity=root,now=NOW,transport=transport,regional=True)
    assert len(result['reading']['grid']['percentages'])==21
    chunks=[name for op,name in transport.calls if op=='read' and '/'+FIELD+'/' in name]
    assert len(chunks)==len(set(chunks))==4
    assert result['receipt']['worker_operations']==18


def test_four_frame_cache_bound_and_failure_removes_expired_frame(transport):
    clock=[0]; historical=service(transport,lambda:clock[0]);local=service(transport,lambda:clock[0],local=True)
    for reader in (historical,local):
        for lead in (5,6,7):grids.frame(reader,INIT+timedelta(hours=lead))
    assert len(grids._entries)==4
    clock[0]=61
    def refuse(*args,**kwargs):raise RuntimeError('fixture unavailable')
    local._native_acquire=refuse
    with pytest.raises(RuntimeError):grids.frame(local,VALID)
    assert grids.key(local,VALID) not in grids._entries
    assert grids.cached_point(local,selection()) is None


def test_invalid_response_and_oversized_serialization(transport):
    from pydantic import ValidationError
    grid=grids.frame(service(transport),VALID)
    payload=grid.model_dump()
    payload['provenance']['licence']='x'*(2*1024**2)
    with pytest.raises(ValidationError):grids.SourceGridResponse.model_validate(payload)
    payload=grid.model_dump();payload['latitude_edges'][1]+=.01
    with pytest.raises(ValidationError):grids.SourceGridResponse.model_validate(payload)


def test_api_credentials_and_missing_run_are_disclosed(monkeypatch):
    import importlib
    module=importlib.import_module('weather_api.app')
    monkeypatch.setattr(module,'configured_mode',lambda:module.LIVE_MODE)
    def unavailable(*args):
        error=RuntimeError('private error text');error.http_status=403;raise error
    monkeypatch.setattr(grids,'selected_service',unavailable)
    response=TestClient(module.app).get(f'{module.PREFIX}/sources/{grids.SOURCE}/grid',params={'product':'WeatherNext 3 local','field':grids.FIELD,'selected_time':VALID.isoformat()})
    assert response.status_code==403 and 'credentials required' in response.text
    assert 'private error text' not in response.text


@pytest.mark.parametrize('transport',['atlantic'],indirect=True)
def test_atlantic_complete_and_region_cache_identity(transport):
    reader=service(transport)
    grid=grids.frame(reader,VALID,region='atlantic')
    assert grid.region==(-70,40,-40,55)
    assert len(grid.latitudes)==151 and len(grid.longitudes)==301
    assert sum(map(len,grid.percentages))==45451
    assert len(grid.model_dump_json().encode())<2*1024**2
    chunks=[name for op,name in transport.calls if op=='read' and '/'+FIELD+'/' in name]
    assert len(chunks)==len(set(chunks))==4
    count=len(transport.calls)
    for y,x in [(0,0),(150,300),(75,150),(3,3),(4,4),(5,5)]:
        lat=min(55,max(40,grid.latitudes[y]));lon=min(-40,max(-70,grid.longitudes[x]))
        point=reader.read_point(lat,lon,VALID,field=grids.FIELD)[0]
        assert point.value==grid.percentages[y][x]
    assert len(transport.calls)==count
    avalon=grids.frame(reader,VALID)
    assert len(avalon.latitudes)==21 and len(avalon.longitudes)==41
    assert grids.key(reader,VALID)!=grids.key(reader,VALID,'atlantic')

@pytest.mark.parametrize('transport',['atlantic'],indirect=True)
def test_linux_default_worker_atlantic(transport):
    if sys.platform!='linux':pytest.skip('Linux bounded native decoder proof')
    from weather_api.weathernext_gcs_bridge import read_historical_point
    root=transport.describe(BUCKET,PREFIX+'zarr.json',timeout=1)
    result=read_historical_point(selection(),root_identity=root,now=NOW,transport=transport,regional='atlantic')
    assert len(result['reading']['grid']['percentages'])==151
    assert len(result['reading']['grid']['percentages'][0])==301

@pytest.mark.parametrize('transport',['atlantic'],indirect=True)
def test_public_point_route_reuses_atlantic_cells_and_retains_other_coverage(transport,monkeypatch):
    import importlib
    module=importlib.import_module('weather_api.app')
    monkeypatch.setattr(module,'configured_mode',lambda:module.LIVE_MODE)
    reader=service(transport)
    monkeypatch.setattr(grids,'selected_service',lambda *args:reader)
    grid=grids.frame(reader,VALID,region='atlantic')
    count=len(transport.calls)
    client=TestClient(module.app)
    params={'product':'WeatherNext 3 historical','field':grids.FIELD,'time_selection':'directional','valid_time':VALID.isoformat(),'latitude':55,'longitude':-40}
    response=client.get(f'{module.PREFIX}/point',params=params)
    assert response.status_code==200,response.text
    assert response.json()['fields'][0]['value']==grid.percentages[0][-1]
    assert len(transport.calls)==count
    assert client.get(f'{module.PREFIX}/point',params={**params,'latitude':56}).status_code==422
    assert client.get(f'{module.PREFIX}/point',params={**params,'product':'RDPS'}).status_code==422

@pytest.mark.parametrize('level',['low','medium','high'])
def test_all_cloud_means_reuse_native_grid_and_keep_field_identity(transport,level):
    from copy import deepcopy
    native=level+'_cloud_cover_mean'
    transport.nodes[native]=deepcopy(transport.nodes[FIELD])
    for name,body in list(transport.bodies.items()):
        if name.startswith(FIELD+'/'):transport.bodies[name.replace(FIELD,native,1)]=body
    reader=service(transport)
    original=grids.frame(reader,VALID)
    field='weathernext3_'+native
    grid=grids.frame(reader,VALID,field=field)
    assert grid.field==field and grid.percentages==original.percentages
    assert grid.provenance.native_variable==native
    assert grids.key(reader,VALID,field=field)!=grids.key(reader,VALID)
    selection=WeatherNextSelection(INIT,VALID,47.5,-53.,(native,))
    point=grids.cached_point(reader,selection)[0]
    assert point.key==field and point.provenance.native_variable==native
