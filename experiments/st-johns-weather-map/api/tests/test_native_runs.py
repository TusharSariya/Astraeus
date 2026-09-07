"""Mapped to desktop-evidence-api: source-scoped latest/previous and finite pins."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib
import threading

import pytest
from ingest.contract import RunCandidate
from weather_api.native_runs import NativeRunInventory, RunUnavailable

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def candidate(hours=0):
    run = NOW - timedelta(hours=hours)
    return RunCandidate(run.strftime('%Y%m%d%H'), run, [],
        {'cycle_url': f'https://example/{run:%Y%m%d%H}/', 'available_hours': ['000', '006', '012']})


def test_inventory_fixed_expiry_no_stale_and_removed_run_refusal():
    elapsed = 0
    calls = []
    current = [candidate(12), candidate(6), candidate(), candidate(-6)]
    def discover(window):
        calls.append(window)
        if current is None: raise OSError('provider unavailable')
        return current
    inventory = NativeRunInventory(discover, now=lambda: NOW, clock=lambda: elapsed, ttl=10)
    assert [run.provider_run_id for run in inventory.candidates()] == [candidate().provider_run_id, candidate(6).provider_run_id]
    assert calls[0].back_hours == 24 and calls[0].forward_hours == 0
    assert inventory.resolve(candidate(6).provider_run_id).run_time == NOW - timedelta(hours=6)
    result = inventory.candidates()
    result[0].detail['available_hours'].clear()
    elapsed = 9
    assert inventory.candidates()[0].detail['available_hours']
    assert len(calls) == 1
    elapsed = 10
    current = None
    with pytest.raises(OSError): inventory.candidates()
    current = [candidate()]
    with pytest.raises(RunUnavailable): inventory.resolve(candidate(6).provider_run_id)
    assert len(calls) == 3


def test_inventory_coalesces_concurrent_misses_and_rejects_conflicting_identity():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def discover(_):
        calls.append(1); entered.set(); assert release.wait(2)
        return [candidate()]
    inventory = NativeRunInventory(discover, now=lambda: NOW, clock=lambda: 0, ttl=10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(inventory.candidates)
        assert entered.wait(2)
        two = pool.submit(inventory.candidates)
        release.set()
        assert one.result() == two.result()
    assert calls == [1]
    changed = candidate(); changed.detail['cycle_url'] = 'https://different/'
    invalid = NativeRunInventory(lambda _: [candidate(), changed], now=lambda: NOW, clock=lambda: 0, ttl=10)
    with pytest.raises(ValueError, match='Conflicting'): invalid.candidates()


@pytest.mark.parametrize('model', ['hrdps', 'rdps', 'gdps'])
def test_named_run_is_resolved_before_exact_frame_and_cache_key(model):
    module = importlib.import_module(f'weather_api.{model}_query')
    candidates = [candidate(), candidate(6)]
    class Adapter:
        var_map = {field: None for field in getattr(module, f'{model.upper()}_POINT_FIELDS')}
        bounds = {'north': 48, 'south': 47, 'west': -53, 'east': -52}
        def demand_operation_bounds(self, count): assert count > 0
        def discover(self, window): return candidates
    coordinator = getattr(module, f'{model.upper()}QueryCoordinator')(adapter=Adapter(), now=lambda: NOW)
    requested = []
    class Cache:
        def query(self, key): requested.append(key); return key
    coordinator._cache = Cache()
    old = coordinator.query(NOW, run_id=candidate(6).provider_run_id)
    new = coordinator.query(NOW, run_id=candidate().provider_run_id)
    assert old.provider_run_id != new.provider_run_id
    assert old != new
    assert NOW in coordinator.run_times(candidate(6).provider_run_id)
    with pytest.raises((ValueError, getattr(module, f'{model.upper()}QueryUnavailable', ValueError))):
        coordinator.query(NOW + timedelta(hours=1), run_id=candidate(6).provider_run_id)
    with pytest.raises(RunUnavailable): coordinator.query(NOW, run_id='removed')
    assert len(requested) == 2


@pytest.mark.parametrize('model', ['rdps', 'gdps'])
def test_failed_named_inventory_does_not_attach_default_run_failure_receipt(model):
    module = importlib.import_module(f'weather_api.{model}_query')
    class Adapter:
        var_map = {field: None for field in getattr(module, f'{model.upper()}_POINT_FIELDS')}
        bounds = {}
        def demand_operation_bounds(self, count): pass
        def discover(self, window): raise OSError('listing unavailable')
    coordinator = getattr(module, f'{model.upper()}QueryCoordinator')(adapter=Adapter(), now=lambda: NOW)
    coordinator._candidate = (0, candidate())
    class Cache:
        def expired_acquisition(self, key): pytest.fail('named read consulted default run receipt')
    coordinator._cache = Cache()
    with pytest.raises(getattr(module, f'{model.upper()}QueryUnavailable')):
        coordinator.query(NOW, run_id=candidate(6).provider_run_id)
