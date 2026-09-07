from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
import importlib

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from ingest.adapters.eccc_datamart import (
    ECCCDataMartAdapter,
    GDPS_ADAPTER,
    GDPS_DEMAND_VARS,
    declare_native_true_direction,
    retrieval_completed_at,
    selected_demand_filename,
)
from registry.fields import storage_of
from registry.source_data import registry
from ingest.contract import RunCandidate
from ingest.grib import write_zarr
from weather_api.gdps_query import (
    GDPS_POINT_FIELDS,
    GDPSQueryCoordinator,
    GDPSQueryEntry,
    GDPSQueryService,
    GDPSQueryUnavailable,
    GDPSRequestKey,
)

app_module = importlib.import_module("weather_api.app")

@pytest.fixture(autouse=True)
def fixed_http_clock(monkeypatch):
    """HTTP selection bounds use the fixture date, never the wall clock."""
    monkeypatch.setattr(app_module, "now", lambda: datetime(2026, 9, 6, 12, tzinfo=UTC))


RUN = datetime(2026, 9, 6, 12, tzinfo=UTC)


def key(lead: int = 8) -> GDPSRequestKey:
    return GDPSRequestKey(
        "https://example/15km/12/", "2026090612", lead,
        GDPS_POINT_FIELDS, (("east", -52.4),),
    )


def entry(request: GDPSRequestKey) -> GDPSQueryEntry:
    return GDPSQueryEntry(
        request, RUN, RUN + timedelta(hours=request.lead), RUN,
        "a" * 64, b"zip", {"source_id": "eccc-gdps"},
    )


def candidate(*hours: str) -> RunCandidate:
    return RunCandidate(
        "2026090612", RUN, [],
        {"cycle_url": "https://example/15km/12/", "available_hours": list(hours)},
    )


def test_point_contract_uses_native_scalar_wind_without_component_derivation() -> None:
    assert GDPS_POINT_FIELDS == (
        "temperature_2m", "dew_point_2m", "wind_speed_10m",
        "wind_direction_10m", "mean_sea_level_pressure",
    )
    assert GDPS_DEMAND_VARS["wind_speed_10m"] == ("WindSpeed", "AGL-10m")
    assert GDPS_DEMAND_VARS["wind_direction_10m"] == ("WindDir", "AGL-10m")
    assert "wind_u_10m" not in GDPS_DEMAND_VARS
    assert "wind_v_10m" not in GDPS_DEMAND_VARS


def test_native_true_direction_preserves_provider_unit_and_declares_basis() -> None:
    field = xr.DataArray([85.3], attrs={"units": "Degree true"})
    normalized = declare_native_true_direction(field, "eccc-gdps")
    assert normalized.item() == 85.3
    assert normalized.attrs == {
        "units": "degree",
        "original_units": "Degree true",
        "direction_basis": "producer-native true north",
    }
    with pytest.raises(ValueError, match="undeclared true-north units"):
        declare_native_true_direction(xr.DataArray([85.3], attrs={"units": "degree"}), "eccc-gdps")


def test_native_filename_grid_and_catalogue_are_exact() -> None:
    expected = "20260906T12Z_MSC_GDPS_WindDir_AGL-10m_LatLon0.15_PT011H.grib2"
    assert selected_demand_filename(
        "eccc-gdps", RUN, "011", "wind_direction_10m",
        "WindDir", "AGL-10m", "LatLon0.15",
    ) == expected
    assert "RLatLon0.09" not in expected
    assert {
        name: storage_of("eccc-gdps", name)
        for name in GDPS_POINT_FIELDS
    } == {name: "stored" for name in GDPS_POINT_FIELDS}


def test_retrieval_time_is_last_transport_final_byte_not_decode_clock() -> None:
    receipts = [
        {"completed_at": "2026-09-06T23:00:01+00:00"},
        {"completed_at": "2026-09-06T23:00:03+00:00"},
    ]
    after_decode = datetime(2026, 9, 6, 23, 1, tzinfo=UTC)
    assert retrieval_completed_at(receipts, after_decode) == datetime(2026, 9, 6, 23, 0, 3, tzinfo=UTC)
    with pytest.raises(ValueError, match="no transport completion receipt"):
        retrieval_completed_at([], after_decode, required=True)


def test_registered_native_path_is_the_atmospheric_15km_product() -> None:
    assert GDPS_ADAPTER.model_subpath == "model_gdps/15km"
    assert GDPS_ADAPTER.grid_token == "LatLon0.15"
    record = next(source for source in registry()["sources"] if source["id"] == "eccc-gdps")
    assert record["access_endpoints"] == [
        "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_gdps/15km/{HH}/{FFF}/"
    ]
    assert "10 km tree carries sea-ice analysis" in record["reason"]


def test_cache_key_coalesces_identical_misses_with_fixed_clocks() -> None:
    calls = 0
    monotonic = 50.0
    completed = datetime(2026, 9, 6, 20, 0, 1, tzinfo=UTC)

    def load(request: GDPSRequestKey) -> GDPSQueryEntry:
        nonlocal calls
        calls += 1
        return entry(request)

    service = GDPSQueryService(load, clock=lambda: monotonic, now=lambda: completed)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.query(key()), range(8)))
    assert calls == 1
    assert len({id(item) for item in results}) == 1
    assert results[0].acquisition is not None
    assert results[0].acquisition.cached_at == completed
    assert results[0].acquisition.request.model_dump() == {
        "source_id": "eccc-gdps", "product": "GDPS",
        "cycle_url": "https://example/15km/12/", "provider_run_id": "2026090612",
        "lead": 8, "fields": GDPS_POINT_FIELDS, "bounds": {"east": -52.4},
    }


def test_expired_values_are_never_returned_and_identity_survives_one_ttl() -> None:
    current = 0.0
    attempts = 0

    def load(request: GDPSRequestKey) -> GDPSQueryEntry:
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            raise RuntimeError("provider unavailable")
        return entry(request)

    service = GDPSQueryService(load, ttl_seconds=10, clock=lambda: current, now=lambda: RUN)
    first = service.query(key())
    current = 11
    with pytest.raises(GDPSQueryUnavailable) as caught:
        service.query(key())
    assert caught.value.outcome.reason == "refresh_failed"
    assert caught.value.outcome.expired_acquisition == first.acquisition
    assert attempts == 2
    current = 21
    with pytest.raises(GDPSQueryUnavailable) as expired:
        service.query(key())
    assert expired.value.outcome.expired_acquisition is None


def test_cached_gdps_acquisition_reaches_all_native_point_values(tmp_path: Path) -> None:
    valid = RUN + timedelta(hours=11)
    dataset = xr.Dataset(
        {
            "temperature_2m": (("valid_time", "y", "x"), [[[14.8]]], {"units": "degC", "original_units": "K"}),
            "dew_point_2m": (("valid_time", "y", "x"), [[[14.6]]], {"units": "degC", "original_units": "K"}),
            "wind_speed_10m": (("valid_time", "y", "x"), [[[3.0]]], {"units": "m s-1", "original_units": "m s**-1"}),
            "wind_direction_10m": (("valid_time", "y", "x"), [[[103.5]]], {"units": "degree", "original_units": "Degree true"}),
            "mean_sea_level_pressure": (("valid_time", "y", "x"), [[[1002.6]]], {"units": "hPa", "original_units": "Pa"}),
        },
        coords={
            "valid_time": [np.datetime64(valid.replace(tzinfo=None), "ns")],
            "latitude": (("y", "x"), [[47.6186]]),
            "longitude": (("y", "x"), [[-52.7519]]),
        },
    )
    payload = write_zarr(dataset, tmp_path / "gdps-point.zip").read_bytes()
    request = key(11)
    receipts = [
        {
            "field": name,
            "url": f"https://example.test/12/011/{name}.grib2",
            "request_headers": {"accept": "*/*"},
            "response_headers": {"etag": f'"{index}"'},
            "bytes": 100 + index,
            "sha256": f"{index + 1:064x}",
            "completed_at": (valid + timedelta(seconds=index)).isoformat(),
        }
        for index, name in enumerate(request.fields)
    ]
    provenance = {
        "source_id": "eccc-gdps",
        "producer": "Environment and Climate Change Canada",
        "product": "ECCC-GDPS",
        "native_resolution": "LatLon0.15",
        "native_crs": "EPSG:4326",
        "adapter_version": "gdps-demand-v1",
        "original_units": {name: dataset[name].attrs["original_units"] for name in dataset.data_vars},
        "run_time": RUN.isoformat(),
        "valid_times": [valid.isoformat()],
        "quality": {"status": "passed", "flags": []},
        "coverage": {"status": "complete", "fraction": 1.0},
        "evidence_classes": ["retrieved"],
        "evidence_class_by_variable": {name: "retrieved" for name in dataset.data_vars},
        "transport_receipts": receipts,
    }
    loaded = GDPSQueryEntry(
        request, RUN, valid, valid + timedelta(seconds=4),
        "b" * 64, payload, provenance,
    )
    selected = GDPSQueryService(
        lambda _request: loaded,
        now=lambda: valid + timedelta(seconds=5),
        clock=lambda: 10.0,
    ).query(request)
    coordinator = GDPSQueryCoordinator(adapter=object())
    coordinator.query = lambda *_args, **_kwargs: selected
    fields, _consensus, _sources = coordinator.point_fields(47.6186, -52.7519, valid)
    native = {field.field: field for field in fields if field.field != "relative_humidity"}
    assert {name: field.value for name, field in native.items()} == {
        "temperature": 14.8,
        "dew_point": 14.6,
        "wind_speed": 3.0,
        "wind_direction": 103.5,
        "mean_sea_level_pressure": 1002.6,
    }
    assert all(field.provenance.demand_acquisition is not None for field in native.values())
    assert all(field.provenance.demand_acquisition.request.source_id == "eccc-gdps" for field in native.values())
    assert all(field.storage == "stored" for field in native.values())


def test_selected_fetch_refuses_non_native_and_out_of_range_before_payload(tmp_path: Path) -> None:
    adapter = ECCCDataMartAdapter(
        source_id="eccc-gdps", model_subpath="model_gdps/15km",
        grid_token="LatLon0.15", var_map=GDPS_DEMAND_VARS,
    )
    run = candidate("000", "240")
    with pytest.raises(Exception, match="exact native hourly lead"):
        adapter.fetch_selected(run, RUN + timedelta(minutes=30), tmp_path, fields=GDPS_POINT_FIELDS)
    with pytest.raises(Exception, match="unavailable"):
        adapter.fetch_selected(run, RUN + timedelta(hours=241), tmp_path, fields=GDPS_POINT_FIELDS)


def test_selected_fetch_narrows_to_one_lead_and_requested_fields(monkeypatch, tmp_path: Path) -> None:
    adapter = ECCCDataMartAdapter(
        source_id="eccc-gdps", model_subpath="model_gdps/15km",
        grid_token="LatLon0.15", var_map=GDPS_DEMAND_VARS,
    )
    observed = {}

    def fake_fetch(self, narrowed, window, workdir):
        observed.update(fields=tuple(self.var_map), hours=narrowed.detail["available_hours"],
                        now=window.now, receipts=self._capture_transport_receipts,
                        model=self.model_subpath, grid=self.grid_token)
        return object()

    monkeypatch.setattr(ECCCDataMartAdapter, "fetch", fake_fetch)
    adapter.fetch_selected(candidate("000", "001"), RUN + timedelta(hours=1), tmp_path,
                           fields=("temperature_2m", "wind_speed_10m"))
    assert observed == {
        "fields": ("temperature_2m", "wind_speed_10m"), "hours": ["001"],
        "now": RUN + timedelta(hours=1), "receipts": True,
        "model": "model_gdps/15km", "grid": "LatLon0.15",
    }


def test_coordinator_selects_latest_exact_native_hour_through_f240() -> None:
    advertised = candidate("000", "001", "240")

    class Adapter:
        bounds = {"south": 45.0, "north": 50.5, "west": -58.0, "east": -46.0}
        var_map = GDPS_DEMAND_VARS
        def demand_operation_bounds(self, field_count):
            assert 0 < field_count <= 5
            return object()
        def discover(self, _window):
            return [advertised]

    class Coordinator(GDPSQueryCoordinator):
        def _load(self, request):
            return entry(request)

    coordinator = Coordinator(adapter=Adapter(), now=lambda: RUN, clock=lambda: 0.0)
    result = coordinator.query(RUN + timedelta(hours=240, minutes=37))
    assert result.valid_time == RUN + timedelta(hours=240)
    assert result.key.lead == 240
    assert coordinator.timeline_times(RUN) == (
        RUN, RUN + timedelta(hours=1), RUN + timedelta(hours=240),
    )


def test_gdps_point_uses_demand_path_without_artifact_store(monkeypatch) -> None:
    class Coordinator:
        @staticmethod
        def point_fields(*_args):
            return [], None, []

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr("weather_api.gdps_query.gdps_query_coordinator", lambda: Coordinator())
    monkeypatch.setattr(app_module, "live_store", lambda: pytest.fail("GDPS point opened ArtifactStore"))
    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/point",
        params={"latitude": 47.56, "longitude": -52.71,
                "valid_time": "2026-09-06T14:00:00Z", "product": "GDPS"},
    )
    assert response.status_code == 200
    assert response.json()["selection"]["mode"] == "evidence_only"
    assert "demand_query_empty:eccc-gdps" in response.json()["fields"][0]["provenance"]["quality"]["flags"]


def test_gdps_timeline_is_metadata_only_and_never_opens_store(monkeypatch) -> None:
    reference = datetime(2026, 9, 6, 14, tzinfo=UTC)

    class Coordinator:
        @staticmethod
        def timeline_times(_selected):
            return (reference, reference + timedelta(hours=1))

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(app_module, "now", lambda: reference)
    monkeypatch.setattr(app_module, "live_store", lambda: pytest.fail("GDPS timeline opened ArtifactStore"))
    monkeypatch.setattr("weather_api.gdps_query.gdps_query_coordinator", lambda: Coordinator())
    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/timeline", params={"product": "GDPS"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "live"
    by_time = {datetime.fromisoformat(item["valid_time_utc"]): item for item in body["items"]}
    assert by_time[reference]["available_products"] == ["eccc-gdps"]
    assert any("metadata only" in notice for notice in body["notices"])


def test_gdps_profile_is_explicitly_unsupported_without_query_or_store(monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr("weather_api.gdps_query.gdps_query_coordinator", lambda: pytest.fail("GDPS profile queried provider"))
    monkeypatch.setattr(app_module, "live_store", lambda: pytest.fail("GDPS profile opened ArtifactStore"))
    response = TestClient(app_module.app).get(
        f"{app_module.PREFIX}/profile",
        params={"latitude": 47.56, "longitude": -52.71,
                "valid_time": "2026-09-06T14:00:00Z", "product": "GDPS"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "unavailable"
    assert all("unsupported_profile:eccc-gdps" in field["provenance"]["quality"]["flags"]
               for level in body["levels"] for field in level["fields"])
    assert any("#189" in notice and "no provider request" in notice for notice in body["notices"])
