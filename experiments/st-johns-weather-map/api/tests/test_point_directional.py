"""Selected-layer-point-data directional, capability and radar scenarios."""
from datetime import UTC, datetime, timedelta
from dataclasses import replace
import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from ingest.adapters.eccc_geomet import GeoMetSample, RADAR_RAIN_LAYER, RADAR_SNOW_LAYER
from weather_api.point_time import choose_native_time
from weather_api.native_runs import RunUnavailable
from weather_api.radar_delivery import RadarSource
from weather_api.source_delivery import source_capabilities
from weather_api import wms

AT = datetime(2026, 9, 8, 12, tzinfo=UTC)


@pytest.mark.parametrize('kind,offset,expected', [('observation',0,0),('forecast',0,0),('observation',1,0),('forecast',1,6),('observation',-1,-6),('forecast',-1,0)])
def test_native_boundaries(kind, offset, expected):
    times = [AT + timedelta(minutes=i) for i in (-6,0,6)]
    assert choose_native_time(times, AT+timedelta(minutes=offset), kind) == AT+timedelta(minutes=expected)


@pytest.mark.parametrize('kind,selected', [('observation',AT-timedelta(minutes=1)),('forecast',AT+timedelta(minutes=1))])
def test_no_wrong_side_or_stale_fallback(kind, selected):
    with pytest.raises(RunUnavailable):
        choose_native_time([AT], selected, kind)
    with pytest.raises(RunUnavailable):
        choose_native_time([AT], AT+timedelta(minutes=21), 'observation', max_age=timedelta(minutes=20))


class RadarFixture:
    def __init__(self, rain=2.5, snow=.4, classification=None):
        self.calls = []
        self.rain, self.snow, self.classification = rain, snow, classification
    def time_dimension(self, layer):
        return (AT-timedelta(minutes=6), AT)
    def feature_info(self, layer, latitude, longitude, *, valid_time, resolve):
        self.calls.append((layer,latitude,longitude,valid_time,resolve))
        value = self.rain if layer == RADAR_RAIN_LAYER else self.snow
        if isinstance(value, Exception): raise value
        if value is None: return None
        units = 'mm h-1' if layer == RADAR_RAIN_LAYER else 'cm h-1'
        return GeoMetSample(layer,value,valid_time,None,units,units,True,47.5,-52.7,'Native radar',self.classification,latitude,longitude)


@pytest.fixture
def radar(monkeypatch):
    fixture = RadarFixture()
    monkeypatch.setattr(wms,'geomet_client',lambda:fixture)
    return fixture


@pytest.mark.parametrize('rain,snow,classification,expected', [(2.5,.4,None,[2.5,.4,1]),(0,0,'Undetected',[None,None,0]),(None,None,None,[None,None,None]),(RuntimeError('failed'),None,None,[None,None,None]),(0,None,'Undetected',[None,None,None])])
def test_radar_numeric_no_echo_coverage_and_failure(radar,rain,snow,classification,expected):
    radar.rain,radar.snow,radar.classification = rain,snow,classification
    fields = RadarSource().read_point(47.5,-52.7,AT)
    assert [f.value for f in fields] == expected
    assert [f.provenance.normalized_units for f in fields] == ['mm h-1','cm h-1','flag']
    assert len(radar.calls) == 2
    assert all(f.provenance.run_time is None and f.provenance.valid_time == AT for f in fields)


def test_radar_directional_http_and_legacy_exact(monkeypatch,data_mode,radar):
    app = importlib.import_module('weather_api.app')
    monkeypatch.setattr(app,'now',lambda:AT)
    data_mode('live')
    params = dict(latitude=47.5,longitude=-52.7,product='Radar',valid_time=(AT+timedelta(minutes=2)).isoformat(),time_selection='directional')
    client = TestClient(app.app)
    response = client.get(app.PREFIX+'/point',params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['time_selection'] == 'directional'
    assert datetime.fromisoformat(body['valid_time']) == AT+timedelta(minutes=2)
    assert body['data_mode'] == 'live'
    assert {datetime.fromisoformat(f['provenance']['valid_time']) for f in body['fields']} == {AT}
    count = len(radar.calls)
    params['valid_time'] = (AT+timedelta(minutes=21)).isoformat()
    assert client.get(app.PREFIX+'/point',params=params).json()['data_mode'] == 'unavailable'
    assert len(radar.calls) == count
    import weather_api.observation_companions as companions
    monkeypatch.setattr(companions,'with_aqhi_observation',lambda _:pytest.fail('Radar must not acquire forecast companions'))
    params.pop('time_selection');params['valid_time']=AT.isoformat()
    legacy = client.get(app.PREFIX+'/point',params=params).json()
    assert legacy['time_selection'] is None
    assert legacy['fields'][0]['value'] == 2.5


def test_capabilities_do_not_infer_numeric_support_from_imagery():
    assert {c.field for c in source_capabilities('eccc-radar')} == {'precipitation_rate','snow_rate','radar_echo'}
    assert all(c.point_time_kind == 'observation' and c.directional_time_selection for c in source_capabilities('eccc-radar'))
    assert source_capabilities('noaa-goes-east') == []
    assert all(c.point_time_kind == 'forecast' for c in source_capabilities('eccc-hrdps'))


def test_forecast_resolves_declared_native_frame_and_pins_run(monkeypatch,data_mode):
    from weather_api import point_time
    from weather_api.source_delivery import ForecastSource
    from weather_api.fixtures import point_fields
    app = importlib.import_module('weather_api.app')
    monkeypatch.setattr(app,'now',lambda:AT)
    field = point_fields(AT)[0][0].model_copy(deep=True)
    field.provenance.source_id='eccc-hrdps';field.provenance.valid_time=AT+timedelta(hours=1)
    field.provenance.freshness.status='fresh';field.provenance.quality.status='passed'
    calls=[]
    coordinator=SimpleNamespace(run_inventory=lambda:[SimpleNamespace(provider_run_id='native-run',run_time=AT)],
        run_times=lambda _: [AT,AT+timedelta(hours=1)],
        point_fields=lambda *args,**kwargs:(calls.append((args,kwargs)) or [field],None,[]))
    reader=ForecastSource('eccc-hrdps','hrdps',lambda:coordinator,('temperature_2m',),named_runs=True)
    monkeypatch.setattr(point_time,'source_readers',lambda:{reader.source_id:reader})
    data_mode('live')
    result=point_time.directional_point(47.5,-52.7,AT+timedelta(minutes=1),'HRDPS')
    assert result.fields and result.fields[0].provenance.valid_time == AT+timedelta(hours=1)
    assert calls[0][0][2] == AT+timedelta(hours=1)
    assert calls[0][1] == {'run_id':'native-run'}
    field.provenance.valid_time=AT
    assert not point_time.directional_point(47.5,-52.7,AT+timedelta(minutes=1),'HRDPS').fields
    field.provenance.valid_time=AT+timedelta(hours=1);field.provenance.freshness.status='stale'
    assert not point_time.directional_point(47.5,-52.7,AT+timedelta(minutes=1),'HRDPS').fields


def test_radar_reuses_native_client_and_discovery_cache(monkeypatch,tmp_path):
    from test_adapter_eccc_geomet import radar_service, NOW
    from ingest.adapters.eccc_geomet import GeoMetClient
    service=radar_service()
    client=service.client()
    monkeypatch.setattr(wms,'geomet_client',lambda:client)
    reader=RadarSource()
    native=reader.resolve_point_time(NOW+timedelta(minutes=1))
    fields=reader.read_point(47.5615,-52.7126,native)
    assert [field.value for field in fields] == [None,None,0]
    reader.resolve_point_time(NOW+timedelta(minutes=2))
    assert len([url for url in service.requests if url.params.get('request')=='GetCapabilities']) == 2
    assert len([url for url in service.requests if url.params.get('request')=='GetFeatureInfo']) == 2
    assert not [url for url in service.requests if url.params.get('request')=='GetMap']


@pytest.mark.parametrize('change',[{'valid_time':AT-timedelta(minutes=6)},{'units':'K'},{'value':float('inf')}])
def test_radar_refuses_wrong_native_time_units_and_nonfinite(radar,change):
    original=radar.feature_info
    radar.feature_info=lambda *a,**kw:replace(original(*a,**kw),**change)
    assert all(field.value is None for field in RadarSource().read_point(47.5,-52.7,AT))


def test_directional_refuses_unpublished_discovery_and_unknown_policy(data_mode):
    app=importlib.import_module('weather_api.app');data_mode('live')
    client=TestClient(app.app)
    params=dict(latitude=47.5,longitude=-52.7,product='SWOB',valid_time=AT.isoformat(),time_selection='directional')
    body=client.get(app.PREFIX+'/point',params=params).json()
    assert body['data_mode']=='unavailable'
    assert 'Native time selection unavailable' in body['selection']['reason']
    params['time_selection']='nearest'
    assert client.get(app.PREFIX+'/point',params=params).status_code==422


def test_ecmwf_directional_uses_published_exact_frame(monkeypatch,data_mode):
    from test_ecmwf_query import Fixture, coordinator, RUN
    from test_source_point_integration import native_fixture
    import weather_api.ecmwf_query as module
    app=importlib.import_module('weather_api.app');data_mode('live')
    monkeypatch.setattr(app,'now',lambda:RUN)
    import weather_api.store as store
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return RUN
    monkeypatch.setattr(store,'datetime',Clock)
    service=coordinator(Fixture('ecmwf-ifs'),decoder=native_fixture)
    monkeypatch.setattr(module,'ecmwf_query_coordinator',lambda source_id:service)
    client=TestClient(app.app)
    params=dict(latitude=47.5,longitude=-52.75,product='IFS',valid_time=(RUN-timedelta(minutes=1)).isoformat(),time_selection='directional')
    body=client.get(app.PREFIX+'/point',params=params).json()
    assert body['data_mode']=='live',body
    assert {datetime.fromisoformat(f['provenance']['valid_time']) for f in body['fields']}=={RUN}
    params['valid_time']=(RUN+timedelta(minutes=1)).isoformat()
    assert client.get(app.PREFIX+'/point',params=params).json()['data_mode']=='unavailable'

def test_radar_preserves_ogc_fault_code_without_fabricating_a_value(radar):
    from ingest.adapters.eccc_geomet import GeoMetServiceException
    radar.rain=GeoMetServiceException('RADAR_1KM_RRAI: NoMatch: request time unavailable')
    radar.snow=None
    fields=RadarSource().read_point(47.5,-52.7,AT)
    assert fields[0].value is None
    assert 'geomet_NoMatch' in fields[0].provenance.quality.flags
    assert fields[2].value is None
