"""api-first-source-delivery: actual ECCC reader refresh, coalescing and expiry."""
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib
import threading
from types import SimpleNamespace

import pytest

from ingest.contract import RunCandidate
from weather_api.source_delivery import ForecastSource

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


@pytest.fixture(params=['hrdps', 'rdps', 'gdps'])
def native(request, monkeypatch):
    name = request.param
    module = importlib.import_module(f'weather_api.{name}_query')
    prefix = name.upper()
    clock = [0.0]
    calls = {'discover': 0, 'load': 0}
    candidate = RunCandidate('2026090712', NOW, [], {
        'cycle_url': 'https://fixture.invalid/12/', 'available_hours': ['000']})
    fields = getattr(module, f'{prefix}_POINT_FIELDS')
    def discover(window):
        calls['discover'] += 1
        return [candidate]
    adapter = SimpleNamespace(var_map=dict.fromkeys(fields), bounds={'east': -52.4},
        demand_operation_bounds=lambda count: None, discover=discover)
    coordinator = getattr(module, f'{prefix}QueryCoordinator')(adapter, now=lambda: NOW + timedelta(seconds=clock[0]), clock=lambda: clock[0])
    entry_type = getattr(module, f'{prefix}QueryEntry')
    def load(key):
        calls['load'] += 1
        return entry_type(key, NOW, NOW, NOW + timedelta(seconds=clock[0]),
            str(calls['load']) * 64, b'zip', {'source_id': f'eccc-{name}'})
    coordinator._cache._loader = load
    monkeypatch.setattr(coordinator, '_samples', lambda *args: ([], SimpleNamespace(skipped=[], unmodelled=[])))
    reader = ForecastSource(f'eccc-{name}', name, lambda: coordinator, ('temperature_2m',), named_runs=True)
    return SimpleNamespace(coordinator=coordinator, reader=reader, clock=clock, calls=calls, load=load, adapter=adapter)


def test_public_reader_refresh_reaches_actual_coordinator(native):
    native.reader.read_point(47.5, -52.7, NOW)
    native.reader.read_point(47.5, -52.7, NOW)
    assert native.calls == {'discover': 1, 'load': 1}
    native.reader.read_point(47.5, -52.7, NOW, refresh=True)
    assert native.calls == {'discover': 2, 'load': 2}


def test_identical_refreshes_coalesce_discovery_and_payload(native):
    native.coordinator.query(NOW)
    entered, release, joined = threading.Event(), threading.Event(), threading.Event()
    original = native.coordinator._cache._loader
    def blocked(key):
        entered.set()
        assert release.wait(5)
        return original(key)
    native.coordinator._cache._loader = blocked
    # Observe the second caller joining the actual pending future, avoiding
    # sleeps or scheduler assumptions in the overlapping refresh proof.
    class ObservedFuture(Future):
        def result(self, *args, **kwargs):
            joined.set()
            return super().result(*args, **kwargs)
    module = importlib.import_module(type(native.coordinator).__module__)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, 'Future', ObservedFuture)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(native.coordinator.query, NOW, refresh=True)
            assert entered.wait(5)
            second = pool.submit(native.coordinator.query, NOW, refresh=True)
            try:
                assert joined.wait(5)
            finally:
                release.set()
            assert first.result() is second.result()
    assert native.calls == {'discover': 2, 'load': 2}


def test_failed_refresh_preserves_unexpired_value_and_fixed_deadline(native):
    first = native.coordinator.query(NOW)
    native.clock[0] = 100
    def fail(key):
        raise ValueError('offline failed refresh')
    native.coordinator._cache._loader = fail
    with pytest.raises(Exception):
        native.coordinator.query(NOW, refresh=True)
    assert native.coordinator.query(NOW) is first
    native.clock[0] = 601
    with pytest.raises(Exception):
        native.coordinator.query(NOW)
    native.coordinator._cache._loader = native.load
    # Explicit retry bypasses failure backoff without extending the old value.
    renewed = native.coordinator.query(NOW, refresh=True)
    assert renewed is not first
    deadline = next(iter(native.coordinator._cache._entries.values()))[0]
    native.clock[0] = deadline - 1
    assert native.coordinator.query(NOW) is renewed
    assert next(iter(native.coordinator._cache._entries.values()))[0] == deadline


def test_pinned_refresh_keeps_requested_run(native):
    native.coordinator.query(NOW, run_id='2026090712')
    native.coordinator.query(NOW, run_id='2026090712', refresh=True)
    assert native.calls == {'discover': 2, 'load': 2}


def test_failed_discovery_refresh_keeps_unexpired_discovery_and_value(native):
    first = native.coordinator.query(NOW)
    original_deadline = native.coordinator._candidate[0]
    native.clock[0] = 100
    def fail(window):
        raise ValueError('offline discovery unavailable')
    native.adapter.discover = fail
    with pytest.raises(Exception):
        native.coordinator.query(NOW, refresh=True)
    assert native.coordinator.query(NOW) is first
    assert native.coordinator._candidate[0] == original_deadline
    native.clock[0] = 601
    with pytest.raises(Exception):
        native.coordinator.query(NOW)


def test_refresh_deadline_starts_after_new_payload_finishes(native):
    native.coordinator.query(NOW)
    native.clock[0] = 100
    def slow(key):
        native.clock[0] = 125
        return native.load(key)
    native.coordinator._cache._loader = slow
    refreshed = native.coordinator.query(NOW, refresh=True)
    deadline, cached = next(iter(native.coordinator._cache._entries.values()))
    assert cached is refreshed and deadline == 725
    acquisition = getattr(refreshed, 'acquisition', None)
    if acquisition is not None:
        assert acquisition.cached_at == NOW + timedelta(seconds=125)
        assert acquisition.expires_at == NOW + timedelta(seconds=725)


def test_pending_refresh_bookkeeping_is_bounded(native):
    module = importlib.import_module(type(native.coordinator).__module__)
    bound = getattr(module, type(native.coordinator).__name__.replace('QueryCoordinator', '') + '_CACHE_MAX_ENTRIES')
    native.coordinator._refreshes = {('pending', i): Future() for i in range(bound)}
    with pytest.raises(ValueError, match='concurrent refresh bound'):
        native.coordinator.query(NOW, refresh=True)
    assert native.calls == {'discover': 0, 'load': 0}


def test_refresh_failure_after_deadline_discloses_actual_expiry(native):
    first = native.coordinator.query(NOW)
    native.clock[0] = 599
    def slow_failure(key):
        native.clock[0] = 601
        raise ValueError('offline refresh failed after deadline')
    native.coordinator._cache._loader = slow_failure
    with pytest.raises(Exception) as failure:
        native.coordinator.query(NOW, refresh=True)
    acquisition = getattr(first, 'acquisition', None)
    if acquisition is not None:
        assert failure.value.outcome.reason == 'refresh_failed'
        assert failure.value.outcome.expired_acquisition == acquisition
    with pytest.raises(Exception):
        native.coordinator.query(NOW)
