from __future__ import annotations

import importlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from weather_api.lightning_query import CACHE_MAX_BYTES, CACHE_MAX_ENTRIES, LightningQueryService, LightningQueryUnavailable
from weather_api.lightning_query_worker import normalize_capabilities, normalize_sample

SELECTED = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)


class Clocks:
    monotonic = 100.0
    wall = SELECTED + timedelta(seconds=1)

    def tick(self, seconds: int):
        self.monotonic += seconds
        self.wall += timedelta(seconds=seconds)


def capabilities(*times: datetime) -> bytes:
    extent = ",".join(item.isoformat().replace("+00:00", "Z") for item in times)
    return f'''<WMS_Capabilities updateSequence="fixed" xmlns="http://www.opengis.net/wms"><Capability><Layer><Layer queryable="1"><Name>Lightning_2.5km_Density</Name><Dimension name="time" units="ISO8601">{extent}</Dimension></Layer></Layer></Capability></WMS_Capabilities>'''.encode()


def sample(value=0.42, *, at=SELECTED, latitude=47.5391, longitude=-52.6859):
    return {
        "type": "FeatureCollection", "layer": "Lightning_2.5km_Density", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "properties": {
                "value": value, "title_en": "Lightning Flash Density over Canada (2.5 km) [flash/km²/min]",
                "time": at.isoformat().replace("+00:00", "Z"), "dim_reference_time": "N/A",
            },
        }],
    }


def fixed_decode(kind: str, body: bytes):
    return normalize_capabilities(body) if kind == "capabilities" else normalize_sample(body)


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def service(handler, clocks: Clocks, *, decode=fixed_decode):
    return LightningQueryService(
        client=mock_client(handler), clock=lambda: clocks.monotonic,
        utcnow=lambda: clocks.wall, decode=decode,
    )


def successful_handler(calls: list[httpx.Request], *, payload=None, max_age=60):
    def handler(request):
        calls.append(request)
        if "GetCapabilities" in str(request.url):
            return httpx.Response(200, content=capabilities(SELECTED), headers={"Cache-Control": f"max-age={max_age}"})
        return httpx.Response(200, json=sample() if payload is None else payload, headers={"Cache-Control": f"max-age={max_age}"})
    return handler


def test_worker_preserves_exact_advertised_times_numeric_cell_and_native_empty_semantics():
    assert normalize_capabilities(capabilities(SELECTED))["times"] == [SELECTED.isoformat()]
    numeric = normalize_sample(json.dumps(sample()).encode())
    assert numeric["value"] == 0.42 and numeric["valid_time"] == SELECTED.isoformat()
    assert numeric["latitude"] == 47.5391 and numeric["native_units"] == "flash/km²/min"
    assert normalize_sample(b"{}") == {
        "value": None, "valid_time": None, "latitude": None, "longitude": None,
        "title": None, "native_units": None,
    }


def test_registry_and_field_catalogue_describe_the_exact_frame_demand_path():
    from registry.fields import storage_of
    from registry.source_data import registry

    record = next(item for item in registry()["sources"] if item["id"] == "eccc-lightning")
    assert record["access_endpoints"] == ["https://geo.weather.gc.ca/geomet/"]
    assert record["integration"]["kind"] == "typed_adapter"
    assert "GetCapabilities and GetFeatureInfo" in record["integration"]["client"]
    assert "GeoMet Lightning_2.5km_Density" in record["schema_version"]
    assert record["caching"].startswith("Finite source-local selected-time cache")
    assert record["archival"].startswith("No lightning archive")
    assert storage_of("eccc-lightning", "lightning_observed") == "available-not-stored"
    assert storage_of("eccc-lightning", "lightning_strike") == "available-not-stored"


def test_default_decoder_invokes_the_existing_bounded_child_contract(monkeypatch):
    module = importlib.import_module("weather_api.lightning_query")
    seen = []

    def bounded(**kwargs):
        seen.append(kwargs)
        result = fixed_decode(kwargs["command"][-2], kwargs["stdin"])
        return SimpleNamespace(stdout=json.dumps(result, separators=(",", ":")).encode())

    monkeypatch.setattr(module, "run_bounded_process", bounded)
    calls, clocks = [], Clocks()
    fields = service(successful_handler(calls), clocks, decode=module._decode).point_fields(47.56, -52.72, SELECTED)
    assert [field.value for field in fields] == [1, 0.42]
    assert [item["command"].count("{output}") for item in seen] == [1, 1]
    assert all(item["destination"] is None and item["require_output"] is False for item in seen)


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS rejects the decoder's required locked RLIMIT_AS")
def test_actual_bounded_child_decodes_fixed_capability_and_sample_payloads():
    calls, clocks = [], Clocks()
    fields = service(successful_handler(calls), clocks).point_fields(47.56, -52.72, SELECTED)
    assert [field.value for field in fields] == [1, 0.42]
    assert fields[1].provenance.sampled_latitude == 47.5391


def test_exact_frame_cache_hit_is_zero_upstream_and_freshness_age_advances():
    calls, clocks = [], Clocks()
    query = service(successful_handler(calls, max_age=60), clocks)
    first = query.point_fields(47.56, -52.72, SELECTED)
    clocks.tick(17)
    second = query.point_fields(47.56, -52.72, SELECTED)
    assert len(calls) == 2
    assert first[1].value == second[1].value == 0.42
    assert first[1].provenance.freshness.age_seconds == 0
    assert second[1].provenance.freshness.age_seconds == 17
    acquisition = second[1].provenance.lightning_acquisition
    assert acquisition.request.selected_time == SELECTED
    assert [item.kind for item in acquisition.transport_receipts] == ["capabilities", "sample"]
    assert len(acquisition.model_dump_json().encode()) <= 16 * 1024


def test_nonadvertised_time_is_unsupported_without_a_sample_request():
    calls, clocks = [], Clocks()
    query = service(successful_handler(calls), clocks)
    with pytest.raises(LightningQueryUnavailable) as caught:
        query.point_fields(47.56, -52.72, SELECTED + timedelta(minutes=1))
    assert caught.value.outcome.reason == "unsupported_time"
    assert len(calls) == 1 and "GetCapabilities" in str(calls[0].url)


def test_native_empty_is_zero_without_inventing_published_cell_coordinates():
    calls, clocks = [], Clocks()
    fields = service(successful_handler(calls, payload={}), clocks).point_fields(47.56, -52.72, SELECTED)
    assert [(field.field, field.value) for field in fields] == [("lightning_observed", 0)]
    provenance = fields[0].provenance
    assert provenance.sampled_latitude is None and provenance.sampled_longitude is None
    assert provenance.sample_distance_km is None and provenance.sample_method == "wms_getfeatureinfo_pixel_identity_unavailable"
    assert "published_cell_coordinate_unavailable" in provenance.quality.flags


def test_a_returned_cell_beyond_the_accepted_distance_is_withheld():
    calls, clocks = [], Clocks()
    handler = successful_handler(calls, payload=sample(latitude=49.0, longitude=-54.0))
    with pytest.raises(LightningQueryUnavailable, match="too far"):
        service(handler, clocks).point_fields(47.56, -52.72, SELECTED)


def test_identical_concurrent_misses_coalesce_capability_and_sample_requests():
    calls, lock, clocks = [], Lock(), Clocks()

    def handler(request):
        with lock:
            calls.append(request)
        time.sleep(0.03)
        if "GetCapabilities" in str(request.url):
            return httpx.Response(200, content=capabilities(SELECTED), headers={"Cache-Control": "max-age=60"})
        return httpx.Response(200, json=sample(), headers={"Cache-Control": "max-age=60"})

    query = service(handler, clocks)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: query.point_fields(47.56, -52.72, SELECTED), range(8)))
    assert len(calls) == 2
    assert {result[1].provenance.lightning_acquisition.transport_receipts[1].body_sha256 for result in results}


def test_expired_failure_withholds_values_and_expired_metadata_residency_is_bounded():
    clocks = Clocks()
    fail = False

    def handler(request):
        if fail:
            return httpx.Response(503)
        if "GetCapabilities" in str(request.url):
            return httpx.Response(200, content=capabilities(SELECTED), headers={"Cache-Control": "max-age=1"})
        return httpx.Response(200, json=sample(), headers={"Cache-Control": "max-age=1"})

    query = service(handler, clocks)
    for index in range(CACHE_MAX_ENTRIES + 5):
        longitude = -52.72 + index / 10000
        fail = False
        original = query.entry_for(47.56, longitude, SELECTED).acquisition
        clocks.tick(2)
        fail = True
        with pytest.raises(LightningQueryUnavailable) as caught:
            query.entry_for(47.56, longitude, SELECTED)
        assert caught.value.outcome.reason == "refresh_failed"
        assert caught.value.outcome.expired_acquisition == original
        assert caught.value.outcome.values_withheld is True
    resident = sum(item.backing_bytes for item in query._entries.values()) + sum(
        len(item.model_dump_json().encode()) for item in query._expired.values()
    )
    assert len(query._entries) + len(query._expired) <= CACHE_MAX_ENTRIES
    assert resident <= CACHE_MAX_BYTES


def test_default_point_and_layers_serialize_native_lightning_without_store_or_catalog_fetch(monkeypatch, data_mode, no_default_demand_evidence):
    app_module = importlib.import_module("weather_api.app")
    module = importlib.import_module("weather_api.lightning_query")
    calls, clocks = [], Clocks()
    query = service(successful_handler(calls), clocks)
    monkeypatch.setattr(module, "lightning_query_service", lambda: query)
    monkeypatch.setattr(app_module, "live_store", lambda: None)
    monkeypatch.setattr(app_module, "_proxied_forecast_layers", lambda: ([], []))
    data_mode("live")
    client = TestClient(app_module.app)

    response = client.get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.56, "longitude": -52.72, "valid_time": SELECTED.isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert [(item["field"], item["value"]) for item in body["fields"]] == [("lightning_observed", 1), ("lightning_strike", 0.42)]
    assert body["fields"][1]["provenance"]["lightning_acquisition"]["native_valid_time"] == "2026-09-07T02:00:00Z"
    assert body["observation_unavailable"] == [] and len(calls) == 2

    layers = client.get(f"{app_module.PREFIX}/layers")
    assert layers.status_code == 200 and len(calls) == 2
    layer = next(item for item in layers.json()["layers"] if item["id"] == "eccc-lightning-demand-observations")
    assert layer["times"] == ["2026-09-07T02:00:00Z"] and layer["evidence_basis"] == "demand_query"


def test_public_expired_outcome_carries_bounded_identity_and_no_lightning_values(monkeypatch, data_mode, no_default_demand_evidence):
    app_module = importlib.import_module("weather_api.app")
    module = importlib.import_module("weather_api.lightning_query")
    clocks, fail = Clocks(), False

    def handler(request):
        if fail:
            return httpx.Response(503)
        if "GetCapabilities" in str(request.url):
            return httpx.Response(200, content=capabilities(SELECTED), headers={"Cache-Control": "max-age=1"})
        return httpx.Response(200, json=sample(), headers={"Cache-Control": "max-age=1"})

    query = service(handler, clocks)
    original = query.entry_for(47.56, -52.72, SELECTED).acquisition
    clocks.tick(2)
    fail = True
    monkeypatch.setattr(module, "lightning_query_service", lambda: query)
    data_mode("live")
    response = TestClient(app_module.app).get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.56, "longitude": -52.72, "valid_time": SELECTED.isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert all(item["provenance"]["source_id"] != "eccc-lightning" for item in body["fields"])
    outcome = next(item for item in body["observation_unavailable"] if item["source_id"] == "eccc-lightning")
    assert outcome["values_withheld"] is True
    assert outcome["expired_acquisition"]["expires_at"] == original.expires_at.isoformat().replace("+00:00", "Z")
    assert len(json.dumps(outcome).encode()) <= 20 * 1024
