"""Safe source read outcomes stay separate from catalogue and actual coverage."""
from collections import OrderedDict
from datetime import UTC, datetime
from types import SimpleNamespace
import importlib

from fastapi.testclient import TestClient
import httpx
import pytest

from weather_api.native_runs import RunUnavailable
from weather_api.source_delivery import AQHISource, source_capabilities, source_configuration

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


@pytest.fixture
def status_clock(monkeypatch):
    import weather_api.source_status as module
    elapsed = [0.0]
    monkeypatch.setattr(module, "_latest", OrderedDict())
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    return elapsed


@pytest.mark.parametrize("kind,expected", [("denied", "access_denied"),
    ("wrapped_denied", "access_denied"), ("failed", "acquisition_failed"), ("run", "product_unavailable")])
def test_failed_read_reports_only_safe_state_through_status_api(status_clock, kind, expected):
    def fail(*args):
        if kind == "run":
            raise RunUnavailable("untrusted-run-message")
        if kind == "failed":
            raise ValueError("private-provider-message")
        denied = httpx.HTTPStatusError("private-provider-message", request=httpx.Request("GET", "https://fixture.invalid/?token=private"),
            response=httpx.Response(403))
        if kind == "wrapped_denied":
            raise ValueError("private-wrapper-message") from denied
        raise denied
    reader = AQHISource(lambda: SimpleNamespace(point_field=fail))
    declared = source_capabilities(reader.source_id)
    with pytest.raises(Exception):
        reader.read_point(47.5, -52.7, NOW)
    app = importlib.import_module("weather_api.app")
    response = TestClient(app.app).get(f"{app.PREFIX}/sources/status")
    assert response.status_code == 200
    status = next(item for item in response.json()["statuses"] if item["source_id"] == reader.source_id)
    assert status["configuration"]["state"] == expected
    assert status["configuration"]["checked_at"]
    assert "private" not in str(status["configuration"]) and "untrusted" not in str(status["configuration"])
    assert source_capabilities(reader.source_id) == declared


def test_read_status_has_fixed_expiry_and_does_not_retry_acquisition(status_clock):
    calls = []
    def fail(*args):
        calls.append(1)
        raise ValueError("fixed failure")
    reader = AQHISource(lambda: SimpleNamespace(point_field=fail))
    with pytest.raises(ValueError):
        reader.read_point(47.5, -52.7, NOW)
    status_clock[0] = 299
    assert source_configuration(reader.source_id).state == "acquisition_failed"
    status_clock[0] = 300
    disposition = source_configuration(reader.source_id)
    assert disposition.state == "ready" and disposition.checked_at is None
    assert "software" in disposition.reason and calls == [1]


def test_success_replaces_failure_without_claiming_coverage(status_clock):
    from weather_api.fixtures import point_fields
    def fail(*args):
        raise ValueError("fixed failure")
    service = SimpleNamespace(point_field=fail)
    reader = AQHISource(lambda: service)
    with pytest.raises(ValueError):
        reader.read_point(47.5, -52.7, NOW)
    service.point_field = lambda *args: point_fields(NOW)[0][0]
    reader.read_point(47.5, -52.7, NOW)
    disposition = source_configuration(reader.source_id)
    assert disposition.state == "ready" and "coverage are reported separately" in disposition.reason


def test_actual_aqhi_http_denial_retains_typed_cause(status_clock):
    from weather_api.aqhi_query import AQHIQueryService, AqhiQueryUnavailable
    service = AQHIQueryService(client=httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(403, text="private-provider-message"))))
    reader = AQHISource(lambda: service)
    with pytest.raises(AqhiQueryUnavailable):
        reader.read_point(47.5, -52.7, NOW)
    state = source_configuration(reader.source_id)
    assert state.state == "access_denied" and "private" not in state.reason


@pytest.mark.parametrize("product", ["HRDPS", "RDPS", "GDPS", "GFS"])
def test_named_forecast_point_failure_updates_source_status(status_clock, monkeypatch, product):
    name = product.lower()
    source_id = f"{'noaa' if product == 'GFS' else 'eccc'}-{name}"
    module = importlib.import_module(f"weather_api.{name}_query")
    def fail(*args):
        raise httpx.HTTPStatusError("private", request=httpx.Request("GET", "https://fixture.invalid/"),
                                    response=httpx.Response(403))
    monkeypatch.setattr(module, f"{name}_query_coordinator", lambda: SimpleNamespace(point_fields=fail))
    app = importlib.import_module("weather_api.app")
    response = app._live_point(47.5, -52.7, NOW, product=product)
    assert all(field.value is None for field in response.fields)
    assert source_configuration(source_id).state == "access_denied"
