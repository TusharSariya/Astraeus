from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from threading import Lock
import time
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from weather_api.aqhi_query import AQHIQueryService, AQHIStationObservation, AqhiQueryUnavailable
from weather_api.aqhi_query_worker import normalize


SELECTED = datetime(2026, 9, 7, 0, 30, tzinfo=UTC)


class Clock:
    value = 100.0

    def __call__(self):
        return self.value


def feature(station: str, value: object, observed: str, longitude: float, latitude: float, *, quality: str | None = None):
    properties = {
        "properties._id": station,
        "properties.location_name_en": f"Station {station}",
        "properties.aqhi": value,
        "properties.observation_datetime": observed,
    }
    if quality is not None:
        properties["properties.quality_flag"] = quality
    return {
        "type": "Feature", "properties": properties,
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
    }


def document(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def station_rows(body: bytes):
    return tuple(AQHIStationObservation(
        station_id=item["station_id"], station_name=item["station_name"],
        observation_time=datetime.fromisoformat(item["observation_time"]),
        latitude=item["latitude"], longitude=item["longitude"], value=item["value"],
        quality=item.get("quality"), feature_id=item.get("feature_id"),
    ) for item in normalize(json.loads(body)))


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_worker_requires_native_point_identity_time_and_numeric_index():
    rows = normalize(document(feature("ABEFS", "2.7", "2026-09-07T00:00:00Z", -52.7252, 47.5658, quality="A")))
    assert rows == [{
        "station_id": "ABEFS", "station_name": "Station ABEFS",
        "observation_time": "2026-09-07T00:00:00+00:00",
        "latitude": 47.5658, "longitude": -52.7252, "value": 2.7, "quality": "A",
    }]
    with pytest.raises(ValueError, match="numeric AQHI"):
        normalize(document(feature("ABEFS", "", "2026-09-07T00:00:00Z", -52.7252, 47.5658)))
    broken = feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)
    broken["geometry"]["type"] = "Polygon"
    with pytest.raises(ValueError, match="point geometry"):
        normalize(document(broken))


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS rejects the decoder's required locked RLIMIT_AS")
def test_default_bounded_decoder_serves_fixed_http_payload_without_injection():
    service = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=document(
            feature("ABEFS", 2.7, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
            headers={"Cache-Control": "max-age=60"},
        )),
        clock=Clock(), utcnow=lambda: SELECTED,
    )
    field = service.point_field(47.56, -52.72, SELECTED)
    assert field.value == 2.7
    assert field.provenance.native_report.station_id == "ABEFS"
    assert field.provenance.aqhi_acquisition.body_bytes > 0


def test_default_decoder_uses_required_output_argument_and_serves_fixed_http_payload(monkeypatch):
    import weather_api.aqhi_query as module

    seen = {}

    def bounded(**kwargs):
        seen.update(kwargs)
        rows = normalize(json.loads(kwargs["stdin"]))
        return SimpleNamespace(stdout=json.dumps(rows, separators=(",", ":")))

    monkeypatch.setattr(module, "run_bounded_process", bounded)
    service = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=document(
            feature("ABEFS", 2.7, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
            headers={"Cache-Control": "max-age=60"},
        )), clock=Clock(), utcnow=lambda: SELECTED,
    )
    field = service.point_field(47.56, -52.72, SELECTED)
    assert field.value == 2.7 and field.provenance.native_report.station_id == "ABEFS"
    assert seen["command"].count("{output}") == 1
    assert seen["destination"] is None and seen["require_output"] is False


def test_one_canonical_cache_fetch_serves_native_nearest_station_with_typed_receipt():
    calls = []
    payload = document(
        feature("ABEFS", "2.7", "2026-09-07T00:00:00Z", -52.7252, 47.5658, quality="A"),
        # Closer in longitude but far in latitude: a sparse outer-product grid
        # could invent a cell at the mixed coordinates. Point selection cannot.
        feature("ABYRK", "8", "2026-09-07T00:00:00Z", -55.6666, 48.9333),
    )
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload, headers={"Cache-Control": "max-age=60", "ETag": '"one"'})
    clock = Clock()
    service = AQHIQueryService(client=mock_client(handler), clock=clock, utcnow=lambda: SELECTED, decode=station_rows)
    first = service.point_field(47.56, -52.72, SELECTED)
    second = service.point_field(47.56, -52.72, SELECTED + timedelta(minutes=1))
    assert len(calls) == 1
    assert "layers=AQHI-OBS" in service.request_url and "feature_count=50" in service.request_url
    assert first.value == second.value == 2.7
    assert first.field == "aqhi" and first.key == "air_quality_health_index"
    assert first.provenance.native_report.station_id == "ABEFS"
    assert first.provenance.sampled_latitude == 47.5658
    assert first.provenance.sampled_longitude == -52.7252
    assert first.provenance.sample_method == "nearest_published_cell"
    assert first.provenance.run_time is None and first.provenance.run_stale is None
    assert first.provenance.quality.status == "unknown"
    assert first.provenance.quality.flags == ["native_aqhi", "provider_quality:A"]
    assert first.provenance.original_units == first.provenance.normalized_units == "index"
    receipt = first.provenance.aqhi_acquisition
    assert receipt is not None and receipt.body_sha256 == first.provenance.artifact_revision.removeprefix("demand:")
    assert receipt.request_headers["accept"] == "application/json"
    assert receipt.response_headers["etag"] == '"one"'
    assert 0 < receipt.body_bytes <= 2 * 1024 * 1024
    assert len(receipt.model_dump_json().encode()) <= 12 * 1024


def test_concurrent_cache_misses_coalesce_to_one_provider_request():
    count = 0
    lock = Lock()

    def handler(_request):
        nonlocal count
        with lock:
            count += 1
        time.sleep(0.05)
        return httpx.Response(200, json=document(
            feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
            headers={"Cache-Control": "max-age=60"},
        )

    service = AQHIQueryService(
        client=mock_client(handler), clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows,
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(lambda _: service.entry(), range(8)))
    assert count == 1
    assert len({entry.acquisition.body_sha256 for entry in entries}) == 1


def test_future_exact_hour_age_and_far_station_are_withheld():
    payload = document(
        feature("FUTURE", 1, "2026-09-07T00:31:00Z", -52.7252, 47.5658),
        feature("OLD", 2, "2026-09-06T23:30:00Z", -52.7252, 47.5658),
    )
    service = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=payload, headers={"Cache-Control": "max-age=60"})),
        clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows,
    )
    with pytest.raises(AqhiQueryUnavailable, match="less than one hour"):
        service.point_field(47.56, -52.72, SELECTED)

    far = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=document(
            feature("FAR", 3, "2026-09-07T00:00:00Z", -54.0, 49.0)), headers={"Cache-Control": "max-age=60"})),
        clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows,
    )
    with pytest.raises(AqhiQueryUnavailable, match="near the requested coordinate"):
        far.point_field(47.56, -52.72, SELECTED)

    diagonal = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=document(
            feature("DIAGONAL", 4, "2026-09-07T00:00:00Z", -52.02, 48.26)), headers={"Cache-Control": "max-age=60"})),
        clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows,
    )
    with pytest.raises(AqhiQueryUnavailable, match="near the requested coordinate"):
        diagonal.point_field(47.56, -52.72, SELECTED)


def test_nearest_applicable_native_station_precedes_newest_time_tie_break():
    service = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=document(
            feature("NEAR", 2, "2026-09-06T23:50:00Z", -52.7252, 47.5658),
            feature("FARTHER", 7, "2026-09-07T00:20:00Z", -52.2, 47.8),
        ), headers={"Cache-Control": "max-age=60"})),
        clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows,
    )
    field = service.point_field(47.56, -52.72, SELECTED)
    assert field.value == 2
    assert field.provenance.native_report.station_id == "NEAR"
    assert field.provenance.valid_time == datetime(2026, 9, 6, 23, 50, tzinfo=UTC)


def test_failed_expired_refresh_retains_only_bounded_receipt_and_withholds_values():
    clock = Clock()
    responses = [
        httpx.Response(200, json=document(feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)), headers={"Cache-Control": "max-age=1"}),
        httpx.Response(503),
    ]
    service = AQHIQueryService(
        client=mock_client(lambda _: responses.pop(0)), clock=clock,
        utcnow=lambda: SELECTED, decode=station_rows,
    )
    initial = service.entry()
    clock.value += 2
    with pytest.raises(AqhiQueryUnavailable) as caught:
        service.entry()
    outcome = caught.value.outcome
    assert outcome.reason == "refresh_failed" and outcome.values_withheld is True
    assert outcome.expired_acquisition == initial.acquisition
    assert service._entry is None
    assert service._expired_acquisition == initial.acquisition
    assert not hasattr(caught.value, "observations")


def test_initial_query_failure_is_not_mislabeled_as_a_refresh():
    service = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(503)), clock=Clock(),
        utcnow=lambda: SELECTED, decode=station_rows,
    )
    with pytest.raises(AqhiQueryUnavailable) as caught:
        service.entry()
    assert caught.value.outcome.reason == "query_failed"
    assert caught.value.outcome.expired_acquisition is None
    assert caught.value.outcome.values_withheld is True


def test_cache_listing_never_fetches_and_expired_entry_is_not_listed():
    calls = []
    clock = Clock()
    service = AQHIQueryService(
        client=mock_client(lambda request: (calls.append(request) or httpx.Response(500))),
        clock=clock, utcnow=lambda: SELECTED, decode=station_rows,
    )
    assert service.cached_entry() is None and calls == []
    acquisition_service = AQHIQueryService(
        client=mock_client(lambda _: httpx.Response(200, json=document(
            feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)), headers={"Cache-Control": "max-age=1"})),
        clock=clock, utcnow=lambda: SELECTED, decode=station_rows,
    )
    acquisition_service.entry()
    assert acquisition_service.cached_entry() is not None
    clock.value += 2
    assert acquisition_service.cached_entry() is None


def test_default_point_and_layer_bridge_use_fixed_query_without_legacy_store_or_catalog_fetch(
    monkeypatch, data_mode, no_default_demand_evidence,
):
    app_module = importlib.import_module("weather_api.app")
    import weather_api.aqhi_query as aqhi_module

    requests = []
    service = AQHIQueryService(
        client=mock_client(lambda request: (requests.append(request) or httpx.Response(
            200, json=document(feature("ABEFS", 2.7, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
            headers={"Cache-Control": "max-age=60"},
        ))),
        clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows,
    )
    monkeypatch.setattr(aqhi_module, "aqhi_query_service", lambda: service)
    monkeypatch.setattr(app_module, "live_store", lambda: None)
    data_mode("live")
    client = TestClient(app_module.app)

    point = client.get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.56, "longitude": -52.72, "valid_time": SELECTED.isoformat(),
    })
    assert point.status_code == 200
    body = point.json()
    assert [item["field"] for item in body["fields"]] == ["aqhi"]
    assert body["fields"][0]["value"] == 2.7
    assert body["fields"][0]["provenance"]["native_report"]["station_id"] == "ABEFS"
    assert body["observation_unavailable"] == []
    assert len(requests) == 1

    monkeypatch.setattr(app_module, "_proxied_forecast_layers", lambda: ([], []))
    layers = client.get(f"{app_module.PREFIX}/layers")
    assert layers.status_code == 200 and len(requests) == 1
    layer = next(item for item in layers.json()["layers"] if item["id"] == "eccc-aqhi-demand-observations")
    assert layer["times"] == ["2026-09-07T00:00:00Z"]
    assert layer["evidence_basis"] == "demand_query" and layer["raster_available"] is False

    class RaisingStore:
        @staticmethod
        def current():
            raise RuntimeError("fixed store failure")

    class EmptyStore:
        @staticmethod
        def current():
            return []

    for store in (RaisingStore(), EmptyStore()):
        monkeypatch.setattr(app_module, "live_store", lambda store=store: store)
        branch = client.get(f"{app_module.PREFIX}/layers")
        assert branch.status_code == 200 and len(requests) == 1
        assert any(item["id"] == "eccc-aqhi-demand-observations" for item in branch.json()["layers"])


def test_default_api_serializes_expired_receipt_without_values_when_every_demand_source_fails(
    monkeypatch, data_mode, no_default_demand_evidence,
):
    app_module = importlib.import_module("weather_api.app")
    import weather_api.aqhi_query as aqhi_module

    clock = Clock()
    responses = [
        httpx.Response(200, json=document(
            feature("ABEFS", 2.7, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
            headers={"Cache-Control": "max-age=1"}),
        httpx.Response(503),
    ]
    service = AQHIQueryService(
        client=mock_client(lambda _: responses.pop(0)), clock=clock,
        utcnow=lambda: SELECTED, decode=station_rows,
    )
    original = service.entry().acquisition
    clock.value += 2
    monkeypatch.setattr(aqhi_module, "aqhi_query_service", lambda: service)
    data_mode("live")

    response = TestClient(app_module.app).get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.56, "longitude": -52.72, "valid_time": SELECTED.isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert all(item["provenance"]["source_id"] != "eccc-aqhi" for item in body["fields"])
    assert len(body["observation_unavailable"]) == 1
    unavailable = body["observation_unavailable"][0]
    assert unavailable["values_withheld"] is True
    assert unavailable["expired_acquisition"]["body_sha256"] == original.body_sha256
    assert unavailable["expired_acquisition"]["expires_at"] == original.expires_at.isoformat().replace("+00:00", "Z")


def test_explicit_refresh_replaces_fresh_entry_without_sliding_cache_hits():
    clock = Clock()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=document(feature(
            "ABEFS", len(calls), "2026-09-07T00:00:00Z", -52.7252, 47.5658,
        )), headers={"Cache-Control": "max-age=60"})
    service = AQHIQueryService(client=mock_client(handler), clock=clock,
                               utcnow=lambda: SELECTED, decode=station_rows)
    first = service.point_field(47.56, -52.72, SELECTED)
    deadline = service.cached_entry().expires_at_monotonic
    clock.value += 10
    assert service.point_field(47.56, -52.72, SELECTED).value == first.value
    assert service.cached_entry().expires_at_monotonic == deadline
    refreshed = service.point_field(47.56, -52.72, SELECTED, refresh=True)
    assert refreshed.value == 2 and len(calls) == 2
    assert refreshed.provenance.artifact_revision != first.provenance.artifact_revision
    assert service.cached_entry().expires_at_monotonic == clock.value + 60


def test_final_byte_expiry_includes_decode_time():
    clock = Clock()
    def slow_decode(body):
        clock.value += 20
        return station_rows(body)
    service = AQHIQueryService(client=mock_client(lambda _: httpx.Response(
        200, json=document(feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
        headers={"Cache-Control": "max-age=60"},
    )), clock=clock, utcnow=lambda: SELECTED, decode=slow_decode)
    assert service.entry().expires_at_monotonic == 160
    clock.value = 160
    assert service.cached_entry() is None


def test_response_expiring_during_decode_is_never_admitted():
    clock = Clock()
    def slow_decode(body):
        clock.value += 60
        return station_rows(body)
    service = AQHIQueryService(client=mock_client(lambda _: httpx.Response(
        200, json=document(feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
        headers={"Cache-Control": "max-age=60"},
    )), clock=clock, utcnow=lambda: SELECTED, decode=slow_decode)
    with pytest.raises(AqhiQueryUnavailable, match="expired during validation"):
        service.entry()
    assert service.cached_entry() is None


def test_numeric_zero_quality_token_is_preserved_without_certification():
    service = AQHIQueryService(client=mock_client(lambda _: httpx.Response(
        200, json=document(feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658, quality=0)),
    )), clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows)
    field = service.point_field(47.56, -52.72, SELECTED)
    assert field.provenance.native_report.native_metadata == {"provider_quality": "0"}
    assert field.provenance.quality.status == "unknown"
    assert "provider_quality:0" in field.provenance.quality.flags


@pytest.mark.parametrize("latitude,longitude", [(float("nan"), -52.72), (47.56, float("inf")), (91, 0), (0, -181)])
def test_invalid_point_fails_before_provider_request(latitude, longitude):
    calls = []
    service = AQHIQueryService(client=mock_client(lambda request: calls.append(request)))
    with pytest.raises(ValueError, match="coordinates"):
        service.point_field(latitude, longitude, SELECTED)
    assert calls == []


def test_companion_predicate_admits_only_native_aqhi_observation_identity():
    from weather_api.aqhi_query import is_aqhi_observation_companion

    service = AQHIQueryService(client=mock_client(lambda _: httpx.Response(
        200, json=document(feature("ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)),
    )), clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows)
    field = service.point_field(47.56, -52.72, SELECTED)
    assert is_aqhi_observation_companion(field)
    for update in ({"field": "pm25"}, {"key": "particulate_matter_2_5"}, {"value": None}, {"value": float("nan")}):
        assert not is_aqhi_observation_companion(field.model_copy(update=update))
    for update in (
        {"source_id": "eccc-raqdps"}, {"source_id": "eccc-rdaqa"},
        {"product": "AQHI forecast regions"}, {"run_time": SELECTED},
        {"native_report": None}, {"aqhi_acquisition": None},
        {"valid_time": SELECTED}, {"sampled_latitude": 48},
        {"sampled_longitude": -53}, {"original_units": "ug/m3"},
        {"normalized_units": "ug/m3"}, {"adapter_version": "other"},
        {"data_mode": "fixture"}, {"evidence_class": "derived"},
    ):
        assert not is_aqhi_observation_companion(field.model_copy(update={
            "provenance": field.provenance.model_copy(update=update),
        })), update


def test_concurrent_explicit_refreshes_coalesce_and_failure_withholds_previous_values():
    from threading import Event

    started, release = Event(), Event()
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=document(feature(
                "ABEFS", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658,
            )), headers={"Cache-Control": "max-age=60"})
        started.set()
        assert release.wait(5)
        return httpx.Response(503)
    service = AQHIQueryService(client=mock_client(handler), clock=Clock(),
                               utcnow=lambda: SELECTED, decode=station_rows)
    original = service.entry().acquisition
    with ThreadPoolExecutor(max_workers=4) as pool:
        owner = pool.submit(service.entry, refresh=True)
        assert started.wait(5)
        # Signal after the waiter has joined the actual in-flight Future.
        joined = Event()
        pending = service._inflight
        original_result = pending.result
        def joined_result(*args, **kwargs):
            joined.set()
            return original_result(*args, **kwargs)
        pending.result = joined_result
        waiter = pool.submit(service.entry, refresh=True)
        assert joined.wait(5)
        assert service.cached_entry() is None
        release.set()
        for future in (owner, waiter):
            with pytest.raises(AqhiQueryUnavailable) as caught:
                future.result()
            assert caught.value.outcome.values_withheld is True
            assert caught.value.outcome.expired_acquisition == original
    assert len(calls) == 2
    assert service.cached_entry() is None


def test_native_location_id_is_station_identity_and_feature_id_is_retained():
    native = feature("AQ_OBS-ABEFS-20260907000000", 2, "2026-09-07T00:00:00Z", -52.7252, 47.5658)
    native["properties"].update({"properties.location_id": "ABEFS", "properties.aqhi_type": "AQHI-Observation"})
    service = AQHIQueryService(client=mock_client(lambda _: httpx.Response(200, json=document(native))),
                               clock=Clock(), utcnow=lambda: SELECTED, decode=station_rows)
    report = service.point_field(47.56, -52.72, SELECTED).provenance.native_report
    assert report.station_id == "ABEFS"
    assert report.native_metadata["provider_feature_id"] == "AQ_OBS-ABEFS-20260907000000"
    native["properties"]["properties.aqhi_type"] = "AQHI-Forecast"
    with pytest.raises(ValueError, match="not an observation"):
        normalize(document(native))
