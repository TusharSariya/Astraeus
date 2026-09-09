"""Historical temperature provider mean; fixtures never authenticate or fetch."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC,datetime,timedelta
import hashlib
import threading

import pytest

from weather_api.weathernext_delivery import HistoricalConfiguration, WeatherNextHistoricalDelivery, WeatherNextDeliveryUnavailable, NATIVE_FIELD
from weather_api.weathernext_gcs_bridge import ROOT

NOW=datetime(2026,9,8,tzinfo=UTC)
INIT=datetime(2026,8,1,tzinfo=UTC)
VALID=INIT+timedelta(hours=6)


@pytest.fixture
def payload():
    prefix=ROOT.name.rsplit('/',1)[0]+'/'
    identities=[asdict(ROOT)]
    for name in ['init_time/c','lat_0p1/c/0','lead_time/c/0','lon_0p1/c/0',NATIVE_FIELD+'/c/5/0/0']:
        identities.append(dict(bucket=ROOT.bucket,name=prefix+name,generation='42',etag='fixture-etag',size=4))
    operations=[]
    for identity in identities:
        operations.append(dict(name=identity['name'],kind='media',generation=identity['generation'],bytes=identity['size'],
                               sha256=hashlib.sha256(identity['name'].encode()).hexdigest(),completed_at=NOW.isoformat()))
    count=sum(x['size'] for x in identities)
    return {'reading':{'initialization':INIT.isoformat(),'valid_time':VALID.isoformat(),
            'values':[dict(field=NATIVE_FIELD,value=280.0,unit='K',statistic='mean',grid='0p1',latitude=47.5,longitude=-52.7)],
            'objects':identities,'received_bytes':count,'pressure_level':None,'member':None},
            'receipt':{'http_objects':operations,'http_response_bytes':count}}


def service(payload,**kwargs):
    return WeatherNextHistoricalDelivery(HistoricalConfiguration(INIT,ROOT,'astraeus'),acquire=lambda _:deepcopy(payload),utcnow=lambda:NOW,data_mode='fixture',**kwargs)


def test_consumable_point_and_descriptor(payload):
    reader=service(payload)
    point=reader.read_point(47.5,-52.7,VALID)[0]
    assert point.provenance.native_variable==NATIVE_FIELD
    assert point.key=='temperature_2m' and point.value==pytest.approx(6.85)
    assert point.provenance.original_units=='K' and point.provenance.normalized_units=='degC'
    assert point.provenance.ensemble.statistic=='ensemble_mean' and not point.provenance.ensemble.computed_here
    assert point.provenance.member is None and point.provenance.ensemble.member_set is None
    assert point.provenance.quality.status=='unknown' and point.provenance.source_display_primary is False
    assert point.provenance.run_time==INIT and point.provenance.valid_time==VALID
    assert point.provenance.source_acquisition.normalized_sha256==point.provenance.artifact_revision
    assert reader.descriptors()[0].variants[0].kind=='provider_statistic'
    assert reader.configuration().state=='ready' and reader.plan_series(INIT,VALID) is None
    assert point.model_validate_json(point.model_dump_json(round_trip=True)).value==point.value


def test_null_retains_native_mask(payload):
    payload['reading']['values'][0]['value']=None
    point=service(payload).read_point(47.5,-52.7,VALID)[0]
    assert point.value is None and point.absence_state=='null'
    assert 'native_fill_mask' in point.provenance.quality.flags


@pytest.mark.parametrize('drift',['field','unit','statistic','grid','member','run','location','bytes','generation'])
def test_identity_refusal(payload,drift):
    native=payload['reading']['values'][0]
    if drift in ('field','unit','statistic','grid'):native[drift]='wrong'
    elif drift=='member':payload['reading']['member']='member0'
    elif drift=='run':payload['reading']['initialization']=VALID.isoformat()
    elif drift=='location':native['latitude']=50
    elif drift=='bytes':payload['reading']['received_bytes']+=1
    elif drift=='generation':payload['reading']['objects'][0]['generation']='43'
    with pytest.raises(WeatherNextDeliveryUnavailable):service(payload).read_point(47.5,-52.7,VALID)


def test_cache_hit_copy_and_fixed_expiry(payload):
    clock=[0.]
    reader=service(payload,clock=lambda:clock[0])
    calls=[]
    reader._acquire=lambda s:(calls.append(s),deepcopy(payload))[1]
    first=reader.read_point(47.5,-52.7,VALID)[0]
    first.value=100
    clock[0]=30
    second=reader.read_point(47.5,-52.7,VALID)[0]
    assert second.value==pytest.approx(6.85) and len(calls)==1
    reader.read_point(47.5,-52.7,VALID,refresh=True)
    assert len(calls)==2
    assert reader._entries[next(iter(reader._entries))][1]==60
    clock[0]=61
    reader.read_point(47.5,-52.7,VALID)
    assert len(calls)==3


def test_failure_is_safe_no_stale_and_cooldown(payload):
    clock=[0.]
    reader=service(payload,clock=lambda:clock[0])
    reader.read_point(47.5,-52.7,VALID)
    calls=[]
    def fail(_):calls.append(1);raise RuntimeError('private token detail')
    reader._acquire=fail
    with pytest.raises(WeatherNextDeliveryUnavailable,match='bounded historical'):
        reader.read_point(47.5,-52.7,VALID,refresh=True)
    assert reader.read_point(47.5,-52.7,VALID)[0].value==pytest.approx(6.85)
    with pytest.raises(WeatherNextDeliveryUnavailable,match='cooldown'):
        reader.read_point(47.5,-52.7,VALID,refresh=True)
    assert len(calls)==1
    clock[0]=61
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,VALID)


def test_misses_coalesce(payload):
    reader=service(payload)
    entered=threading.Event();release=threading.Event();calls=[]
    def acquire(_):calls.append(1);entered.set();release.wait(3);return deepcopy(payload)
    reader._acquire=acquire
    with ThreadPoolExecutor(max_workers=5) as pool:
        first=pool.submit(reader.read_point,47.5,-52.7,VALID)
        assert entered.wait(1)
        others=[pool.submit(reader.read_point,47.5,-52.7,VALID) for _ in range(4)]
        release.set()
        assert first.result()[0].value==pytest.approx(6.85)
        assert all(f.result()[0].value==pytest.approx(6.85) for f in others)
    assert len(calls)==1


def test_historical_and_wrong_run_no_acquisition(payload):
    reader=service(payload)
    reader._acquire=lambda _:pytest.fail('must not acquire')
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,NOW)
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,VALID,run='other')


def test_cache_entry_bound(payload):
    reader=service(payload)
    for offset in range(12):reader.read_point(47.5,-52.7+offset*.001,VALID)
    assert len(reader._entries)==8


def test_cache_cannot_bypass_historical_permission(payload):
    reader=service(payload)
    reader.read_point(47.5,-52.7,VALID)
    reader._utcnow=lambda:VALID+timedelta(hours=48)
    with pytest.raises(WeatherNextDeliveryUnavailable):reader.read_point(47.5,-52.7,VALID)


def test_explicit_64mib_ceiling_keeps_lower_default():
    from weather_api.weathernext_gcs_bridge import AccountedGCSTransport,CAP,MAX_CAP
    assert CAP==16*1024**2 and MAX_CAP==64*1024**2
    assert AccountedGCSTransport(token_provider=lambda **_:'fixture',max_received_bytes=MAX_CAP).max_received_bytes==MAX_CAP
    with pytest.raises(ValueError):AccountedGCSTransport(token_provider=lambda **_:'fixture',max_received_bytes=MAX_CAP+1)


def test_wire_fixture_stays_consumable(payload):
    import json
    from pathlib import Path
    fixture=json.loads((Path(__file__).parent/'fixtures/weathernext3/historical-temperature-point.json').read_text())
    reader=service(payload)
    assert fixture['point']==reader.read_point(47.5,-52.7,VALID)[0].model_dump(mode='json')
    assert fixture['descriptor']==reader.descriptors()[0].model_dump(mode='json')


@pytest.mark.parametrize('kind',['unknown','duplicate'])
def test_ambiguous_http_receipt_refused(payload,kind):
    if kind=='unknown':payload['receipt']['http_objects'][0]['kind']='unknown'
    else:payload['receipt']['http_objects'].append(deepcopy(payload['receipt']['http_objects'][0]))
    with pytest.raises(WeatherNextDeliveryUnavailable):service(payload).read_point(47.5,-52.7,VALID)


def test_comparison_batch_reuses_acquisition_metadata_for_fields_and_quantiles(payload):
    """GOV-SPEC-004/006: one native read, published statistics, exact units."""
    from registry.weathernext import BY_NATIVE
    fields=['temperature_2m_mean','temperature_2m_p10','temperature_2m_p90','total_cloud_cover_mean','total_precipitation_1hr_mean']
    prefix=ROOT.name.rsplit('/',1)[0]+'/'
    for native in fields[1:]:
        mapping=BY_NATIVE[native]
        payload['reading']['values'].append(dict(field=native,value=.002 if 'precipitation' in native else .4 if 'cloud' in native else 279.,unit=mapping.native_unit,
            statistic=native.rsplit('_',1)[1],grid=mapping.grid,latitude=47.5,longitude=-52.7))
        identity=dict(bucket=ROOT.bucket,name=prefix+native+'/c/5/0/0',generation='42',etag='fixture-etag',size=4)
        payload['reading']['objects'].append(identity)
        payload['receipt']['http_objects'].append(dict(name=identity['name'],kind='media',generation='42',bytes=4,sha256=hashlib.sha256(native.encode()).hexdigest(),completed_at=NOW.isoformat()))
        payload['reading']['received_bytes']+=4
        payload['receipt']['http_response_bytes']+=4
    reader=service(payload);calls=[]
    reader._acquire=lambda s:(calls.append(s),deepcopy(payload))[1]
    result=reader.read_batch(47.5,-52.7,VALID,fields=tuple(BY_NATIVE[n].key for n in fields))
    assert len(calls)==1 and set(calls[0].fields)==set(fields) and len(result)==5
    assert len({f.provenance.artifact_revision for f in result})==1
    precipitation=next(f for f in result if f.key==BY_NATIVE['total_precipitation_1hr_mean'].key)
    assert precipitation.value==2 and precipitation.provenance.normalized_units=='mm'
    cloud=next(f for f in result if f.key==BY_NATIVE['total_cloud_cover_mean'].key)
    assert cloud.value==40 and cloud.provenance.normalized_units=='percent'
    assert {f.provenance.ensemble.quantile for f in result}=={None,.1,.9}


def test_comparison_partial_batch_preserves_unread_metadata_receipt(payload):
    from registry.weathernext import BY_NATIVE
    missing='total_cloud_cover_mean';native_path=ROOT.name.rsplit('/',1)[0]+'/'+missing+'/c/5/0/0'
    payload['reading']['unavailable_fields']=[missing]
    payload['reading']['unread_objects']=[dict(bucket=ROOT.bucket,name=native_path,generation='42',etag='fixture-etag',size=64*1024**2)]
    payload['receipt']['http_objects'].append(dict(name=native_path,kind='metadata',generation='42',bytes=4,sha256=hashlib.sha256(b'meta').hexdigest(),completed_at=NOW.isoformat()))
    payload['receipt']['http_response_bytes']+=4
    values,failures=service(payload).read_batch(47.5,-52.7,VALID,fields=('temperature_2m',BY_NATIVE[missing].key),report_failures=True)
    assert len(values)==1 and values[0].value==pytest.approx(6.85)
    assert failures=={BY_NATIVE[missing].key:'Source acquisition budget reached for this field'}
    assert len(values[0].provenance.source_acquisition.transport_receipts)==7
