"""Mapped GEPS shared delivery: exact variants, unknown run and full5 receipts."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import json
import sys
import pytest
from test_geps_query import FixtureClient, RUN, VALID
from weather_api.geps_delivery import (GEPSReductionSource, GEPSPointService, GEPSLatestLoader,
    acquire_latest, PRODUCT_ID)
from weather_api.source_delivery import reading_identity
from weather_api.native_runs import RunUnavailable


class ReceiptFixture(FixtureClient):
    def get_bytes_with_receipt(self, *args, **kwargs):
        body, receipt = super().get_bytes_with_receipt(*args, **kwargs)
        receipt['http_status'] = 200
        return body, receipt

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@pytest.fixture
def setup(tmp_path):
    clock = [0.]
    calls = []
    client = ReceiptFixture()
    def acquire(selected):
        calls.append(selected)
        return acquire_latest(selected, client, tmp_path, clock=lambda: clock[0], utcnow=lambda: VALID+timedelta(minutes=1,seconds=clock[0]))
    service = GEPSPointService(tmp_path, loader=acquire, clock=lambda: clock[0], utcnow=lambda: VALID+timedelta(minutes=1,seconds=clock[0]))
    return service, calls, client, clock


def test_descriptors_are_exact_variants_without_io(setup):
    service, calls, client, _ = setup
    reader = GEPSReductionSource(lambda: service)
    descriptors = reader.descriptors()
    assert len(descriptors) == 4
    assert [d.variants[0].statistic for d in descriptors] == ['ensemble_mean','ensemble_spread','ensemble_quantile','ensemble_quantile']
    assert [d.variants[0].quantile for d in descriptors] == [None,None,.5,.5]
    assert all(d.variants[0].kind == 'provider_statistic' and d.run_selection == 'not_applicable' and not d.native_series for d in descriptors)
    assert all('527' in d.coverage_description and 'raw gust' in d.coverage_description for d in descriptors)
    assert not calls and not client.requests


def test_point_preserves_provider_variants_unknown_run_and_all_five(setup):
    service, calls, client, _ = setup
    reader = GEPSReductionSource(lambda: service)
    fields = reader.read_point(47.5,-52.,VALID)
    assert len(fields) == 4 and len(client.requests) == 11
    identities = [reading_identity(f, PRODUCT_ID) for f in fields]
    assert len({i.model_dump_json() for i in identities}) == 4
    for field, identity in zip(fields, identities, strict=True):
        p = field.provenance
        assert field.value == 42
        assert field.storage == 'available-not-stored'
        assert p.run_time is None and p.run_stale is None and p.source_acquisition.provider_run_id is None
        assert p.ensemble.computed_here is False and p.member is None and p.ensemble.member_set is None
        assert p.quality.status == 'unknown' and p.freshness.status == 'unknown'
        assert p.source_display_primary is False and p.delivery_kind == 'reprocessed'
        assert p.sampled_latitude == 47.25 and p.sampled_longitude == -51.75
        assert identity.variant.kind == 'provider_statistic' and identity.run_time is None
        assert len(p.source_acquisition.transport_receipts) == 11
        assert 'DIM_REFERENCE_TIME=' in p.source_acquisition.transport_receipts[-1].url
        assert p.source_acquisition.run_time is None
    assert [f.provenance.normalized_units for f in fields] == ['degC','degC','degC','percent']
    entry = service.query(VALID)
    assert len(entry.provenance['reductions']) == 5
    assert entry.provenance['reductions'][-1]['field'] == 'raw_gust_threshold'
    assert len(calls) == 1 and len(client.requests) == 11


def test_masked_output_stays_null(setup):
    service, *_ = setup
    fields = service.point_fields(50.25,-57.75,VALID)
    assert all(f.value is None and f.provenance.quality.status == 'unknown' for f in fields)


def test_unsupported_run_and_point_have_no_io(setup):
    service, calls, client, _ = setup
    reader = GEPSReductionSource(lambda: service)
    with pytest.raises(RunUnavailable):
        reader.read_point(47.5,-52.,VALID,run='2026090500')
    with pytest.raises(ValueError):
        reader.read_point(0.,0.,VALID)
    with pytest.raises(ValueError):
        reader.read_point(47.5,-52.,VALID+timedelta(minutes=1))
    assert reader.plan_series(VALID,VALID+timedelta(hours=3)) is None
    assert not calls and not client.requests


def test_final_byte_expiry_and_failed_refresh(setup):
    service, calls, client, clock = setup
    first = service.query(VALID)
    def fail(_):
        raise RuntimeError('fixture unavailable')
    service.loader = fail
    clock[0] = 10
    with pytest.raises(RuntimeError):service.query(VALID,refresh=True)
    assert service.query(VALID) == first
    clock[0] = 300
    with pytest.raises(RuntimeError):service.query(VALID)
    assert service.cached is None


def test_late_decode_does_not_extend_expiry(setup):
    service, calls, client, clock = setup
    original = service.loader
    def delayed(selected):
        entry = original(selected)
        clock[0] = 40.
        return entry
    service.loader = delayed
    service.query(VALID)
    assert service.cached[0] == 300


@pytest.mark.skipif(sys.platform != 'linux', reason='real bounded Linux worker')
def test_real_latest_worker_offline(tmp_path):
    from ingest.isolation import run_bounded_process
    def runner(**kwargs):
        code = f"import sys;sys.path.insert(0,{str(Path(__file__).parent)!r});from test_geps_delivery import ReceiptFixture;import weather_api.geps_delivery_worker as worker;worker.GEPSDeliveryHTTP=ReceiptFixture;worker.main()"
        kwargs['command'] = [sys.executable,'-c',code,'{output}']
        return run_bounded_process(**kwargs)
    entry = GEPSLatestLoader(tmp_path,runner=runner)(VALID)
    assert entry.key.valid_time == VALID and entry.key.reference_time == RUN
    assert len(entry.provenance['transport_receipts']) == 10
    assert len(entry.provenance['discovery_receipts']) == 1
    assert list(tmp_path.iterdir()) == []


def test_concurrent_refresh_shares_one_acquisition(setup, monkeypatch):
    import threading
    from concurrent.futures import Future, ThreadPoolExecutor
    import weather_api.geps_delivery as module
    service, calls, client, clock = setup
    entered, release, joined = threading.Event(), threading.Event(), threading.Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout)
    monkeypatch.setattr(module, 'Future', ObservedFuture)
    original = service.loader
    def held(selected):
        entered.set()
        assert release.wait(5)
        return original(selected)
    service.loader = held
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(service.query, VALID, refresh=True)
        assert entered.wait(5)
        second = pool.submit(service.query, VALID, refresh=True)
        assert joined.wait(5)
        release.set()
        assert first.result() == second.result()
    assert len(calls) == 1


def test_returned_metadata_cannot_modify_cached_evidence(setup):
    service, *_ = setup
    entry = service.query(VALID)
    entry.provenance['quality']['status'] = 'passed'
    assert service.query(VALID).provenance['quality']['status'] == 'unknown'


def test_raw_unmapped_fifth_is_not_advertised_as_numeric_gust(setup):
    service, *_ = setup
    reader = GEPSReductionSource(lambda: service)
    assert {d.field for d in reader.descriptors()} == {'temperature_2m','total_cloud_opacity'}
    assert all(f.key != 'wind_gust_10m' for f in reader.read_point(47.5,-52.,VALID))
