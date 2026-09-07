from __future__ import annotations

import json
import sys
from weather_api.swob_query_worker import normalize

SELECTED = "2026-09-07T03:00:00Z"


def feature(*, provider="MSC", dataset="msc-observation-atmospheric-surface_weather-surface", station="CAJW", latitude=47.56, longitude=-52.72, time=SELECTED, temperature=12.4, temperature_qa="passed"):
    return {
        "type": "Feature", "id": station,
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": {
            "data_pvdr-value": provider, "dataset": dataset, "stn_nam-value": "ST. JOHN'S WEST",
            "date_tm-value": time, "wmo_id": "71801", "air_temp": temperature, "air_temp-qa": temperature_qa,
            "dwpt_temp": 8.2, "rel_hum": 76, "mslp": 1013.4, "wnd_spd": 4.5, "wnd_dir": 210,
        },
    }


def test_worker_admits_only_canonical_msc_surface_weather_records():
    document = {"type": "FeatureCollection", "features": [
        feature(), feature(provider="NAV CANADA", station="CYYT"), feature(dataset="partner-observation-weather", station="PARTNER"),
    ]}
    rows = normalize(document)
    assert len(rows) == 1
    row = rows[0]
    assert row["station_id"] == "71801" and row["provider_report_id"] == "CAJW"
    assert row["observation_time"] == "2026-09-07T03:00:00+00:00"
    assert row["station_metadata"] == {"wmo_id": "71801"}
    assert row["values"] == {
        "temperature_2m": 12.4, "dew_point_2m": 8.2, "relative_humidity_2m": 76.0,
        "mean_sea_level_pressure": 1013.4, "wind_speed_10m": 4.5, "wind_direction_10m": 210.0,
    }


def test_worker_preserves_individual_missing_and_unknown_qc_fields_without_crossfill():
    item = feature(temperature=99.0, temperature_qa="failed")
    item["properties"].pop("dwpt_temp")
    rows = normalize({"type": "FeatureCollection", "features": [item]})
    row = rows[0]
    assert row["values"]["temperature_2m"] == 99.0
    assert row["values"]["dew_point_2m"] is None
    assert row["values"]["relative_humidity_2m"] == 76.0
    assert row["field_quality_tokens"]["temperature_2m"] == "failed"


def test_worker_refuses_report_id_as_a_station_and_preserves_unknown_qc_tokens():
    item = feature(temperature=14.0, temperature_qa="unfailed")
    for key in ("wmo_id", "wmo_stn", "msc_id", "stn_id", "station_id"):
        item["properties"].pop(key, None)
    with pytest.raises(ValueError, match="native station identifier"):
        normalize(fixture_document(item))

    item = feature(temperature=14.0, temperature_qa="unfailed")
    assert normalize(fixture_document(item))[0]["values"]["temperature_2m"] == 14.0
    item = feature(temperature=14.0, temperature_qa="not passed")
    assert normalize(fixture_document(item))[0]["values"]["temperature_2m"] == 14.0
    item = feature(temperature=14.0, temperature_qa="REJECTED")
    assert normalize(fixture_document(item))[0]["values"]["temperature_2m"] == 14.0


def test_worker_rejects_malformed_canonical_geometry_and_report_time():
    item = feature()
    item["geometry"] = {"type": "Point", "coordinates": ["bad", -52.72]}
    try:
        normalize({"type": "FeatureCollection", "features": [item]})
    except ValueError as error:
        assert "coordinates" in str(error)
    else:
        raise AssertionError("malformed canonical record must be refused")

import httpx
import pytest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock

from weather_api.swob_query import SWOBQueryService, SWOBStationObservation, SwobQueryUnavailable


class Clocks:
    monotonic = 100.0
    wall = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)

    def tick(self, seconds: int):
        self.monotonic += seconds
        self.wall += timedelta(seconds=seconds)


def fixture_document(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def station_rows(body: bytes):
    return tuple(SWOBStationObservation(
        station_id=item["station_id"], station_name=item.get("station_name"),
        observation_time=datetime.fromisoformat(item["observation_time"]),
        latitude=item["latitude"], longitude=item["longitude"], dataset=item["dataset"],
        provider_report_id=item.get("provider_report_id"), field_quality_tokens=item["field_quality_tokens"], station_metadata=item["station_metadata"],
        values=item["values"],
    ) for item in normalize(json.loads(body)))


def query_service(handler, clocks):
    return SWOBQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: clocks.monotonic, utcnow=lambda: clocks.wall, decode=station_rows,
    )


def test_exact_msc_station_point_cache_and_final_byte_freshness():
    calls, clocks = [], Clocks()

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})

    query = query_service(handler, clocks)
    selected = clocks.wall
    first = query.point_fields(47.5615, -52.7126, selected)
    clocks.tick(17)
    second = query.point_fields(47.5615, -52.7126, selected)
    assert len(calls) == 1
    assert [item.value for item in first] == [12.4, 8.2, 76.0, 1013.4, 4.5, 210.0]
    assert second[0].provenance.freshness.age_seconds == 17
    acquisition = second[0].provenance.swob_acquisition
    assert acquisition.request.selected_time == datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    assert acquisition.request.provider_url == acquisition.effective_url
    assert "datetime=2026-09-07T03%3A00%3A00Z" in acquisition.request.provider_url


def test_exact_time_and_provider_identity_refuse_without_neighbour_or_partner():
    clocks = Clocks()

    def handler(_request):
        return httpx.Response(200, json=fixture_document(
            feature(time="2026-09-07T02:00:00Z"), feature(provider="NAV CANADA", station="CYYT"),
        ), headers={"Cache-Control": "max-age=60"})

    with pytest.raises(SwobQueryUnavailable) as caught:
        query_service(handler, clocks).point_fields(47.5615, -52.7126, clocks.wall)
    assert caught.value.outcome.reason == "unsupported_time"


def test_nearest_exact_station_and_individual_nulls_keep_native_tokens_unknown():
    clocks = Clocks()

    def handler(_request):
        nearer = feature(station="MSC-NEAR", latitude=47.56, longitude=-52.71, temperature=10)
        nearer["properties"].pop("dwpt_temp")
        farther = feature(station="MSC-FAR", latitude=47.8, longitude=-52.2, temperature=30)
        return httpx.Response(200, json=fixture_document(farther, nearer), headers={"Cache-Control": "max-age=60"})

    fields = query_service(handler, clocks).point_fields(47.5615, -52.7126, clocks.wall)
    assert fields[0].value == 10.0 and fields[1].value is None
    assert all(item.provenance.native_report.station_id == "71801" for item in fields)
    assert all(item.provenance.native_report.provider_report_id == "MSC-NEAR" for item in fields)
    assert fields[0].provenance.quality.status == "unknown"
    assert "provider_quality:passed" in fields[0].provenance.quality.flags


def test_expired_refresh_failure_withholds_values_and_preserves_bounded_metadata():
    clocks, fail = Clocks(), False

    def handler(_request):
        if fail:
            return httpx.Response(503)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=1"})

    query = query_service(handler, clocks)
    selected = clocks.wall
    original = query.entry_for(47.5615, -52.7126, selected).acquisition
    clocks.tick(2)
    fail = True
    with pytest.raises(SwobQueryUnavailable) as caught:
        query.point_fields(47.5615, -52.7126, selected)
    assert caught.value.outcome.reason == "refresh_failed"
    assert caught.value.outcome.expired_acquisition == original
    assert caught.value.outcome.values_withheld is True


def test_identical_misses_coalesce_to_one_request():
    calls, lock, clocks = [], Lock(), Clocks()

    def handler(request):
        with lock:
            calls.append(request)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})

    query = query_service(handler, clocks)
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: query.point_fields(47.5615, -52.7126, clocks.wall)[0].value, range(8)))
    assert values == [12.4] * 8 and len(calls) == 1


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS rejects the decoder's required locked RLIMIT_AS")
def test_default_bounded_decoder_serves_fixed_payload_without_injection():
    clocks, calls = Clocks(), []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})

    service = SWOBQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: clocks.monotonic, utcnow=lambda: clocks.wall,
    )
    fields = service.point_fields(47.5615, -52.7126, clocks.wall)
    assert fields[0].value == 12.4 and fields[0].provenance.swob_acquisition.body_bytes > 0
    snapshot = service.cached_entries_for(47.5615, -52.7126)
    assert len(snapshot) == 1
    assert service.point_fields_from_entry(snapshot[0], 47.5615, -52.7126, clocks.wall) == fields
    assert len(calls) == 1


def test_default_decoder_uses_one_output_argument_and_serves_fixed_payload(monkeypatch):
    import weather_api.swob_query as module
    from types import SimpleNamespace

    seen = {}

    def bounded(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(stdout=json.dumps(normalize(json.loads(kwargs["stdin"])), separators=(",", ":")))

    monkeypatch.setattr(module, "run_bounded_process", bounded)
    clocks = Clocks()
    service = SWOBQueryService(
        client=httpx.Client(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})
        )), clock=lambda: clocks.monotonic, utcnow=lambda: clocks.wall,
    )
    fields = service.point_fields(47.5615, -52.7126, clocks.wall)
    assert fields[0].value == 12.4 and fields[0].provenance.native_report.station_id == "71801"
    assert seen["command"].count("{output}") == 1
    assert seen["destination"] is None and seen["require_output"] is False


def test_default_point_and_layer_bridge_serve_cached_swob_without_legacy_store(
    monkeypatch, data_mode, no_default_demand_evidence,
):
    import importlib
    from fastapi.testclient import TestClient

    app_module = importlib.import_module("weather_api.app")
    import weather_api.swob_query as swob_module

    clocks, requests = Clocks(), []
    service = SWOBQueryService(
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: (requests.append(request) or httpx.Response(
                200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"}
            ))
        )), clock=lambda: clocks.monotonic, utcnow=lambda: clocks.wall, decode=station_rows,
    )
    monkeypatch.setattr(swob_module, "swob_query_service", lambda: service)
    monkeypatch.setattr(app_module, "live_store", lambda: None)
    monkeypatch.setattr(app_module, "_proxied_forecast_layers", lambda: ([], []))
    data_mode("live")
    client = TestClient(app_module.app)

    point = client.get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.5615, "longitude": -52.7126, "valid_time": clocks.wall.isoformat(),
    })
    assert point.status_code == 200
    body = point.json()
    swob_fields = [item for item in body["fields"] if item["provenance"]["source_id"] == "eccc-swob"]
    assert [item["field"] for item in swob_fields] == list(_FIELD_NAMES)
    assert swob_fields[0]["provenance"]["swob_acquisition"]["request"]["selected_time"] == SELECTED
    assert len(requests) == 1

    layers = client.get(f"{app_module.PREFIX}/layers")
    assert layers.status_code == 200 and len(requests) == 1
    layer = next(item for item in layers.json()["layers"] if item["id"] == "eccc-swob-demand-observations")
    assert layer["times"] == [SELECTED]
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
        assert any(item["id"] == "eccc-swob-demand-observations" for item in branch.json()["layers"])


_FIELD_NAMES = (
    "temperature_2m", "dew_point_2m", "relative_humidity_2m", "mean_sea_level_pressure",
    "wind_speed_10m", "wind_direction_10m",
)


def test_default_api_serializes_expired_swob_receipt_without_values(
    monkeypatch, data_mode, no_default_demand_evidence,
):
    import importlib
    from fastapi.testclient import TestClient

    app_module = importlib.import_module("weather_api.app")
    import weather_api.swob_query as swob_module

    clocks = Clocks()
    responses = [
        httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=1"}),
        httpx.Response(503),
    ]
    service = SWOBQueryService(
        client=httpx.Client(transport=httpx.MockTransport(lambda _: responses.pop(0))),
        clock=lambda: clocks.monotonic, utcnow=lambda: clocks.wall, decode=station_rows,
    )
    selected = clocks.wall
    original = service.entry_for(47.5615, -52.7126, selected).acquisition
    clocks.tick(2)
    monkeypatch.setattr(swob_module, "swob_query_service", lambda: service)
    data_mode("live")

    response = TestClient(app_module.app).get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.5615, "longitude": -52.7126, "valid_time": selected.isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert all(item["provenance"]["source_id"] != "eccc-swob" for item in body["fields"])
    unavailable = next(item for item in body["observation_unavailable"] if item["source_id"] == "eccc-swob")
    assert unavailable["reason"] == "refresh_failed" and unavailable["values_withheld"] is True
    assert unavailable["expired_acquisition"]["body_sha256"] == original.body_sha256
    assert unavailable["expired_acquisition"]["expires_at"] == original.expires_at.isoformat().replace("+00:00", "Z")


def test_worker_refuses_pagination_or_a_feature_ceiling_without_a_complete_count():
    document = fixture_document(feature())
    document["links"] = [{"rel": "next", "href": "https://example.invalid/next"}]
    with pytest.raises(ValueError, match="next page"):
        normalize(document)
    document = fixture_document(feature())
    document["numberMatched"] = 2
    document["numberReturned"] = 1
    with pytest.raises(ValueError, match="incomplete"):
        normalize(document)
    document = fixture_document(*(feature(station=f"MSC-{index}") for index in range(64)))
    with pytest.raises(ValueError, match="feature ceiling"):
        normalize(document)
    document["numberMatched"] = document["numberReturned"] = 64
    assert len(normalize(document)) == 64


def test_request_envelope_covers_a_station_inside_corrected_distance_boundary():
    from urllib.parse import parse_qs, urlparse
    clocks, requested = Clocks(), []
    within_radius = feature(station="MSC-EAST", latitude=47.5615, longitude=-51.9126)

    def handler(request):
        requested.append(request)
        return httpx.Response(200, json=fixture_document(within_radius), headers={"Cache-Control": "max-age=60"})

    fields = query_service(handler, clocks).point_fields(47.5615, -52.7126, clocks.wall)
    bbox = [float(value) for value in parse_qs(urlparse(str(requested[0].url)).query)["bbox"][0].split(",")]
    assert bbox[2] >= -51.9126 and fields[0].provenance.native_report.provider_report_id == "MSC-EAST"


# Spec-Refs: swob-demand-query/specs/demand-query-cache (native identity,
# finite expiry, coalesced misses); GOV-SPEC-004, GOV-SPEC-006.
def test_explicit_refresh_replaces_fresh_snapshot_without_retiming_or_qc_reinterpretation():
    clocks, requests = Clocks(), []

    def handler(request):
        requests.append(request)
        item = feature(temperature=12.4 if len(requests) == 1 else 14.2, temperature_qa="suspect")
        item["properties"].pop("dwpt_temp")
        return httpx.Response(200, json=fixture_document(item), headers={"Cache-Control": "max-age=60"})

    service = query_service(handler, clocks)
    selected = clocks.wall
    first = service.point_fields(47.5615, -52.7126, selected)
    clocks.tick(3)
    refreshed = service.point_fields(47.5615, -52.7126, selected, refresh=True)
    assert len(requests) == 2
    assert first[0].value == 12.4 and refreshed[0].value == 14.2
    assert refreshed[1].value is None
    assert refreshed[0].provenance.quality.status == "unknown"
    assert "provider_quality:suspect" in refreshed[0].provenance.quality.flags
    assert refreshed[0].provenance.valid_time == selected
    assert refreshed[0].provenance.retrieval_time == clocks.wall
    assert refreshed[0].provenance.native_report == first[0].provenance.native_report
    assert refreshed[0].provenance.original_units == "degC"
    assert service.point_fields(47.5615, -52.7126, selected)[0].value == 14.2
    assert len(requests) == 2


@pytest.mark.parametrize("expires_during_refresh", [False, True])
def test_failed_explicit_refresh_keeps_only_still_fresh_old_entry(expires_during_refresh):
    clocks, requests = Clocks(), []

    def handler(request):
        requests.append(request)
        if len(requests) > 1:
            if expires_during_refresh:
                clocks.tick(61)
            return httpx.Response(503)
        return httpx.Response(200, json=fixture_document(feature()), headers={"Cache-Control": "max-age=60"})

    service = query_service(handler, clocks)
    selected = clocks.wall
    old = service.entry_for(47.5615, -52.7126, selected)
    with pytest.raises(SwobQueryUnavailable) as caught:
        service.entry_for(47.5615, -52.7126, selected, refresh=True)
    if expires_during_refresh:
        assert service.cached_entries_for(47.5615, -52.7126) == ()
        assert caught.value.outcome.reason == "refresh_failed"
        assert caught.value.outcome.expired_acquisition == old.acquisition
        assert caught.value.outcome.values_withheld
    else:
        assert service.entry_for(47.5615, -52.7126, selected) is old
        assert caught.value.outcome.expired_acquisition is None
    assert len(requests) == 2


def test_concurrent_explicit_refresh_coalesces_and_normal_hit_remains_available(monkeypatch):
    from concurrent.futures import Future
    from threading import Event
    import weather_api.swob_query as module

    entered, release, waiter = Event(), Event(), Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiter.set()
            return super().result(timeout)

    monkeypatch.setattr(module, "Future", ObservedFuture)
    clocks, requests = Clocks(), []

    def handler(request):
        requests.append(request)
        if len(requests) > 1:
            entered.set()
            assert release.wait(5)
        return httpx.Response(200, json=fixture_document(feature(temperature=10 + len(requests))),
                              headers={"Cache-Control": "max-age=60"})

    service = query_service(handler, clocks)
    selected = clocks.wall
    old = service.entry_for(47.5615, -52.7126, selected)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.entry_for, 47.5615, -52.7126, selected, refresh=True)
        try:
            assert entered.wait(5)
            second = pool.submit(service.entry_for, 47.5615, -52.7126, selected, refresh=True)
            assert waiter.wait(5)
            assert service.entry_for(47.5615, -52.7126, selected) is old
        finally:
            release.set()
        assert first.result() is second.result()
    assert len(requests) == 2


def test_native_planning_snapshot_is_location_scoped_finite_and_cache_only():
    clocks, requests = Clocks(), []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=fixture_document(feature(time=request.url.params["datetime"])),
                              headers={"Cache-Control": "max-age=60"})

    service = query_service(handler, clocks)
    selected = clocks.wall
    assert service.cached_entries_for(47.5615, -52.7126) == ()
    late = service.entry_for(47.5615, -52.7126, selected + timedelta(minutes=7))
    early = service.entry_for(47.5615, -52.7126, selected)
    service.entry_for(47.6, -52.7, selected + timedelta(minutes=4))
    snapshot = service.cached_entries_for(47.5615, -52.7126)
    assert snapshot == (early, late)
    assert len(requests) == 3
    fields = service.point_fields_from_entry(snapshot[1], 47.5615, -52.7126, selected + timedelta(minutes=7))
    assert fields[0].provenance.valid_time == selected + timedelta(minutes=7)
    with pytest.raises(SwobQueryUnavailable, match="does not match"):
        service.point_fields_from_entry(early, 47.6, -52.7, selected)
    with pytest.raises(SwobQueryUnavailable, match="does not match"):
        service.point_fields_from_entry(early, 47.5615, -52.7126, selected + timedelta(minutes=1))
    clocks.tick(61)
    assert service.cached_entries_for(47.5615, -52.7126) == ()
    with pytest.raises(SwobQueryUnavailable, match="expired"):
        service.point_fields_from_entry(early, 47.5615, -52.7126, selected)
    assert len(requests) == 3
