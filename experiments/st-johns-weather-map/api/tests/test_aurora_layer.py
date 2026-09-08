"""OVATION demand-raster rendering preserves the native current grid."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sys

import numpy
from fastapi.testclient import TestClient

from weather_api import aurora, ovation_query
import weather_api.app  # noqa: F401
from weather_api.app import PREFIX, app

api_module = sys.modules["weather_api.app"]
from weather_api.models import KpAcquisition
from weather_api.ovation_query import OvationEntry, OvationFrameUnavailable, OvationUnavailable
from tests.test_rendered_grids import GridStore, decode_png, grid_dataset, use_store

client = TestClient(app)
LATS = [46.0, 47.0, 48.0, 49.0]
LONS = [-54.0, -53.0, -52.0, -51.0]
CELL_BOUNDS = {"south": 45.5, "west": -54.5, "north": 49.5, "east": -50.5}
FORECAST = datetime(2026, 9, 7, 1, 40, tzinfo=UTC)
OBSERVATION = FORECAST - timedelta(minutes=40)
PROBS = numpy.array([
    [0.0, 1.0, 1.9, 2.0], [5.0, 10.0, 20.0, 30.0],
    [50.0, 60.0, 70.0, numpy.nan], [90.0, 95.0, 99.0, 100.0],
])


def demand_entry() -> OvationEntry:
    cells = tuple((lat, lon, float(PROBS[row, col])) for row, lat in enumerate(LATS)
                  for col, lon in enumerate(LONS) if numpy.isfinite(PROBS[row, col]))
    acquisition = KpAcquisition(
        provider_url=ovation_query.OVATION_URL, effective_url=ovation_query.OVATION_URL,
        request_headers={"accept": "application/json"}, response_headers={"cache-control": "max-age=60"},
        transport_completed_at=FORECAST, body_bytes=777, body_sha256="a" * 64,
        expires_at=FORECAST + timedelta(minutes=1),
    )
    return OvationEntry(OBSERVATION, FORECAST, cells, acquisition, float("inf"))


class DemandService:
    def __init__(self, entry: OvationEntry | None = None, error: Exception | None = None) -> None:
        self.entry, self.error, self.calls = entry, error, []

    def entry_for(self, selected: datetime) -> OvationEntry:
        self.calls.append(selected)
        if self.error:
            raise self.error
        assert self.entry is not None
        if not self.entry.supports(selected):
            raise OvationFrameUnavailable("selected time is outside the native OVATION Forecast Time tolerance")
        return self.entry


def use_demand(monkeypatch, data_mode, service: DemandService) -> None:
    # The layer index remains local. The provider call is made only by raster.
    use_store(monkeypatch, data_mode, GridStore(grid_dataset()))
    monkeypatch.setattr(api_module, "now", lambda: FORECAST)
    monkeypatch.setattr(ovation_query, "ovation_query_service", lambda: service)


def raster(params: dict | None = None):
    query = {"valid_time": FORECAST.isoformat(), "width": 8, "height": 8, **CELL_BOUNDS}
    query.update(params or {})
    return client.get(f"{PREFIX}/layers/{aurora.LAYER_ID}/raster", params=query)


def test_demand_raster_preserves_zero_missing_and_nearest_native_cells(monkeypatch, data_mode):
    service = DemandService(demand_entry())
    use_demand(monkeypatch, data_mode, service)
    response = raster()
    assert response.status_code == 200
    pixels = decode_png(response.content)

    def cell(row, col):
        return pixels[(3 - row) * 2, col * 2]

    for col in range(3):
        assert tuple(cell(0, col)) == (0, 0, 0, 0)
    assert tuple(cell(0, 3)) == (*aurora.GREEN_RGB, aurora.ALPHA_MIN)
    assert tuple(cell(3, 3)) == (*aurora.RED_RGB, aurora.ALPHA_MAX)
    assert tuple(cell(2, 3)) == (0, 0, 0, 0)
    for row in range(0, 8, 2):
        for col in range(0, 8, 2):
            block = pixels[row:row + 2, col:col + 2].reshape(4, 4)
            assert (block == block[0]).all()


def test_demand_raster_receipt_and_model_headers_are_truthful(monkeypatch, data_mode):
    service = DemandService(demand_entry())
    use_demand(monkeypatch, data_mode, service)
    headers = raster().headers
    assert headers["X-Weather-Evidence-Basis"] == "demand_query"
    assert headers["X-Weather-Valid-Time"] == FORECAST.isoformat()
    assert headers["X-Weather-Reference-Time"] == "none"
    assert headers["X-Weather-Observation-Time"] == OBSERVATION.isoformat()
    assert headers["X-Weather-Retrieval-Time"] == FORECAST.isoformat()
    assert headers["X-Weather-Content-Digest"] == "a" * 64
    receipt = json.loads(headers["X-Weather-Acquisition"])
    assert receipt == {
        "provider_url": ovation_query.OVATION_URL, "effective_url": ovation_query.OVATION_URL,
        "request_headers": {"accept": "application/json"}, "response_headers": {"cache-control": "max-age=60"},
        "transport_completed_at": FORECAST.isoformat(), "body_bytes": 777, "body_sha256": "a" * 64,
        "expires_at": (FORECAST + timedelta(minutes=1)).isoformat(),
    }
    assert headers["X-Weather-Operational"] == "false"
    assert "Forecast Time" in headers["X-Weather-Time-Semantics"]
    assert "OVATION" in headers["X-Weather-Render-Semantics"]


def test_layer_listing_is_requestable_but_makes_no_provider_request(monkeypatch, data_mode):
    service = DemandService(demand_entry())
    use_demand(monkeypatch, data_mode, service)
    layers = client.get(f"{PREFIX}/layers").json()["layers"]
    entry = {layer["id"]: layer for layer in layers}[aurora.LAYER_ID]
    assert service.calls == []
    assert entry["evidence_basis"] == "demand_query"
    assert entry["evidence_class"] == "retrieved"
    assert entry["family"] == "space_weather"
    assert entry["field_key"] == "aurora_probability"
    assert entry["times"] == []
    assert entry["staleness_tolerance_seconds"] == 600
    assert "selected-time query" in entry["semantics"]


def test_selection_beyond_existing_native_interval_is_422(monkeypatch, data_mode):
    service = DemandService(demand_entry())
    use_demand(monkeypatch, data_mode, service)
    response = raster({"valid_time": (FORECAST + timedelta(seconds=601)).isoformat()})
    assert response.status_code == 422
    assert "Forecast Time tolerance" in response.json()["detail"]


def test_expired_replacement_failure_withholds_values_but_discloses_receipt(monkeypatch, data_mode):
    cached = demand_entry().acquisition
    service = DemandService(error=OvationUnavailable("SWPC OVATION transport failed: ConnectError", cached=cached))
    use_demand(monkeypatch, data_mode, service)
    response = raster()
    assert response.status_code == 502
    assert response.json()["detail"] == {
        "reason": "SWPC OVATION transport failed: ConnectError", "cached_identity": "a" * 64,
        "cached_expires_at": cached.expires_at.isoformat(), "values_withheld": True,
    }
    assert response.headers["X-Weather-Values-Withheld"] == "true"
    assert response.headers["X-Weather-Cached-Content-Digest"] == "a" * 64
    assert response.headers["X-Weather-Cached-Expiry"] == cached.expires_at.isoformat()


def test_legend_keeps_model_threshold_and_guidance_disclosure():
    response = client.get(f"{PREFIX}/layers/{aurora.LAYER_ID}/legend")
    assert response.status_code == 200
    caption = response.headers["X-Weather-Legend-Semantics"]
    assert "OVATION" in caption and "30-40" in caption and "2 percent" in caption and "Kp 4-5" in caption


class NoArtifactsStore:
    def current(self):
        return []

    def source_activity(self):
        return {}


class FailingStore:
    def current(self):
        raise RuntimeError("legacy store failed")


class CoverageFailStore:
    def current(self):
        return [object()]

    def published_layer_times(self):
        raise RuntimeError("legacy coverage failed")


def test_demand_layer_listing_survives_absent_failing_or_empty_legacy_store(monkeypatch, data_mode):
    data_mode("live")
    monkeypatch.setattr(api_module, "_proxied_forecast_layers", lambda: ([], []))
    for store in (None, FailingStore(), NoArtifactsStore(), CoverageFailStore()):
        monkeypatch.setattr(api_module, "live_store", lambda store=store: store)
        response = client.get(f"{PREFIX}/layers")
        assert response.status_code == 200
        assert response.json()["data_mode"] == "live"
        assert aurora.LAYER_ID in {row["id"] for row in response.json()["layers"]}


def test_ovation_product_filter_is_requestable_without_the_legacy_store(monkeypatch, data_mode):
    data_mode("live")
    monkeypatch.setattr(api_module, "live_store", lambda: None)
    response = client.get(f"{PREFIX}/layers", params={"product": "OVATION"})
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["layers"]] == [aurora.LAYER_ID]
    assert response.json()["layers"][0]["times"] == []
