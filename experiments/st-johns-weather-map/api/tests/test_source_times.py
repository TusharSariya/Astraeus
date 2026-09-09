"""WN3 native-time inventory; Spec-Refs: GOV-SPEC-004, GOV-SPEC-006."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import importlib
import pytest
from fastapi.testclient import TestClient
from weather_api.source_times import inventory
from weather_api.weathernext_native import NativeStatisticsReader
from weather_api.weathernext_query import WeatherNextSelection
from test_weathernext_native import transport, selection, NOW, INIT, FIELD


def test_inventory_decodes_only_native_time_coordinates(transport):
    result = NativeStatisticsReader(transport).read_point(selection(), now=NOW, inventory=True)
    assert result.native_times == tuple((INIT + timedelta(hours=h)).isoformat() for h in (5,6,7))
    assert not result.values
    assert [name for op,name in transport.calls if op == 'read'] == ['zarr.json','init_time/c','lead_time/c/0']


def test_inventory_does_not_require_selected_lead_or_spatial_chunks(transport):
    result = NativeStatisticsReader(transport).read_point(
        WeatherNextSelection(INIT, INIT+timedelta(hours=1),47.5,-53,(FIELD,)),now=NOW,inventory=True)
    assert len(result.native_times) == 3


def test_inventory_scope_cutoff_and_two_run_limit():
    calls=[]
    now=datetime(2026,9,8,12,tzinfo=UTC)
    def service(product,anchor):
        calls.append(anchor)
        return SimpleNamespace(config=SimpleNamespace(root_identity=str(anchor),initialization=anchor-timedelta(hours=1)))
    def axis(service):
        run=service.config.initialization
        return ([run+timedelta(hours=h) for h in range(1,361)],[],now+timedelta(seconds=60))
    result=inventory('WeatherNext 3 historical',now-timedelta(days=7),now,now=now,service_for=service,axis_for=axis)
    assert len(calls)==2
    assert result.frames and all(frame.valid_time < now-timedelta(hours=48) for frame in result.frames)
    assert any('48 hours' in note for note in result.notices)


def test_inventory_missing_runs_are_not_scheduled_dots():
    def missing(*args):raise ValueError('not published')
    result=inventory('WeatherNext 3 local',INIT,INIT+timedelta(hours=6),now=NOW,service_for=missing)
    assert result.frames==[] and len(result.notices)==3


def test_inventory_refuses_unbounded_window():
    with pytest.raises(ValueError):inventory('WeatherNext 3 local',INIT,INIT+timedelta(days=16))


def test_route_validates_source_scope_and_aware_window(monkeypatch):
    app=importlib.import_module('weather_api.app')
    client=TestClient(app.app)
    path='/api/experiments/weather/v0/sources/google-weathernext-3-statistics/times'
    params={'product':'WeatherNext 3 local','field':'weathernext3_total_cloud_cover_mean','start':INIT.isoformat(),'end':(INIT+timedelta(hours=6)).isoformat()}
    assert client.get(path,params={**params,'field':'temperature_2m'}).status_code==422
    assert client.get(path,params={**params,'start':'2026-08-01T00:00:00'}).status_code==422
    monkeypatch.setattr(app,'configured_mode',lambda:app.LIVE_MODE)
    times=importlib.import_module('weather_api.source_times')
    monkeypatch.setattr(times,'inventory',lambda p,s,e: inventory(p,s,e,now=NOW,service_for=lambda *_:(_ for _ in ()).throw(ValueError())))
    response=client.get(path,params=params)
    assert response.status_code==200 and response.json()['frames']==[]


def test_default_linux_inventory_bridge_without_science(transport):
    import sys
    if sys.platform!='linux':pytest.skip('bounded worker proof runs in Linux')
    from weather_api.weathernext_gcs_bridge import read_historical_point
    from weather_api.weathernext_native import BUCKET
    root=transport.describe(BUCKET,'weathernext_3_0_0_statistics/zarr/2026_to_present/20260801_00hr_01_preds/predictions.zarr/zarr.json',timeout=1)
    result=read_historical_point(selection(),root_identity=root,now=NOW,transport=transport,inventory=True,max_received_bytes=1024**2,timeout=30)
    assert len(result['reading']['native_times'])==3
    assert result['receipt']['worker_operations']==6
    assert not any(name.startswith(FIELD) for op,name in transport.calls)


def test_run_axis_coalesces_and_expires(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    module=importlib.import_module('weather_api.source_times')
    from weather_api.weathernext_native import ObjectIdentity
    module._cache.clear()
    clock=[0.0]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    root=ObjectIdentity('weathernext3_statistics_spatial','fixture','42','etag',10)
    service=SimpleNamespace(_scope_label='historical',config=SimpleNamespace(root_identity=root,initialization=INIT,gcloud_profile='astraeus'),_utcnow=lambda:NOW)
    entered=threading.Event();release=threading.Event();calls=[]
    def acquire(*args,**kwargs):
        calls.append(kwargs)
        entered.set();assert release.wait(5)
        return {'reading':{'native_times':[(INIT+timedelta(hours=h)).isoformat() for h in (1,2,3)],'objects':[]}}
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(module.run_axis,service,acquire=acquire)
        assert entered.wait(5)
        second=pool.submit(module.run_axis,service,acquire=acquire)
        release.set()
        assert first.result()==second.result()
    module.run_axis(service,acquire=acquire)
    assert len(calls)==1 and calls[0]['inventory'] and calls[0]['max_received_bytes']==1024**2
    clock[0]=61
    module.run_axis(service,acquire=acquire)
    assert len(calls)==2
    module._cache.clear()
