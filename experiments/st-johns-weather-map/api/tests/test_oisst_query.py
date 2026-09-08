from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import httpx
import numpy as np
import pytest
import xarray as xr

from ingest.http import PoliteClient, USER_AGENT
from weather_api.oisst_query import OISSTQueryService, OISSTUnavailable

DAY = datetime(2026, 9, 7, 12, tzinfo=UTC)


def service(tmp_path, *, final=False, missing_error=False, native_time=DAY, native_units='Celsius'):
    filename = 'oisst-avhrr-v02r01.20260907' + ('' if final else '_preliminary') + '.nc'
    variables = {'sst': (('time','zlev','lat','lon'), np.array([[[[12,np.nan],[11.5,11]]]], dtype='float32'), {'units':native_units})}
    if not missing_error:
        variables['err'] = (('time','zlev','lat','lon'), np.array([[[[.2,np.nan],[.3,.4]]]], dtype='float32'), {'units':'Celsius'})
    ds = xr.Dataset(variables, coords={'time':[np.datetime64(native_time.replace(tzinfo=None),'ns')], 'zlev':[0.0], 'lat':[45.125,50.375], 'lon':[302.125,313.875]}, attrs={'id':filename,'title':'NOAA Daily OISST Analysis'})
    path = tmp_path / filename
    ds.to_netcdf(path)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if str(request.url).endswith('/'):
            return httpx.Response(200,text=f'<a href="{filename}">{filename}</a>')
        return httpx.Response(200,content=path.read_bytes())
    client = PoliteClient(attempts=1,min_host_interval_seconds=0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler),headers={'User-Agent':USER_AGENT})
    clock = [0.0]
    original = client.download_with_receipt
    def download(*args, **kwargs):
        receipt = original(*args, **kwargs)
        receipt['completed_at'] = DAY + timedelta(seconds=clock[0])
        return receipt
    client.download_with_receipt = download
    return OISSTQueryService(client=client,clock=lambda:clock[0],utcnow=lambda:DAY+timedelta(seconds=clock[0])), calls, clock


@pytest.mark.parametrize('final',[True,False])
def test_exact_native_analysis_fields_and_shared_cache(tmp_path, final):
    query,calls,_ = service(tmp_path,final=final)
    fields = query.point_fields(45.125,-57.875,DAY)
    assert [f.value for f in fields] == pytest.approx([12,.2])
    assert fields[0].provenance.run_time is None
    assert fields[0].provenance.valid_time == DAY
    assert fields[0].provenance.retrieval_time == DAY
    assert fields[0].provenance.original_units == 'Celsius'
    assert fields[0].provenance.normalized_units == 'degC'
    assert fields[0].provenance.operational is False
    entry=query.query(DAY)
    assert entry['analysis_status'] == ('final' if final else 'preliminary')
    assert ('_preliminary' in entry['provenance']['product_identity']) == (not final)
    assert [f.value for f in query.point_fields(45.125,-46.125,DAY)] == [None,None]
    assert len(calls) == 2


@pytest.mark.parametrize('kwargs',[{'missing_error':True},{'native_units':'kelvin'},{'native_time':DAY-timedelta(days=1)}])
def test_native_contract_refusal(tmp_path,kwargs):
    query,_,_ = service(tmp_path,**kwargs)
    with pytest.raises(OISSTUnavailable):query.query(DAY)
    assert query.entry is None


@pytest.mark.parametrize('selected',[DAY.replace(hour=0),DAY.replace(tzinfo=None),DAY-timedelta(days=5),DAY+timedelta(days=1)])
def test_unsupported_time_has_no_transport(tmp_path,selected):
    query,calls,_ = service(tmp_path)
    with pytest.raises(ValueError):query.query(selected)
    assert not calls


def test_expiry_and_failed_refresh(tmp_path):
    query,calls,clock=service(tmp_path)
    first=query.query(DAY)
    query.client._client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(404)))
    with pytest.raises(OISSTUnavailable):query.query(DAY,refresh=True)
    assert query.query(DAY)==first
    clock[0]=301
    with pytest.raises(OISSTUnavailable):query.query(DAY)


def test_actual_linux_worker(tmp_path):
    import sys
    from ingest.isolation import run_bounded_process
    from weather_api.oisst_query import LIMITS
    code=f"""
import sys, tempfile, runpy
sys.path.insert(0,{str(Path(__file__).resolve().parent)!r})
from test_oisst_query import service
from pathlib import Path
import ingest.http
NativeClient=ingest.http.PoliteClient
with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
    client=service(Path(directory))[0].client
    client.download_with_receipt=NativeClient.download_with_receipt.__get__(client)
    ingest.http.PoliteClient=lambda **kwargs:client
    runpy.run_module('weather_api.oisst_query_worker',run_name='__main__')
"""
    result=run_bounded_process(command=[sys.executable,'-c',code,'{output}'],stdin=DAY.isoformat().encode(),destination=None,limits=LIMITS,timeout_seconds=30,require_output=False)
    data=json.loads(result.stdout)
    assert data['valid_time']==DAY.isoformat()
    assert data['sea_surface_temperature'][0]==[12,None]
    assert data['analysis_status']=='preliminary'


def test_delayed_qc_does_not_renew_receipt(tmp_path,monkeypatch):
    import ingest.captures.sst_analysis as native
    query,_,clock=service(tmp_path)
    original=native.validate_run
    def delayed(*args,**kwargs):
        clock[0]=40
        return original(*args,**kwargs)
    monkeypatch.setattr(native,'validate_run',delayed)
    entry=query.query(DAY)
    assert entry['provenance']['retrieval_time']==DAY.isoformat()
    assert query.entry[1]==300


def test_identical_misses_coalesce(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import weather_api.oisst_query as module
    query,calls,_=service(tmp_path)
    entered,release=threading.Event(),threading.Event()
    original=module.acquire
    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(module,'acquire',blocked)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(query.query,DAY)
        assert entered.wait(5)
        second=pool.submit(query.query,DAY)
        release.set()
        assert first.result()==second.result()
    assert len(calls)==2


def test_outside_native_box_no_request(tmp_path):
    query,calls,_=service(tmp_path)
    with pytest.raises(ValueError):query.point_fields(44,-52,DAY)
    assert not calls
