from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib
from pathlib import Path

import pytest
import numpy as np
import xarray as xr
from fastapi.testclient import TestClient

from ingest.adapters.eccc_datamart import ECCCDataMartAdapter, RDPS_DEMAND_VARS, manifest_for
from ingest.contract import RunCandidate
from ingest.grib import write_zarr
from weather_api.rdps_query import (
    RDPS_POINT_FIELDS,
    rdps_profile_fields,
    RDPSQueryEntry,
    RDPSQueryCoordinator,
    RDPSQueryService,
    RDPSRequestKey,
)
app_module = importlib.import_module("weather_api.app")


def key(lead: int = 8) -> RDPSRequestKey:
    return RDPSRequestKey("https://example/12/", "2026090612", lead,
                           RDPS_POINT_FIELDS, (("east", -52.4),))


def entry(request: RDPSRequestKey) -> RDPSQueryEntry:
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    return RDPSQueryEntry(request, run, run + timedelta(hours=request.lead), run,
                           "a" * 64, b"zip", {"source_id": "eccc-rdps"})


def test_cache_key_includes_native_lead_but_coalesces_identical_misses() -> None:
    calls = 0

    def load(request: RDPSRequestKey) -> RDPSQueryEntry:
        nonlocal calls
        calls += 1
        return entry(request)

    service = RDPSQueryService(load)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.query(key()), range(8)))
    assert calls == 1
    assert {item.valid_time for item in results} == {datetime(2026, 9, 6, 20, tzinfo=UTC)}
    service.query(key(9))
    assert calls == 2


def test_cache_expiry_reloads_and_never_returns_wrong_identity() -> None:
    current = 0.0
    calls = 0

    def load(request: RDPSRequestKey) -> RDPSQueryEntry:
        nonlocal calls
        calls += 1
        return entry(request)

    service = RDPSQueryService(load, ttl_seconds=10, clock=lambda: current)
    service.query(key())
    current = 11
    service.query(key())
    assert calls == 2

    bad = RDPSQueryService(lambda _request: entry(key(9)))
    with pytest.raises(ValueError, match="different request identity"):
        bad.query(key())


def test_fetch_selected_refuses_non_native_and_unavailable_times_before_fetch(tmp_path: Path) -> None:
    adapter = ECCCDataMartAdapter(source_id="eccc-rdps", model_subpath="model_rdps/continental/2.5km",
                                  grid_token="RLatLon0.0225", var_map=RDPS_DEMAND_VARS)
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    candidate = RunCandidate("2026090612", run, [], {"cycle_url": "https://example/12/", "available_hours": ["000"]})
    with pytest.raises(Exception, match="exact native hourly lead"):
        adapter.fetch_selected(candidate, run + timedelta(minutes=30), tmp_path, fields=RDPS_POINT_FIELDS)
    with pytest.raises(Exception, match="unavailable"):
        adapter.fetch_selected(candidate, run + timedelta(hours=1), tmp_path, fields=RDPS_POINT_FIELDS)


def test_fetch_selected_narrows_candidate_and_fields(monkeypatch, tmp_path: Path) -> None:
    adapter = ECCCDataMartAdapter(source_id="eccc-rdps", model_subpath="model_rdps/continental/2.5km",
                                  grid_token="RLatLon0.0225", var_map=RDPS_DEMAND_VARS)
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


def test_rdps_point_demand_bypasses_artifact_store(monkeypatch) -> None:
    class Coordinator:
        @staticmethod
        def point_fields(*_args):
            return [], None, []

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr("weather_api.rdps_query.rdps_query_coordinator", lambda: Coordinator())
    monkeypatch.setattr(app_module, "live_store", lambda: pytest.fail("RDPS demand path opened ArtifactStore"))
    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/point",
        params={"latitude": 47.56, "longitude": -52.71,
                "valid_time": "2026-09-06T14:00:00Z", "product": "RDPS"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "unavailable"
    assert "demand_query_empty:eccc-rdps" in body["fields"][0]["provenance"]["quality"]["flags"]


def test_coordinator_preflights_before_discovery() -> None:
    class Adapter:
        var_map = RDPS_DEMAND_VARS
        def demand_operation_bounds(self, _field_count):
            raise RuntimeError("unsupported runtime")
        def discover(self, _window):
            pytest.fail("provider discovery happened before platform preflight")

    coordinator = RDPSQueryCoordinator(adapter=Adapter())
    with pytest.raises(RuntimeError, match="unsupported runtime"):
        coordinator.query(datetime(2026, 9, 6, 14, 22, tzinfo=UTC))


def test_failure_is_coalesced_and_backed_off() -> None:
    calls = 0
    current = 0.0

    def fail(_request):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    service = RDPSQueryService(fail, clock=lambda: current)
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
        var_map = RDPS_DEMAND_VARS
        def demand_operation_bounds(self, _field_count): return object()
        def discover(self, _window): return [candidate]

    class Coordinator(RDPSQueryCoordinator):
        def _load(self, request): return entry(request)

    result = Coordinator(adapter=Adapter()).query(datetime(2026, 9, 6, 14, 37, tzinfo=UTC))
    assert result.valid_time == datetime(2026, 9, 6, 14, tzinfo=UTC)
    assert result.key.lead == 2
    profile_fields = rdps_profile_fields([1000, 850, 700, 500])
    profile = Coordinator(adapter=Adapter()).query(
        datetime(2026, 9, 6, 14, 37, tzinfo=UTC), fields=profile_fields
    )
    assert profile.key.fields == tuple(sorted(profile_fields))
    assert len(profile_fields) == 19
    assert set(RDPS_POINT_FIELDS) != set(profile_fields)


def test_timeline_discovery_advertises_native_hours_without_loading_fields() -> None:
    run = datetime(2026, 9, 6, 12, tzinfo=UTC)
    candidate = RunCandidate("2026090612", run, [], {
        "cycle_url": "https://example/12/", "available_hours": ["000", "001", "084", "085"]
    })

    class Adapter:
        def demand_operation_bounds(self, field_count):
            assert field_count == 1
        def discover(self, _window):
            return [candidate]

    class Coordinator(RDPSQueryCoordinator):
        def _load(self, _request):
            pytest.fail("timeline discovery fetched a selected-field payload")

    assert Coordinator(adapter=Adapter()).timeline_times(run) == (
        run, run + timedelta(hours=1), run + timedelta(hours=84)
    )


def test_live_timeline_uses_rdps_demand_availability_without_artifact_store(monkeypatch) -> None:
    reference = datetime(2026, 9, 6, 14, tzinfo=UTC)

    class Coordinator:
        @staticmethod
        def timeline_times(_selected):
            return (reference.replace(minute=0), reference.replace(minute=0) + timedelta(hours=1))

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(app_module, "now", lambda: reference)
    monkeypatch.setattr(app_module, "live_store", lambda: None)
    monkeypatch.setattr("weather_api.rdps_query.rdps_query_coordinator", lambda: Coordinator())
    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/timeline", params={"product": "RDPS"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "live"
    by_time = {datetime.fromisoformat(item["valid_time_utc"]): item for item in body["items"]}
    assert by_time[reference.replace(minute=0)]["available_products"] == ["eccc-rdps"]
    assert by_time[reference.replace(minute=0) + timedelta(hours=1)]["available_products"] == ["eccc-rdps"]
    assert any("provider-advertised demand availability" in item for item in body["notices"])


def test_rdps_demand_timeline_survives_a_raising_legacy_store(monkeypatch) -> None:
    reference = datetime(2026, 9, 6, 14, tzinfo=UTC)

    class Coordinator:
        @staticmethod
        def timeline_times(_selected):
            return (reference,)

    class RaisingStore:
        @staticmethod
        def published_products():
            raise RuntimeError("legacy store unavailable")

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(app_module, "now", lambda: reference)
    monkeypatch.setattr(app_module, "live_store", lambda: RaisingStore())
    monkeypatch.setattr("weather_api.rdps_query.rdps_query_coordinator", lambda: Coordinator())
    body = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/timeline", params={"product": "RDPS"}
    ).json()
    assert body["data_mode"] == "live"
    item = next(item for item in body["items"] if datetime.fromisoformat(item["valid_time_utc"]) == reference)
    assert item["available_products"] == ["eccc-rdps"]
    assert any("no GRIB prefetch or retained artifact coverage" in notice for notice in body["notices"])


def test_live_proxy_layers_survive_a_raising_legacy_store(monkeypatch) -> None:
    class RaisingStore:
        @staticmethod
        def current():
            raise RuntimeError("legacy store unavailable")

    proxy = app_module.LAYERS[0].model_copy(update={"evidence_basis": "live_proxy"})
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(app_module, "live_store", lambda: RaisingStore())
    monkeypatch.setattr(app_module, "_proxied_forecast_layers", lambda: ([proxy], ["provider metadata retained"]))
    body = TestClient(app_module.app).get(f"{app_module.PREFIX}/layers").json()
    assert body["data_mode"] == "live"
    assert [item["id"] for item in body["layers"]] == [proxy.id]
    assert any("legacy artifact store raised" in notice for notice in body["notices"])



def test_native_direction_and_mask_reach_real_api_unchanged(tmp_path, monkeypatch):
    valid = datetime(2026, 9, 6, 14, tzinfo=UTC)
    ds = xr.Dataset({
        "temperature_2m": (("valid_time", "y", "x"), [[[np.nan, 12.5]]], {"units": "degC"}),
        "wind_speed_10m": (("valid_time", "y", "x"), [[[4.0, 5.0]]], {"units": "m s-1"}),
        "wind_direction_10m": (("valid_time", "y", "x"), [[[85.3, 86.5]]], {"units": "degree", "original_units": "Degree true"}),
        "wind_direction_850hPa": (("valid_time", "y", "x"), [[[125.5, 126.5]]], {"units": "degree", "level_type": "isobaricInhPa", "level_value": 850}),
    }, coords={"valid_time": [np.datetime64(valid.replace(tzinfo=None), "ns")],
               "latitude": (("y", "x"), [[47.56, 47.56]]), "longitude": (("y", "x"), [[-52.71, -52.6]])})
    payload = write_zarr(ds, tmp_path / "native.zip").read_bytes()
    provenance = {"source_id": "eccc-rdps", "producer": "Environment and Climate Change Canada", "product": "RDPS",
                  "native_resolution": "RLatLon0.09", "native_crs": "EPSG:4326", "adapter_version": "rdps-demand-v1",
                  "original_units": {"wind_direction_10m": "Degree true", "wind_direction_850hPa": "Degree true"},
                  "quality": {"status": "passed", "flags": []}, "coverage": {"status": "complete", "fraction": 1.0},
                  **manifest_for("eccc-rdps", {name: RDPS_DEMAND_VARS[name] for name in ds.data_vars}).as_manifest_block()}
    selected = RDPSQueryEntry(key(2), valid-timedelta(hours=2), valid, valid, "b"*64, payload, provenance)
    coordinator = RDPSQueryCoordinator(adapter=object())
    monkeypatch.setattr(coordinator, "query", lambda *_args, **_kwargs: selected)
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr("weather_api.rdps_query.rdps_query_coordinator", lambda: coordinator)
    monkeypatch.setattr(app_module, "live_store", lambda: pytest.fail("RDPS opened retained store"))
    # Observation acquisition is independent and explicitly empty in this fixture.
    monkeypatch.setattr("weather_api.metar_query.metar_query_service", lambda: type("M", (), {"point_fields": lambda *a: ([],valid,None)})())
    client = TestClient(app_module.app)
    params = {"latitude":47.56,"longitude":-52.71,"valid_time":valid.isoformat(),"product":"RDPS"}
    body = client.get(f"{app_module.PREFIX}/point", params=params).json()
    fields = {f["field"]:f for f in body["fields"] if f["provenance"]["source_id"]=="eccc-rdps"}
    assert fields["temperature"]["value"] is None
    assert fields["wind_direction"]["value"] == 85.3
    assert fields["wind_speed"]["value"] == 4.0
    for field in fields.values():
        assert field["provenance"]["sample_method"] == "curvilinear_nearest_cell"
        assert field["provenance"]["sampled_longitude"] == pytest.approx(-52.71, abs=1e-12)
    assert fields["wind_direction"]["provenance"]["original_units"] == "Degree true"
    assert fields["wind_direction"]["provenance"]["derivation"] is None
    profile = client.get(f"{app_module.PREFIX}/profile", params=params).json()
    direction = next(f for level in profile["levels"] for f in level["fields"] if f["field"]=="wind_direction_850hPa")
    assert direction["value"] == 125.5
    assert direction["provenance"]["derivation"] is None


def test_cache_bounds_evict_and_failure_bookkeeping_is_finite(monkeypatch):
    import weather_api.rdps_query as module
    service = RDPSQueryService(entry)
    for lead in range(20): service.query(key(lead))
    assert len(service._entries) == 4
    fail = RDPSQueryService(lambda _: (_ for _ in ()).throw(ValueError("bad")))
    for lead in range(20):
        with pytest.raises(ValueError): fail.query(key(lead))
    assert len(fail._failures) == 4
    monkeypatch.setattr(module, "RDPS_CACHE_MAX_BYTES", 2)
    with pytest.raises(ValueError, match="byte ceiling"): RDPSQueryService(entry).query(key())


def test_native_identity_guard_refuses_wrong_parameter_level_time_grid_and_multiple(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    eccodes = SimpleNamespace(codes_get=None, codes_get_long=None, codes_release=None, codes_grib_new_from_file=None)
    monkeypatch.setitem(sys.modules, "eccodes", eccodes)
    from ingest.adapters.eccc_datamart import _validate_rdps_message
    stamp = datetime(2026,9,6,18,tzinfo=UTC)
    path = tmp_path / "field.grib2"; path.write_bytes(b"fixture")
    metadata = {"gridType":"rotated_ll", "Ni":1140,"Nj":1045,"numberOfPoints":1140*1045,
                "dataDate":20260906,"dataTime":1800,"validityDate":20260906,"validityTime":1800,
                "discipline":0,"parameterCategory":2,"parameterNumber":0,
                "typeOfFirstFixedSurface":103,"level":10,"stepType":"instant"}
    def validate():
        handles=iter([1,None])
        monkeypatch.setattr(eccodes,"codes_grib_new_from_file",lambda _:next(handles))
        _validate_rdps_message(path,stamp,stamp,"wind_direction_10m")
    monkeypatch.setattr(eccodes,"codes_get",lambda _,k:metadata[k])
    monkeypatch.setattr(eccodes,"codes_get_long",lambda _,k:metadata[k])
    monkeypatch.setattr(eccodes,"codes_release",lambda _:None)
    validate()
    for key,value in [("Ni",1102),("parameterNumber",1),("level",2),("validityTime",1700),("stepType","avg")]:
        old=metadata[key];metadata[key]=value
        with pytest.raises(ValueError):validate()
        metadata[key]=old
    monkeypatch.setattr(eccodes,"codes_grib_new_from_file",lambda _:1)
    with pytest.raises(ValueError,match="multiple"):_validate_rdps_message(path,stamp,stamp,"wind_direction_10m")


def test_permuted_fields_and_different_instants_share_canonical_request():
    run=datetime(2026,9,6,12,tzinfo=UTC); calls=[]
    class Adapter:
        bounds={"north":48.,"south":46.,"west":-54.,"east":-51.}
        var_map=RDPS_DEMAND_VARS
        def demand_operation_bounds(self,_):pass
        def discover(self,_):return [RunCandidate("2026090612",run,[],{"cycle_url":"https://example/12/","available_hours":["002"]})]
    class Coordinator(RDPSQueryCoordinator):
        def _load(self,key):calls.append(key);return entry(key)
    q=Coordinator(adapter=Adapter())
    first=q.query(run+timedelta(hours=2,minutes=1),fields=("temperature_2m","dew_point_2m"))
    second=q.query(run+timedelta(hours=2,minutes=59),fields=("dew_point_2m","temperature_2m","temperature_2m"))
    assert first is second and len(calls)==1
    with pytest.raises(ValueError):q.query(run+timedelta(hours=3))
    assert len(calls)==1
