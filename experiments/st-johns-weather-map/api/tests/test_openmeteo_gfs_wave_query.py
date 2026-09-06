from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from weather_api.openmeteo_gfs_wave_query import (
    OPEN_METEO_GFS_WAVE_CACHE_MAX_BYTES,
    OPEN_METEO_GFS_WAVE_CACHE_MAX_ENTRIES,
    OPEN_METEO_GFS_WAVE_FIELDS,
    OpenMeteoGfsWaveQueryService,
    OpenMeteoGfsWaveUnavailable,
)
from weather_api.app import PREFIX, app

client = TestClient(app)

UTC = timezone.utc
SELECTED = datetime(2026, 9, 6, 15, tzinfo=UTC)


def payload(*, values=None, time="2026-09-06T15:00"):
    if values is None:
        values = {name: float(index + 1) for index, name in enumerate(OPEN_METEO_GFS_WAVE_FIELDS)}
    return {
        "latitude": 47.5, "longitude": -52.75,
        "hourly_units": {"time": "iso8601", **{name: "m" if name.endswith("height") else "s" if name.endswith("period") else "°" for name in OPEN_METEO_GFS_WAVE_FIELDS}},
        "hourly": {"time": [time], **{name: [values.get(name)] for name in OPEN_METEO_GFS_WAVE_FIELDS}},
    }


def service(handler, *, clock=lambda: 0.0):
    return OpenMeteoGfsWaveQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        clock=clock, utcnow=lambda: SELECTED,
    )


def test_canonical_request_is_one_hour_gfs_wave_sea_cell_and_fresh_hit_is_zero_provider_io():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload(), headers={"cache-control": "max-age=120"}, request=request)

    query = service(handler)
    first = query.query(47.5615, -52.7126, SELECTED)
    assert query.query(47.5615, -52.7126, SELECTED) is first
    assert len(calls) == 1
    params = dict(calls[0].url.params)
    assert params == {
        "latitude": "47.561500", "longitude": "-52.712600",
        "hourly": ",".join(OPEN_METEO_GFS_WAVE_FIELDS), "models": "ncep_gfswave016",
        "cell_selection": "sea", "timezone": "GMT", "start_hour": "2026-09-06T15:00", "end_hour": "2026-09-06T15:00",
    }


def test_concurrent_identical_misses_coalesce_to_one_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload(), request=request)

    query = service(handler)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: query.query(47.5615, -52.7126, SELECTED), range(8)))
    assert len(calls) == 1
    assert all(item is results[0] for item in results)


def test_exact_native_hour_is_required_and_neighbouring_provider_time_is_refused():
    query = service(lambda request: httpx.Response(200, json=payload(time="2026-09-06T14:00"), request=request))
    with pytest.raises(OpenMeteoGfsWaveUnavailable, match="exact selected native hour"):
        query.query(47.5615, -52.7126, SELECTED)
    with pytest.raises(ValueError, match="exact native hourly"):
        query.query(47.5615, -52.7126, SELECTED.replace(minute=1))


def test_missing_native_field_is_null_with_its_own_flag_while_valid_siblings_remain():
    values = {name: float(index + 1) for index, name in enumerate(OPEN_METEO_GFS_WAVE_FIELDS)}
    body = payload(values=values)
    del body["hourly"]["swell_wave_period"]
    del body["hourly_units"]["swell_wave_period"]
    query = service(lambda request: httpx.Response(200, json=body, request=request))

    fields = {field.field: field for field in query.point_fields(47.5615, -52.7126, SELECTED)}
    assert fields["swell_wave_period"].value is None
    assert "native_field_unavailable" in fields["swell_wave_period"].provenance.quality.flags
    assert fields["wave_height"].value == 1.0
    assert fields["wave_height"].provenance.run_time is None
    assert fields["wave_height"].provenance.intermediary == "Open-Meteo"


def test_all_null_sea_response_is_unavailable_not_calm():
    query = service(lambda request: httpx.Response(200, json=payload(values={}), request=request))
    with pytest.raises(OpenMeteoGfsWaveUnavailable, match="no sea-cell values"):
        query.query(47.5615, -52.7126, SELECTED)


def test_expired_provider_cache_directive_never_extends_the_source_ceiling():
    ticks = [0.0]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload(), headers={"cache-control": "max-age=1", "age": "1"}, request=request)

    query = service(handler, clock=lambda: ticks[0])
    query.query(47.5615, -52.7126, SELECTED)
    ticks[0] = 1.0
    query.query(47.5615, -52.7126, SELECTED)
    assert len(calls) == 2


def test_expired_cache_never_serves_stale_values_when_replacement_transport_fails():
    ticks = [0.0]
    calls = [0]

    def handler(request):
        calls[0] += 1
        if calls[0] == 2:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json=payload(), headers={"cache-control": "max-age=1"}, request=request)

    query = service(handler, clock=lambda: ticks[0])
    first = query.query(47.5615, -52.7126, SELECTED)
    ticks[0] = 1.0
    with pytest.raises(OpenMeteoGfsWaveUnavailable, match="transport failed"):
        query.query(47.5615, -52.7126, SELECTED)
    assert calls[0] == 2
    assert all(entry is not first for _, entry in query._entries.values())


def test_cache_enforces_aggregate_residency_and_entry_count_limits():
    query = service(lambda request: httpx.Response(200, json=payload(), request=request))
    for index in range(OPEN_METEO_GFS_WAVE_CACHE_MAX_ENTRIES + 5):
        query.query(47.0 + index / 100, -52.7126, SELECTED)
    assert len(query._entries) <= OPEN_METEO_GFS_WAVE_CACHE_MAX_ENTRIES
    assert sum(entry.backing_bytes for _, entry in query._entries.values()) <= OPEN_METEO_GFS_WAVE_CACHE_MAX_BYTES


def test_cached_provenance_freshness_ages_from_final_received_byte():
    now = [SELECTED]
    query = OpenMeteoGfsWaveQueryService(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload(), request=request))),
        clock=lambda: 0.0, utcnow=lambda: now[0],
    )
    query.point_fields(47.5615, -52.7126, SELECTED)
    now[0] = SELECTED.replace(minute=1)
    fields = query.point_fields(47.5615, -52.7126, SELECTED)
    assert fields[0].provenance.freshness.age_seconds == 60


def test_live_point_product_returns_wave_evidence_that_existing_web_mapping_consumes(monkeypatch):
    query = service(lambda request: httpx.Response(200, json=payload(), request=request))
    import weather_api.openmeteo_gfs_wave_query as module
    import importlib
    app_module = importlib.import_module("weather_api.app")

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(module, "openmeteo_gfs_wave_query_service", lambda: query)
    monkeypatch.setattr(app_module, "now", lambda: SELECTED)
    response = client.get(f"{PREFIX}/point", params={
        "latitude": 47.5615, "longitude": -52.7126, "valid_time": SELECTED.isoformat(), "product": "GFS Wave",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data_mode"] == "live"
    assert body["selection"]["mode"] == "evidence_only"
    assert body["selection"]["selected_source_id"] is None
    wave = next(item for item in body["fields"] if item["field"] == "wave_height")
    assert wave["value"] == 1.0
    assert wave["provenance"]["intermediary"] == "Open-Meteo"
    assert wave["provenance"]["run_time"] is None
    expected = {
        "wave_height": (1.0, "m"), "wave_period": (2.0, "s"), "wave_direction": (3.0, "degree"),
        "swell_height": (4.0, "m"), "swell_wave_period": (5.0, "s"), "swell_wave_direction": (6.0, "degree"),
        "wind_wave_height": (7.0, "m"), "wind_wave_period": (8.0, "s"), "wind_wave_direction": (9.0, "degree"),
    }
    received = {item["field"]: (item["value"], item["provenance"]["normalized_units"]) for item in body["fields"]}
    assert received == expected
    for item in body["fields"]:
        assert item["provenance"]["provider"] == "NOAA NCEP"
        assert item["provenance"]["delivery_kind"] == "reprocessed"
        assert item["provenance"]["sampled_latitude"] == 47.5
        assert item["provenance"]["sampled_longitude"] == -52.75
        assert item["provenance"]["display_primary_eligible"] is False
    assert {item["field"]: item["key"] for item in body["fields"]} == {
        "wave_height": "significant_wave_height", "wave_period": "wave_period", "wave_direction": "wave_direction",
        "swell_height": "swell_height", "swell_wave_period": "swell_wave_period", "swell_wave_direction": "swell_wave_direction",
        "wind_wave_height": "wind_wave_height", "wind_wave_period": "wind_wave_period", "wind_wave_direction": "wind_wave_direction",
    }
