"""Mapped Activity delivery fixtures; not provider admission or live-source proof."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from weather_api.activity import ActivityService, Focus, profiles
from weather_api.fixtures import point_fields
from weather_api.models import Quality
from weather_api.profiles.evaluator import evaluate
from registry.fields import units_for

AT = datetime(2026, 9, 7, 12, tzinfo=UTC)
FOCUS = Focus(latitude=47.5615, longitude=-52.7126, valid_time=AT)


def inputs(at=AT):
    original = point_fields(at)[0][0]
    fields = {'temperature_2m': 10, 'dew_point_2m': 10, 'wind_speed_10m': 2, 'visibility': 10000,
              'cloud_high': 10, 'cloud_middle': 10, 'cloud_low': 10, 'total_cloud_opacity': 10,
              'precipitable_water': 10, 'relative_humidity_2m': 60, 'kp_index': 5,
              'sun_altitude': -20, 'moon_altitude': 20, 'moon_illuminated_fraction': .2}
    result = []
    for key, value in fields.items():
        row = original.model_copy(deep=True)
        row.key, row.field, row.value = key, key, value
        row.provenance.normalized_units = units_for(key)
        row.provenance.source_id = 'nasa-jpl-de442' if key in ('sun_altitude', 'moon_altitude', 'moon_illuminated_fraction') else 'noaa-swpc-kp' if key == 'kp_index' else 'eccc-hrdps' if key == 'total_cloud_opacity' else 'noaa-gfs'
        row.provenance.quality = Quality(status='passed')
        result.append(row)
    return result


class Reader:
    def __init__(self):
        self.calls = 0
        self.failed = False
    def __call__(self, focus, selected, reference, stop):
        self.calls += 1
        if self.failed:
            raise RuntimeError('constructed acquisition failure')
        return inputs(focus.valid_time), {pid: {'outside_window': False, 'unresolved_fields': [], 'intervals': []} for pid in selected}, ['constructed fixed evidence']
    def native_times(self, focus, end, reference, stop):
        return [focus.valid_time+timedelta(hours=i) for i in (0,2,3,5)], 3600, []


def test_real_v2_profiles_match_selected_curves_budgets_and_exclusions():
    selected, unavailable = profiles()
    assert not unavailable
    assert selected['running']['weights'] == pytest.approx({'thermal':5/14,'dew_point':5/14,'wind':1/7,'visibility':1/7})
    assert selected['aurora']['weights'] == pytest.approx({'kp':.7,'moon':.3})
    assert selected['landscape_photography']['weights'] == pytest.approx({'wind':.5,'sun':.5})
    assert 'relative_humidity_2m' not in selected['running']['admitted_paths']
    assert all(profile['version'] == 2 for profile in selected.values())
    assert selected['landscape_photography']['site_needs']['sectors'][0]['bearing_field'] == 'sun_azimuth'


def test_evaluator_retains_unknown_stops_native_values_and_static_budget():
    service = ActivityService(Reader(), utcnow=lambda: AT)
    result = service.read(FOCUS)
    assert [row['profile_id'] for row in result['verdicts']] == ['running','astronomy','aurora','landscape_photography']
    running, astronomy, aurora, landscape = result['verdicts']
    assert running['state'] == landscape['state'] == 'unchecked'
    assert running['score'] is None and len(running['criteria']) == 4
    assert all(stop['outcome'] == 'unknown' for stop in running['hard_stops'])
    assert astronomy['score'] == aurora['score'] == 100
    assert astronomy['overrides']['no_override_in_force']
    assert running['admission_residuals']


def test_missing_moon_altitude_is_unresolved_and_below_horizon_is_explicit_not_applicable():
    selected, _ = profiles()
    rows = inputs()
    def run(evidence):
        return evaluate(selected['aurora'], at=AT, tier='core', readings=evidence,
            window={'outside_window':False}, overrides={}, site_id=None)
    missing = run([row for row in rows if row.key != 'moon_altitude'])
    assert missing['state'] == 'unresolved' and missing['score'] is None
    assert missing['unresolved_fields'] == ['moon_altitude']
    next(row for row in rows if row.key == 'moon_altitude').value = -1
    below = run(rows)
    assert below['applicability'][0]['applicable'] is False
    assert below['criteria'][1]['reason'] == 'not_applicable:moon_at_or_below_horizon'
    assert below['coverage']['declared'] == 1 and below['coverage']['evaluated'] == .7
    assert below['active_weights'] == pytest.approx({'kp':.7,'moon':.3})


def test_failed_qc_remains_numeric_but_does_not_score():
    selected,_=profiles(); rows=inputs()
    next(row for row in rows if row.key=='kp_index').provenance.quality = Quality(status='failed')
    result=evaluate(selected['aurora'],at=AT,tier='core',readings=rows,window={'outside_window':False},overrides={},site_id=None)
    assert result['state']=='unscorable'
    assert result['criteria'][0]['input']['evidence']['value']==5
    assert result['criteria'][0]['reason']=='quality_failed'
    assert result['coverage']['evaluated']==.3


def test_fixed_expiry_cache_hits_failed_refresh_and_expired_failure():
    clock=[0.]; reader=Reader(); service=ActivityService(reader, clock=lambda:clock[0], utcnow=lambda:AT+timedelta(seconds=clock[0]))
    first=service.read(FOCUS); clock[0]=299
    hit=service.read(FOCUS)
    assert hit['cache']['state']=='hit' and reader.calls==1
    assert hit['cache']['expires_at']==first['cache']['expires_at']
    reader.failed=True
    with pytest.raises(HTTPException): service.read(FOCUS,refresh=True)
    with pytest.raises(HTTPException): service.read(FOCUS)
    reader.failed=False; service.read(FOCUS); clock[0]=600;reader.failed=True
    with pytest.raises(HTTPException): service.read(FOCUS)
    assert not service.entries


def test_concurrent_misses_coalesce_and_return_isolated_bodies():
    entered, release=Event(),Event(); reader=Reader()
    def read(*args):
        entered.set(); assert release.wait(5); return reader(*args)
    service=ActivityService(read,utcnow=lambda:AT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(service.read,FOCUS);assert entered.wait(5)
        second=pool.submit(service.read,FOCUS);release.set()
        a,b=first.result(),second.result()
    assert reader.calls==1
    a['verdicts'].clear()
    assert len(b['verdicts'])==4 and len(service.read(FOCUS)['verdicts'])==4


def test_strip_preserves_native_gaps_bounds_and_explicit_unqueried_spans():
    reader=Reader();service=ActivityService(reader,utcnow=lambda:AT)
    result=service.read(FOCUS,end=AT+timedelta(hours=6))
    assert reader.calls==3 and len(result['cells'])==3
    assert [row['focus']['valid_time'] for row in result['cells']]==[(AT+timedelta(hours=i)).isoformat().replace('+00:00','Z') for i in (0,2,3)]
    assert result['next_start']==(AT+timedelta(hours=5)).isoformat()
    assert result['complete'] is False
    with pytest.raises(HTTPException):service.read(FOCUS,end=AT+timedelta(hours=25))


def test_override_validation_and_http_registration(monkeypatch):
    import weather_api.activity as module
    from weather_api.app import app
    service=ActivityService(Reader(),utcnow=lambda:AT)
    monkeypatch.setattr(module,'activity_service',lambda:service)
    client=TestClient(app)
    query={'latitude':FOCUS.latitude,'longitude':FOCUS.longitude,'valid_time':AT.isoformat()}
    assert client.get('/api/experiments/weather/v0/verdicts',params=query).status_code==200
    for value in ('unknown:2','running_dew_point_start:nan','running_dew_point_start:30'):
        assert client.get('/api/experiments/weather/v0/verdicts',params={**query,'override':value}).status_code==422
    changed=client.get('/api/experiments/weather/v0/verdicts',params={**query,'override':'aurora_kp_start:6'}).json()
    assert changed['verdicts'][2]['overrides']['overrides'][0]['value']==6


def test_deadline_holds_worker_capacity_and_never_publishes_late_results():
    gate=Event()
    def reader(*args):
        gate.wait(5)
        return Reader()(*args)
    service=ActivityService(reader,utcnow=lambda:AT,read_seconds=.01)
    try:
        with pytest.raises(HTTPException): service.read(FOCUS)
        with pytest.raises(HTTPException): service.read(FOCUS.model_copy(update={'longitude':-52.71}))
        with pytest.raises(HTTPException) as failure: service.read(FOCUS.model_copy(update={'longitude':-52.72}))
        assert failure.value.detail['code']=='activity_capacity_unavailable'
        assert not service.entries
    finally:
        gate.set()


def test_individually_malformed_profile_and_method_refusal(monkeypatch):
    import weather_api.activity as module
    from ingest.derive.registry import Refusal
    available,_=profiles();available.pop('running')
    service=ActivityService(Reader(),utcnow=lambda:AT,loader=lambda:(available,{'running':'constructed malformed profile'}))
    response=service.read(FOCUS)
    assert response['verdicts'][0]['unavailable']=='constructed malformed profile'
    assert response['verdicts'][2]['score']==100
    monkeypatch.setattr(module,'resolve',lambda method, **kwargs:Refusal('method_disabled',method,'constructed refusal'))
    refused=service.read(FOCUS)
    assert refused['verdicts']==[] and refused['refusal']['code']=='method_disabled'


def test_byte_ceiling_and_empty_native_inventory_do_not_invent_cells(monkeypatch):
    import weather_api.activity as module
    reader=Reader();service=ActivityService(reader,utcnow=lambda:AT)
    reader.native_times=lambda *args:([],None,['constructed unknown inventory'])
    response=service.read(FOCUS,end=AT+timedelta(hours=3))
    assert response['cells']==[] and reader.calls==0
    monkeypatch.setattr(module,'MAX_RESPONSE_BYTES',100)
    with pytest.raises(HTTPException) as error:service.read(FOCUS)
    assert error.value.detail['code']=='query_limit_exceeded'


def test_actual_acquisition_seam_uses_coordinators_exact_times_and_registered_windows(monkeypatch, data_mode):
    from types import SimpleNamespace
    from weather_api.profiles.acquisition import ActivityReader
    import weather_api.astronomy as astronomy
    import weather_api.swpc_kp_query as kp
    data_mode('live'); calls=[]
    class Coordinator:
        def __init__(self,source): self.source=source
        def point_fields(self,lat,lon,at):
            calls.append((self.source,lat,lon,at))
            return [row for row in inputs(at) if row.provenance.source_id==self.source],None,[]
    reader=ActivityReader()
    monkeypatch.setattr(reader,'factories',lambda:{source:lambda s=source:Coordinator(s) for source in ('eccc-hrdps','eccc-rdps','eccc-gdps','noaa-gfs')})
    monkeypatch.setattr(kp,'swpc_kp_query_service',lambda:SimpleNamespace(series=lambda at:(SimpleNamespace(available=False,readings=[],acquisition=None),)*2))
    def geometry(lat,lon,start,end,at):
        assert end-start==timedelta(hours=25)
        return SimpleNamespace(sun_altitude_deg=-20,moon_altitude_deg=10,moon=SimpleNamespace(illuminated_fraction=.2),sun_samples=((at,-20),(end,-20)))
    monkeypatch.setattr(astronomy,'sky_geometry',geometry)
    selected,_=profiles(); rows,windows,_,resolutions=reader(FOCUS,selected,AT,lambda:False)
    assert [source for source,*_ in calls]==['eccc-hrdps','eccc-rdps','eccc-gdps','noaa-gfs']
    assert all(row.provenance.valid_time==AT for row in rows)
    assert windows['astronomy']['outside_window'] is False
    assert windows['landscape_photography']['unresolved_fields']==['sun_azimuth']
    assert windows['landscape_photography']['intervals']==[]


def test_reader_switch_refuses_before_acquisition():
    reader=Reader();service=ActivityService(reader,utcnow=lambda:AT)
    result=service.read(FOCUS,disabled_method='activity_verdict')
    assert reader.calls==0 and result['verdicts']==[]
    assert result['refusal']['code']=='reader_disabled'


def test_planning_resolution_uses_actual_driving_sources_and_keeps_missing_inventory_gaps(monkeypatch):
    from types import SimpleNamespace
    from weather_api.profiles.acquisition import ActivityReader
    import weather_api.swpc_kp_query as kp
    selected,_=profiles(); readings=inputs()
    result=evaluate(selected['aurora'],at=AT,tier='planning',readings=readings,
        window={'outside_window':False},overrides={},site_id=None,resolutions={'noaa-swpc-kp':10800,'noaa-gfs':3600})
    assert result['resolution_seconds']==10800 and result['score']==100
    reader=ActivityReader()
    class Inventory:
        def timeline_times(self, at): return (at,at+timedelta(hours=3))
        def native_resolution_seconds(self, at, end): return 3600
    monkeypatch.setattr(reader,'factories',lambda:{'eccc-gdps':Inventory,'noaa-gfs':lambda:SimpleNamespace(timeline_times=lambda at:((at,at+timedelta(hours=3)),{}),native_resolution_seconds=lambda at,end:3600)})
    monkeypatch.setattr(kp,'swpc_kp_query_service',lambda:SimpleNamespace(series=lambda at:(SimpleNamespace(available=False),)*2))
    stamps,steps,_=reader.native_times(FOCUS,AT+timedelta(hours=6),AT-timedelta(days=2),lambda:False)
    assert stamps==[AT,AT+timedelta(hours=3)]
    assert steps=={'eccc-gdps':3600,'noaa-gfs':3600}  # the two missing files are not a 3h cadence


@pytest.mark.parametrize('mutation, fragment', [
    (lambda p:p['weights'].update(thermal=.5),'sum to one'),
    (lambda p:p['saved_stack'].append({'id':'invented-layer','opacity':1}),'unknown saved layer'),
    (lambda p:p['thresholds']['running_thermal_low_full'].update(default=20),'band anchors'),
    (lambda p:p['admitted_paths'].pop('temperature_2m'),'no admitted path'),
])
def test_v2_audit_refuses_changed_budgets_unknown_stacks_and_invalid_anchors(mutation,fragment):
    from pathlib import Path
    from registry.profile_audit import Profile,audit_profile
    selected,_=profiles();profile=selected['running'];mutation(profile)
    assert any(fragment in error for error in audit_profile(Profile('running',Path('running.yaml'),profile)))
