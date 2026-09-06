from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib
from pathlib import Path

import pytest
import numpy as np
import xarray as xr
from fastapi.testclient import TestClient

from ingest.adapters.eccc_datamart import ECCCDataMartAdapter, HRDPS_VARS, manifest_for
from ingest.contract import RunCandidate
from ingest.grib import write_zarr
from weather_api.hrdps_query import (
    HRDPS_POINT_FIELDS,
    hrdps_profile_fields,
    HRDPSQueryEntry,
    HRDPSQueryCoordinator,
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
        observed.update(fields=tuple(self.var_map), hours=narrowed.detail["available_hours"], now=window.now,
                        receipts=self._capture_transport_receipts)
        return object()

    monkeypatch.setattr(ECCCDataMartAdapter, "fetch", fake_fetch)
    result = adapter.fetch_selected(candidate, run + timedelta(hours=1), tmp_path,
                                    fields=("temperature_2m", "wind_u_10m"))
    assert result is not None
    assert observed == {"fields": ("temperature_2m", "wind_u_10m"), "hours": ["001"],
                        "now": run + timedelta(hours=1), "receipts": True}


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


def test_coordinator_preflights_before_discovery() -> None:
    class Adapter:
        def demand_operation_bounds(self, _field_count):
            raise RuntimeError("unsupported runtime")
        def discover(self, _window):
            pytest.fail("provider discovery happened before platform preflight")

    coordinator = HRDPSQueryCoordinator(adapter=Adapter())
    with pytest.raises(RuntimeError, match="unsupported runtime"):
        coordinator.query(datetime(2026, 9, 6, 14, 22, tzinfo=UTC))


def test_failure_is_coalesced_and_backed_off() -> None:
    calls = 0
    current = 0.0

    def fail(_request):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    service = HRDPSQueryService(fail, clock=lambda: current)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(service.query, key()) for _ in range(8)]
        for future in futures:
            with pytest.raises(RuntimeError, match="provider unavailable"):
                future.result()
    assert calls == 1
    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.query(key())
    assert calls == 1


def test_ordinary_selection_resolves_latest_native_hour() -> None:
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    candidate = RunCandidate("2026090612", run, [], {
        "cycle_url": "https://example/12/", "available_hours": ["000", "001", "002"]
    })

    class Adapter:
        bounds = {"south": 46.0, "north": 48.0, "west": -54.0, "east": -51.0}
        def demand_operation_bounds(self, _field_count): return object()
        def discover(self, _window): return [candidate]

    class Coordinator(HRDPSQueryCoordinator):
        def _load(self, request): return entry(request)

    result = Coordinator(adapter=Adapter()).query(datetime(2026, 9, 6, 14, 37, tzinfo=UTC))
    assert result.valid_time == datetime(2026, 9, 6, 14, tzinfo=UTC)
    assert result.key.lead == 2
    profile_fields = hrdps_profile_fields([1000, 850, 700, 500])
    profile = Coordinator(adapter=Adapter()).query(
        datetime(2026, 9, 6, 14, 37, tzinfo=UTC), fields=profile_fields
    )
    assert profile.key.fields == profile_fields
    assert len(profile_fields) == 19
    assert set(HRDPS_POINT_FIELDS) != set(profile_fields)


def test_real_zarr_sampler_serves_point_and_profile(tmp_path: Path, monkeypatch) -> None:
    valid = datetime(2026, 9, 6, 14, tzinfo=UTC)
    dataset = xr.Dataset(
        {
            "temperature_2m": (("valid_time", "latitude", "longitude"), [[[12.5]]], {"units": "degC", "level_type": "heightAboveGround", "level_value": 2}),
            "temperature_850hPa": (("valid_time", "latitude", "longitude"), [[[4.25]]], {"units": "degC", "level_type": "isobaricInhPa", "level_value": 850}),
        },
        coords={"valid_time": [np.datetime64(valid.replace(tzinfo=None), "ns")], "latitude": [47.56], "longitude": [-52.71]},
    )
    path = write_zarr(dataset, tmp_path / "selected.zarr.zip")
    fields = {"temperature_2m": HRDPS_VARS["temperature_2m"], "temperature_850hPa": HRDPS_VARS["temperature_850hPa"]}
    provenance = {
        "source_id": "eccc-hrdps", "producer": "Environment and Climate Change Canada",
        "product": "HRDPS", "native_resolution": "RLatLon0.0225", "native_crs": "EPSG:4326",
        "adapter_version": "hrdps-demand-v1", "run_time": datetime(2026, 9, 6, 12, tzinfo=UTC).isoformat(),
        "quality": {"status": "passed", "flags": []}, "coverage": {"status": "complete", "fraction": 1.0},
        **manifest_for("eccc-hrdps", fields).as_manifest_block(),
    }
    request = key(2)
    selected = HRDPSQueryEntry(request, datetime(2026, 9, 6, 12, tzinfo=UTC), valid, valid,
                               "b" * 64, path.read_bytes(), provenance)
    coordinator = HRDPSQueryCoordinator(adapter=object())
    monkeypatch.setattr(coordinator, "query", lambda *_args, **_kwargs: selected)
    point, _consensus, _sources = coordinator.point_fields(47.56, -52.71, valid)
    assert [(item.field, item.value) for item in point] == [("temperature", 12.5)]
    profile, native = coordinator.profile_levels(47.56, -52.71, valid, [850])
    assert native == valid
    level = next(item for item in profile if item.pressure_hpa == 850)
    assert [(item.field, item.value) for item in level.fields if item.value is not None] == [("temperature_850hPa", 4.25)]
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr("weather_api.hrdps_query.hrdps_query_coordinator", lambda: coordinator)
    client = TestClient(app_module.app)
    point_response = client.get(f"{app_module.PREFIX}/point", params={
        "latitude": 47.56, "longitude": -52.71, "valid_time": valid.isoformat(), "product": "HRDPS"
    })
    assert point_response.status_code == 200
    assert point_response.json()["fields"][0]["value"] == 12.5
    profile_response = client.get(f"{app_module.PREFIX}/profile", params={
        "latitude": 47.56, "longitude": -52.71, "valid_time": valid.isoformat(), "product": "HRDPS"
    })
    assert profile_response.status_code == 200
    assert profile_response.json()["valid_time"] == valid.isoformat().replace("+00:00", "Z")
