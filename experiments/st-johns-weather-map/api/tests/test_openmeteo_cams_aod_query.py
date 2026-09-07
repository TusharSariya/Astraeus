"""GOV-SPEC-004/006: isolated named CAMS AOD delivery and cache verification."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import threading

import pytest

from weather_api.openmeteo_cams_aod_query import (
    MAX_RESPONSE_BYTES, TTL_SECONDS, OpenMeteoCamsAodQueryService,
    OpenMeteoCamsAodUnavailable,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def payload(times=None, values=None):
    return {"latitude": 47.55, "longitude": -52.7, "utc_offset_seconds": 0,
            "hourly_units": {"time": "iso8601", "aerosol_optical_depth": ""},
            "hourly": {"time": times or ["2026-09-07T12:00"],
                       "aerosol_optical_depth": values if values is not None else [0.15]}}


class Client:
    def __init__(self):
        self.payload = payload()
        self.calls = []
        self.fail = False
        self.entered = None
        self.release = None

    def download(self, url, path, *, max_bytes, headers, chunk_size):
        self.calls.append((url, max_bytes))
        if self.entered is not None:
            self.entered.set()
            assert self.release.wait(5)
        if self.fail:
            raise RuntimeError("fixture unavailable")
        body = json.dumps({"last_run_initialisation_time": NOW.timestamp()} if "meta.json" in url else self.payload).encode()
        if len(body) > max_bytes:
            raise RuntimeError("body exceeds bound")
        path.write_bytes(body)


def service():
    client = Client()
    monotonic = [0.0]
    query = OpenMeteoCamsAodQueryService(client=client, clock=lambda: monotonic[0], utcnow=lambda: NOW + timedelta(seconds=monotonic[0]))
    return query, client, monotonic


def test_named_point_identity_cache_and_fixed_expiry():
    query, client, clock = service()
    fields = query.point_fields(47.5615, -52.7126, NOW)
    field = fields[0]
    assert field.value == 0.15 and field.key == "aerosol_optical_depth_550nm"
    assert field.provenance.source_id == "openmeteo-cams-aod"
    assert field.provenance.run_time is None
    assert field.provenance.original_units == "" and field.provenance.normalized_units == "1"
    assert field.provenance.intermediary == "Open-Meteo"
    assert "Temporal interpolation" in field.provenance.intermediary_method
    entry = query.query(47.5615, -52.7126, NOW)
    assert len(client.calls) == 2
    assert "domains=cams_global" in client.calls[0][0]
    assert "latitude=47.5615" in client.calls[0][0]
    assert all(limit == MAX_RESPONSE_BYTES for _, limit in client.calls)
    clock[0] = TTL_SECONDS - 1
    assert query.query(47.5615, -52.7126, NOW) is entry
    clock[0] = TTL_SECONDS
    assert query.query(47.5615, -52.7126, NOW) is not entry
    assert len(client.calls) == 4


def test_series_preserves_null_and_absent_hour_without_interpolation():
    query, client, _ = service()
    client.payload = payload(["2026-09-07T12:00", "2026-09-07T14:00", "2026-09-07T15:00"], [0.1, None, 0.3])
    result = query.query(47.5, -52.7, NOW, NOW+timedelta(hours=3))
    assert result.times == (NOW, NOW+timedelta(hours=2), NOW+timedelta(hours=3))
    assert result.values == (0.1, None, 0.3)


def test_failed_refresh_retains_original_deadline_and_expired_never_returns():
    query, client, clock = service()
    old = query.query(47.5, -52.7, NOW)
    client.fail = True
    clock[0] = 100
    with pytest.raises(OpenMeteoCamsAodUnavailable):
        query.query(47.5, -52.7, NOW, refresh=True)
    assert query.query(47.5, -52.7, NOW) is old
    clock[0] = TTL_SECONDS
    with pytest.raises(OpenMeteoCamsAodUnavailable):
        query.query(47.5, -52.7, NOW)


@pytest.mark.parametrize("latitude,longitude,start,end", [
    (91, 0, NOW, None), (0, 181, NOW, None), (float("nan"), 0, NOW, None),
    (True, 0, NOW, None), (0, 0, NOW.replace(tzinfo=None), None),
    (0, 0, NOW+timedelta(minutes=1), None), (0, 0, NOW, NOW+timedelta(hours=24)),
    (0, 0, NOW, NOW-timedelta(hours=1)),
])
def test_invalid_selection_has_no_upstream_calls(latitude, longitude, start, end):
    query, client, _ = service()
    with pytest.raises(ValueError):
        query.query(latitude, longitude, start, end)
    assert client.calls == []


@pytest.mark.parametrize("change", [
    lambda p: p["hourly_units"].update(aerosol_optical_depth="μg/m³"),
    lambda p: p["hourly"].update(aerosol_optical_depth=[None]),
    lambda p: p["hourly"].update(aerosol_optical_depth=[True]),
    lambda p: p["hourly"].update(aerosol_optical_depth_cams_europe=[1]),
    lambda p: p["hourly"].update(time=["2026-09-07T13:00"]),
    lambda p: p["hourly"].update(time=["2026-09-07T12:00"]*2, aerosol_optical_depth=[0.1, 0.2]),
    lambda p: p.update(utc_offset_seconds=3600),
    lambda p: p.update(latitude=100),
])
def test_invalid_response_fails_closed(change):
    query, client, _ = service()
    change(client.payload)
    with pytest.raises(OpenMeteoCamsAodUnavailable):
        query.query(47.5, -52.7, NOW)
    assert not query._entries


def test_identical_misses_coalesce_and_distinct_misses_are_bounded():
    query, client, _ = service()
    client.entered, client.release = threading.Event(), threading.Event()
    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(query.query, 47.5, -52.7, NOW)
        assert client.entered.wait(5)
        same = pool.submit(query.query, 47.5, -52.7, NOW)
        second = pool.submit(query.query, 48.5, -52.7, NOW)
        # Wait for the second admitted request using a deterministic service lock.
        import time
        deadline = time.monotonic()+5
        while len(query._inflight) < 2 and time.monotonic() < deadline:
            time.sleep(0.001)
        with pytest.raises(OpenMeteoCamsAodUnavailable, match="concurrent"):
            query.query(49.5, -52.7, NOW)
        client.release.set()
        assert first.result() is same.result()
        assert second.result().selection.latitude == 48.5
    assert len(client.calls) == 4


def test_explicit_refresh_replaces_only_after_success():
    query, client, clock = service()
    old = query.query(47.5, -52.7, NOW)
    clock[0] = 100
    client.payload["hourly"]["aerosol_optical_depth"] = [0.25]
    new = query.query(47.5, -52.7, NOW, refresh=True)
    assert new.values == (0.25,) and old.values == (0.15,)
    assert new.response_sha256 != old.response_sha256
    assert new.expires_at_monotonic == 400
    assert query.query(47.5, -52.7, NOW) is new


def test_byte_ceiling_and_metadata_failure_leave_no_cache():
    query, client, _ = service()
    client.payload["oversized"] = "x" * MAX_RESPONSE_BYTES
    with pytest.raises(OpenMeteoCamsAodUnavailable):
        query.query(47.5, -52.7, NOW)
    assert not query._entries and len(client.calls) == 1


def test_cache_entry_ceiling_evicts_without_changing_expiry(monkeypatch):
    import weather_api.openmeteo_cams_aod_query as module
    monkeypatch.setattr(module, "MAX_CACHE_ENTRIES", 1)
    query, client, clock = service()
    first = query.query(47.5, -52.7, NOW)
    clock[0] = 10
    second = query.query(48.5, -52.7, NOW)
    assert list(query._entries.values()) == [second]
    assert first.expires_at_monotonic == TTL_SECONDS
    assert len(client.calls) == 4


@pytest.mark.parametrize("status", [200, 429, 503])
def test_real_polite_http_transport_and_adapter_readback(status):
    import httpx
    from ingest.http import PoliteClient
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Accept-Encoding"] == "identity"
        body = {"last_run_initialisation_time": NOW.timestamp()} if "meta.json" in request.url.path else payload()
        return httpx.Response(status, json=body)

    polite = PoliteClient(attempts=1, min_host_interval_seconds=0)
    polite.close()
    polite._client = httpx.Client(transport=httpx.MockTransport(handler))
    query = OpenMeteoCamsAodQueryService(client=polite, utcnow=lambda: NOW)
    try:
        if status == 200:
            field = query.point_fields(47.5, -52.7, NOW)[0]
            assert field.field == "aerosol_optical_depth_550nm" and field.value == 0.15
            assert len(requests) == 2
            query.point_fields(47.5, -52.7, NOW)
            assert len(requests) == 2
        else:
            with pytest.raises(OpenMeteoCamsAodUnavailable):
                query.point_fields(47.5, -52.7, NOW)
            assert len(requests) == 1
    finally:
        polite.close()


def test_expiry_during_adapter_validation_never_enters_cache(monkeypatch):
    import weather_api.openmeteo_cams_aod_query as module
    query, client, clock = service()
    original = module.OpenMeteoCompositionAdapter.fetch

    def delayed_fetch(adapter, *args):
        result = original(adapter, *args)
        clock[0] = TTL_SECONDS
        return result

    monkeypatch.setattr(module.OpenMeteoCompositionAdapter, "fetch", delayed_fetch)
    with pytest.raises(OpenMeteoCamsAodUnavailable, match="expired"):
        query.query(47.5, -52.7, NOW)
    assert not query._entries


def test_download_time_counts_toward_total_budget():
    query, client, clock = service()
    original = client.download

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] += 600
        return result

    client.download = delayed
    with pytest.raises(OpenMeteoCamsAodUnavailable, match="total acquisition budget"):
        query.query(47.5, -52.7, NOW)
    assert len(client.calls) == 1 and not query._entries


def test_dateline_distance_uses_shortest_geodesic():
    query, client, _ = service()
    client.payload.update(latitude=0, longitude=-179.95)
    field = query.point_fields(0, 179.99, NOW)[0]
    assert field.provenance.sample_distance_km == pytest.approx(6.6717, abs=0.01)
    assert field.provenance.sampled_longitude == -179.95


def test_default_cancellable_child_runs_existing_adapter_offline(tmp_path, monkeypatch):
    import weather_api.openmeteo_cams_aod_query as module
    original = module.run_bounded_process
    script = tmp_path / "child_fixture.py"
    script.write_text('''
import json
import weather_api.openmeteo_cams_aod_query_worker as worker
class Client:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def download(self, url, path, **kwargs):
        data = {"last_run_initialisation_time": 1788782400} if "meta.json" in url else {"latitude":47.55,"longitude":-52.7,"utc_offset_seconds":0,"hourly_units":{"time":"iso8601","aerosol_optical_depth":""},"hourly":{"time":["2026-09-07T12:00"],"aerosol_optical_depth":[0.15]}}
        path.write_text(json.dumps(data))
worker.PoliteClient = Client
worker.main()
''')

    def run(**kwargs):
        kwargs["command"][1] = str(script)
        return original(**kwargs)

    monkeypatch.setattr(module, "run_bounded_process", run)
    query = module.OpenMeteoCamsAodQueryService()
    entry = query.query(47.5, -52.7, NOW)
    assert entry.values == (0.15,) and entry.times == (NOW,)
    assert query.query(47.5, -52.7, NOW) is entry


def test_default_child_timeout_cancels_work_and_refuses_cache(tmp_path, monkeypatch):
    import weather_api.openmeteo_cams_aod_query as module
    original = module.run_bounded_process
    script = tmp_path / "stalled_acquisition.py"
    script.write_text("import time\ntime.sleep(60)\n")

    def run(**kwargs):
        kwargs["command"][1] = str(script)
        kwargs["timeout_seconds"] = 0.2
        return original(**kwargs)

    monkeypatch.setattr(module, "run_bounded_process", run)
    query = module.OpenMeteoCamsAodQueryService()
    with pytest.raises(OpenMeteoCamsAodUnavailable, match="bounded acquisition"):
        query.query(47.5, -52.7, NOW)
    assert not query._entries and not query._inflight


def test_coalesced_wait_has_explicit_deadline():
    from concurrent.futures import Future
    import weather_api.openmeteo_cams_aod_query as module
    query, client, _ = service()
    observed = []

    class Pending(Future):
        def result(self, timeout=None):
            observed.append(timeout)
            raise TimeoutError()

    key = module.CamsAodSelection(47.5, -52.7, NOW, NOW)
    query._inflight[key] = Pending()
    with pytest.raises(OpenMeteoCamsAodUnavailable, match="wait expired"):
        query.query(47.5, -52.7, NOW)
    assert observed == [module.ACQUISITION_TIMEOUT_SECONDS + 5]
    assert not client.calls and not query._entries
