"""Explicit historical point bridge: parent runtime auth, isolated Linux decoder.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006. Experiment only.
"""
import base64
from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import uuid

from weather_api.weathernext_gcs import GcloudProfileToken, WeatherNextGCSTransport
from weather_api.weathernext_native import BUCKET, ObjectIdentity
from weather_api.weathernext_query import WeatherNextSelection

CAP = 16 * 1024**2
MAX_CAP = 64 * 1024**2
ROOT = ObjectIdentity(BUCKET,'weathernext_3_0_0_statistics/zarr/2026_to_present/20260801_00hr_01_preds/predictions.zarr/zarr.json',
                      '1787792319369404','CLyhg7HNv5YDEAE=',182540)


class BridgeUnavailable(RuntimeError):
    pass


class AccountedGCSTransport(WeatherNextGCSTransport):
    """Counts successful JSON metadata and payload response bodies together."""
    def __init__(self, *, max_received_bytes=CAP, **kwargs):
        if type(max_received_bytes) is not int or not 0 < max_received_bytes <= MAX_CAP:
            raise ValueError("WeatherNext received-byte cap")
        self.max_received_bytes = max_received_bytes
        super().__init__(**kwargs)
        self.received_bytes = 0
        self.operations = []
    def _get(self, name, params, *, cap, timeout, expected=None):
        if len(self.operations) >= 30 or cap <= 0 or self.received_bytes >= self.max_received_bytes:
            raise BridgeUnavailable('WeatherNext operation or byte budget')
        effective = min(cap, self.max_received_bytes-self.received_bytes)
        if expected is not None and expected.size > effective:
            raise BridgeUnavailable('WeatherNext chunk exceeds remaining byte budget')
        operation={'name':name,'kind':'media' if expected else 'metadata','generation':expected.generation if expected else None}
        self.operations.append(operation)
        if isinstance(self._token_provider,GcloudProfileToken):
            body=self._subprocess_get(name,params,effective,timeout,expected)
        else:
            body=super()._get(name,params,cap=effective,timeout=timeout,expected=expected)
        self.received_bytes += len(body)
        operation.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),completed_at=datetime.now(UTC).isoformat())
        return body

    def _subprocess_get(self,name,params,cap,timeout,expected):
        request={'name':name,'params':params,'cap':cap,'timeout':timeout,
                 'expected':asdict(expected) if expected else None,'profile':self._token_provider.profile}
        child=subprocess.Popen([sys.executable,'-m','weather_api.weathernext_gcs_worker','--http'],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        try:
            output,_=child.communicate(json.dumps(request).encode(),timeout=timeout)
            if child.returncode or len(output)>90*1024**2: raise BridgeUnavailable('WeatherNext HTTP child failed')
            response=json.loads(output)
            if 'body' not in response:
                error=BridgeUnavailable('WeatherNext HTTP child refused')
                error.http_status=response.get('http_status') if response.get('http_status') in (401,403) else None
                raise error
            body=base64.b64decode(response['body'],validate=True)
            if len(body)>cap: raise BridgeUnavailable('WeatherNext HTTP child byte cap')
            return body
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGKILL)
                child.communicate(timeout=5)


def worker_command(container_name=None):
    if sys.platform == 'linux':
        return [sys.executable,'-m','weather_api.weathernext_gcs_worker']
    experiment=Path(__file__).resolve().parents[2]
    return ['docker','run','--rm','--pull','never','--name',container_name or ('weathernext-'+uuid.uuid4().hex),'--network','none','--memory','2g','--cpus','2','-i',
            '-v',f'{experiment}:/work:ro','-w','/work','-e','PYTHONPATH=/work/api:/work',
            '-e','OPENBLAS_NUM_THREADS=1','astraeus-lightning-proof:c88ff83',
            'python','-m','weather_api.weathernext_gcs_worker']


from .weathernext_scope import HISTORICAL, INTERNAL_FORECAST, validate_scope


def read_historical_point(selection: WeatherNextSelection, **kwargs):
    """Retained strict historical path; no caller scope override."""
    return _read_point(selection, acquisition_scope=HISTORICAL, **kwargs)


def read_local_experimental_point(selection: WeatherNextSelection, **kwargs):
    """Explicit internal-use forecast experiment; no registration or publication."""
    return _read_point(selection, acquisition_scope=INTERNAL_FORECAST, **kwargs)


def _read_point(selection: WeatherNextSelection, *, root_identity: ObjectIdentity,
                          acquisition_scope: str, now: datetime | None = None, transport=None, command=None, timeout=90, max_received_bytes=CAP):
    """Root identity must be explicitly supplied; no listing or current-run guess.

    No source registration/cache. Caller gets native reading plus response hashes.
    """
    if type(max_received_bytes) is not int or not 0 < max_received_bytes <= MAX_CAP:
        raise BridgeUnavailable("WeatherNext received-byte cap")
    now=now or datetime.now(UTC)
    try:
        validate_scope(selection, now, acquisition_scope)
    except ValueError as error:
        raise BridgeUnavailable(str(error)) from None
    expected_prefix=f'weathernext_3_0_0_statistics/zarr/2026_to_present/{selection.initialization:%Y%m%d_%H}hr_01_preds/predictions.zarr/'
    if (root_identity.bucket != BUCKET or root_identity.name != expected_prefix+'zarr.json'
            or not root_identity.generation.isdecimal() or not root_identity.etag or not 0<root_identity.size<=256*1024
            or len(selection.fields)!=1 or not 0<timeout<=90):
        raise BridgeUnavailable('WeatherNext explicit root or point bound')
    transport=transport or AccountedGCSTransport(token_provider=GcloudProfileToken('astraeus'),max_received_bytes=max_received_bytes)
    started=time.monotonic()
    deadline=started+timeout
    process=None
    container_name="weathernext-"+uuid.uuid4().hex if command is None and sys.platform!="linux" else None
    selector=selectors.DefaultSelector()
    def remaining():
        value=deadline-time.monotonic()
        if value<=0: raise BridgeUnavailable('WeatherNext worker deadline')
        return value
    try:
        process=subprocess.Popen(command or worker_command(container_name),stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL,start_new_session=True)
        selector.register(process.stdout,selectors.EVENT_READ)
        request={'initialization':selection.initialization.isoformat(),'valid_time':selection.valid_time.isoformat(),
                 'latitude':selection.latitude,'longitude':selection.longitude,'fields':selection.fields,'now':now.isoformat(),'max_received_bytes':max_received_bytes,'acquisition_scope':acquisition_scope}
        os.set_blocking(process.stdin.fileno(),False)
        def send(value):
            body=memoryview(json.dumps(value,allow_nan=False).encode()+b'\n')
            with selectors.DefaultSelector() as writer:
                writer.register(process.stdin,selectors.EVENT_WRITE)
                while body:
                    if not writer.select(remaining()): raise BridgeUnavailable('WeatherNext worker write deadline')
                    try: count=os.write(process.stdin.fileno(),body)
                    except BlockingIOError: continue
                    body=body[count:]
        send(request)
        pending=b''
        calls=0
        described={}
        payload_bytes=0
        while True:
            if not selector.select(remaining()): raise BridgeUnavailable('WeatherNext worker deadline')
            part=os.read(process.stdout.fileno(),65536)
            if not part: raise BridgeUnavailable('WeatherNext worker exited')
            pending+=part
            if len(pending)>65536: raise BridgeUnavailable('WeatherNext worker output bound')
            if b'\n' not in pending: continue
            line,pending=pending.split(b'\n',1)
            message=json.loads(line)
            op=message.get('op')
            if op=='result':
                reading=message['reading']
                if (reading['initialization']!=selection.initialization.isoformat()
                        or reading['valid_time']!=selection.valid_time.isoformat()
                        or [v['field'] for v in reading['values']]!=list(selection.fields)
                        or reading['received_bytes']!=payload_bytes):
                    raise BridgeUnavailable('WeatherNext result identity')
                return {'reading':reading,'receipt':{'evidence_class':'bounded_native_gcs_point','acquisition_scope':acquisition_scope,'completed_at':datetime.now(UTC).isoformat(),
                        'elapsed_seconds':time.monotonic()-started,'worker_operations':calls,'payload_bytes':payload_bytes,
                        'http_response_bytes':getattr(transport,'received_bytes',None),'http_objects':getattr(transport,'operations',[])}}
            calls+=1
            if calls>30: raise BridgeUnavailable('WeatherNext worker operation cap')
            if op=='describe':
                name=message['name']
                if message['bucket']!=BUCKET or not name.startswith(expected_prefix): raise BridgeUnavailable('WeatherNext worker path')
                identity=root_identity if name==root_identity.name else transport.describe(BUCKET,name,timeout=remaining())
                described[name]=identity
                send({'identity':asdict(identity)})
            elif op=='read':
                identity=ObjectIdentity(**message['identity'])
                if described.get(identity.name)!=identity or message['max_bytes']!=identity.size or payload_bytes+identity.size>max_received_bytes:
                    raise BridgeUnavailable('WeatherNext worker read identity or byte cap')
                body=transport.read(identity,max_bytes=identity.size,timeout=remaining())
                if len(body)!=identity.size: raise BridgeUnavailable('WeatherNext worker truncated payload')
                payload_bytes+=len(body)
                send({'body':base64.b64encode(body).decode('ascii')})
            else: raise BridgeUnavailable('WeatherNext bounded native worker failed')
    except Exception as cause:
        error=BridgeUnavailable('WeatherNext bounded point acquisition failed')
        error.http_status=getattr(cause,'http_status',None) if getattr(cause,'http_status',None) in (401,403) else None
        raise error from None
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL)
            process.stdin.close()
            process.stdout.close()
            process.wait(timeout=5)
        if container_name:
            subprocess.run(['docker','rm','--force',container_name],stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=5,check=False)
