"""Selected-model AQHI composition through the frozen point-reader seam."""
from datetime import UTC, datetime, timedelta
import importlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from weather_api.aqhi_query import AQHIQueryService, AQHIStationObservation, AqhiQueryUnavailable
from weather_api.fixtures import point_fields
from weather_api.models import AQHIDemandUnavailable, DataMode, PointResponse, Selection

NOW = datetime(2026, 9, 7, 12, 30, tzinfo=UTC)


@pytest.fixture
def aqhi(monkeypatch):
    import weather_api.aqhi_query as module
    requests = []
    station = AQHIStationObservation("ABEFS", "St John's", NOW - timedelta(minutes=30),
        47.5658, -52.7252, 2.7, "0", "native-report-id")
    service = AQHIQueryService(client=httpx.Client(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, content=b"{}"))),
        clock=lambda: 100.0, utcnow=lambda: NOW, decode=lambda _: (station,))
    monkeypatch.setattr(module, "aqhi_query_service", lambda: service)
    return service, requests


@pytest.mark.parametrize("product", ["HRDPS", "RDPS", "GDPS", "GFS", "GEFS", "IFS", "ICON", "GFS Wave"])
def test_named_model_keeps_selection_and_native_aqhi_identity(monkeypatch, data_mode, aqhi, product):
    app = importlib.import_module("weather_api.app")
    forecast = point_fields(NOW)[0][0]
    response = PointResponse(data_mode=DataMode.LIVE, latitude=47.56, longitude=-52.72,
        valid_time=NOW, fields=[forecast], selection=Selection(mode="fallback",
            selected_source_id=forecast.provenance.source_id, selected_product_id=product.lower(),
            badge=f"{product} selected", reason="Fixed selected-model evidence"))
    monkeypatch.setattr(app, "_live_point", lambda *args, **kwargs: response)
    data_mode("live")
    client = TestClient(app.app)
    for _ in range(2):
        result = client.get(f"{app.PREFIX}/point", params={"latitude": 47.56,
            "longitude": -52.72, "valid_time": NOW.isoformat(), "product": product})
        assert result.status_code == 200
        body = result.json()
        assert body["selection"] == response.selection.model_dump(mode="json")
        assert body["fields"][0] == forecast.model_dump(mode="json")
        observation = body["fields"][1]
        assert observation["value"] == 2.7 and observation["key"] == "air_quality_health_index"
        p = observation["provenance"]
        assert p["source_id"] == "eccc-aqhi" and p["run_time"] is None
        assert p["normalized_units"] == "index"
        assert p["native_report"]["station_id"] == "ABEFS"
        assert p["native_report"]["native_metadata"]["provider_quality"] == "0"
        assert p["quality"]["status"] == "unknown"
        assert p["native_report"]["observation_time"] == "2026-09-07T12:00:00Z"
        assert body["observation_unavailable"] == []
    assert len(aqhi[1]) == 1
    assert len(response.fields) == 1  # Composition does not mutate retained responses.


def test_failed_aqhi_preserves_selected_model_and_safe_typed_outcome(monkeypatch):
    from weather_api.observation_companions import with_aqhi_observation
    import weather_api.aqhi_query as module
    response = PointResponse(data_mode=DataMode.LIVE, latitude=47.56, longitude=-52.72,
        valid_time=NOW, fields=point_fields(NOW)[0], selection=Selection(mode="fallback",
            selected_source_id="noaa-gfs", selected_product_id="gfs", badge="GFS", reason="Selected"))
    outcome = AQHIDemandUnavailable(reason="refresh_failed", error_type="HTTPStatusError")
    def fail(*args, **kwargs):
        raise AqhiQueryUnavailable("private-provider-exception", outcome=outcome)
    monkeypatch.setattr(module, "aqhi_query_service", lambda: SimpleNamespace(point_field=fail))
    result = with_aqhi_observation(response)
    assert result.fields == response.fields and result.selection == response.selection
    assert result.observation_unavailable == [outcome]
    assert "private-provider-exception" not in result.model_dump_json()


@pytest.mark.parametrize("change", ["other_source", "forecast_run", "future", "old", "pm25"])
def test_composition_rejects_noncompanion_identity(monkeypatch, aqhi, change):
    from weather_api.observation_companions import with_aqhi_observation
    import weather_api.aqhi_query as module
    field = aqhi[0].point_field(47.56, -52.72, NOW)
    if change == "other_source":
        field.provenance.source_id = "eccc-raqdps"
    elif change == "forecast_run":
        field.provenance.run_time = NOW
    elif change in ("future", "old"):
        stamp = NOW + timedelta(minutes=1) if change == "future" else NOW - timedelta(hours=1)
        field.provenance.valid_time = stamp
        field.provenance.native_report.observation_time = stamp
    else:
        field.key = "pm2_5_concentration"
    monkeypatch.setattr(module, "aqhi_query_service", lambda: SimpleNamespace(point_field=lambda *args: field))
    response = PointResponse(data_mode=DataMode.LIVE, latitude=47.56, longitude=-52.72,
        valid_time=NOW, fields=[], selection=Selection(mode="evidence_only", selected_source_id=None,
            selected_product_id=None, badge="GFS unavailable", reason="Fixed failure"))
    result = with_aqhi_observation(response)
    assert not result.fields and result.selection == response.selection
    assert result.observation_unavailable[0].values_withheld
