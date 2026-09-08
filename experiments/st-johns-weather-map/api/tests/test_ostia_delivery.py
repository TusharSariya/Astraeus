"""OSTIA named point delivery: native analysis, masks and isolated admission."""
from datetime import timedelta
import importlib
from fastapi.testclient import TestClient
import pytest

from test_ostia_query import DAY, service
from weather_api.ostia_delivery import OSTIASource


def test_descriptor_is_offline_and_has_no_run_or_series():
    source=OSTIASource(lambda:pytest.fail('descriptor acquired native data'))
    caps=source.descriptors()
    assert len(caps)==3
    assert {c.point_product for c in caps}=={'OSTIA SST'}
    assert all(c.point and not c.native_series and c.run_selection=='not_applicable' for c in caps)
    assert source.plan_series(DAY,DAY) is None
    with pytest.raises(ValueError,match='no selectable forecast runs'):
        source.read_point(47.5,-52,DAY,run='invented-run')


@pytest.mark.parametrize('age_hours',[0,36,96])
def test_http_native_time_units_masks_revision_and_repeat(monkeypatch,data_mode,age_hours):
    import weather_api.ostia_query as module
    from weather_api.source_delivery import source_readers
    app=importlib.import_module('weather_api.app')
    query,calls,_clock=service()
    monkeypatch.setattr(module,'ostia_query_service',lambda:query)
    monkeypatch.setattr(app,'now',lambda:DAY+timedelta(hours=age_hours))
    data_mode('live')
    client=TestClient(app.app)
    params={'latitude':48.0,'longitude':-52.1,'valid_time':DAY.isoformat(),'product':'OSTIA SST'}
    response=client.get(f'{app.PREFIX}/point',params=params)
    assert response.status_code==200,response.text
    body=response.json()
    assert body['data_mode']=='live' and body['operational'] is False
    assert body['selection']['mode']=='evidence_only'
    assert not body['observation_unavailable']
    assert [f['value'] for f in body['fields']]==pytest.approx([10,.25,9],abs=.0001)
    entry=query.query(DAY)
    for field in body['fields']:
        p=field['provenance']
        assert p['source_id']=='metoffice-ostia-sst'
        assert p['valid_time']==DAY.isoformat().replace('+00:00','Z')
        assert p['run_time'] is None and p['source_display_primary'] is False
        assert p['artifact_revision']==entry['provenance']['artifact_revision']
        assert field['storage']=='available-not-stored'
    assert body['fields'][0]['provenance']['original_units']=='kelvin'
    assert body['fields'][0]['provenance']['normalized_units']=='degC'
    assert body['fields'][2]['provenance']['normalized_units']=='flag'
    assert len(calls)==7
    assert client.get(f'{app.PREFIX}/point',params=params).json()['fields']==body['fields']
    assert len(calls)==7
    params.update(latitude=47.5,longitude=-52.1)
    assert [f['value'] for f in client.get(f'{app.PREFIX}/point',params=params).json()['fields']]==[None,None,2]
    assert len(calls)==7
    assert len(source_readers()['metoffice-ostia-sst'].descriptors())==3


def test_http_outside_window_refused_before_source(monkeypatch,data_mode):
    import weather_api.ostia_query as module
    app=importlib.import_module('weather_api.app')
    monkeypatch.setattr(module,'ostia_query_service',lambda:pytest.fail('invalid window acquired source'))
    monkeypatch.setattr(app,'now',lambda:DAY+timedelta(days=5))
    data_mode('live')
    response=TestClient(app.app).get(f'{app.PREFIX}/point',params={'latitude':47.5,'longitude':-52,'valid_time':DAY.isoformat(),'product':'OSTIA SST'})
    assert response.status_code==422


def test_native_float32_axis_precision_preserves_centres():
    import numpy as np
    from weather_api.ostia_query import _native_axis_cell, OSTIAUnavailable
    centres=np.array([45.025+.05*i for i in range(110)],dtype=np.float32)
    assert _native_axis_cell(float(centres[50]),centres)==50
    assert _native_axis_cell(44.9,centres)==-1
    changed=centres.copy()
    changed[50]+=.005
    with pytest.raises(OSTIAUnavailable,match='spacing changed'):
        _native_axis_cell(47.5,changed)
