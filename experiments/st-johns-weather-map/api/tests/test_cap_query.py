from __future__ import annotations

import json
import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from weather_api.cap_query import CAPQueryService, CapQueryUnavailable
from weather_api.app import PREFIX, app


NOW = datetime(2026, 9, 6, 21, 0, tzinfo=UTC)


class Clock:
    value = 100.0

    def __call__(self) -> float:
        return self.value


def feature(identifier: str, *, sent: str, effective: str, expires: str) -> dict:
    return {
        "type": "Feature",
        "id": identifier,
        "geometry": {"type": "Polygon", "coordinates": [[[-53, 47], [-52, 47], [-52, 48], [-53, 47]]]},
        "properties": {
            "identifier": identifier,
            "senderName": "Environment and Climate Change Canada",
            "headline": f"Alert {identifier}",
            "description": f"Verbatim description {identifier}",
            "sent": sent,
            "effective": effective,
            "expires": expires,
            "severity": "Moderate",
            "urgency": "Expected",
            "certainty": "Likely",
        },
    }


class Client:
    def __init__(self, payloads: list[object], *, delay: float = 0) -> None:
        self.payloads = payloads
        self.delay = delay
        self.calls = 0
        self.lock = threading.Lock()

    def get_bytes_with_receipt(self, url: str, *, max_bytes: int):
        with self.lock:
            index = self.calls
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        payload = self.payloads[index]
        if isinstance(payload, BaseException):
            raise payload
        body = json.dumps(payload).encode()
        assert len(body) <= max_bytes
        return body, {
            "url": url,
            "request_headers": {"accept-encoding": "identity", "user-agent": "test"},
            "response_headers": {"cache-control": "max-age=60", "etag": '"cap-one"'},
            "completed_at": NOW.isoformat(),
            "byte_size": len(body),
            "sha256": __import__("hashlib").sha256(body).hexdigest(),
        }


BOXES = (
    {"south": 46.5, "west": -54.0, "north": 47.5, "east": -53.0},
    {"south": 46.5, "west": -53.0, "north": 47.5, "east": -52.0},
)


def collection(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def test_every_box_success_preserves_native_features_and_filters_exact_validity():
    current = feature("current", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:30:00Z", expires="2026-09-06T22:00:00Z")
    future = feature("future", sent="2026-09-06T21:30:00Z", effective="2026-09-06T21:30:00Z", expires="2026-09-06T23:00:00Z")
    expired = feature("expired", sent="2026-09-06T18:00:00Z", effective="2026-09-06T18:00:00Z", expires="2026-09-06T20:59:59Z")
    client = Client([collection(current, future), collection(current, expired)])
    response = CAPQueryService(client=client, boxes=BOXES, clock=Clock()).query(NOW)
    assert client.calls == 2
    assert response["alerts_in_force"] == 1
    assert response["all_boxes_succeeded"] is True
    assert response["features"] == [current]
    assert response["features"][0]["properties"]["description"] == "Verbatim description current"
    assert set(response["excluded_features"]) == {"future", "expired"}
    assert len(response["acquisition"]) == 2


def test_successful_empty_every_box_is_zero_but_partial_failure_never_all_clear():
    empty = collection()
    response = CAPQueryService(client=Client([empty, empty]), boxes=BOXES, clock=Clock()).query(NOW)
    assert response["alerts_in_force"] == 0
    assert response["empty_is_an_answer"] is True

    service = CAPQueryService(client=Client([empty, RuntimeError("second box failed")]), boxes=BOXES, clock=Clock())
    with pytest.raises(CapQueryUnavailable, match="declared-box query failed") as caught:
        service.query(NOW)
    assert caught.value.partial_features == ()


def test_partial_failure_preserves_valid_sibling_warning_in_error_context():
    warning = feature("warning", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    service = CAPQueryService(client=Client([collection(warning), RuntimeError("failed")]), boxes=BOXES, clock=Clock())
    with pytest.raises(CapQueryUnavailable) as caught:
        service.query(NOW)
    assert caught.value.partial_features == (warning,)


def test_identical_concurrent_miss_coalesces_and_fresh_hit_adds_no_requests():
    warning = feature("warning", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    client = Client([collection(warning), collection()], delay=0.03)
    service = CAPQueryService(client=client, boxes=BOXES, clock=Clock())
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: service.query(NOW), range(8)))
    assert client.calls == 2
    assert {item["content_digest"] for item in responses} == {responses[0]["content_digest"]}
    assert service.query(NOW)["content_digest"] == responses[0]["content_digest"]
    assert client.calls == 2


def test_historical_selection_and_invalid_native_validity_fail_closed():
    malformed = feature("bad", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="missing")
    service = CAPQueryService(client=Client([collection(malformed), collection()]), boxes=BOXES, clock=Clock())
    with pytest.raises(CapQueryUnavailable, match="invalid native expires"):
        service.query(NOW)
    valid = feature("valid", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    service = CAPQueryService(client=Client([collection(valid), collection()]), boxes=BOXES, clock=Clock())
    with pytest.raises(CapQueryUnavailable, match="outside the mutable current-alert acquisition context"):
        service.query(datetime(2026, 9, 5, tzinfo=UTC))


@pytest.mark.parametrize("payload", [{}, {"type": "FeatureCollection", "features": "bad"}])
def test_malformed_collection_is_unavailable(payload):
    with pytest.raises(CapQueryUnavailable, match="FeatureCollection|feature list"):
        CAPQueryService(client=Client([payload, collection()]), boxes=BOXES, clock=Clock()).query(NOW)


def test_conflicting_duplicate_identity_and_bad_receipt_fail_closed():
    first = feature("same", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    second = {**first, "properties": {**first["properties"], "headline": "Different warning"}}
    with pytest.raises(CapQueryUnavailable, match="conflicts across declared boxes"):
        CAPQueryService(client=Client([collection(first), collection(second)]), boxes=BOXES, clock=Clock()).query(NOW)

    client = Client([collection(first), collection()])
    original = client.get_bytes_with_receipt
    def corrupt(url, *, max_bytes):
        body, receipt = original(url, max_bytes=max_bytes)
        receipt["sha256"] = "0" * 64
        return body, receipt
    client.get_bytes_with_receipt = corrupt
    with pytest.raises(CapQueryUnavailable, match="receipt does not match"):
        CAPQueryService(client=client, boxes=BOXES, clock=Clock()).query(NOW)


def test_failed_miss_has_finite_negative_backoff():
    clock = Clock()
    client = Client([RuntimeError("offline"), collection(), collection()])
    service = CAPQueryService(client=client, boxes=BOXES, clock=clock)
    with pytest.raises(CapQueryUnavailable, match="offline"):
        service.query(NOW)
    with pytest.raises(CapQueryUnavailable, match="offline"):
        service.query(NOW)
    assert client.calls == 1
    clock.value += 31
    assert service.query(NOW)["alerts_in_force"] == 0
    assert client.calls == 3


def test_geometry_boxes_and_completion_require_exact_bounded_shapes():
    valid = feature("valid", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    open_ring = {**valid, "geometry": {"type": "Polygon", "coordinates": [[[-53, 47], [-52, 47], [-52, 48], [-53, 48]]]}}
    with pytest.raises(CapQueryUnavailable, match="ring is not closed"):
        CAPQueryService(client=Client([collection(open_ring), collection()]), boxes=BOXES, clock=Clock()).query(NOW)
    with pytest.raises(ValueError, match="ordered"):
        CAPQueryService(client=Client([]), boxes=({"south": 48, "west": -54, "north": 47, "east": -52},), clock=Clock())

    client = Client([collection(valid), collection()])
    original = client.get_bytes_with_receipt
    def naive(url, *, max_bytes):
        body, receipt = original(url, max_bytes=max_bytes)
        receipt["completed_at"] = "2026-09-06T21:00:00"
        return body, receipt
    client.get_bytes_with_receipt = naive
    with pytest.raises(CapQueryUnavailable, match="final-byte completion"):
        CAPQueryService(client=client, boxes=BOXES, clock=Clock()).query(NOW)


def test_demand_features_route_bypasses_artifact_store_and_preserves_partial_warning(monkeypatch):
    warning = feature("warning", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    error = CapQueryUnavailable("east Avalon box failed", partial_features=[warning])
    class Service:
        def query(self, _moment):
            raise error
        def partial_response(self, moment, caught):
            return CAPQueryService.partial_response(self, moment, caught)
    import weather_api.cap_query as cap_module
    app_module = sys.modules["weather_api.app"]
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(cap_module, "cap_query_service", lambda: Service())
    monkeypatch.setattr(app_module, "live_store", lambda: (_ for _ in ()).throw(AssertionError("store must not be read")))
    response = TestClient(app).get(f"{PREFIX}/layers/eccc-cap-alerts-current/features", params={"valid_time": NOW.isoformat()})
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "unavailable"
    assert payload["alerts_in_force"] is None and payload["all_boxes_succeeded"] is False
    assert payload["features"] == [warning]
    assert "no aggregate all-clear" in payload["notices"][1]


def test_cap_layer_listing_is_cache_only(monkeypatch):
    warning = feature("warning", sent="2026-09-06T20:00:00Z", effective="2026-09-06T20:00:00Z", expires="2026-09-06T22:00:00Z")
    service = CAPQueryService(client=Client([collection(warning), collection()]), boxes=BOXES, clock=Clock())
    service.query(NOW)
    calls = service._client.calls
    def must_not_query(_moment):
        raise AssertionError("layer listing must not fetch")
    service.query = must_not_query
    import weather_api.cap_query as cap_module
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(cap_module, "cap_query_service", lambda: service)
    response = TestClient(app).get(f"{PREFIX}/layers", params={"product": "CAP"})
    assert response.status_code == 200
    payload = response.json()
    assert service._client.calls == calls
    assert payload["layers"][0]["id"] == "eccc-cap-alerts-current"
    assert payload["layers"][0]["evidence_basis"] == "demand_query"
    assert "no provider request" in payload["notices"][0]
