"""Actual shared HTTP replay; GOV-SPEC-001/004/005/006 experimental evidence."""
import importlib
import json
import os
from pathlib import Path
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from test_geps_delivery import setup
from test_geps_query import VALID

PREFIX = '/api/experiments/weather/v0'
PARAMS = dict(product='GEPS reductions', latitude=47.5, longitude=-52., valid_time=VALID.isoformat())


def test_actual_api_exact_variants_and_manifest(setup, monkeypatch, data_mode):
    service, calls, transport, _ = setup
    module = importlib.import_module('weather_api.app')
    monkeypatch.setattr(importlib.import_module('weather_api.geps_delivery'), 'geps_point_service', lambda: service)
    monkeypatch.setattr(module, 'now', lambda: VALID + timedelta(minutes=1))
    monkeypatch.setattr(importlib.import_module('weather_api.observation_companions'), 'with_aqhi_observation', lambda *_: pytest.fail('Unrelated acquisition'))
    data_mode('live')
    client = TestClient(module.app)
    catalog_response = client.get(PREFIX + '/catalog')
    assert catalog_response.status_code == 200
    assert client.get(PREFIX + '/sources/status').status_code == 200
    assert not calls
    cases = []
    for statistic, quantile, expected in [('ensemble_mean',None,1), ('ensemble_spread',None,1), ('ensemble_quantile',.5,2)]:
        params = {**PARAMS, 'statistic':statistic}
        if quantile is not None:
            params['quantile'] = quantile
        response = client.get(PREFIX + '/point', params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['data_mode'] == 'live' and body['selection']['mode'] == 'evidence_only'
        assert len(body['fields']) == expected
        for field in body['fields']:
            p = field['provenance']
            assert p['ensemble']['statistic'] == statistic and p['ensemble']['quantile'] == quantile
            assert p['ensemble']['computed_here'] is False and p['run_time'] is None and p['member'] is None
            assert p['source_acquisition']['provider_run_id'] is None and p['source_acquisition']['run_time'] is None
            assert len(p['source_acquisition']['transport_receipts']) == 11
            assert p['quality']['status'] == 'unknown' and p['source_display_primary'] is False
            assert field['storage'] == 'available-not-stored'
            assert (p['sampled_latitude'],p['sampled_longitude']) == (47.25,-51.75)
            assert 'fifth_reduction_uncatalogued' in p['quality']['flags']
        assert client.get(PREFIX + '/point', params=params).json()['fields'] == body['fields']
        cases.append(dict(product='GEPS reductions', statistic=statistic, quantile=quantile, params=params, point=body))
    assert len(calls) == 1 and len(transport.requests) == 11
    output = os.getenv('GEPS_FRONTEND_MANIFEST')
    if output:
        Path(output).write_text(json.dumps(dict(reference_time=(VALID+timedelta(minutes=1)).isoformat(), catalog=catalog_response.json(), cases=cases, basis='Offline actual HTTP replay with anonymous transport fixtures; no provider requests'), indent=2))


@pytest.mark.parametrize('extra', [{}, {'statistic':'ensemble_quantile'}, {'statistic':'ensemble_quantile','quantile':.9},
    {'statistic':'ensemble_mean','quantile':.5}, {'statistic':'ensemble_spread','member':'all'},
    {'statistic':'ensemble_mean','threshold':15}, {'statistic':'ensemble_mean','comparison':'ge'},
    {'statistic':'ensemble_threshold_probability','threshold':15,'comparison':'ge'},
    {'statistic':'ensemble_mean','run':'2026-09-05T00:00:00Z'}, {'statistic':'ensemble_mean','valid_time':'2026-09-05T12:30:00Z'},
    {'statistic':'ensemble_mean','valid_time':'2026-09-05T12:00:00'}, {'statistic':'ensemble_mean','valid_time':None}])
def test_unsupported_selection_refused_before_acquisition(extra, monkeypatch, data_mode):
    module = importlib.import_module('weather_api.app')
    monkeypatch.setattr(importlib.import_module('weather_api.geps_delivery'), 'geps_point_service', lambda: pytest.fail('Acquisition before refusal'))
    data_mode('live')
    params = {**PARAMS, **extra}
    if params.get('valid_time') is None:
        params.pop('valid_time')
    assert TestClient(module.app).get(PREFIX + '/point', params=params).status_code == 422


def test_provider_failure_remains_unavailable(monkeypatch, data_mode):
    module = importlib.import_module('weather_api.app')
    def fail():
        raise RuntimeError('untrusted internal error')
    monkeypatch.setattr(importlib.import_module('weather_api.geps_delivery'), 'geps_point_service', fail)
    data_mode('live')
    response = TestClient(module.app).get(PREFIX + '/point', params={**PARAMS,'statistic':'ensemble_mean'})
    assert response.status_code == 200
    assert response.json()['data_mode'] == 'unavailable' and response.json()['fields'] == []
    assert 'untrusted' not in response.text


def test_fixture_mode_does_not_synthesize_geps(data_mode):
    data_mode('fixture')
    module = importlib.import_module('weather_api.app')
    response = TestClient(module.app).get(PREFIX + '/point', params={**PARAMS,'statistic':'ensemble_mean'})
    assert response.status_code == 200
    assert response.json()['data_mode'] == 'unavailable'
    assert not response.json()['fields']


@pytest.mark.parametrize('product', ['WeatherNext 3 historical', 'OSTIA SST', 'GFS', None])
def test_explicit_run_cannot_be_ignored_by_other_products(product, monkeypatch, data_mode):
    module = importlib.import_module('weather_api.app')
    monkeypatch.setattr(module, '_live_point', lambda *_a, **_k: pytest.fail('Acquisition before run refusal'))
    data_mode('live')
    params = {**PARAMS, 'run':'other'}
    if product is None:
        params.pop('product')
    else:
        params['product'] = product
    assert TestClient(module.app).get(PREFIX + '/point', params=params).status_code == 422
