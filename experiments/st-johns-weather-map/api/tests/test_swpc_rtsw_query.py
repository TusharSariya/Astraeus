from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from weather_api.swpc_rtsw_query import SWPCRTSWQueryService, SWPCRTSWUnavailable
from weather_api.swpc_rtsw_worker import validated


FIXTURE = Path(__file__).parent / "fixtures/space_weather/rtsw_mag_1m.json"
NOW = datetime(2026, 9, 5, 17, 59, 30, tzinfo=UTC)


def decode(body: bytes, at: datetime | None):
    rows = validated(body)
    if at is None:
        return {"rows": len(rows)}
    candidates = [(datetime.fromisoformat(row["time_tag"]).replace(tzinfo=UTC), row["source"], row) for row in rows if datetime.fromisoformat(row["time_tag"]).replace(tzinfo=UTC) <= at and isinstance(row["bz_gsm"], (int, float))]
    newest = max(item[0] for item in candidates)
    choices = [(source, row) for stamp, source, row in candidates if stamp == newest]
    active = [item for item in choices if item[1]["active"] is True]
    source, row = sorted(active if len(active) == 1 else choices, key=lambda item: item[0])[0]
    return {"time": newest.isoformat(), "source": source, "row": row, "active_count": len(active)}


def service(*, status: int = 200, delay: float = 0):
    calls = []
    body = FIXTURE.read_bytes()
    def handler(request: httpx.Request):
        if delay:
            import time
            time.sleep(delay)
        calls.append(request)
        return httpx.Response(status, content=body, headers={"cache-control": "max-age=60"}, request=request)
    return SWPCRTSWQueryService(client=httpx.Client(transport=httpx.MockTransport(handler)), utcnow=lambda: NOW, bounded_decode=decode), calls


def test_selected_native_row_preserves_spacecraft_quality_and_transport():
    query, calls = service()
    wind = query.latest(NOW)
    assert len(calls) == 1
    assert wind.bz_gsm_nt == 0.64 and wind.bt_nt == 6.63
    assert wind.measured_at == datetime(2026, 9, 5, 17, 59, tzinfo=UTC)
    assert wind.feed_declared_spacecraft == "SOLAR1"
    assert wind.active is True and wind.overall_quality == 0
    assert wind.freshness.status == "fresh"
    assert wind.acquisition is not None
    assert wind.acquisition.body_bytes == len(FIXTURE.read_bytes())
    assert wind.acquisition.request_headers["accept-encoding"] == "identity"
    assert len(wind.acquisition.body_sha256) == 64


def test_fresh_hit_and_concurrent_miss_add_no_provider_requests():
    query, calls = service(delay=0.02)
    with ThreadPoolExecutor(max_workers=8) as pool:
        winds = list(pool.map(lambda _: query.latest(NOW), range(8)))
    assert len(calls) == 1
    assert {wind.acquisition.body_sha256 for wind in winds if wind.acquisition} == {winds[0].acquisition.body_sha256}
    assert query.latest(NOW).bz_gsm_nt == 0.64
    assert len(calls) == 1


def test_expired_entry_conditionally_revalidates_without_replacing_body_identity():
    body = FIXTURE.read_bytes()
    calls = []
    monotonic = [0.0]
    completed = [NOW]
    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, content=body, headers={
                "cache-control": "max-age=60", "etag": '"native-revision"',
                "last-modified": "Sat, 05 Sep 2026 17:59:00 GMT",
            }, request=request)
        return httpx.Response(304, content=b"", headers={
            "cache-control": "max-age=60", "age": "54", "etag": '"native-revision"',
        }, request=request)
    query = SWPCRTSWQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: monotonic[0], utcnow=lambda: completed[0], bounded_decode=decode,
    )
    first = query.entry()
    monotonic[0] = 61.0
    completed[0] = NOW + timedelta(minutes=20)
    second = query.entry()
    assert len(calls) == 2
    assert calls[1].headers["if-none-match"] == '"native-revision"'
    assert calls[1].headers["if-modified-since"] == "Sat, 05 Sep 2026 17:59:00 GMT"
    assert second.body is first.body
    assert second.acquisition.body_sha256 == first.acquisition.body_sha256
    assert second.acquisition.transport_completed_at == first.acquisition.transport_completed_at
    assert second.acquisition.last_revalidation is not None
    assert second.acquisition.last_revalidation["http_status"] == 304
    assert second.expires_at_monotonic == 67.0
    with pytest.raises(SWPCRTSWUnavailable, match="acquisition context"):
        query.latest(NOW)


def test_304_rejects_changed_last_modified():
    body = FIXTURE.read_bytes()
    calls = []
    monotonic = [0.0]
    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, content=body, headers={
                "cache-control": "max-age=60", "etag": '"native-revision"',
                "last-modified": "Sat, 05 Sep 2026 17:59:00 GMT",
            }, request=request)
        headers = {"cache-control": "max-age=60", "etag": '"native-revision"'}
        headers["last-modified"] = "Sat, 05 Sep 2026 18:00:00 GMT"
        return httpx.Response(304, content=b"", headers=headers, request=request)
    query = SWPCRTSWQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: monotonic[0], utcnow=lambda: NOW, bounded_decode=decode,
    )
    query.entry()
    monotonic[0] = 61.0
    with pytest.raises(SWPCRTSWUnavailable, match="changed Last-Modified"):
        query.entry()


def test_304_rejects_changed_effective_identity():
    body = FIXTURE.read_bytes()
    responses = [
        httpx.Response(200, content=body, headers={"cache-control": "max-age=60", "etag": '"native-revision"'},
                       request=httpx.Request("GET", "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json")),
        httpx.Response(304, content=b"", headers={"cache-control": "max-age=60", "etag": '"native-revision"'},
                       request=httpx.Request("GET", "https://example.invalid/rtsw.json")),
    ]
    class Client:
        @contextmanager
        def stream(self, *_args, **_kwargs):
            yield responses.pop(0)
    monotonic = [0.0]
    query = SWPCRTSWQueryService(client=Client(), clock=lambda: monotonic[0], utcnow=lambda: NOW, bounded_decode=decode)
    query.entry()
    monotonic[0] = 61.0
    with pytest.raises(SWPCRTSWUnavailable, match="effective URL differs"):
        query.entry()


def test_current_document_refuses_historical_future_and_stale_selection():
    query, _calls = service()
    with pytest.raises(SWPCRTSWUnavailable, match="acquisition context"):
        query.latest(datetime(2026, 9, 5, 17, 40, tzinfo=UTC))
    with pytest.raises(SWPCRTSWUnavailable, match="acquisition context"):
        query.latest(datetime(2026, 9, 5, 18, 2, tzinfo=UTC))


def test_no_active_flag_is_disclosed_and_gap_is_never_zero():
    rows = json.loads(FIXTURE.read_text())
    rows[-1]["active"] = None
    rows[-1]["bz_gsm"] = None
    rows[-2]["active"] = None
    body = json.dumps(rows).encode()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={"cache-control": "max-age=60"}, request=request)))
    wind = SWPCRTSWQueryService(client=client, utcnow=lambda: NOW, bounded_decode=decode).latest(NOW)
    assert wind.measured_at < NOW and wind.bz_gsm_nt != 0
    assert wind.active is None
    assert "no spacecraft carried" in wind.notices[0]


def test_transport_failure_is_independently_unavailable():
    query, calls = service(status=503)
    with pytest.raises(SWPCRTSWUnavailable, match="HTTP 503"):
        query.latest(NOW)
    with pytest.raises(SWPCRTSWUnavailable, match="HTTP 503"):
        query.latest(NOW)
    assert len(calls) == 1


@pytest.mark.parametrize("mutation, message", [
    (lambda rows: rows[0].pop("overall_quality"), "missing native fields"),
    (lambda rows: rows[0].__setitem__("bt", "6.2"), "not finite numeric or null"),
    (lambda rows: rows[0].__setitem__("active", 1), "not boolean or null"),
    (lambda rows: rows.append(dict(rows[0])), "duplicates native time/source"),
    (lambda rows: rows[0].__setitem__("time_tag", "not-a-time"), "invalid timestamp"),
])
def test_every_native_row_field_and_identity_validates_without_silent_drop(mutation, message):
    rows = json.loads(FIXTURE.read_text())
    mutation(rows)
    body = json.dumps(rows).encode()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={"cache-control": "max-age=60"}, request=request)))
    with pytest.raises(SWPCRTSWUnavailable, match=message):
        SWPCRTSWQueryService(client=client, utcnow=lambda: NOW, bounded_decode=decode).latest(NOW)


def test_multiple_active_spacecraft_is_disclosed_before_deterministic_fallback():
    rows = json.loads(FIXTURE.read_text())
    duplicate = dict(rows[-1])
    duplicate["source"] = "ACE"
    duplicate["bz_gsm"] = -2.0
    rows.append(duplicate)
    body = json.dumps(rows).encode()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={"cache-control": "max-age=60"}, request=request)))
    wind = SWPCRTSWQueryService(client=client, utcnow=lambda: NOW, bounded_decode=decode).latest(NOW)
    assert wind.feed_declared_spacecraft == "ACE" and wind.bz_gsm_nt == -2.0
    assert "multiple spacecraft carried" in wind.notices[0]
