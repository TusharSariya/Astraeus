"""Actual isolated native worker over deterministic Zarr transport objects."""
from datetime import UTC,datetime
import json
import sys

import pytest

from test_weathernext_native import transport, selection
from weather_api.weathernext_gcs_bridge import BridgeUnavailable, read_historical_point, ROOT, AccountedGCSTransport, CAP
from weather_api.weathernext_native import BUCKET,ObjectIdentity

NOW=datetime(2026,9,1,tzinfo=UTC)


def root(transport):
    body=transport.body('zarr.json')
    return ObjectIdentity(BUCKET,ROOT.name,'42','etag',len(body))


def test_actual_native_worker(transport):
    if sys.platform!='linux': pytest.skip('Linux resource-limited worker')
    result=read_historical_point(selection(),root_identity=root(transport),now=NOW,transport=transport)
    assert result['reading']['values'][0]['value']==pytest.approx(.35)
    assert result['reading']['values'][0]['statistic']=='p90'
    assert result['receipt']['payload_bytes']==sum(o['size'] for o in result['reading']['objects'])
    assert result['receipt']['worker_operations']==12
    assert not any(op=='describe' and path=='zarr.json' for op,path in transport.calls)


def test_historical_refusal_before_process(transport):
    with pytest.raises(BridgeUnavailable,match='historical'):
        read_historical_point(selection(),root_identity=root(transport),now=selection().valid_time,transport=transport,command=['does-not-exist'])
    assert transport.calls==[]


def test_root_mismatch_before_process(transport):
    with pytest.raises(BridgeUnavailable,match='root'):
        read_historical_point(selection(),root_identity=ObjectIdentity(BUCKET,ROOT.name+'wrong','42','etag',10),now=NOW,command=['does-not-exist'])


def test_child_timeout_is_bounded_and_safe(transport):
    with pytest.raises(BridgeUnavailable,match='bounded point'):
        read_historical_point(selection(),root_identity=root(transport),now=NOW,transport=transport,
            command=[sys.executable,'-c','import time;time.sleep(5)'],timeout=.1)


def test_child_bad_request_cannot_fetch_foreign_object(transport):
    code='import json; print(json.dumps({"op":"describe","bucket":"other","name":"secret"}),flush=True);input()'
    with pytest.raises(BridgeUnavailable):
        read_historical_point(selection(),root_identity=root(transport),now=NOW,transport=transport,command=[sys.executable,'-c',code])
    assert transport.calls==[]


def test_chunk_over_total_cap_refused_before_get(transport):
    original=transport.describe
    def describe(bucket,name,*,timeout):
        identity=original(bucket,name,timeout=timeout)
        if '/total_cloud_cover_p90/' in name:
            return ObjectIdentity(bucket,name,'42','etag',CAP+1)
        return identity
    transport.describe=describe
    with pytest.raises(BridgeUnavailable):
        read_historical_point(selection(),root_identity=root(transport),now=NOW,transport=transport)
    assert not any(op=='read' and path.startswith('total_cloud_cover') for op,path in transport.calls)


def test_blocked_worker_pipe_cannot_overrun_deadline(transport):
    import time
    name=ROOT.name.rsplit('/',1)[0]+'/total_cloud_cover_p90/c/1/1/0'
    original=transport.describe
    def describe(bucket,path,*,timeout):
        return ObjectIdentity(bucket,path,'42','etag',1024**2) if path==name else original(bucket,path,timeout=timeout)
    transport.describe=describe
    transport.read=lambda identity,**kwargs: b'x'*identity.size
    code='import sys,json,time;sys.stdin.readline();print(json.dumps({"op":"describe","bucket":'+repr(BUCKET)+',"name":'+repr(name)+'}),flush=True);r=json.loads(sys.stdin.readline());print(json.dumps({"op":"read","identity":r["identity"],"max_bytes":1048576}),flush=True);time.sleep(5)'
    started=time.monotonic()
    with pytest.raises(BridgeUnavailable):
        read_historical_point(selection(),root_identity=root(transport),now=NOW,transport=transport,
                              command=[sys.executable,'-c',code],timeout=.2)
    assert time.monotonic()-started<1


@pytest.mark.parametrize('file_provider',[False,True])
def test_http_operation_process_is_killed_at_deadline(monkeypatch, file_provider):
    import subprocess,time
    from weather_api.weathernext_gcs import AccessTokenFile, GcloudProfileToken
    from weather_api import weathernext_gcs_bridge as bridge
    original=subprocess.Popen
    children=[]
    def start(*args,**kwargs):
        # Never invokes gcloud or network; simulate a blocked HTTP operation.
        child=original([sys.executable,'-c','import time;time.sleep(5)'],**kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(bridge.subprocess,'Popen',start)
    transport=AccountedGCSTransport(token_provider=AccessTokenFile('/unused-private-token') if file_provider else GcloudProfileToken('astraeus'))
    started=time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        transport._get(ROOT.name,{'alt':'media'},cap=256*1024,timeout=.1,expected=ROOT)
    assert time.monotonic()-started<1 and children[0].poll() is not None


def test_owned_docker_container_is_explicitly_removed(monkeypatch,transport):
    from weather_api import weathernext_gcs_bridge as bridge
    names=[]
    cleanup=[]
    monkeypatch.setattr(bridge.sys,'platform','darwin')
    def command(name):
        names.append(name)
        return [sys.executable,'-c','print("{}",flush=True)']
    monkeypatch.setattr(bridge,'worker_command',command)
    monkeypatch.setattr(bridge.subprocess,'run',lambda args,**kwargs: cleanup.append(args))
    with pytest.raises(BridgeUnavailable):
        read_historical_point(selection(),root_identity=root(transport),now=NOW,transport=transport)
    assert names[0].startswith('weathernext-')
    assert cleanup==[['docker','rm','--force',names[0]]]


def test_internal_future_scope_reaches_real_isolated_decoder(transport):
    if sys.platform != 'linux': pytest.skip('Linux resource-limited worker')
    from weather_api.weathernext_gcs_bridge import read_local_experimental_point
    result = read_local_experimental_point(selection(), root_identity=root(transport),
        now=selection().initialization, transport=transport)
    assert result['reading']['valid_time'] == selection().valid_time.isoformat()
    assert result['reading']['values'][0]['value'] == pytest.approx(.35)
    assert result['receipt']['worker_operations'] == 12
    assert result['receipt']['acquisition_scope'] == 'internal_experimental_forecast'


def test_internal_future_initialization_refused_before_process(transport):
    from datetime import timedelta
    from weather_api.weathernext_gcs_bridge import read_local_experimental_point
    with pytest.raises(BridgeUnavailable, match='initialization'):
        read_local_experimental_point(selection(), root_identity=root(transport),
            now=selection().initialization-timedelta(seconds=1), transport=transport, command=['does-not-exist'])
    assert transport.calls == []


@pytest.mark.parametrize('mode', ['file', 'missing_file', 'gcloud'])
def test_actual_http_child_selects_provider_without_token_output(tmp_path, mode):
    import base64
    import subprocess
    path = tmp_path / 'synthetic-private-token'
    path.write_text('synthetic-token\n')
    path.chmod(0o600)
    request = {'name': ROOT.name, 'params': {}, 'cap': 100, 'timeout': 5, 'expected': None}
    if mode == 'gcloud': request['profile'] = 'astraeus'
    else: request['token_file'] = str(path if mode == 'file' else tmp_path/'absent')
    # Exercise real worker protocol and file provider in a child, replace only
    # remote HTTP and gcloud execution. No provider/auth calls occur.
    code = '''
from weather_api.weathernext_gcs import WeatherNextGCSTransport, GcloudProfileToken
from weather_api.weathernext_gcs_worker import http_main
GcloudProfileToken.__call__ = lambda self, **kwargs: 'synthetic-token'
def fake_get(self, *args, **kwargs):
    assert self._token_provider(timeout=1) == 'synthetic-token'
    return b'public-fixture-response'
WeatherNextGCSTransport._get = fake_get
http_main()
'''
    result = subprocess.run([sys.executable, '-c', code], input=json.dumps(request).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
    assert b'synthetic-token' not in result.stdout + result.stderr
    assert str(path).encode() not in result.stdout + result.stderr
    reply = json.loads(result.stdout)
    if mode == 'missing_file':
        assert reply == {'error': 'WeatherNext bounded HTTP worker failed', 'http_status': None}
    else:
        assert base64.b64decode(reply['body']) == b'public-fixture-response'


def test_actual_comparison_batch_shares_native_coordinates(transport):
    """GOV-SPEC-004/006: exercise the default worker, not injected acquisition."""
    if sys.platform!='linux':pytest.skip('Linux resource-limited worker')
    from copy import deepcopy
    from dataclasses import replace
    original='total_cloud_cover_p90'
    for field in ['total_cloud_cover_mean','total_cloud_cover_p10']:
        transport.nodes[field]=deepcopy(transport.nodes[original])
        for path,body in list(transport.bodies.items()):
            if path.startswith(original+'/'):
                transport.bodies[path.replace(original,field,1)]=body
    selected=replace(selection(),fields=('total_cloud_cover_mean','total_cloud_cover_p10',original))
    result=read_historical_point(selected,root_identity=root(transport),now=NOW,transport=transport)
    assert {v['statistic'] for v in result['reading']['values']}=={'mean','p10','p90'}
    reads=[path for op,path in transport.calls if op=='read']
    assert len(reads)==len(set(reads))
    assert reads.count('lead_time/c/0')==1 and reads.count('init_time/c')==1
    assert all(sum(path.startswith(field+'/c/') for path in reads)==1 for field in selected.fields)


def test_actual_batch_byte_limit_retains_completed_fields(transport):
    if sys.platform!='linux':pytest.skip('Linux resource-limited worker')
    from copy import deepcopy
    from dataclasses import replace
    from weather_api.weathernext_delivery import HistoricalConfiguration, point_evidence
    original='total_cloud_cover_p90';mean='total_cloud_cover_mean'
    transport.nodes[mean]=deepcopy(transport.nodes[original])
    for path,body in list(transport.bodies.items()):
        if path.startswith(original+'/'):transport.bodies[path.replace(original,mean,1)]=body
    selected=replace(selection(),fields=(mean,original))
    paths=['zarr.json','init_time/c','lead_time/c/0','lat_0p1/c/0','lon_0p1/c/0',mean+'/c/1/1/0']
    cap=sum(len(transport.body(p)) for p in paths)
    result=read_historical_point(selected,root_identity=root(transport),now=NOW,transport=transport,max_received_bytes=cap)
    assert [v['field'] for v in result['reading']['values']]==[mean]
    assert result['reading']['unavailable_fields']==[original]
    assert result['reading']['received_bytes']==cap
    assert not any(op=='read' and path.startswith(original+'/c/') for op,path in transport.calls)
