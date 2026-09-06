from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingest.adapters.eccc_datamart import ECCCDataMartAdapter, HRDPS_VARS
from ingest.contract import RunCandidate
from weather_api.hrdps_query import (
    HRDPS_POINT_FIELDS,
    HRDPSQueryEntry,
    HRDPSQueryService,
    HRDPSRequestKey,
)
app_module = importlib.import_module("weather_api.app")


def key(lead: int = 8) -> HRDPSRequestKey:
    return HRDPSRequestKey("https://example/12/", "2026090612", lead,
                           HRDPS_POINT_FIELDS, (("east", -52.4),))


def entry(request: HRDPSRequestKey) -> HRDPSQueryEntry:
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    return HRDPSQueryEntry(request, run, run + timedelta(hours=request.lead), run,
                           "a" * 64, b"zip", {"source_id": "eccc-hrdps"})


def test_cache_key_includes_native_lead_but_coalesces_identical_misses() -> None:
    calls = 0

    def load(request: HRDPSRequestKey) -> HRDPSQueryEntry:
        nonlocal calls
        calls += 1
        return entry(request)

    service = HRDPSQueryService(load)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.query(key()), range(8)))
    assert calls == 1
    assert {item.valid_time for item in results} == {datetime(2026, 9, 6, 20, tzinfo=UTC)}
    service.query(key(9))
    assert calls == 2


def test_cache_expiry_reloads_and_never_returns_wrong_identity() -> None:
    current = 0.0
    calls = 0

    def load(request: HRDPSRequestKey) -> HRDPSQueryEntry:
        nonlocal calls
        calls += 1
        return entry(request)

    service = HRDPSQueryService(load, ttl_seconds=10, clock=lambda: current)
    service.query(key())
    current = 11
    service.query(key())
    assert calls == 2

    bad = HRDPSQueryService(lambda _request: entry(key(9)))
    with pytest.raises(ValueError, match="different request identity"):
        bad.query(key())


def test_fetch_selected_refuses_non_native_and_unavailable_times_before_fetch(tmp_path: Path) -> None:
    adapter = ECCCDataMartAdapter(source_id="eccc-hrdps", model_subpath="model_hrdps/continental/2.5km",
                                  grid_token="RLatLon0.0225", var_map=HRDPS_VARS)
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    candidate = RunCandidate("2026090612", run, [], {"cycle_url": "https://example/12/", "available_hours": ["000"]})
    with pytest.raises(Exception, match="exact native hourly lead"):
        adapter.fetch_selected(candidate, run + timedelta(minutes=30), tmp_path, fields=HRDPS_POINT_FIELDS)
    with pytest.raises(Exception, match="unavailable"):
        adapter.fetch_selected(candidate, run + timedelta(hours=1), tmp_path, fields=HRDPS_POINT_FIELDS)


def test_fetch_selected_narrows_candidate_and_fields(monkeypatch, tmp_path: Path) -> None:
    adapter = ECCCDataMartAdapter(source_id="eccc-hrdps", model_subpath="model_hrdps/continental/2.5km",
                                  grid_token="RLatLon0.0225", var_map=HRDPS_VARS)
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    candidate = RunCandidate("2026090612", run, [], {"cycle_url": "https://example/12/", "available_hours": ["000", "001"]})
    observed = {}

    def fake_fetch(self, narrowed, window, workdir):
        observed.update(fields=tuple(self.var_map), hours=narrowed.detail["available_hours"], now=window.now)
        return object()

    monkeypatch.setattr(ECCCDataMartAdapter, "fetch", fake_fetch)
    result = adapter.fetch_selected(candidate, run + timedelta(hours=1), tmp_path,
                                    fields=("temperature_2m", "wind_u_10m"))
    assert result is not None
    assert observed == {"fields": ("temperature_2m", "wind_u_10m"), "hours": ["001"], "now": run + timedelta(hours=1)}


def test_hrdps_point_demand_bypasses_artifact_store(monkeypatch) -> None:
    class Coordinator:
        @staticmethod
        def point_fields(*_args):
            return [], None, []

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr("weather_api.hrdps_query.hrdps_query_coordinator", lambda: Coordinator())
    monkeypatch.setattr(app_module, "live_store", lambda: pytest.fail("HRDPS demand path opened ArtifactStore"))
    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/point",
        params={"latitude": 47.56, "longitude": -52.71,
                "valid_time": "2026-09-06T14:00:00Z", "product": "HRDPS"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "unavailable"
    assert "demand_query_empty:eccc-hrdps" in body["fields"][0]["provenance"]["quality"]["flags"]
