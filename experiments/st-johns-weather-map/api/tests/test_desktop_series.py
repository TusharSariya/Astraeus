"""Mapped to desktop-evidence-api-contract/native-series and stable selections."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import threading

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from weather_api.app import app
from weather_api.desktop_series import SeriesSelection, SeriesService, SeriesRow, NativeForecastReader
from weather_api.fixtures import point_fields

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def selection(**updates):
    return SeriesSelection.model_validate(dict(latitude=47.56153, longitude=-52.71261,
        start=NOW, end=NOW + timedelta(hours=3), page_size=1,
        selectors=[dict(id='a', source_id='eccc-hrdps', field='temperature_2m')], **updates))


def sample(at=NOW, value=0):
    field = point_fields(at)[0][0].model_copy(deep=True)
    field.value = value
    field.provenance.source_id = 'eccc-hrdps'
    field.provenance.valid_time = at
    return field


def rows(request, stop):
    return [SeriesRow(selector_id=s.id, source_id=s.source_id, field=s.field,
        requested_run=s.run, availability='available', samples=[sample(), sample(NOW + timedelta(minutes=97), 2)])
        for s in request.selectors]


class Clock:
    elapsed = 0
    def monotonic(self): return self.elapsed
    def utcnow(self): return NOW + timedelta(seconds=self.elapsed)


def test_native_paging_fixed_expiry_and_no_mutable_output():
    clock = Clock()
    service = SeriesService(rows, clock=clock.monotonic, utcnow=clock.utcnow)
    first = service.initial(selection())
    assert first.series[0].samples[0].value == 0
    assert not first.complete
    first.series[0].samples[0].value = 999
    clock.elapsed = 100
    second = service.continuation(first.next_cursor)
    assert second.snapshot == first.snapshot
    assert second.series[0].samples[0].provenance.valid_time == NOW + timedelta(minutes=97)
    assert second.complete
    assert service.changes(first.snapshot.change_token).state == 'unchanged'
    assert service.entries[first.snapshot.id].rows[0].samples[0].value == 0
    clock.elapsed = 300
    service._expire()
    for token, call in [(first.next_cursor, service.continuation), (first.snapshot.change_token, service.changes)]:
        with pytest.raises(HTTPException) as caught: call(token)
        assert caught.value.detail['code'] == 'snapshot_expired'
        assert caught.value.detail['restart_required']


def test_selection_specific_baseline_failed_check_and_explicit_refresh():
    current = rows(selection(), None)
    service = SeriesService(lambda *args: current, utcnow=lambda: NOW)
    first = service.initial(selection())
    # Returning acquisition time is not a change in the selected evidence.
    current = [row.model_copy(deep=True) for row in current]
    current[0].samples[0].provenance.retrieval_time += timedelta(minutes=5)
    assert service.changes(first.snapshot.change_token).state == 'unchanged'
    current[0].samples[0].value = 1
    result = service.changes(first.snapshot.change_token)
    assert result.state == 'changed' and result.changed_selector_ids == ['a']
    assert service.changes(first.snapshot.change_token).state == 'changed'
    assert first.series[0].samples[0].value == 0
    refreshed = service.initial(selection())
    assert refreshed.snapshot.id != first.snapshot.id
    assert refreshed.series[0].samples[0].value == 1
    service.reader = lambda *args: (_ for _ in ()).throw(RuntimeError('unreadable'))
    assert service.changes(first.snapshot.change_token).state == 'unknown'
    with pytest.raises(HTTPException): service.initial(selection())
    assert first.series[0].samples[0].value == 0


def test_altered_cursor_refused_and_outside_point_preserved(monkeypatch):
    import weather_api.desktop_series as api
    service = SeriesService(rows)
    monkeypatch.setattr(api, 'series_service', lambda: service)
    client = TestClient(app)
    url = '/api/experiments/weather/v0/point/series'
    first = client.post(url, json=selection().model_dump(mode='json')).json()
    response = client.post(url, json={'cursor': first['next_cursor'], 'latitude': 1})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'invalid_cursor'
    assert client.post(url, json={'cursor': 'tampered'}).json()['detail']['code'] == 'invalid_cursor'
    request = selection().model_dump(mode='json')
    request['latitude'] = 0
    assert client.post(url, json=request).json()['detail']['code'] == 'outside_supported_area'
    request['latitude'] = 47.56153
    request['end'] = (NOW + timedelta(hours=25)).isoformat()
    assert client.post(url, json=request).json()['detail']['code'] == 'invalid_selection'


def test_coalesced_concurrent_misses_and_cache_capacity(monkeypatch):
    import weather_api.desktop_series as api
    entered, release = threading.Event(), threading.Event()
    calls = []
    def reader(request, stop):
        calls.append(1); entered.set(); assert release.wait(2)
        return rows(request, stop)
    service = SeriesService(reader)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(service.initial, selection())
        assert entered.wait(2)
        attached = threading.Event()
        pending = service.inflight[selection().model_dump_json()]
        original = pending.result
        def awaiting(*args, **kwargs):
            attached.set()
            return original(*args, **kwargs)
        pending.result = awaiting
        two = pool.submit(service.initial, selection())
        assert attached.wait(2)
        release.set()
        assert one.result().snapshot.id == two.result().snapshot.id
    assert len(calls) == 1
    monkeypatch.setattr(api, 'MAX_SELECTIONS', 1)
    with pytest.raises(HTTPException) as caught: service.initial(selection())
    assert caught.value.detail['code'] == 'snapshot_capacity_unavailable'


def test_deadline_stops_fanout_and_retains_slot_until_worker_finishes():
    release = threading.Event()
    stopped = []
    def reader(request, stop):
        release.wait(2)
        stopped.append(stop())
        return rows(request, stop)
    service = SeriesService(reader, read_seconds=.01)
    try:
        for _ in range(2):
            with pytest.raises(HTTPException) as caught: service.initial(selection())
            assert caught.value.detail['code'] == 'snapshot_unreadable'
        with pytest.raises(HTTPException) as caught: service.initial(selection())
        assert caught.value.detail['code'] == 'snapshot_capacity_unavailable'
    finally:
        release.set()
        service.executor.shutdown(wait=True)
    assert stopped == [True, True]


def test_native_adapter_uses_only_advertised_timestamps_and_exact_source(monkeypatch):
    monkeypatch.setenv('WEATHER_DATA_MODE', 'live')
    import weather_api.hrdps_query as hrdps
    calls = []
    class Source:
        def timeline_times(self, reference): return (NOW, NOW + timedelta(minutes=97))
        def point_fields(self, latitude, longitude, stamp):
            calls.append(stamp)
            own = sample(stamp)
            other = own.model_copy(deep=True)
            other.provenance.source_id = 'unrelated-source'
            return [own, other], None, []
    monkeypatch.setattr(hrdps, 'hrdps_query_coordinator', Source)
    result = NativeForecastReader()(selection(), lambda: False)
    assert len(result[0].samples) == 2
    assert calls == [NOW, NOW + timedelta(minutes=97)]
    assert all(s.provenance.source_id == 'eccc-hrdps' for s in result[0].samples)
    request = selection()
    request.selectors[0].run = 'previous-removed'
    assert NativeForecastReader()(request, lambda: False)[0].availability == 'unavailable'
    assert len(calls) == 2


def test_sparse_sources_do_not_borrow_each_others_times(monkeypatch):
    monkeypatch.setenv('WEATHER_DATA_MODE', 'live')
    import weather_api.hrdps_query as hrdps
    import weather_api.gfs_query as gfs
    class Source:
        def __init__(self, source, stamps): self.source, self.stamps = source, stamps
        def timeline_times(self, _): return (self.stamps, {}) if self.source == 'noaa-gfs' else self.stamps
        def point_fields(self, lat, lon, stamp):
            assert stamp in self.stamps
            value = sample(stamp)
            value.provenance.source_id = self.source
            return [value], None, []
    monkeypatch.setattr(hrdps, 'hrdps_query_coordinator', lambda: Source('eccc-hrdps', (NOW, NOW + timedelta(minutes=97))))
    monkeypatch.setattr(gfs, 'gfs_query_coordinator', lambda: Source('noaa-gfs', (NOW + timedelta(minutes=33),)))
    request = selection()
    request.selectors.append(request.selectors[0].model_copy(update={'id': 'b', 'source_id': 'noaa-gfs'}))
    result = NativeForecastReader()(request, lambda: False)
    assert [s.provenance.valid_time for s in result[0].samples] == [NOW, NOW + timedelta(minutes=97)]
    assert [s.provenance.valid_time for s in result[1].samples] == [NOW + timedelta(minutes=33)]


def test_native_acquisition_limit_precedes_payloads_and_missing_field_is_unknown(monkeypatch):
    monkeypatch.setenv('WEATHER_DATA_MODE', 'live')
    import weather_api.hrdps_query as hrdps
    stamps = tuple(NOW + timedelta(minutes=i) for i in range(13))
    class Source:
        def timeline_times(self, _): return stamps
        def point_fields(self, *args): raise AssertionError('no payload before limit gate')
    monkeypatch.setattr(hrdps, 'hrdps_query_coordinator', Source)
    with pytest.raises(HTTPException) as caught: NativeForecastReader()(selection(), lambda: False)
    assert caught.value.detail['code'] == 'query_limit_exceeded'
    stamps = ()
    result = NativeForecastReader()(selection(), lambda: False)
    assert result[0].availability == 'unknown' and result[0].samples == []


def test_byte_budget_and_explicit_checked_absence(monkeypatch):
    import weather_api.desktop_series as api
    from weather_api.models import EvidenceField
    missing = EvidenceField.model_validate(sample().model_dump(round_trip=True) | {'value': None})
    def reader(request, stop):
        result = rows(request, stop)
        result[0].samples = [sample(), missing]
        return result
    service = SeriesService(reader)
    initial = service.initial(selection())
    assert initial.series[0].samples[0].value == 0
    next_page = service.continuation(initial.next_cursor)
    assert next_page.series[0].samples[0].value is None
    assert next_page.series[0].samples[0].absence_state is not None
    monkeypatch.setattr(api, 'MAX_RESPONSE_BYTES', 10)
    with pytest.raises(HTTPException) as caught: service.initial(selection())
    assert caught.value.detail['code'] == 'query_limit_exceeded'
    assert len(service.entries) == 1


def test_unselected_source_update_does_not_change_selection_and_check_cannot_outlive_expiry():
    values = {'eccc-hrdps': 0, 'noaa-gfs': 2}
    consulted = []
    clock = Clock()
    def reader(request, stop):
        result = rows(request, stop)
        for row in result:
            consulted.append(row.source_id)
            for field in row.samples: field.value = values[row.source_id]
        return result
    service = SeriesService(reader, clock=clock.monotonic, utcnow=clock.utcnow)
    first = service.initial(selection())
    values['noaa-gfs'] = 99
    assert service.changes(first.snapshot.change_token).state == 'unchanged'
    assert set(consulted) == {'eccc-hrdps'}
    def slow_read(request, stop):
        clock.elapsed = 300
        return reader(request, stop)
    service.reader = slow_read
    with pytest.raises(HTTPException) as caught: service.changes(first.snapshot.change_token)
    assert caught.value.detail['code'] == 'snapshot_expired'
