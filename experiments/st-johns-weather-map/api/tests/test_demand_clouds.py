"""Fixed verification for GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
All provider requests use MockTransport; synthetic science fixtures are labelled.
"""
from datetime import UTC,datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
import threading
import sys
import json
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from weather_api import demand_clouds as clouds

NOW=datetime(2026,9,8,12,tzinfo=UTC)
STAMP='20262511200000'

def key(product,stamp=STAMP):return f'ABI-L2-{product}/2026/251/12/OR_ABI-L2-{product}-M6_G19_s{stamp}_e20262511209599_c20262511210000.nc'
def listing(*keys,truncated=False):return '<ListBucketResult><IsTruncated>'+str(truncated).lower()+'</IsTruncated>'+''.join(f'<Contents><Key>{k}</Key></Contents>' for k in keys)+'</ListBucketResult>'

def service(*,height=True,decoder=None,clock=lambda:0):
    calls=[]
    def transport(request):
        calls.append(str(request.url))
        if request.url.params.get('prefix','').startswith('ABI-L2-ACMF'):return httpx.Response(200,text=listing(key('ACMF'),key('ACMF','20262511210000')))
        if request.url.params.get('prefix','').startswith('ABI-L2-ACHAF'):return httpx.Response(200,text=listing(key('ACHAF')) if height else listing())
        return httpx.Response(200,content=b'height' if 'ACHAF' in str(request.url) else b'mask')
    return clouds.MaskService(httpx.Client(transport=httpx.MockTransport(transport)),now=lambda:NOW,clock=clock,decoder=decoder or (lambda *a:b'crop')),calls

def test_actual_inventory_no_science_or_future():
    s,calls=service()
    assert list(s.inventory(NOW-timedelta(hours=1),NOW+timedelta(hours=1)))==[NOW]
    assert all('prefix=' in c for c in calls)
    assert s.inventory(NOW+timedelta(minutes=1),NOW+timedelta(hours=1))=={}

def test_pairing_missing_height_gap_and_cache_expiry():
    decoded=[];clock=[0]
    s,calls=service(decoder=lambda *args:decoded.append(args) or b'crop',clock=lambda:clock[0])
    frame=s.selected(NOW+timedelta(seconds=299))
    assert decoded[0][:3]==(b'mask',b'height',STAMP)
    count=len(calls);assert s.selected(NOW)==frame and len(calls)==count
    with pytest.raises(clouds.grids.FrameNotStored):s.selected(NOW+timedelta(seconds=301))
    assert len(decoded)==1
    clock[0]=61;s.selected(NOW);assert len(decoded)==2
    s,_=service(height=False,decoder=lambda *args:decoded.append(args) or b'crop')
    s.selected(NOW);assert decoded[-1][1] is None

def test_duplicate_mask_frames_coalesce():
    started=threading.Event();release=threading.Event();decoded=[]
    def decode(*args):decoded.append(1);started.set();assert release.wait(5);return b'crop'
    s,calls=service(decoder=decode)
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(s.selected,NOW);assert started.wait(5)
        b=pool.submit(s.selected,NOW);release.set();assert a.result()==b.result()
    assert len(decoded)==1
    assert sum('/OR_' in c and 'ACMF' in c for c in calls)==1

def test_transport_caps_and_truncated_metadata():
    s=clouds.MaskService(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'1234'))),clock=lambda:0)
    with pytest.raises(ValueError):s.fetch('https://example.test',3,5)
    with pytest.raises(ValueError):s.fetch('https://example.test',5,0)
    s.client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=listing(key('ACMF'),truncated=True))))
    with pytest.raises(ValueError,match='truncated'):s.listing('ABI-L2-ACMF',NOW,5)

def test_white_rgb_alpha_missing_and_coverage():
    values=np.array([[0.,50.,100.,np.nan,50.]])
    rgba=clouds.white_color(values,np.array([[True,True,True,True,False]]))
    assert rgba[0,:3,:3].tolist()==[[255]*3]*3
    assert rgba[0,:3,3].tolist()==[0,127,255] or rgba[0,:3,3].tolist()==[0,128,255]
    assert tuple(rgba[0,3])==clouds.satellite.INVALID_RGBA
    assert rgba[0,4,3]==0

def test_discoverable_layers_no_provider_and_typed_inventory(monkeypatch):
    import importlib
    app=importlib.import_module('weather_api.app')
    monkeypatch.setattr(app,'configured_mode',lambda:app.LIVE_MODE)
    s,calls=service();monkeypatch.setattr(clouds,'mask_service',lambda:s)
    layers=clouds.layers(app.Layer)
    assert [l.id for l in layers]==[clouds.GOES,clouds.RDPS]
    assert all(l.times==[] and l.raster_available for l in layers) and not calls
    response=TestClient(app.app).get(f'{app.PREFIX}/layers/{clouds.GOES}/times',params={'start':(NOW-timedelta(hours=1)).isoformat(),'end':(NOW+timedelta(hours=1)).isoformat()})
    assert response.status_code==200,response.text
    assert response.json()['basis']=='advertised_native_times'
    assert len(response.json()['frames'])==1
    assert all('prefix=' in c for c in calls)

def test_linux_default_mask_worker(tmp_path,monkeypatch):
    if sys.platform!='linux':pytest.skip('Linux kernel bounded decoder proof')
    import test_adapter_goes_abi as fixture
    # Existing synthetic geostationary granules, expanded over the requested region.
    monkeypatch.setattr(fixture,'TEST_BOUNDS',{'south':40,'west':-70,'north':55,'east':-40})
    original=fixture._fixed_grid_axes
    monkeypatch.setattr(fixture,'_fixed_grid_axes',lambda:original(step_m=20000))
    path=tmp_path/'acmf.nc';fixture._write_acmf(path)
    import xarray as xr
    with xr.open_dataset(path) as ds:stamp=ds.attrs['time_coverage_start']
    native=datetime.fromisoformat(stamp.replace('Z','+00:00'))
    token=native.strftime('%Y%j%H%M%S')+'0'
    result=clouds.MaskService.decode(path.read_bytes(),None,token,90)
    assert 0<len(result)<=16*1024**2
    from pathlib import Path
    import zarr
    out=tmp_path/'out.zip';out.write_bytes(result)
    with zarr.storage.ZipStore(str(out),mode='r') as store:
        with xr.open_zarr(store,consolidated=False) as ds:
            assert ds.attrs['cloud_top_height_used']=='no (all cloudy pixels uncorrected)'
            assert 'parallax_uncorrected' in ds


def test_rdps_regional_request_preserves_legacy_bounds(monkeypatch):
    from weather_api.rdps_query import RDPSQueryCoordinator, RDPS_DEMAND_VARS
    from ingest.contract import RunCandidate, AVALON_CORE_BOUNDS, ATLANTIC_CONTEXT_BOUNDS
    class Adapter:
        bounds=AVALON_CORE_BOUNDS
        var_map=RDPS_DEMAND_VARS
        def demand_operation_bounds(self,count):assert count==1
        def discover(self,window):return [RunCandidate('fixture',NOW,[],{'cycle_url':'https://example.test','available_hours':[0]})]
    coordinator=RDPSQueryCoordinator(Adapter(),now=lambda:NOW)
    seen=[]
    monkeypatch.setattr(coordinator._cache,'query',lambda key,**kwargs:seen.append(key) or key)
    regional=coordinator.query(NOW,fields=('total_cloud_opacity',),region='atlantic')
    legacy=coordinator.query(NOW,fields=('total_cloud_opacity',))
    assert dict(regional.bounds)==ATLANTIC_CONTEXT_BOUNDS
    assert dict(legacy.bounds)==AVALON_CORE_BOUNDS
    assert regional!=legacy and coordinator._adapter.bounds==AVALON_CORE_BOUNDS


def test_rdps_rotated_render_point_agreement_and_missing(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import xarray as xr
    from ingest.grib import write_zarr
    import weather_api.rdps_query as rdps
    from PIL import Image
    from io import BytesIO
    ds=xr.Dataset({'total_cloud_opacity':(('valid_time','y','x'),np.array([[[0,50],[100,np.nan]]]),{'units':'percent'})},
        coords={'valid_time':[np.datetime64(NOW.replace(tzinfo=None),'ns')],'latitude':(('y','x'),[[47.1,47.1],[47.,47.]]),'longitude':(('y','x'),[[-53.,-52.9],[-53.,-52.9]])})
    path=tmp_path/'grid.zip';write_zarr(ds,path)
    entry=SimpleNamespace(payload=path.read_bytes(),valid_time=NOW,run_time=NOW,fetched_at=NOW,content_digest='a'*64,provenance={})
    monkeypatch.setattr(rdps,'rdps_query_coordinator',lambda:SimpleNamespace(query=lambda *a,**kw:entry))
    for lat,lon,value in [(47.1,-53,0),(47.1,-52.9,50),(47,-53,100),(47,-52.9,None)]:
        png,headers=clouds.raster(clouds.RDPS,NOW,bounds={'south':lat-.001,'north':lat+.001,'west':lon-.001,'east':lon+.001},width=1,height=1,crs='EPSG:4326')
        rgba=Image.open(BytesIO(png)).getpixel((0,0))
        assert rgba==(clouds.satellite.INVALID_RGBA if value is None else (255,255,255,round(value/100*255)))
        assert 'Missing RGBA' in headers['X-Weather-Render-Semantics']
        assert headers['X-Weather-Sample-Method']=='curvilinear_nearest_cell'
