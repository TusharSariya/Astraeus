"""All surface mappings use constructed receipts, no provider network."""
from copy import deepcopy
from datetime import timedelta
import pytest
from registry.weathernext import SURFACE_FIELDS
from ingest.adapters.weathernext3_statistics import EXPECTED_FIELDS, _expected_unit
from test_weathernext_delivery import payload, service, INIT, VALID

@pytest.mark.parametrize('mapping',SURFACE_FIELDS,ids=lambda m:m.native)
def test_all_surface_identities_units_and_statistics(payload,mapping):
    assert mapping.native in EXPECTED_FIELDS
    assert mapping.native_unit == _expected_unit(mapping.native)
    p=deepcopy(payload)
    for obj in p['reading']['objects']+p['receipt']['http_objects']:
        obj['name']=obj['name'].replace('temperature_2m_mean',mapping.native).replace('0p1',mapping.grid)
    value=.5 if mapping.family=='cloud_cover' else 280.0 if mapping.native_unit=='K' else 1.0
    p['reading']['values'][0].update(field=mapping.native,unit=mapping.native_unit,grid=mapping.grid,
        statistic=mapping.native.rsplit('_',1)[1],value=value)
    f=service(p).read_point(47.5,-52.7,VALID,field=mapping.key)[0]
    assert f.key==mapping.key and f.value==pytest.approx(value*mapping.scale+mapping.offset)
    assert f.provenance.native_variable==mapping.native
    assert f.provenance.original_units==mapping.native_unit
    assert f.provenance.ensemble.statistic==mapping.statistic
    assert f.provenance.ensemble.quantile==mapping.quantile
    assert f.provenance.ensemble.computed_here is False
    p['reading']['values'][0]['value']=None
    assert service(p).read_point(47.5,-52.7,VALID,field=mapping.key)[0].value is None


def test_complete_descriptors_and_directional_boundaries(payload):
    reader=service(payload)
    assert len(reader.descriptors())==126
    assert len({c.field for c in reader.descriptors()})==126
    assert reader.resolve_point_time(VALID)==VALID
    assert reader.resolve_point_time(VALID-timedelta(seconds=1))==VALID
    assert reader.resolve_point_time(VALID+timedelta(seconds=1))==VALID+timedelta(hours=1)
    with pytest.raises(ValueError):reader.resolve_point_time(INIT+timedelta(days=16))


def test_directional_api_retains_historical_evidence(payload,monkeypatch):
    import importlib
    import weather_api.weathernext_configuration as config
    app_module=importlib.import_module('weather_api.app')
    from weather_api.weathernext_delivery import directional_surface_point
    monkeypatch.setattr(app_module,'configured_mode',lambda:app_module.LIVE_MODE)
    monkeypatch.setattr(config,'weathernext_historical_service',lambda:service(payload))
    selected=VALID-timedelta(minutes=12)
    response=directional_surface_point(47.5,-52.7,selected,'WeatherNext 3 historical',statistic='ensemble_mean')
    assert response.valid_time==selected and response.fields[0].provenance.valid_time==VALID
    assert response.fields[0].value==pytest.approx(6.85)


def test_published_run_discovery_is_bounded_and_never_bills():
    from weather_api.weathernext_runs import discover_configuration
    from weather_api.weathernext_native import ObjectIdentity
    calls=[]
    class Transport:
        def describe(self,bucket,name,*,timeout):
            calls.append((bucket,name,timeout))
            if len(calls)==1:raise ValueError('unpublished')
            return ObjectIdentity(bucket,name,'123','etag',182540)
    config=discover_configuration(VALID,'astraeus',internal=False,now=VALID,transport=Transport())
    assert len(calls)==2
    assert config.initialization==INIT-timedelta(hours=6)
    assert 0<calls[0][2]<=15
    assert all(c[0]=='weathernext3_statistics_spatial' for c in calls)
    calls.clear()
    class Missing:
        def describe(self,*args,**kwargs):calls.append(args);raise ValueError('missing')
    with pytest.raises(ValueError):discover_configuration(VALID,'astraeus',internal=False,now=VALID,transport=Missing())
    assert len(calls)==4


def test_http_rejects_field_and_statistic_mismatch_before_acquisition(monkeypatch):
    from fastapi.testclient import TestClient
    from weather_api.app import app
    client=TestClient(app)
    base={'product':'WeatherNext 3 local','valid_time':VALID.isoformat(),'time_selection':'directional'}
    for extra in ({'field':'not-published'},{'field':'temperature_2m','member':'0'},
                  {'field':'temperature_2m','quantile':.9},{'field':'temperature_2m','statistic':'ensemble_spread'}):
        assert client.get('/api/experiments/weather/v0/point',params=base|extra).status_code==422
    assert client.get('/api/experiments/weather/v0/point',params=base|{'product':'HRDPS','field':'temperature_2m'}).status_code==422
