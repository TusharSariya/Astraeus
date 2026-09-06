from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock
import time
import httpx
import pytest
from weather_api.taf_query import TafQueryService, TafQueryUnavailable

UTC = timezone.utc
class Clock:
    value = 100.0
    def __call__(self): return self.value
def client(handler): return httpx.Client(transport=httpx.MockTransport(handler))
def report():
    return [{"icaoId":"CYYT","issueTime":"2026-09-06T11:41:00Z","bulletinTime":"2026-09-06T11:00:00Z","dbPopTime":"2026-09-06T11:41:27Z","lat":47.627,"lon":-52.748,"elev":128,"mostRecent":1,"prior":3,"name":"St Johns Intl","remarks":"","validTimeFrom":1788696000,"validTimeTo":1788782400,"rawTAF":"TAF CYYT 061141Z 0612/0712","fcsts":[{"timeFrom":1788696000,"timeTo":1788714000,"wspd":12,"wdir":"VRB","visib":"6","clouds":[{"cover":"OVX","base":None}],"wxString":"FG"}]}]

def test_one_provider_cache_entry_serves_many_ui_timestamps_and_preserves_transport():
    calls=[]
    def handler(request):
        calls.append(request); return httpx.Response(200,json=report(),headers={"Cache-Control":"max-age=60","ETag":"\"one\""})
    service=TafQueryService(client=client(handler),clock=Clock())
    first=service.query("CYYT",datetime(2026,9,6,12,tzinfo=UTC)); second=service.query("CYYT",datetime(2026,9,6,13,tzinfo=UTC))
    assert len(calls)==1 and first["revision_id"]==second["revision_id"]
    assert first["groups"][0]["native"]["wind_variable"] is True
    assert first["groups"][0]["presence"]["total_cloud_okta"]=="decoded_absence"
    assert 0 < first["acquisition"]["body_bytes"] <= 65536
    assert first["acquisition"]["request_headers"]["user-agent"] == "python-httpx/0.28.1"
    assert first["acquisition"]["request_headers"]["accept"] == "application/json"

def test_expiry_conditionally_revalidates_and_304_keeps_body_identity():
    clock=Clock(); requests=[]
    def handler(request):
        requests.append(request)
        if len(requests)==1: return httpx.Response(200,json=report(),headers={"Cache-Control":"max-age=60","ETag":"\"one\""})
        assert request.headers["If-None-Match"]=='"one"'; return httpx.Response(304,headers={"Cache-Control":"max-age=60","ETag":"\"one\""})
    service=TafQueryService(client=client(handler),clock=clock); before=service.entry(); clock.value+=61; after=service.entry()
    assert len(requests)==2 and after.body_sha256==before.body_sha256
    assert after.transport_completed_at == before.transport_completed_at
    assert after.response_headers == before.response_headers
    assert after.last_revalidation["status"] == 304
    assert after.last_revalidation["request_headers"]["if-none-match"] == '"one"'

def test_expired_entry_is_not_served_when_revalidation_fails():
    clock=Clock(); count=0
    def handler(_):
        nonlocal count; count+=1
        return httpx.Response(200,json=report(),headers={"Cache-Control":"max-age=1","ETag":"\"one\""}) if count==1 else httpx.Response(503)
    service=TafQueryService(client=client(handler),clock=clock); service.entry(); clock.value+=2
    with pytest.raises(TafQueryUnavailable,match="HTTP 503"): service.entry()

def test_concurrent_miss_is_coalesced():
    lock=Lock(); count=0
    def handler(_):
        nonlocal count
        with lock: count+=1
        return httpx.Response(200,json=report(),headers={"Cache-Control":"max-age=60"})
    service=TafQueryService(client=client(handler),clock=Clock())
    with ThreadPoolExecutor(max_workers=8) as pool: entries=list(pool.map(lambda _:service.entry(),range(8)))
    assert count==1 and len({e.body_sha256 for e in entries})==1

def test_concurrent_failed_miss_shares_one_upstream_outcome():
    lock=Lock(); count=0
    def handler(_):
        nonlocal count
        with lock: count+=1
        time.sleep(0.05)
        return httpx.Response(503)
    service=TafQueryService(client=client(handler),clock=Clock())
    def fetch(_):
        with pytest.raises(TafQueryUnavailable,match="HTTP 503"): service.entry()
    with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(fetch,range(8)))
    assert count==1

def test_oversize_and_missing_finite_ttl_fail_closed():
    with pytest.raises(TafQueryUnavailable,match="65536"):
        TafQueryService(client=client(lambda _:httpx.Response(200,content=b"x"*65537,headers={"Cache-Control":"max-age=60"}))).entry()
    with pytest.raises(TafQueryUnavailable,match="finite max-age"):
        TafQueryService(client=client(lambda _:httpx.Response(200,json=report()))).entry()

def test_timestamp_outside_report_is_distinct_from_provider_failure():
    service=TafQueryService(client=client(lambda _:httpx.Response(200,json=report(),headers={"Cache-Control":"max-age=60"})),clock=Clock())
    response=service.query("CYYT",datetime(2026,9,7,12,tzinfo=UTC))
    assert response["groups"]==[] and response["valid_time_to"]==1788782400
    assert response["applicable"] is False
    assert response["applicability_reason"] == "no native TAF group applies at this timestamp"
