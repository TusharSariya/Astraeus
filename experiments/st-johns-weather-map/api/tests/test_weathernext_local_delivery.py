"""Internal forecast scope and cache isolation; GOV-SPEC-004/GOV-SPEC-006."""
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

import pytest

from test_weathernext_delivery import payload
from weather_api.weathernext_delivery import (
    HistoricalConfiguration, LocalExperimentalConfiguration, WeatherNextHistoricalDelivery,
    WeatherNextLocalExperimentalDelivery, WeatherNextDeliveryUnavailable,
)
from weather_api.weathernext_native import ObjectIdentity
from weather_api import weathernext_configuration as config

INIT = datetime(2026, 9, 7, 18, tzinfo=UTC)
NOW = datetime(2026, 9, 8, tzinfo=UTC)
VALID = datetime(2026, 9, 8, 12, tzinfo=UTC)


@pytest.fixture
def local_payload(payload):
    payload['receipt']['acquisition_scope']='internal_experimental_forecast'
    original = payload['reading']['objects'][0]['name'].rsplit('/',1)[0]
    prefix = original.replace('20260801_00hr', '20260907_18hr')
    payload['reading'].update(initialization=INIT.isoformat(), valid_time=VALID.isoformat())
    for identity in payload['reading']['objects']:
        identity['name'] = identity['name'].replace(original,prefix)
    for receipt in payload['receipt']['http_objects']:
        receipt['name'] = receipt['name'].replace(original,prefix)
    return payload


def configuration(payload, cls=LocalExperimentalConfiguration):
    return cls(INIT,ObjectIdentity(**payload['reading']['objects'][0]),'astraeus')


def service(payload, **kwargs):
    return WeatherNextLocalExperimentalDelivery(configuration(payload), acquire=lambda _:deepcopy(payload),
        utcnow=lambda:NOW,data_mode='fixture',**kwargs)


def test_forward_mean_identity_unknown_freshness_and_local_terms(local_payload):
    evidence = service(local_payload).read_point(47.5,-52.7,VALID)[0]
    p = evidence.provenance
    assert evidence.value == pytest.approx(6.85)
    assert p.native_variable == 'temperature_2m_mean' and p.ensemble.statistic == 'ensemble_mean'
    assert p.original_units == 'K' and p.normalized_units == 'degC'
    assert p.ensemble.computed_here is False and p.member is None and p.ensemble.member_set is None
    assert p.run_time == INIT and p.valid_time == VALID
    assert p.run_stale is None and p.freshness.status == 'unknown'
    assert p.quality.status == 'unknown' and p.source_display_primary is False
    assert 'historical_forecast' not in p.quality.flags and 'internal_experimental_forecast' in p.quality.flags
    assert 'Real-Time' in p.licence and 'section 2(a)' in p.licence and '2026-09-03' in p.licence
    assert p.source_acquisition.expires_at == NOW + timedelta(seconds=60)


def test_historical_scope_still_refuses_same_future_selection(local_payload):
    historical = WeatherNextHistoricalDelivery(configuration(local_payload,HistoricalConfiguration),
        acquire=lambda _:pytest.fail('historical acquisition must remain forbidden'),utcnow=lambda:NOW)
    with pytest.raises(WeatherNextDeliveryUnavailable):
        historical.read_point(47.5,-52.7,VALID)


@pytest.mark.parametrize('selected', [VALID+timedelta(minutes=1), INIT-timedelta(hours=1), INIT+timedelta(hours=361)])
def test_invalid_native_hour_or_horizon_refused_before_acquisition(local_payload,selected):
    reader=service(local_payload)
    reader._acquire=lambda _:pytest.fail('invalid selection acquired')
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,selected)


def test_future_initialization_gate_applies_before_cache_and_after_acquisition(local_payload):
    reader=service(local_payload)
    reader.read_point(47.5,-52.7,VALID)
    reader._utcnow=lambda:INIT-timedelta(seconds=1)
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,VALID)
    reader=service(local_payload)
    times=iter([NOW,INIT-timedelta(seconds=1)])
    reader._utcnow=lambda:next(times)
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,VALID)
    assert not reader._entries


def test_local_null_and_unchanged_refresh_preserve_fixed_expiry(local_payload):
    local_payload['reading']['values'][0]['value']=None
    clock=[0.]
    reader=service(local_payload,clock=lambda:clock[0])
    first=reader.read_point(47.5,-52.7,VALID)[0]
    clock[0]=30
    assert reader.read_point(47.5,-52.7,VALID,refresh=True)[0] == first
    assert next(iter(reader._entries.values()))[1] == 60
    assert first.value is None and 'native_fill_mask' in first.provenance.quality.flags
    assert 'internal_experimental_forecast' in first.provenance.quality.flags
    clock[0]=60
    reader._acquire=lambda _:(_ for _ in ()).throw(RuntimeError('private auth detail'))
    with pytest.raises(WeatherNextDeliveryUnavailable,match='bounded local experimental acquisition failed') as caught:
        reader.read_point(47.5,-52.7,VALID)
    assert 'private' not in str(caught.value) and not reader._entries


def test_default_acquisition_uses_only_local_bridge_and_existing_cap(local_payload,monkeypatch):
    from weather_api import weathernext_gcs_bridge as bridge
    called=[]
    def read(selection,**kwargs):
        called.append((selection,kwargs))
        return deepcopy(local_payload)
    monkeypatch.setattr(bridge,'read_local_experimental_point',read,raising=False)
    reader=WeatherNextLocalExperimentalDelivery(configuration(local_payload),utcnow=lambda:NOW)
    assert reader.read_point(47.5,-52.7,VALID)[0].value == pytest.approx(6.85)
    assert len(called)==1 and called[0][1]['max_received_bytes']==1024**3
    assert called[0][1]['root_identity']==reader.config.root_identity
    assert called[0][1]['transport']._token_provider.profile=='astraeus'


def test_descriptor_supports_shared_unbound_wrapper():
    descriptor=WeatherNextLocalExperimentalDelivery.descriptors(SimpleNamespace())[0]
    assert descriptor.point_product=='WeatherNext 3 local'
    assert descriptor.variants[0].statistic=='ensemble_mean' and not descriptor.native_series
    assert descriptor.run_selection=='not_applicable'


def write_config(path, payload):
    path.write_text(json.dumps(asdict(configuration(payload)),default=str))


def test_configuration_and_service_caches_are_separate(local_payload,tmp_path,monkeypatch):
    path=tmp_path/'local.json';write_config(path,local_payload)
    monkeypatch.setenv(config.LOCAL_CONFIG_ENV,str(path))
    monkeypatch.delenv(config.CONFIG_ENV,raising=False)
    assert isinstance(config.load_local_experimental_configuration(),LocalExperimentalConfiguration)
    with pytest.raises(config.HistoricalConfigurationUnavailable):config.load_historical_configuration()
    monkeypatch.setenv(config.CONFIG_ENV,str(path))
    local=config.weathernext_local_experimental_service()
    history=config.weathernext_historical_service()
    assert local is not history and local._entries is not history._entries
    assert local is config.weathernext_local_experimental_service()
    assert type(history) is WeatherNextHistoricalDelivery


def test_local_configuration_missing_invalid_and_runtime_status_do_not_authenticate(local_payload,tmp_path,monkeypatch):
    monkeypatch.delenv(config.LOCAL_CONFIG_ENV,raising=False)
    assert config.local_experimental_configuration_status().required_environment==[config.LOCAL_CONFIG_ENV]
    path=tmp_path/'local.json';path.write_text('private invalid data')
    monkeypatch.setenv(config.LOCAL_CONFIG_ENV,str(path))
    with pytest.raises(config.HistoricalConfigurationUnavailable) as caught:config.load_local_experimental_configuration()
    assert 'private' not in str(caught.value)
    path.write_text('x'*16385)
    assert config.local_experimental_configuration_status().state=='missing_configuration'
    write_config(path,local_payload)
    monkeypatch.setattr(config.shutil,'which',lambda _:None)
    assert config.local_experimental_configuration_status().state=='product_unavailable'
    monkeypatch.setattr(config.shutil,'which',lambda _:'/runtime/tool')
    assert config.local_experimental_configuration_status().state=='ready'


@pytest.mark.parametrize('scope',[None,'historical','unknown'])
def test_local_receipt_scope_cannot_be_fabricated(local_payload,scope):
    local_payload['receipt']['acquisition_scope']=scope
    with pytest.raises(WeatherNextDeliveryUnavailable):service(local_payload).read_point(47.5,-52.7,VALID)
