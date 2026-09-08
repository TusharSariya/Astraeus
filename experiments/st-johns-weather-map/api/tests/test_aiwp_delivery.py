"""Experimental native transport verification; no scientific admission."""
import httpx
import pytest

from weather_api.aiwp_delivery import NativeObject, RangeReader, RangeRefused

KEY = 'AURO_v100_GFS/2026/0907/AURO_v100_GFS_2026090712_f000_f240_06.nc'
SOURCE = NativeObject(KEY, 16, '"abc-2"')


def transport_for(body=b'abcdefghijklmnop', **overrides):
    requests = []

    def handle(request):
        requests.append(request)
        start, end = map(int, request.headers['range'][6:].split('-'))
        headers = {'Content-Range': f'bytes {start}-{end}/{len(body)}',
                   'Content-Length': str(end-start+1), 'ETag': SOURCE.etag}
        headers.update(overrides.pop('headers', {}))
        return httpx.Response(overrides.get('status', 206), headers=headers,
                              stream=httpx.ByteStream(overrides.get('body', body[start:end+1])))
    return httpx.MockTransport(handle), requests


def test_cross_block_seek_cache_and_exact_anonymous_request():
    transport, requests = transport_for()
    with RangeReader(SOURCE, transport=transport, block_size=4) as reader:
        reader.seek(2)
        assert reader.read(5) == b'cdefg'
        reader.seek(3)
        buffer = bytearray(3)
        assert reader.readinto(buffer) == 3
        assert buffer == b'def'
        assert reader.requests == 2
        assert reader.received_bytes == 8
        assert all(r['object_identity'] == SOURCE.identity for r in reader.receipts)
        reader.seek(-2, 2)
        assert reader.read(9) == b'op'
        assert reader.read(1) == b''
    assert requests[0].url == SOURCE.url
    assert requests[0].headers['if-match'] == SOURCE.etag
    assert requests[0].headers['accept-encoding'] == 'identity'
    assert 'authorization' not in requests[0].headers
    assert 'cookie' not in requests[0].headers


@pytest.mark.parametrize('change', [
    {'status': 200}, {'status': 302}, {'status': 412},
    {'headers': {'ETag': '"def"'}},
    {'headers': {'Content-Range': 'bytes 1-4/16'}},
    {'headers': {'Content-Length': '16'}},
    {'headers': {'Content-Encoding': 'gzip'}},
    {'body': b'ab'}, {'body': b'abcde'},
])
def test_refuses_bad_or_unpinned_response_without_cache(change):
    transport, requests = transport_for(**change)
    with RangeReader(SOURCE, transport=transport, block_size=4) as reader:
        with pytest.raises(RangeRefused):
            reader.read(1)
        assert not reader.receipts
        assert reader.tell() == 0
        assert len(requests) == 1


def test_server_ignoring_range_is_closed_without_consuming_body():
    class ExplodingStream(httpx.SyncByteStream):
        closed = False
        def __iter__(self):
            raise AssertionError('Unbounded response consumed')
            yield b''
        def close(self):
            self.closed = True
    stream = ExplodingStream()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    with RangeReader(SOURCE, transport=transport) as reader:
        with pytest.raises(RangeRefused):
            reader.read(1)
        assert reader.received_bytes == 0
    assert stream.closed


@pytest.mark.parametrize('limits', [{'max_bytes': 4}, {'max_requests': 1}])
def test_budget_stops_next_network_request(limits):
    transport, requests = transport_for()
    with RangeReader(SOURCE, transport=transport, block_size=4, **limits) as reader:
        assert reader.read(4) == b'abcd'
        with pytest.raises(RangeRefused):
            reader.read(1)
        assert len(requests) == 1
        reader.seek(0)
        assert reader.read(4) == b'abcd'


def test_deadline_and_unbounded_reads_never_make_request():
    now = [0.0]
    transport, requests = transport_for()
    with RangeReader(SOURCE, transport=transport, clock=lambda: now[0], timeout_seconds=1) as reader:
        with pytest.raises(RangeRefused):
            reader.read()
        now[0] = 2
        with pytest.raises(RangeRefused):
            reader.read(1)
    assert requests == []


def test_cache_identity_binds_revision_initializer_and_size():
    assert SOURCE.identity != NativeObject(KEY, 17, SOURCE.etag).identity
    assert SOURCE.identity != NativeObject(KEY, 16, '"def"').identity
    assert SOURCE.identity != NativeObject(KEY.replace('GFS', 'IFS'),16, SOURCE.etag).identity
    for key in [KEY.replace('v100','v150'), KEY.replace('/0907/', '/0906/'), 'https://elsewhere/x']:
        with pytest.raises(ValueError):
            NativeObject(key, 16, SOURCE.etag)


def test_failed_attempt_reserves_budget_and_has_no_retry():
    transport, requests = transport_for(status=500)
    with RangeReader(SOURCE, transport=transport, block_size=4, max_bytes=4) as reader:
        for _ in range(2):
            with pytest.raises(RangeRefused):
                reader.read(1)
        assert reader.requests == len(requests) == 1
        assert reader.received_bytes == 0


def test_closed_reader_refuses_reads():
    transport, _ = transport_for()
    reader = RangeReader(SOURCE, transport=transport)
    reader.close()
    with pytest.raises(ValueError):
        reader.read(1)


def test_provider_cookie_does_not_authenticate_later_range():
    transport, requests = transport_for(headers={'Set-Cookie': 'session=value; Path=/'})
    with RangeReader(SOURCE, transport=transport, block_size=4) as reader:
        assert reader.read(8) == b'abcdefgh'
    assert len(requests) == 2
    assert all('cookie' not in request.headers for request in requests)


@pytest.mark.parametrize("limits", [
    {"max_bytes": float("inf")}, {"max_requests": float("nan")},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": float("nan")},
    {"block_size": 0}, {"max_bytes": True}, {"max_requests": 1.5},
])
def test_nonfinite_or_noninteger_budgets_refused(limits):
    with pytest.raises(ValueError):
        RangeReader(SOURCE, **limits)
