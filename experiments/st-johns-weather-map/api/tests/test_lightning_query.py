from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock

import httpx
import pytest

from weather_api.lightning_query import CACHE_MAX_BYTES, CACHE_MAX_ENTRIES, LightningQueryService, LightningQueryUnavailable
from weather_api.lightning_query_worker import normalize_capabilities, normalize_sample

SELECTED = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)


class Clocks:
    monotonic = 100.0
    wall = SELECTED + timedelta(seconds=1)

    def tick(self, seconds: int):
        self.monotonic += seconds
        self.wall += timedelta(seconds=seconds)


def capabilities(*times: datetime) -> bytes:
    extent = ",".join(item.isoformat().replace("+00:00", "Z") for item in times)
    return f'''<WMS_Capabilities updateSequence="fixed" xmlns="http://www.opengis.net/wms"><Capability><Layer><Layer queryable="1"><Name>Lightning_2.5km_Density</Name><Dimension name="time" units="ISO8601">{extent}</Dimension></Layer></Layer></Capability></WMS_Capabilities>'''.encode()


def sample(value=0.42, *, at=SELECTED, latitude=47.5391, longitude=-52.6859):
    return {
        "type": "FeatureCollection", "layer": "Lightning_2.5km_Density", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": {
                "value": value, "title_en": "Lightning Flash Density over Canada (2.5 km) [flash/km²/min]",
                "time": at.isoformat().replace("+00:00", "Z"), "dim_reference_time": "N/A",
            },
        }],
    }


def fixed_decode(kind: str, body: bytes):
    return normalize_capabilities(body) if kind == "capabilities" else normalize_sample(body)


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def service(handler, clocks: Clocks, *, decode=fixed_decode):
    return LightningQueryService(
        client=mock_client(handler), clock=lambda: clocks.monotonic,
        utcnow=lambda: clocks.wall, decode=decode, before_request=lambda: None,
    )


def successful_handler(calls: list[httpx.Request], *, payload=None, max_age=60):
    def handler(request):
        calls.append(request)
        if "GetCapabilities" in str(request.url):
            return httpx.Response(200, content=capabilities(SELECTED), headers={"Cache-Control": f"max-age={max_age}"})
        return httpx.Response(200, json=sample() if payload is None else payload, headers={"Cache-Control": f"max-age={max_age}"})
    return handler


def test_worker_preserves_exact_advertised_times_numeric_cell_and_native_empty_semantics():
    assert normalize_capabilities(capabilities(SELECTED))["times"] == [SELECTED.isoformat()]
    numeric = normalize_sample(json.dumps(sample()).encode())
    assert numeric["value"] == 0.42 and numeric["valid_time"] == SELECTED.isoformat()
    assert numeric["latitude"] == 47.5391 and numeric["native_units"] == "flash/km²/min"
    assert normalize_sample(b"{}") == {
        "value": None, "valid_time": None, "latitude": None, "longitude": None,
        "title": None, "native_units": None,
    }


@pytest.mark.parametrize('value', [None, True, 'bad', float('nan'), float('inf'), -1])
def test_invalid_density_never_becomes_no_detection(value):
    with pytest.raises(ValueError):
        normalize_sample(json.dumps(sample(value)).encode())


def test_empty_feature_list_and_wrong_layer_are_not_no_detection():
    for document in ({'features': []}, {**sample(), 'layer': 'wrong'}):
        with pytest.raises(ValueError):
            normalize_sample(json.dumps(document).encode())


def test_cache_identity_expiry_refresh_and_native_gap():
    calls, clocks = [], Clocks()
    query = service(successful_handler(calls), clocks)
    first = query.entry_for(47.56, -52.72, SELECTED)
    clocks.tick(17)
    assert query.entry_for(47.56, -52.72, SELECTED) is first
    assert len(calls) == 2
    assert first.acquisition.expires_at == SELECTED + timedelta(seconds=61)
    assert query.entry_for(47.56, -52.72, SELECTED, refresh=True) is not first
    assert len(calls) == 4
    with pytest.raises(LightningQueryUnavailable) as caught:
        query.entry_for(47.56, -52.72, SELECTED + timedelta(minutes=1))
    assert caught.value.outcome.reason == 'unsupported_time'
    assert len(calls) == 5
    query.entry_for(47.56000001, -52.72, SELECTED)
    assert len(calls) == 7


def test_capability_expiry_does_not_restart_after_sample_download():
    clocks = Clocks()
    def handler(request):
        if 'GetCapabilities' in str(request.url):
            return httpx.Response(200, content=capabilities(SELECTED), headers={'Cache-Control': 'max-age=60'})
        clocks.tick(20)
        return httpx.Response(200, json=sample(), headers={'Cache-Control': 'max-age=60'})
    query = service(handler, clocks)
    entry = query.entry_for(47.56, -52.72, SELECTED)
    assert entry.acquisition.cached_at == SELECTED + timedelta(seconds=21)
    assert entry.acquisition.expires_at == SELECTED + timedelta(seconds=61)
    assert entry.expires_at_monotonic == 160


def test_identical_concurrent_misses_coalesce():
    calls, lock, clocks = [], Lock(), Clocks()
    def handler(request):
        with lock:
            calls.append(request)
        time.sleep(0.03)
        return httpx.Response(200, content=capabilities(SELECTED)) if 'GetCapabilities' in str(request.url) else httpx.Response(200, json=sample())
    query = service(handler, clocks)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: query.entry_for(47.56, -52.72, SELECTED), range(8)))
    assert len(calls) == 2 and all(item is results[0] for item in results)


def test_distinct_concurrent_misses_are_bounded():
    from threading import Event
    from weather_api.lightning_query import MAX_INFLIGHT
    entered, release, lock = Event(), Event(), Lock()
    count = 0
    def handler(request):
        nonlocal count
        with lock:
            count += 1
            if count == MAX_INFLIGHT:
                entered.set()
        assert release.wait(5)
        return httpx.Response(200, content=capabilities(SELECTED)) if 'GetCapabilities' in str(request.url) else httpx.Response(200, json=sample())
    query = service(handler, Clocks())
    with ThreadPoolExecutor(max_workers=MAX_INFLIGHT) as pool:
        futures = [pool.submit(query.entry_for, 47.56, -52.72 + i / 100, SELECTED) for i in range(MAX_INFLIGHT)]
        try:
            assert entered.wait(5)
            with pytest.raises(LightningQueryUnavailable, match='concurrent'):
                query.entry_for(47.57, -52.72, SELECTED)
        finally:
            release.set()
        for future in futures:
            future.result()


def test_expired_failed_replacement_withholds_values_and_bounds_residency():
    clocks, fail = Clocks(), False
    def handler(request):
        if fail:
            return httpx.Response(503)
        return httpx.Response(200, content=capabilities(SELECTED), headers={'Cache-Control': 'max-age=1'}) if 'GetCapabilities' in str(request.url) else httpx.Response(200, json=sample(), headers={'Cache-Control': 'max-age=1'})
    query = service(handler, clocks)
    for index in range(CACHE_MAX_ENTRIES + 5):
        fail = False
        longitude = -52.72 + index / 10000
        original = query.entry_for(47.56, longitude, SELECTED).acquisition
        clocks.tick(2)
        fail = True
        with pytest.raises(LightningQueryUnavailable) as caught:
            query.entry_for(47.56, longitude, SELECTED)
        assert caught.value.outcome.expired_acquisition == original
        assert caught.value.outcome.values_withheld
    assert len(query._entries) + len(query._expired) <= CACHE_MAX_ENTRIES
    assert sum(e.backing_bytes for e in query._entries.values()) + sum(len(e.model_dump_json().encode()) for e in query._expired.values()) <= CACHE_MAX_BYTES


@pytest.mark.skipif(sys.platform == 'darwin', reason='macOS rejects locked RLIMIT_AS; proved in Linux')
def test_actual_bounded_child_decodes_fixed_capability_and_sample_payloads():
    from weather_api.lightning_query import _decode
    calls, clocks = [], Clocks()
    query = service(successful_handler(calls), clocks, decode=_decode)
    entry = query.entry_for(47.56, -52.72, SELECTED)
    assert entry.sample.value == 0.42
    assert query.entry_for(47.56, -52.72, SELECTED) is entry
    assert len(calls) == 2


def test_ogc_exception_code_and_transport_limits_are_preserved():
    from weather_api.lightning_query import CAPABILITIES_MAX_BYTES, _ttl
    with pytest.raises(ValueError, match='NoMatch'):
        normalize_sample(b'<ServiceExceptionReport><ServiceException code="NoMatch"/></ServiceExceptionReport>')
    for headers in ({'cache-control': 'no-store'}, {'cache-control': 'max-age=10', 'age': '10'}):
        with pytest.raises(LightningQueryUnavailable):
            _ttl(headers, SELECTED)
    def oversized(request):
        return httpx.Response(200, content=b'x', headers={'Content-Length': str(CAPABILITIES_MAX_BYTES + 1)})
    with pytest.raises(LightningQueryUnavailable, match='ceiling'):
        service(oversized, Clocks()).entry_for(47.56, -52.72, SELECTED)


def test_wall_clock_rollback_during_decode_cannot_extend_monotonic_deadline():
    calls, clocks = [], Clocks()
    def decode(kind, body):
        result = fixed_decode(kind, body)
        if kind == 'sample':
            clocks.monotonic += 20
            clocks.wall -= timedelta(seconds=300)
        return result
    query = service(successful_handler(calls), clocks, decode=decode)
    original = query.entry_for(47.56, -52.72, SELECTED)
    assert original.expires_at_monotonic == 160
    assert original.acquisition.expires_at == SELECTED + timedelta(seconds=61)
    clocks.monotonic = 159
    assert query.entry_for(47.56, -52.72, SELECTED) is original
    clocks.monotonic = 160
    assert query.cached_entries() == ()


@pytest.mark.parametrize('expire_during_refresh', [False, True])
def test_concurrent_failed_refresh_preserves_only_still_valid_evidence(expire_during_refresh):
    from threading import Event
    calls, clocks, entered, release = [], Clocks(), Event(), Event()
    fail = False
    initial = successful_handler(calls)
    def handler(request):
        if fail:
            entered.set()
            assert release.wait(5)
            return httpx.Response(503)
        return initial(request)
    query = service(handler, clocks)
    original = query.entry_for(47.56, -52.72, SELECTED)
    fail = True
    clocks.tick(10)
    with ThreadPoolExecutor(max_workers=1) as pool:
        refreshing = pool.submit(query.entry_for, 47.56, -52.72, SELECTED, refresh=True)
        try:
            assert entered.wait(5)
            assert query.entry_for(47.56, -52.72, SELECTED) is original
            assert query.cached_entries() == (original,)
            assert not query._expired
            if expire_during_refresh:
                clocks.tick(50)
                assert query.cached_entries() == ()
        finally:
            release.set()
        with pytest.raises(LightningQueryUnavailable) as caught:
            refreshing.result()
    if expire_during_refresh:
        assert caught.value.outcome.expired_acquisition == original.acquisition
        assert caught.value.outcome.reason == 'refresh_failed'
        assert query.cached_entries() == ()
    else:
        assert caught.value.outcome.expired_acquisition is None
        assert query.entry_for(47.56, -52.72, SELECTED) is original
        clocks.tick(50)
        with pytest.raises(LightningQueryUnavailable) as expired:
            query.entry_for(47.56, -52.72, SELECTED)
        assert expired.value.outcome.expired_acquisition == original.acquisition


@pytest.mark.parametrize('failure_kind', ['capabilities', 'sample'])
def test_decoder_error_text_is_not_exposed(failure_kind):
    def decode(kind, body):
        if kind == failure_kind:
            raise ValueError('untrusted-provider-detail')
        return fixed_decode(kind, body)
    query = service(successful_handler([]), Clocks(), decode=decode)
    with pytest.raises(LightningQueryUnavailable) as caught:
        query.entry_for(47.56, -52.72, SELECTED)
    assert str(caught.value) == f'ECCC lightning {failure_kind} validation failed: ValueError'
    assert 'untrusted-provider-detail' not in caught.value.outcome.model_dump_json()
