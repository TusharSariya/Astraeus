"""Current forecast reaches the shared API without historical or model substitution."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
import importlib
import json

from fastapi.testclient import TestClient
import pytest
from test_weathernext_delivery import payload, NOW
from weather_api.weathernext_gcs_bridge import ROOT
from weather_api.weathernext_delivery import HistoricalConfiguration, WeatherNextLocalExperimentalDelivery

SOURCE = 'google-weathernext-3-statistics'
PRODUCT = 'WeatherNext 3 local'
VALID = NOW + timedelta(hours=12)


@pytest.fixture
def local_reader(payload, monkeypatch, tmp_path, data_mode):
    old_prefix = ROOT.name.rsplit('/', 1)[0]
    new_prefix = old_prefix.replace('20260801_00hr_01_preds', '20260908_00hr_01_preds')
    root = replace(ROOT, name=new_prefix + '/zarr.json')
    payload = deepcopy(payload)
    payload['receipt']['acquisition_scope'] = 'internal_experimental_forecast'
    payload['reading']['initialization'] = NOW.isoformat()
    payload['reading']['valid_time'] = VALID.isoformat()
    for item in payload['reading']['objects']:
        item['name'] = item['name'].replace(old_prefix, new_prefix)
    for item in payload['receipt']['http_objects']:
        item['name'] = item['name'].replace(old_prefix, new_prefix)
    configuration = HistoricalConfiguration(NOW, root, 'astraeus')
    calls = []
    reader = WeatherNextLocalExperimentalDelivery(configuration,
        acquire=lambda selection: (calls.append(selection), deepcopy(payload))[1],
        utcnow=lambda: NOW, data_mode='fixture')
    config = tmp_path / 'local.json'
    config.write_text(json.dumps({'initialization': NOW.isoformat(), 'root_identity': asdict(root), 'gcloud_profile': 'astraeus'}))
    monkeypatch.setenv('WEATHER_WEATHERNEXT_LOCAL_CONFIG', str(config))
    module = importlib.import_module('weather_api.weathernext_configuration')
    monkeypatch.setattr(module, 'weathernext_local_experimental_service', lambda: reader)
    monkeypatch.setattr(module, 'weathernext_historical_service', lambda: pytest.fail('historical substitution'))
    companion = importlib.import_module('weather_api.observation_companions')
    monkeypatch.setattr(companion, 'with_aqhi_observation', lambda *_: pytest.fail('unrelated observation acquisition'))
    app = importlib.import_module('weather_api.app')
    monkeypatch.setattr(app, 'now', lambda: NOW)
    data_mode('live')
    return TestClient(app.app), app.PREFIX, calls


def test_future_read_and_cache_preserve_native_identity(local_reader):
    client, prefix, calls = local_reader
    params = {'product': PRODUCT, 'latitude':47.5, 'longitude':-52.7, 'valid_time': VALID.isoformat()}
    first = client.get(prefix+'/point', params=params)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body['selection']['mode'] == 'evidence_only'
    field = body['fields'][0]
    assert field['value'] == pytest.approx(6.85)
    provenance = field['provenance']
    assert provenance['source_id'] == SOURCE
    assert provenance['valid_time'] == VALID.isoformat().replace('+00:00', 'Z')
    assert provenance['run_time'] == NOW.isoformat().replace('+00:00', 'Z')
    assert 'historical_forecast' not in provenance['quality']['flags']
    assert provenance['source_display_primary'] is False
    assert provenance['ensemble']['computed_here'] is False
    assert client.get(prefix+'/point', params=params).json()['fields'] == body['fields']
    assert len(calls) == 1
    catalogue = client.get(prefix+'/catalog').json()
    source = next(row for row in catalogue['sources'] if row['id'] == SOURCE)
    assert {cap['point_product'] for cap in source['capabilities']} == {PRODUCT, 'WeatherNext 3 historical'}


@pytest.mark.parametrize('changes', [
    {'valid_time': None}, {'valid_time': (VALID+timedelta(minutes=1)).isoformat()},
    {'member': '0'}, {'statistic':'ensemble_spread'}, {'quantile':0.5}, {'run':'other'},
    {'valid_time':(NOW+timedelta(days=16)).isoformat()},
])
def test_invalid_forecast_identity_refuses_before_io(local_reader, changes):
    client, prefix, calls = local_reader
    params = {'product': PRODUCT, 'latitude':47.5, 'longitude':-52.7, 'valid_time':VALID.isoformat()}
    params.update(changes)
    params = {key:value for key,value in params.items() if value is not None}
    assert client.get(prefix+'/point', params=params).status_code == 422
    assert calls == []


def test_private_token_file_can_configure_linux_without_gcloud(local_reader, monkeypatch, tmp_path):
    module = importlib.import_module('weather_api.weathernext_configuration')
    token = tmp_path / 'token'
    token.write_text('synthetic-test-token')
    token.chmod(0o600)
    monkeypatch.setenv('WEATHER_WEATHERNEXT_ACCESS_TOKEN_FILE', str(token))
    monkeypatch.setattr(module.shutil, 'which', lambda _: None)
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    assert module.local_experimental_configuration_status().state == 'ready'
    token.chmod(0o644)
    denied = module.local_experimental_configuration_status()
    assert denied.state == 'missing_configuration'
    assert 'synthetic-test-token' not in denied.model_dump_json()
