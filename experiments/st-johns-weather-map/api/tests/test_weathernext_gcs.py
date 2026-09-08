"""Offline JSON API transport proof. No actual gcloud or provider operations."""
import io
import json
import subprocess
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from weather_api.weathernext_gcs import GcloudProfileToken, GCSUnavailable, WeatherNextGCSTransport
from weather_api.weathernext_native import BUCKET, ObjectIdentity

NAME = 'weathernext_3_0_0_statistics/zarr/2026_to_present/20260801_00hr_01_preds/predictions.zarr/zarr.json'
IDENTITY = ObjectIdentity(BUCKET, NAME, '42', 'etag', 3)


class Response(io.BytesIO):
    def __init__(self, body=b'abc', *, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers if headers is not None else {'Content-Length': str(len(body)), 'x-goog-generation': '42', 'ETag': 'etag'}
        self.read_count = 0
    def read(self, n=-1):
        assert n > 0
        self.read_count += 1
        return super().read(n)


class Opener:
    def __init__(self, response):
        self.response, self.requests = response, []
    def open(self, request, *, timeout):
        self.requests.append(request)
        assert 0 < timeout <= 10
        return self.response


def make(response):
    opener = Opener(response)
    return WeatherNextGCSTransport(token_provider=lambda **_: 'synthetic-token', opener=opener), opener


def test_generation_qualified_read_and_no_billing():
    transport, opener = make(Response())
    assert transport.read(IDENTITY, max_bytes=3, timeout=10) == b'abc'
    request = opener.requests[0]
    assert parse_qs(urlsplit(request.full_url).query) == {'alt': ['media'], 'generation': ['42']}
    assert request.get_header('Authorization') == 'Bearer synthetic-token'
    assert not any('project' in k.lower() for k in request.headers)
    assert urlsplit(request.full_url).hostname == 'storage.googleapis.com'


def test_describe_preserves_actual_identity_and_partial_fields():
    body = json.dumps(dict(bucket=BUCKET, name=NAME, generation='42', etag='etag', size='3')).encode()
    transport, opener = make(Response(body))
    assert transport.describe(BUCKET, NAME, timeout=10) == IDENTITY
    assert parse_qs(urlsplit(opener.requests[0].full_url).query) == {'fields': ['bucket,name,generation,etag,size']}


@pytest.mark.parametrize('status,category', [(401,'authentication refused'), (403,'access denied'), (404,'object absent'), (412,'object changed'), (429,'rate limited'), (302,'HTTP failure')])
def test_http_failures_do_not_read_or_disclose_body(status, category):
    response = Response(b'private provider detail', status=status)
    transport, _ = make(response)
    with pytest.raises(GCSUnavailable) as caught:
        transport.read(IDENTITY, max_bytes=3, timeout=10)
    assert caught.value.http_status == status and caught.value.category == category
    assert response.read_count == 0
    assert 'private' not in str(caught.value)


@pytest.mark.parametrize('header,value', [('Content-Length','4'), ('x-goog-generation','43'), ('ETag','changed'), ('Content-Encoding','gzip')])
def test_header_identity_and_bounds_before_body(header, value):
    response = Response()
    response.headers[header] = value
    transport, _ = make(response)
    with pytest.raises(GCSUnavailable): transport.read(IDENTITY, max_bytes=3, timeout=10)
    assert response.read_count == 0


def test_truncated_body():
    response = Response(b'ab')
    response.headers['Content-Length'] = '3'
    transport, _ = make(response)
    with pytest.raises(GCSUnavailable, match='truncated'): transport.read(IDENTITY, max_bytes=3, timeout=10)


def test_no_content_length_at_cap_refuses_without_extra_byte():
    response = Response(b'abcd', headers={'x-goog-generation':'42', 'ETag':'etag'})
    transport, _ = make(response)
    with pytest.raises(GCSUnavailable, match='boundary'): transport.read(IDENTITY, max_bytes=3, timeout=10)
    assert response.read_count == 1


@pytest.mark.parametrize('bucket,name', [('weathernext3_spatial',NAME), (BUCKET,NAME.replace('statistics/zarr','raw/zarr')), (BUCKET,NAME+'/../../other'), (BUCKET,'https://evil.example/object')])
def test_surface_refusal_precedes_authentication(bucket, name):
    def forbidden(**kwargs): pytest.fail('must not authenticate')
    transport = WeatherNextGCSTransport(token_provider=forbidden)
    with pytest.raises(GCSUnavailable): transport.describe(bucket, name, timeout=10)


def test_runtime_profile_token_only_captured(monkeypatch):
    def run(args, **kwargs):
        assert args == ['gcloud', '--configuration', 'astraeus', '--quiet', 'auth', 'print-access-token']
        assert kwargs['stdout'] == subprocess.PIPE and kwargs['stderr'] == subprocess.PIPE
        assert kwargs['timeout'] == 10
        return subprocess.CompletedProcess(args, 0, b'synthetic-token\n', b'')
    monkeypatch.setattr(subprocess, 'run', run)
    assert GcloudProfileToken()(timeout=10) == 'synthetic-token'


@pytest.mark.parametrize('failure', ['nonzero','exception','oversize'])
def test_runtime_auth_failure_safe(monkeypatch, failure):
    def run(*args, **kwargs):
        if failure == 'exception': raise RuntimeError('private credential detail')
        return subprocess.CompletedProcess([], 1 if failure == 'nonzero' else 0,
                                            b'x'*20000 if failure == 'oversize' else b'', b'private detail')
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises(GCSUnavailable) as caught: GcloudProfileToken()(timeout=10)
    assert str(caught.value) == 'WeatherNext GCS authentication unavailable'


def test_expired_deadline_precedes_http():
    clock = iter([0,0,11])
    def forbidden(*args, **kwargs): pytest.fail('must not open')
    opener = Opener(Response())
    opener.open = forbidden
    transport = WeatherNextGCSTransport(token_provider=lambda **_: 'synthetic', opener=opener, clock=lambda:next(clock))
    with pytest.raises(GCSUnavailable, match='deadline'): transport.read(IDENTITY,max_bytes=3,timeout=10)


def test_http_error_is_closed_without_body_disclosure():
    error = HTTPError('https://storage.googleapis.com/',403,'private provider detail',{},io.BytesIO(b'private detail'))
    opener = Opener(Response())
    def fail(*args, **kwargs): raise error
    opener.open = fail
    transport = WeatherNextGCSTransport(token_provider=lambda **_: 'synthetic',opener=opener)
    with pytest.raises(GCSUnavailable, match='access denied'):
        transport.read(IDENTITY,max_bytes=3,timeout=10)
    assert error.fp.closed


def test_default_opener_refuses_redirects():
    from weather_api.weathernext_gcs import _NoRedirect
    assert _NoRedirect().redirect_request(None, None, 302, 'redirect', {}, 'https://elsewhere.example') is None


def test_describe_rejects_changed_name():
    body = json.dumps(dict(bucket=BUCKET, name=NAME+'other', generation='42', etag='etag', size='3')).encode()
    transport, _ = make(Response(body))
    with pytest.raises(GCSUnavailable, match='invalid object metadata'):
        transport.describe(BUCKET,NAME,timeout=10)


def test_transport_exception_does_not_disclose_token():
    opener = Opener(Response())
    def fail(*args, **kwargs): raise RuntimeError('Bearer synthetic-token')
    opener.open = fail
    transport = WeatherNextGCSTransport(token_provider=lambda **_: 'synthetic-token',opener=opener)
    with pytest.raises(GCSUnavailable) as caught:
        transport.read(IDENTITY,max_bytes=3,timeout=10)
    assert str(caught.value) == 'WeatherNext GCS bounded request failed'
    assert caught.value.__suppress_context__


def private_token(tmp_path, body=b'synthetic-token\n'):
    path = tmp_path / 'runtime-token'
    path.write_bytes(body)
    path.chmod(0o600)
    return path


def test_token_file_rereads_atomic_replacement(tmp_path):
    from weather_api.weathernext_gcs import AccessTokenFile
    path = private_token(tmp_path)
    provider = AccessTokenFile(str(path))
    assert provider(timeout=1) == 'synthetic-token'
    replacement = tmp_path / 'replacement'
    replacement.write_bytes(b'new.synthetic_token+/==\r\n')
    replacement.chmod(0o600)
    replacement.replace(path)
    assert provider(timeout=1) == 'new.synthetic_token+/=='


@pytest.mark.parametrize('body', [b'', b'Bearer secret', b'one\ntwo', b'one\n\n', b' token', b'token ', b'\xff', b'x'*16385, b'token:secret', b'=token'])
def test_token_file_invalid_content_is_safe(tmp_path, body):
    from weather_api.weathernext_gcs import AccessTokenFile
    path = private_token(tmp_path, body)
    with pytest.raises(GCSUnavailable) as caught:
        AccessTokenFile(str(path))(timeout=1)
    assert str(caught.value) == 'WeatherNext GCS authentication unavailable'


@pytest.mark.parametrize('kind', ['missing', 'public', 'symlink', 'directory', 'fifo'])
def test_token_file_path_failures_are_safe_and_nonblocking(tmp_path, kind):
    import os
    from weather_api.weathernext_gcs import AccessTokenFile
    path = private_token(tmp_path)
    if kind == 'missing': path.unlink()
    elif kind == 'public': path.chmod(0o644)
    elif kind == 'symlink':
        target = tmp_path / 'link'
        target.symlink_to(path)
        path = target
    elif kind == 'directory': path = tmp_path
    elif kind == 'fifo':
        path.unlink()
        os.mkfifo(path, 0o600)
    with pytest.raises(GCSUnavailable) as caught:
        AccessTokenFile(str(path))(timeout=1)
    assert str(caught.value) == 'WeatherNext GCS authentication unavailable'


def test_explicit_token_file_precedes_gcloud_and_empty_does_not_fallback(tmp_path, monkeypatch):
    from weather_api.weathernext_gcs import ACCESS_TOKEN_FILE_ENV, AccessTokenFile, runtime_token_provider
    path = private_token(tmp_path)
    monkeypatch.setenv(ACCESS_TOKEN_FILE_ENV, str(path))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('must not invoke gcloud'))
    assert runtime_token_provider('astraeus')(timeout=1) == 'synthetic-token'
    monkeypatch.setenv(ACCESS_TOKEN_FILE_ENV, '')
    provider = runtime_token_provider('astraeus')
    assert isinstance(provider, AccessTokenFile)
    with pytest.raises(GCSUnavailable): provider(timeout=1)
    monkeypatch.delenv(ACCESS_TOKEN_FILE_ENV)
    assert isinstance(runtime_token_provider('astraeus'), GcloudProfileToken)


def test_token_file_http_uses_only_bearer_header(tmp_path):
    from weather_api.weathernext_gcs import AccessTokenFile
    opener = Opener(Response())
    transport = WeatherNextGCSTransport(token_provider=AccessTokenFile(str(private_token(tmp_path))), opener=opener)
    assert transport.read(IDENTITY, max_bytes=3, timeout=10) == b'abc'
    assert opener.requests[0].get_header('Authorization') == 'Bearer synthetic-token'
    assert 'synthetic-token' not in opener.requests[0].full_url


def test_token_file_exact_byte_limit_and_expired_deadline(tmp_path):
    from weather_api.weathernext_gcs import AccessTokenFile
    provider = AccessTokenFile(str(private_token(tmp_path, b'x'*16384)))
    assert len(provider(timeout=1)) == 16384
    with pytest.raises(GCSUnavailable): provider(timeout=0)


def test_token_file_requires_current_process_owner(tmp_path, monkeypatch):
    import os
    from weather_api.weathernext_gcs import AccessTokenFile
    path = private_token(tmp_path)
    monkeypatch.setattr(os, 'geteuid', lambda: path.stat().st_uid + 1)
    with pytest.raises(GCSUnavailable): AccessTokenFile(str(path))(timeout=1)
