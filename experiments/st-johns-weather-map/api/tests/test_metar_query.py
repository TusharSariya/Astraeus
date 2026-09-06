from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import hashlib
from threading import Lock
import time
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
import importlib

from weather_api.metar_query import MetarQueryService
from weather_api.taf_query import TafQueryUnavailable
from weather_api.fixtures import point_fields
from weather_api.models import DataMode
from weather_api.store import FIELD_BY_VARIABLE
from ingest.awc_metar_isolated import _decode
from ingest.contract import AdapterUnavailable, FetchWindow

app_module=importlib.import_module("weather_api.app")


class Clock:
    value = 100.0
    def __call__(self): return self.value


class BoundedAdapter:
    calls = 0
    def demand_operation_bounds(self): self.calls += 1


def client(handler): return httpx.Client(transport=httpx.MockTransport(handler))


AT=datetime(2026,9,6,12,30,tzinfo=UTC)

def reports():
    return [
        {"icaoId":"CYYT", "obsTime":int(AT.timestamp())-900, "temp":10, "dewp":8, "wspd":10, "wdir":180,
         "visib":"6+", "clouds":[{"cover":"BKN", "base":20}], "wxString":"BR"},
        {"icaoId":"CYYT", "obsTime":int(AT.timestamp())-1800, "temp":11, "dewp":9, "wspd":12, "wdir":190,
         "visib":"5", "clouds":[{"cover":"OVC", "base":15}], "wxString":"FG"},
    ]



def test_canonical_response_cache_serves_multiple_timestamps_once():
    calls=[]
    service=MetarQueryService(client=client(lambda request: (calls.append(request) or httpx.Response(
        200, json=reports(), headers={"Cache-Control":"max-age=60", "ETag":"\"one\""}))),
        adapter=BoundedAdapter(), clock=Clock())
    first=service.entry(AT); second=service.entry(AT)
    assert len(calls)==1 and first.body_sha256==second.body_sha256
    assert first.cache_key == ("aviationweather.gov", "metar-json", "CYYT", "two-hours-ending:2026-09-06T13:00:00Z")
    assert "date=2026-09-06T13%3A00%3A00Z" in first.provider_url
    assert first.request_headers["accept"] == "application/json"
    assert first.response_headers["etag"] == '"one"'
    assert 0 < first.body_bytes <= 65536
    third=service.entry(AT.replace(minute=31))
    assert len(calls)==1 and third.body_sha256==first.body_sha256
    selected, observed=service.select_record(first,AT.replace(minute=10))
    assert observed==AT.replace(minute=0)
    assert selected["temp"]==11


def test_exact_hour_uses_that_boundary_and_next_minute_uses_next_bucket():
    _url,key,end=MetarQueryService.request_identity(AT.replace(minute=0))
    assert end==AT.replace(minute=0)
    assert key[-1]=="two-hours-ending:2026-09-06T12:00:00Z"
    _url,key,end=MetarQueryService.request_identity(AT.replace(minute=1))
    assert end==AT.replace(minute=0,hour=13)
    assert key[-1]=="two-hours-ending:2026-09-06T13:00:00Z"


def test_early_hour_selection_keeps_prior_hour_observation_and_excludes_future():
    selected=datetime(2026,9,6,10,5,tzinfo=UTC)
    rows=[
        {"icaoId":"CYYT","obsTime":int(datetime(2026,9,6,9,40,tzinfo=UTC).timestamp()),"temp":9},
        {"icaoId":"CYYT","obsTime":int(datetime(2026,9,6,10,20,tzinfo=UTC).timestamp()),"temp":12},
    ]
    service=MetarQueryService(client=client(lambda _:httpx.Response(200,json=rows,
        headers={"Cache-Control":"max-age=60"})),adapter=BoundedAdapter(),clock=Clock())
    entry=service.entry(selected)
    chosen,observed=service.select_record(entry,selected)
    assert observed==datetime(2026,9,6,9,40,tzinfo=UTC)
    assert chosen["temp"]==9


def test_expiry_revalidates_without_replacing_body_acquisition():
    clock=Clock(); requests=[]
    def handler(request):
        requests.append(request)
        if len(requests)==1:
            return httpx.Response(200,json=reports(),headers={"Cache-Control":"max-age=1","ETag":"\"one\""})
        assert request.headers["If-None-Match"]=='"one"'
        return httpx.Response(304,headers={"Cache-Control":"max-age=60","ETag":"\"one\""})
    service=MetarQueryService(client=client(handler),adapter=BoundedAdapter(),clock=clock)
    before=service.entry(AT); clock.value+=2; after=service.entry(AT)
    assert after.body_sha256==before.body_sha256
    assert after.transport_completed_at==before.transport_completed_at
    assert after.last_revalidation["status"]==304


def test_cache_lru_has_finite_entry_and_exact_body_byte_limits():
    def handler(request):
        end=datetime.fromisoformat(request.url.params["date"].replace("Z","+00:00"))
        return httpx.Response(200,json=[{"icaoId":"CYYT","obsTime":int(end.timestamp())-1800}],
                              headers={"Cache-Control":"max-age=60"})
    service=MetarQueryService(client=client(handler),adapter=BoundedAdapter(),clock=Clock())
    for hour in range(65):
        service.entry(datetime(2026,9,1,tzinfo=UTC)+timedelta(hours=hour))
    assert len(service._entries)==64
    assert sum(entry.body_bytes for entry in service._entries.values()) <= 64*65536


def test_concurrent_success_and_failure_each_have_one_upstream_outcome():
    for status in (200,503):
        lock=Lock(); count=0
        def handler(_request):
            nonlocal count
            with lock: count+=1
            time.sleep(.03)
            return httpx.Response(status,json=reports(),headers={"Cache-Control":"max-age=60"})
        service=MetarQueryService(client=client(handler),adapter=BoundedAdapter(),clock=Clock())
        def fetch(_):
            if status==503:
                with pytest.raises(TafQueryUnavailable): service.entry(AT)
            else: service.entry(AT)
        with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(fetch,range(8)))
        assert count==1


def test_oversize_redirect_and_expired_failure_fail_closed():
    adapter=BoundedAdapter()
    with pytest.raises(TafQueryUnavailable,match="65536"):
        MetarQueryService(client=client(lambda _:httpx.Response(200,content=b"x"*65537,
            headers={"Cache-Control":"max-age=60"})),adapter=adapter).entry(AT)
    with pytest.raises(TafQueryUnavailable,match="redirect refused"):
        MetarQueryService(client=client(lambda _:httpx.Response(302,headers={"Location":"https://example.test"})),adapter=adapter).entry(AT)
    clock=Clock(); count=0
    def handler(_):
        nonlocal count; count+=1
        return httpx.Response(200,json=reports(),headers={"Cache-Control":"max-age=1","ETag":"\"one\""}) if count==1 else httpx.Response(503)
    service=MetarQueryService(client=client(handler),adapter=adapter,clock=clock)
    retained=service.entry(AT); clock.value+=2
    with pytest.raises(TafQueryUnavailable) as caught: service.entry(AT)
    assert caught.value.detail["cached_identity"]==retained.body_sha256
    assert caught.value.detail["values_withheld"] is True


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS rejects the required child RLIMIT_AS")
def test_latest_before_selection_is_normalized_and_sampled_without_artifact_store(monkeypatch):
    observed=datetime(2026,9,6,12,tzinfo=UTC)
    rows=[{"icaoId":"CYYT", "obsTime":int(observed.timestamp()), "temp":10, "dewp":8,
           "slp":1012.3, "wspd":10, "wdir":180, "visib":"6+",
           "wgst":20, "clouds":[{"cover":"BKN", "base":20}], "wxString":"BR",
           "metarId":42, "metarType":"METAR", "rawOb":"METAR CYYT TEST",
           "reportTime":"2026-09-06T12:00:00Z", "receiptTime":"2026-09-06T12:01:00Z",
           "name":"St Johns Intl", "lat":47.627, "lon":-52.748, "elev":128,
           "fltCat":"MVFR", "qcField":0}]
    monkeypatch.setattr("ingest.adapters.awc.AWCMetarAdapter.demand_operation_bounds", lambda *_args: None)
    service=MetarQueryService(client=client(lambda _:httpx.Response(200,json=rows,
        headers={"Cache-Control":"max-age=60"})),clock=Clock())
    fields,native,entry=service.point_fields(47.627,-52.748,datetime(2026,9,6,12,30,tzinfo=UTC))
    by_name={field.field:field for field in fields}
    assert native==observed and entry.body_bytes>0
    assert by_name["temperature"].value==10
    assert by_name["dew_point"].value==8
    assert by_name["visibility"].value==pytest.approx(9656.064)
    assert by_name["wind_speed"].value==pytest.approx(5.1)
    assert by_name["wind_gust"].value==pytest.approx(10.28888)
    assert by_name["fog_state"].value=="unknown"
    assert all(field.provenance.source_id=="awc-metar-speci" for field in fields)
    identity=by_name["temperature"].provenance.native_report
    assert identity.provider_report_id==42
    assert identity.report_type=="METAR"
    assert identity.raw_report_sha256==hashlib.sha256(b"METAR CYYT TEST").hexdigest()
    assert identity.receipt_time==datetime(2026,9,6,12,1,tzinfo=UTC)


def test_future_and_one_hour_old_observations_are_refused():
    observed=datetime(2026,9,6,12,tzinfo=UTC)
    no_data=MetarQueryService(client=client(lambda _:httpx.Response(204)),adapter=BoundedAdapter(),clock=Clock())
    with pytest.raises(TafQueryUnavailable,match="no observation"):
        no_data.point_fields(47.627,-52.748,observed.replace(hour=11))
    rows=[{"icaoId":"CYYT", "obsTime":int(observed.timestamp()), "temp":10}]
    service=MetarQueryService(client=client(lambda _:httpx.Response(200,json=rows,
        headers={"Cache-Control":"max-age=60"})),adapter=BoundedAdapter(),clock=Clock())
    with pytest.raises(ValueError,match="one hour"):
        service.point_fields(47.627,-52.748,observed.replace(hour=13))


@pytest.mark.parametrize("change, detail", [
    ({"unexpected":"value"}, "unsupported keys"),
    ({"visib":"opaque"}, "invalid visib"),
    ({"clouds":[]}, None),
    ({"clouds":[{"cover":"ALIEN", "base":20}]}, "invalid cloud cover"),
    ({"reportTime":"not-a-time"}, "invalid reportTime"),
    ({"lat":91}, "invalid lat"),
    ({"wdir":"sideways"}, "invalid wdir"),
])
def test_complete_native_row_vocabulary_is_validated(change, detail):
    row=reports()[0] | change
    window=FetchWindow(AT.replace(hour=13),back_hours=2,forward_hours=0)
    raw=json.dumps([row]).encode()
    if detail is None:
        assert _decode(raw,window)==[row]
    else:
        with pytest.raises(AdapterUnavailable,match=detail): _decode(raw,window)


def test_variable_wind_direction_and_native_metadata_are_preserved():
    row=reports()[0] | {
        "wdir":"VRB", "rawOb":"METAR CYYT TEST", "reportTime":"2026-09-06T12:15:00Z",
        "receiptTime":"2026-09-06T12:16:00Z", "metarType":"METAR", "name":"St Johns Intl",
        "lat":47.627, "lon":-52.748, "elev":128, "altim":1004.1, "fltCat":"MVFR", "qcField":0,
    }
    window=FetchWindow(AT.replace(hour=13),back_hours=2,forward_hours=0)
    assert _decode(json.dumps([row]).encode(),window)[0]==row


def test_metar_gust_variable_has_a_canonical_point_field():
    assert FIELD_BY_VARIABLE["wind_gust_10m"] == "wind_gust"


def test_default_point_uses_demand_metar_when_legacy_store_is_unreachable(monkeypatch):
    at=datetime(2026,9,6,12,30,tzinfo=UTC)
    field=point_fields(at)[0][0]
    field=field.model_copy(update={"provenance":field.provenance.model_copy(update={
        "data_mode":DataMode.LIVE, "source_id":"awc-metar-speci", "product":"CYYT METAR/SPECI",
        "valid_time":at.replace(minute=0), "retrieval_time":at,
    })})
    class Service:
        @staticmethod
        def point_fields(*_args): return [field], at.replace(minute=0), object()
    monkeypatch.setenv("WEATHER_DATA_MODE","live")
    monkeypatch.setattr("weather_api.metar_query.metar_query_service",lambda:Service())
    monkeypatch.setattr(app_module,"live_store",lambda:None)
    response=TestClient(app_module.app).get(f"{app_module.PREFIX}/point",params={
        "latitude":47.627,"longitude":-52.748,"valid_time":at.isoformat(),
    })
    assert response.status_code==200
    body=response.json()
    assert body["data_mode"]=="live"
    assert [item["provenance"]["source_id"] for item in body["fields"]]==["awc-metar-speci"]
    assert body["selection"]["mode"]=="evidence_only"
