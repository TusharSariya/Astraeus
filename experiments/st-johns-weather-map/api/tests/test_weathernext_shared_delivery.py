"""WeatherNext shared API uses configured historical evidence only; no provider I/O."""
from dataclasses import asdict
from datetime import timedelta
import importlib
import json

from fastapi.testclient import TestClient
import pytest

from test_weathernext_delivery import payload, service, INIT, VALID, NOW
from weather_api.weathernext_gcs_bridge import ROOT
from weather_api.weathernext_configuration import CONFIG_ENV, load_historical_configuration, historical_configuration_status
from weather_api.source_delivery import source_readers, source_configuration

SOURCE='google-weathernext-3-statistics'
PRODUCT='WeatherNext 3 historical'


@pytest.fixture
def configured(monkeypatch,tmp_path):
    path=tmp_path/'historical.json'
    path.write_text(json.dumps({'initialization':INIT.isoformat(),'root_identity':asdict(ROOT),'gcloud_profile':'astraeus'}))
    monkeypatch.setenv(CONFIG_ENV,str(path))
    return path


def test_safe_missing_and_invalid_configuration(monkeypatch,tmp_path):
    monkeypatch.delenv(CONFIG_ENV,raising=False)
    assert source_configuration(SOURCE).state=='missing_configuration'
    path=tmp_path/'nonsecret.json';path.write_text('private malformed configuration')
    monkeypatch.setenv(CONFIG_ENV,str(path))
    status=historical_configuration_status()
    assert status.state=='missing_configuration' and 'private' not in status.model_dump_json()
    path.write_text('x'*16385)
    assert historical_configuration_status().state=='missing_configuration'


def test_runtime_prerequisites_do_not_authenticate(configured,monkeypatch):
    module=importlib.import_module('weather_api.weathernext_configuration')
    assert load_historical_configuration().gcloud_profile=='astraeus'
    monkeypatch.setattr(module.shutil,'which',lambda _:None)
    assert historical_configuration_status().state=='product_unavailable'
    monkeypatch.setattr(module.shutil,'which',lambda _:'/runtime/tool')
    assert historical_configuration_status().state=='ready'


def test_catalogue_declares_point_without_config_or_acquisition(monkeypatch,data_mode):
    module=importlib.import_module('weather_api.weathernext_configuration')
    monkeypatch.delenv(CONFIG_ENV,raising=False)
    monkeypatch.setattr(module,'weathernext_historical_service',lambda:pytest.fail('catalogue must not acquire'))
    app=importlib.import_module('weather_api.app')
    body=TestClient(app.app).get(app.PREFIX+'/catalog').json()
    record=next(r for r in body['sources'] if r['id']==SOURCE)
    statuses=TestClient(app.app).get(app.PREFIX+'/sources/status').json()['statuses']
    assert next(s for s in statuses if s['source_id']==SOURCE)['configuration']['state']=='missing_configuration'
    assert not record['display_primary'] and not record['schedulable']
    assert record['capabilities'][0]['point_product']==PRODUCT
    assert record['capabilities'][0]['variants']==[{'kind':'provider_statistic','member':None,'statistic':'ensemble_mean','quantile':None,'threshold':None,'comparison':None}]


def test_shared_api_replays_exact_point_and_cache(configured,payload,monkeypatch,data_mode):
    module=importlib.import_module('weather_api.weathernext_configuration')
    reader=service(payload);calls=[]
    original=reader._acquire
    reader._acquire=lambda selection:(calls.append(selection),original(selection))[1]
    monkeypatch.setattr(module,'weathernext_historical_service',lambda:reader)
    app=importlib.import_module('weather_api.app')
    companion=importlib.import_module('weather_api.observation_companions')
    monkeypatch.setattr(companion,'with_aqhi_observation',lambda *_:pytest.fail('historical source must not acquire AQHI'))
    shared=importlib.import_module('weather_api.source_delivery')
    readers=shared.source_readers()
    for source_id,other in readers.items():
        if source_id!=SOURCE:
            monkeypatch.setattr(other,'read_point',lambda *a,**k:pytest.fail('unrelated source acquired'))
    monkeypatch.setattr(shared,'source_readers',lambda:readers)
    monkeypatch.setattr(app,'now',lambda:NOW)
    data_mode('live')
    client=TestClient(app.app)
    params={'latitude':47.5,'longitude':-52.7,'valid_time':VALID.isoformat(),'product':PRODUCT,'statistic':'ensemble_mean'}
    response=client.get(app.PREFIX+'/point',params=params)
    assert response.status_code==200,response.text
    body=response.json()
    assert body['selection']['mode']=='evidence_only' and len(body['fields'])==1
    point=body['fields'][0]
    assert point['value']==pytest.approx(6.85)
    assert point['provenance']['source_id']==SOURCE and point['provenance']['native_variable']=='temperature_2m_mean'
    assert point['provenance']['valid_time']==VALID.isoformat().replace('+00:00','Z')
    assert point['provenance']['ensemble']['computed_here'] is False
    assert not body['observation_unavailable']
    assert client.get(app.PREFIX+'/point',params=params).json()['fields']==body['fields']
    assert len(calls)==1


@pytest.mark.parametrize('changes',[{'valid_time':(NOW-timedelta(hours=48)).isoformat()}, {'valid_time':(VALID+timedelta(minutes=1)).isoformat()},
    {'valid_time':(INIT-timedelta(hours=1)).isoformat()},{'valid_time':None},{'member':'0'},{'statistic':'ensemble_spread'},{'quantile':.9}])
def test_unsupported_identity_refused_before_acquisition(configured,monkeypatch,data_mode,changes):
    module=importlib.import_module('weather_api.weathernext_configuration')
    monkeypatch.setattr(module,'weathernext_historical_service',lambda:pytest.fail('must not acquire'))
    app=importlib.import_module('weather_api.app');monkeypatch.setattr(app,'now',lambda:NOW);data_mode('live')
    params={'latitude':47.5,'longitude':-52.7,'valid_time':VALID.isoformat(),'product':PRODUCT}
    params.update(changes)
    if params['valid_time'] is None:del params['valid_time']
    assert TestClient(app.app).get(app.PREFIX+'/point',params=params).status_code==422


def test_unconfigured_history_is_unavailable_not_substituted(monkeypatch,data_mode):
    monkeypatch.delenv(CONFIG_ENV,raising=False)
    app=importlib.import_module('weather_api.app');monkeypatch.setattr(app,'now',lambda:NOW);data_mode('live')
    body=TestClient(app.app).get(app.PREFIX+'/point',params={'latitude':47.5,'longitude':-52.7,'valid_time':VALID.isoformat(),'product':PRODUCT}).json()
    assert body['data_mode']=='unavailable' and body['fields']==[]


def test_access_denial_survives_delivery_and_cooldown(configured,payload,monkeypatch,data_mode):
    import httpx
    from weather_api.weathernext_gcs_bridge import BridgeUnavailable
    module=importlib.import_module('weather_api.weathernext_configuration')
    monkeypatch.setattr(module.shutil,'which',lambda _:'/runtime/tool')
    reader=service(payload);calls=[]
    def denied(_):
        calls.append(1)
        error=BridgeUnavailable('safe refusal');error.http_status=403
        raise error
    reader._acquire=denied
    monkeypatch.setattr(module,'weathernext_historical_service',lambda:reader)
    for _ in range(2):
        with pytest.raises(httpx.HTTPStatusError):source_readers()[SOURCE].read_point(47.5,-52.7,VALID)
        status=source_configuration(SOURCE)
        assert status.state=='access_denied' and 'token' not in status.reason
    assert len(calls)==1


def test_http_worker_denial_code_is_redacted(monkeypatch,capsys):
    import io,sys
    from weather_api.weathernext_gcs_worker import http_main
    from weather_api.weathernext_gcs import WeatherNextGCSTransport,GCSUnavailable
    document={'name':ROOT.name,'params':{'alt':'media'},'cap':256*1024,'timeout':1,'expected':asdict(ROOT),'profile':'astraeus'}
    monkeypatch.setattr(sys,'stdin',io.TextIOWrapper(io.BytesIO(json.dumps(document).encode())))
    def denied(*args,**kwargs):raise GCSUnavailable('private upstream details',403)
    monkeypatch.setattr(WeatherNextGCSTransport,'_get',denied)
    http_main()
    output=capsys.readouterr().out
    assert json.loads(output)['http_status']==403 and 'private' not in output


def test_http_denial_code_survives_child_protocol(monkeypatch):
    import subprocess,sys
    from weather_api import weathernext_gcs_bridge as bridge
    from weather_api.weathernext_gcs import GcloudProfileToken
    original=subprocess.Popen
    def response(*args,**kwargs):
        return original([sys.executable,'-c','import json;print(json.dumps({"error":"safe refusal","http_status":403}))'],**kwargs)
    monkeypatch.setattr(bridge.subprocess,'Popen',response)
    transport=bridge.AccountedGCSTransport(token_provider=GcloudProfileToken('astraeus'))
    with pytest.raises(bridge.BridgeUnavailable) as caught:
        transport._subprocess_get(ROOT.name,{'alt':'media'},256*1024,5,ROOT)
    assert caught.value.http_status==403
