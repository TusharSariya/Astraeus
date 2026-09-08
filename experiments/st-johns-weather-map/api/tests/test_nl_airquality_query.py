"""GOV-SPEC-005/006: isolated NL acquisition; no production promotion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import threading
import sys

import httpx
import pytest

from ingest.contract import FetchWindow
from ingest.experimental.nl_air_quality import CSV_URL, MAX_CSV_BYTES, _parse
from weather_api.nl_airquality_query import (
    CACHE_MAX_ENTRIES, CACHE_TTL_SECONDS, MISSING_CONTRACT,
    NLAirQualityQueryService, NLAirQualityUnavailable, NativeObservation,
)

FIXTURE = Path(__file__).parent / "fixtures/nl_air_quality/stjohns-line.trimmed.csv"
START = datetime(2026, 9, 5, 21, tzinfo=UTC)
END = datetime(2026, 9, 6, 0, tzinfo=UTC)


def decode(body, start, end):
    rows = _parse(body, FetchWindow(end, back_hours=(end - start).total_seconds() / 3600, forward_hours=0))
    return tuple(NativeObservation(row["time"], row["local_time"], row["values"]["PM2_5_RUN_AVG"], row["values"]["O3"]) for row in rows)


def service(handler=None, decoder=decode):
    elapsed = [0.0]
    calls = []
    def transport(request):
        calls.append(request)
        assert str(request.url) == CSV_URL
        return handler(request) if handler else httpx.Response(200, content=FIXTURE.read_bytes())
    instance = NLAirQualityQueryService(client=httpx.Client(transport=httpx.MockTransport(transport)),
        clock=lambda: elapsed[0], utcnow=lambda: END + timedelta(seconds=elapsed[0]), decode=decoder)
    return instance, elapsed, calls


def test_native_parser_cache_receipt_units_quality_and_exact_time():
    query, elapsed, calls = service()
    first = query.query("010102", START, END)
    assert query.query("010102", START, END) is first
    assert len(calls) == 1
    assert len(first.observations) == 3
    row = first.observations[-1]
    assert row.observation_time == datetime(2026, 9, 5, 23, 30, tzinfo=UTC)
    assert row.local_time == "2026-09-05T21:00:00-02:30"
    assert row.pm2_5_24h_mean_ug_m3 == 5.7 and row.ozone_ppb == 27.8
    assert row.quality_status == "unknown" and row.quality_flags == ("provisional", "not_quality_controlled")
    assert not row.operational and not row.redistribution
    assert first.complete and first.window_start == START and first.window_end == END
    assert first.acquisition.body_bytes == len(FIXTURE.read_bytes())
    assert first.acquisition.expires_at == END + timedelta(seconds=CACHE_TTL_SECONDS)
    exact = query.query("010102", row.observation_time, row.observation_time)
    assert exact.observations == (row,)
    assert "production" in MISSING_CONTRACT
    elapsed[0] = CACHE_TTL_SECONDS
    assert query.query("010102", START, END) is not first
    assert len(calls) == 3


def test_refresh_replaces_and_failure_never_extends_deadline():
    failing = [False]
    def handler(request):
        return httpx.Response(503) if failing[0] else httpx.Response(200, content=FIXTURE.read_bytes())
    query, elapsed, calls = service(handler)
    first = query.query("010102", START, END)
    elapsed[0] = 10
    replacement = query.query("010102", START, END, refresh=True)
    assert replacement.acquisition.expires_at > first.acquisition.expires_at
    failing[0] = True
    with pytest.raises(NLAirQualityUnavailable):
        query.query("010102", START, END, refresh=True)
    assert query.query("010102", START, END) is replacement
    elapsed[0] = 10 + CACHE_TTL_SECONDS
    with pytest.raises(NLAirQualityUnavailable):
        query.query("010102", START, END)
    assert not query._cache


def test_coalesces_same_window_and_bounds_retained_windows():
    entered, release = threading.Event(), threading.Event()
    def handler(request):
        entered.set()
        assert release.wait(10)
        return httpx.Response(200, content=FIXTURE.read_bytes())
    query, elapsed, calls = service(handler)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(query.query, "010102", START, END)
        assert entered.wait(10)
        second = pool.submit(query.query, "010102", START, END)
        release.set()
        assert first.result() is second.result()
    assert len(calls) == 1
    for index in range(CACHE_MAX_ENTRIES + 2):
        query.query("010102", START - timedelta(minutes=index + 1), END)
    assert len(query._cache) == CACHE_MAX_ENTRIES


@pytest.mark.parametrize("station,start,end", [
    ("StJohns", START, END), ("010102", START.replace(tzinfo=None), END),
    ("010102", END, START), ("010102", START - timedelta(days=36), END),
])
def test_invalid_request_has_no_transport(station, start, end):
    query, _, calls = service()
    with pytest.raises(ValueError):
        query.query(station, start, end)
    assert not calls


@pytest.mark.parametrize("response", [
    lambda: httpx.Response(302, headers={"location": "https://example.com/"}),
    lambda: httpx.Response(200, headers={"content-length": str(MAX_CSV_BYTES + 1)}),
    lambda: httpx.Response(200, content=b"x" * (MAX_CSV_BYTES + 1)),
    lambda: httpx.Response(200, content=FIXTURE.read_bytes().replace(b"StJohns,", b"Foreign,")),
    lambda: httpx.Response(200, content=FIXTURE.read_bytes().replace(b"PROVISIONAL", b"FINAL")),
])
def test_response_drift_fails_closed(response):
    query, _, calls = service(lambda request: response())
    with pytest.raises(NLAirQualityUnavailable):
        query.query("010102", START, END)
    assert len(calls) == 1 and not query._cache


def test_missing_values_stay_null_and_final_byte_clock_owns_expiry():
    elapsed = [0]
    def handler(request):
        elapsed[0] = 12
        return httpx.Response(200, content=FIXTURE.read_bytes().replace(b",5.7,", b",,"))
    query, _, _ = service(handler)
    query._clock = lambda: elapsed[0]
    query._utcnow = lambda: END + timedelta(seconds=elapsed[0])
    entry = query.query("010102", START, END)
    assert entry.observations[-1].pm2_5_24h_mean_ug_m3 is None
    assert not entry.complete
    assert entry.acquisition.transport_completed_at == END + timedelta(seconds=12)
    assert entry.expires_at_monotonic == 12 + CACHE_TTL_SECONDS


def test_decoder_cannot_publish_after_deadline():
    query, elapsed, _ = service()
    def slow_decoder(body, start, end):
        elapsed[0] = CACHE_TTL_SECONDS
        return decode(body, start, end)
    query._decode = slow_decoder
    with pytest.raises(NLAirQualityUnavailable, match="expired during"):
        query.query("010102", START, END)
    assert not query._cache


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_AS proof requires Linux")
def test_default_bounded_worker_reuses_actual_adapter_fixture():
    from weather_api.nl_airquality_query import _decode
    query, _, calls = service(decoder=_decode)
    first = query.query("010102", START, END)
    assert query.query("010102", START, END) is first
    assert first.observations[-1].ozone_ppb == 27.8
    assert len(calls) == 1  # Fixed MockTransport; zero provider network requests.
