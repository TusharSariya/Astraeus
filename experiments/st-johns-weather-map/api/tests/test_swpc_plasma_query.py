from __future__ import annotations

import json
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import weather_api.swpc_kp_query as kp_query_module
import weather_api.swpc_rtsw_query as rtsw_query_module
from ingest.adapters.swpc import RTSW_WIND_FIELDS
from registry.fields import SOURCE_FIELDS
from weather_api.swpc_plasma_query import (
    PLASMA_FRESHNESS_SECONDS,
    SWPCPlasmaQueryService,
    SWPCPlasmaUnavailable,
)
from weather_api.swpc_plasma_worker import validated


FIXTURE = Path(__file__).parent / "fixtures/space_weather/rtsw_wind_1m.json"
NOW = datetime(2026, 9, 5, 17, 57, 30, tzinfo=UTC)
app_module = importlib.import_module("weather_api.app")


def test_native_schema_is_two_identity_keys_plus_exactly_29_fields():
    rows = json.loads(FIXTURE.read_text())
    declared = {"time_tag", "source", *(field.name for field in RTSW_WIND_FIELDS)}

    assert len(RTSW_WIND_FIELDS) == 29
    assert len(declared) == 31
    assert all(set(row) == declared for row in rows)
    plasma_fields = {
        item["key"]: (item["upstream"], item["storage"])
        for item in SOURCE_FIELDS
        if item["source_id"] == "noaa-swpc-plasma"
    }
    assert plasma_fields == {
        "solar_wind_density": ("rtsw_wind_1m.json proton_density", "available-not-stored"),
        "solar_wind_speed": ("rtsw_wind_1m.json proton_speed", "available-not-stored"),
        "solar_wind_temperature": ("rtsw_wind_1m.json proton_temperature", "available-not-stored"),
    }


def decode(body: bytes, at: datetime | None):
    rows = validated(body)
    if at is None:
        return {"rows": len(rows)}
    candidates = []
    for row in rows:
        stamp = datetime.fromisoformat(row["time_tag"]).replace(tzinfo=UTC)
        if stamp <= at:
            candidates.append((stamp, row["source"], row))
    newest = max(item[0] for item in candidates)
    choices = [(source, row) for stamp, source, row in candidates if stamp == newest]
    active = [item for item in choices if item[1]["active"] is True]
    source, row = sorted(active if len(active) == 1 else choices, key=lambda item: item[0])[0]
    return {"time": newest.isoformat(), "source": source, "row": row, "active_count": len(active)}


def service(*, status: int = 200, delay: float = 0, body: bytes | None = None):
    calls: list[httpx.Request] = []
    payload = FIXTURE.read_bytes() if body is None else body

    def handler(request: httpx.Request):
        if delay:
            import time

            time.sleep(delay)
        calls.append(request)
        return httpx.Response(
            status,
            content=payload,
            headers={"cache-control": "max-age=60"},
            request=request,
        )

    query = SWPCPlasmaQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        utcnow=lambda: NOW,
        bounded_decode=decode,
    )
    return query, calls


def test_selected_native_row_preserves_values_spacecraft_quality_and_transport():
    query, calls = service()

    plasma = query.latest(NOW)

    assert len(calls) == 1
    assert str(calls[0].url) == "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
    assert plasma.proton_density_cm3 == 3.63
    assert plasma.proton_speed_km_s == 339.2
    assert plasma.proton_temperature_k == 86894
    assert plasma.measured_at == datetime(2026, 9, 5, 17, 57, tzinfo=UTC)
    assert plasma.feed_declared_spacecraft == "SOLAR1"
    assert plasma.active is True and plasma.overall_quality == 0
    assert plasma.freshness.status == "fresh"
    assert plasma.acquisition.body_bytes == len(FIXTURE.read_bytes())
    assert plasma.acquisition.request_headers["accept-encoding"] == "identity"
    assert len(plasma.acquisition.body_sha256) == 64


def test_default_bounded_worker_validates_and_selects_representative_document():
    payload = FIXTURE.read_bytes()

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            content=payload,
            headers={"cache-control": "max-age=60"},
            request=request,
        )

    query = SWPCPlasmaQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        utcnow=lambda: NOW,
    )

    try:
        plasma = query.latest(NOW)
    except SWPCPlasmaUnavailable as error:
        if "runtime rejected required kernel allocation limits" in str(error):
            pytest.skip("host kernel rejects RLIMIT_AS; container gate exercises the bounded worker")
        raise

    assert plasma.feed_declared_spacecraft == "SOLAR1"
    assert plasma.proton_density_cm3 == 3.63
    assert plasma.proton_speed_km_s == 339.2
    assert plasma.proton_temperature_k == 86894


def test_transport_completion_is_captured_before_decode_work():
    wall = [NOW]

    def delayed_decode(body: bytes, at: datetime | None):
        if at is None:
            wall[0] += timedelta(minutes=5)
        return decode(body, at)

    query, _calls = service()
    query._utcnow = lambda: wall[0]
    query._decode = delayed_decode

    entry = query.entry()

    assert entry.acquisition.transport_completed_at == NOW
    assert entry.acquisition.expires_at == NOW + timedelta(seconds=60)


def test_fresh_hit_and_concurrent_miss_add_no_provider_requests():
    query, calls = service(delay=0.02)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: query.latest(NOW), range(8)))

    assert len(calls) == 1
    assert {result.acquisition.body_sha256 for result in results} == {results[0].acquisition.body_sha256}
    assert query.latest(NOW).proton_speed_km_s == 339.2
    assert len(calls) == 1


def test_individual_null_never_borrows_from_other_spacecraft_or_minute():
    rows = json.loads(FIXTURE.read_text())
    rows[-1]["proton_speed"] = None
    payload = json.dumps(rows).encode()
    query, _calls = service(body=payload)

    plasma = query.latest(NOW)

    assert plasma.feed_declared_spacecraft == "SOLAR1"
    assert plasma.measured_at == datetime(2026, 9, 5, 17, 57, tzinfo=UTC)
    assert plasma.proton_density_cm3 == 3.63
    assert plasma.proton_speed_km_s is None
    assert plasma.proton_temperature_k == 86894


def test_all_null_newest_row_stays_newest_and_never_falls_back_a_minute():
    rows = json.loads(FIXTURE.read_text())
    for name in ("proton_density", "proton_speed", "proton_temperature"):
        rows[-1][name] = None
    query, _calls = service(body=json.dumps(rows).encode())

    plasma = query.latest(NOW)

    assert plasma.feed_declared_spacecraft == "SOLAR1"
    assert plasma.measured_at == datetime(2026, 9, 5, 17, 57, tzinfo=UTC)
    assert plasma.proton_density_cm3 is None
    assert plasma.proton_speed_km_s is None
    assert plasma.proton_temperature_k is None


@pytest.mark.parametrize("active_count", [0, 2])
def test_ambiguous_active_flag_uses_first_source_label_and_discloses(active_count: int):
    rows = json.loads(FIXTURE.read_text())
    newest = rows[-2:]
    for row in newest:
        row["active"] = active_count == 2
    payload = json.dumps(rows).encode()
    query, _calls = service(body=payload)

    plasma = query.latest(NOW)

    assert plasma.feed_declared_spacecraft == "ACE"
    expected = "multiple spacecraft carried" if active_count == 2 else "no spacecraft carried"
    assert expected in plasma.notices[0]


def test_current_document_refuses_selection_outside_acquisition_context():
    query, _calls = service()

    with pytest.raises(SWPCPlasmaUnavailable, match="acquisition context"):
        query.latest(NOW - timedelta(seconds=PLASMA_FRESHNESS_SECONDS))
    with pytest.raises(SWPCPlasmaUnavailable, match="acquisition context"):
        query.latest(NOW + timedelta(seconds=61))


def test_native_row_at_exact_age_limit_is_unavailable():
    rows = json.loads(FIXTURE.read_text())
    selected = datetime(2026, 9, 5, 18, 12, tzinfo=UTC)
    completed = selected
    query, _calls = service(body=json.dumps(rows).encode())
    query._utcnow = lambda: completed

    with pytest.raises(SWPCPlasmaUnavailable, match="900 s old"):
        query.latest(selected)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows: rows[0].pop("alpha_vz_gsm"), "missing native fields"),
        (lambda rows: rows[0].__setitem__("proton_speed", "339.2"), "not finite numeric or null"),
        (lambda rows: rows[0].__setitem__("active", 1), "not boolean or null"),
        (lambda rows: rows.append(dict(rows[0])), "duplicates native time/source"),
        (
            lambda rows: rows.append({**rows[0], "time_tag": f"{rows[0]['time_tag']}+00:00"}),
            "duplicates native time/source",
        ),
        (lambda rows: rows[0].__setitem__("time_tag", "not-a-time"), "invalid timestamp"),
    ],
)
def test_full_native_shape_and_identity_are_validated(mutation, message):
    rows = json.loads(FIXTURE.read_text())
    mutation(rows)
    query, _calls = service(body=json.dumps(rows).encode())

    with pytest.raises(SWPCPlasmaUnavailable, match=message):
        query.latest(NOW)


def test_unknown_future_native_field_is_retained_in_raw_document_identity():
    rows = json.loads(FIXTURE.read_text())
    rows[0]["future_native_field"] = "verbatim"
    payload = json.dumps(rows, separators=(",", ":")).encode()
    query, _calls = service(body=payload)

    entry = query.entry()

    assert entry.body == payload
    assert entry.backing_bytes == len(payload)


def test_transport_failure_is_backed_off_without_cached_values():
    query, calls = service(status=503)

    with pytest.raises(SWPCPlasmaUnavailable, match="HTTP 503") as first:
        query.latest(NOW)
    with pytest.raises(SWPCPlasmaUnavailable, match="HTTP 503") as second:
        query.latest(NOW)

    assert len(calls) == 1
    assert first.value.detail == second.value.detail
    assert first.value.detail["values_withheld"] is True
    assert first.value.detail["cached_identity"] is None


def test_oversized_declared_body_is_refused_before_decode():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(
            200,
            content=b"[]",
            headers={"content-length": str(9 * 1024 * 1024), "cache-control": "max-age=60"},
            request=request,
        )

    query = SWPCPlasmaQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        utcnow=lambda: NOW,
        bounded_decode=decode,
    )

    with pytest.raises(SWPCPlasmaUnavailable, match="bounded document ceiling"):
        query.latest(NOW)
    assert len(calls) == 1


def test_mocked_cache_reaches_public_api_with_typed_native_provenance(monkeypatch, data_mode):
    query, calls = service()

    class UnavailableKp:
        def series(self, _at):
            raise kp_query_module.SWPCKpUnavailable("Kp fixture intentionally unavailable")

    class UnavailableMagnetic:
        def latest(self, _at):
            raise rtsw_query_module.SWPCRTSWUnavailable("magnetic fixture intentionally unavailable")

    data_mode("live")
    monkeypatch.setattr("weather_api.swpc_plasma_query.swpc_plasma_query_service", lambda: query)
    monkeypatch.setattr(kp_query_module, "swpc_kp_query_service", lambda: UnavailableKp())
    monkeypatch.setattr(rtsw_query_module, "swpc_rtsw_query_service", lambda: UnavailableMagnetic())
    monkeypatch.setattr(
        app_module,
        "live_store",
        lambda: (_ for _ in ()).throw(AssertionError("retained artifact store must not be read")),
    )

    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/space-weather", params={"at": NOW.isoformat()}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "live" and payload["operational"] is False
    plasma = payload["solar_wind_plasma"]
    assert plasma["available"] is True
    assert plasma["source_id"] == "noaa-swpc-plasma"
    assert plasma["proton_density_cm3"] == 3.63
    assert plasma["proton_speed_km_s"] == 339.2
    assert plasma["proton_temperature_k"] == 86894
    assert plasma["measured_at"] == "2026-09-05T17:57:00Z"
    assert plasma["feed_declared_spacecraft"] == "SOLAR1"
    assert plasma["active"] is True and plasma["overall_quality"] == 0
    assert plasma["acquisition"]["transport_completed_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert plasma["acquisition"]["body_sha256"] == query.entry().acquisition.body_sha256
    assert len(calls) == 1


def test_expired_refresh_failure_exposes_receipt_but_withholds_every_public_value(monkeypatch, data_mode):
    payload = FIXTURE.read_bytes()
    monotonic = [0.0]
    wall = [NOW]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, content=payload, headers={"cache-control": "max-age=60"}, request=request)
        return httpx.Response(503, content=b"", request=request)

    query = SWPCPlasmaQueryService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: monotonic[0],
        utcnow=lambda: wall[0],
        bounded_decode=decode,
    )
    expired = query.entry().acquisition
    monotonic[0] = 61
    wall[0] = NOW + timedelta(seconds=61)

    class UnavailableKp:
        def series(self, _at):
            raise kp_query_module.SWPCKpUnavailable("Kp fixture intentionally unavailable")

    class UnavailableMagnetic:
        def latest(self, _at):
            raise rtsw_query_module.SWPCRTSWUnavailable("magnetic fixture intentionally unavailable")

    data_mode("live")
    monkeypatch.setattr("weather_api.swpc_plasma_query.swpc_plasma_query_service", lambda: query)
    monkeypatch.setattr(kp_query_module, "swpc_kp_query_service", lambda: UnavailableKp())
    monkeypatch.setattr(rtsw_query_module, "swpc_rtsw_query_service", lambda: UnavailableMagnetic())

    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/space-weather", params={"at": wall[0].isoformat()}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "unavailable"
    assert body["solar_wind_plasma"]["available"] is False
    assert body["solar_wind_plasma"]["proton_density_cm3"] is None
    assert body["solar_wind_plasma"]["proton_speed_km_s"] is None
    assert body["solar_wind_plasma"]["proton_temperature_k"] is None
    unavailable = body["plasma_demand_unavailable"]
    assert unavailable["values_withheld"] is True
    assert unavailable["cached_acquisition"]["body_sha256"] == expired.body_sha256
    assert unavailable["cached_acquisition"]["expires_at"] == expired.expires_at.isoformat().replace("+00:00", "Z")
    assert len(calls) == 2
