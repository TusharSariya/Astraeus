"""API-first native point/image wiring, without source admission or provider I/O."""
from datetime import timedelta
import importlib
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest
import xarray

from ingest.grib import normalize_units, write_zarr
from test_ecmwf_query import FIELDS, Fixture, RUN, coordinator
from weather_api.source_delivery import source_readers


def test_gefs_statistic_keeps_explicit_member_filter(monkeypatch):
    from types import SimpleNamespace
    import weather_api.gefs_query as module
    app = importlib.import_module("weather_api.app")
    calls = []
    def point_fields(*args, **kwargs):
        calls.append(kwargs)
        return [], None, []
    monkeypatch.setattr(module, "gefs_query_coordinator", lambda: SimpleNamespace(point_fields=point_fields))
    app._live_point(47.5, -52.75, RUN, "GEFS", member="p01", statistic="ensemble_mean")
    assert len(calls) == 1
    assert calls[0]["member"] == "p01"
    assert calls[0]["statistic"] == "ensemble_mean"


def native_fixture(request):
    from ingest.manifest import RequiredField, RunManifest
    source = request["source_id"]
    cloud, units = (0.5, "(0 - 1)") if source == "ecmwf-ifs" else (50.0, "%")
    dataset = xarray.Dataset({
        key: (("valid_time", "latitude", "longitude"), [[[value]]], {"units": unit})
        for key, value, unit in (("t2m", 280.15, "K"), ("d2m", 278.15, "K"),
                                ("msl", 101325.0, "Pa"), ("tcc", cloud, units))
    }, coords={"valid_time": [RUN.replace(tzinfo=None)], "latitude": [47.5], "longitude": [-52.75]})
    normalized = normalize_units(dataset).rename({"t2m": "temperature_2m", "d2m": "dew_point_2m",
        "msl": "mean_sea_level_pressure", "tcc": "total_cloud_geometric"})
    path = write_zarr(normalized, Path(request["directory"]) / "fixture.zarr.zip")
    manifest = RunManifest(source, tuple(RequiredField(key, unit) for key, unit in FIELDS.values()))
    return {**manifest.as_manifest_block(), "source_id": source, "run_time": request["run_time"], "valid_time": request["valid_time"],
            "fields": [value[0] for value in FIELDS.values()], "complete": True, "qc_passed": True}, path.read_bytes()


@pytest.mark.parametrize("source,product,cloud_units", [
    ("ecmwf-ifs", "IFS", "(0 - 1)"), ("ecmwf-aifs-single", "AIFS Single", "%")])
def test_deterministic_point_http_retains_native_receipt_and_no_primary(monkeypatch, data_mode, source, product, cloud_units):
    import weather_api.ecmwf_query as module
    app = importlib.import_module("weather_api.app")
    fixture = Fixture(source)
    service = coordinator(fixture, decoder=native_fixture)
    monkeypatch.setattr(module, "ecmwf_query_coordinator", lambda selected_source: service if selected_source == source else pytest.fail("source substituted"))
    monkeypatch.setattr(app, "now", lambda: RUN)
    data_mode("live")
    client = TestClient(app.app)
    params = {"latitude": 47.5, "longitude": -52.75, "valid_time": RUN.isoformat(), "product": product}
    response = client.get(f"{app.PREFIX}/point", params=params)
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "live" and body["selection"]["mode"] == "evidence_only"
    fields = {field["key"]: field for field in body["fields"]}
    assert fields["temperature_2m"]["value"] == pytest.approx(7)
    assert fields["total_cloud_geometric"]["value"] == pytest.approx(50)
    assert fields["total_cloud_geometric"]["provenance"]["original_units"] == cloud_units
    for field in fields.values():
        assert field["storage"] == "available-not-stored"
        p = field["provenance"]
        assert p["source_id"] == source and p["source_display_primary"] is False
        receipt = p["source_acquisition"]
        assert receipt["run_time"] == receipt["valid_time"] == RUN.isoformat().replace("+00:00", "Z")
        assert len(receipt["transport_receipts"]) == 6  # One valid listing, index and four ranges.
        assert all("set-cookie" not in item["response_headers"] for item in receipt["transport_receipts"])
    count = len(fixture.calls)
    assert client.get(f"{app.PREFIX}/point", params=params).json()["fields"] == body["fields"]
    assert len(fixture.calls) == count
    assert all(not cap.native_series for cap in source_readers()[source].descriptors())


def test_swob_selected_point_uses_exact_station_report(monkeypatch, data_mode):
    from test_swob_query import Clocks, feature, fixture_document, query_service
    import weather_api.swob_query as module
    app = importlib.import_module("weather_api.app")
    clocks, calls = Clocks(), []
    service = query_service(lambda request: calls.append(request) or httpx.Response(200, json=fixture_document(feature())), clocks)
    monkeypatch.setattr(module, "swob_query_service", lambda: service)
    monkeypatch.setattr(app, "now", lambda: clocks.wall)
    data_mode("live")
    client = TestClient(app.app)
    params = {"latitude": 47.5615, "longitude": -52.7126, "valid_time": clocks.wall.isoformat(), "product": "SWOB"}
    body = client.get(f"{app.PREFIX}/point", params=params).json()
    assert body["data_mode"] == "live" and len(body["fields"]) == 6
    assert not body["observation_unavailable"]  # No unrelated selected-model companion request.
    assert {field["provenance"]["native_report"]["station_id"] for field in body["fields"]} == {"71801"}
    assert all(field["provenance"]["run_time"] is None for field in body["fields"])
    assert client.get(f"{app.PREFIX}/point", params=params).json()["fields"] == body["fields"]
    assert len(calls) == 1
    params["valid_time"] = (clocks.wall + timedelta(minutes=1)).isoformat()
    assert client.get(f"{app.PREFIX}/point", params=params).json()["fields"] == []


@pytest.mark.parametrize("analysis_age_hours", [0, 36, 96])
def test_oisst_http_uses_native_analysis_and_reuses_crop(monkeypatch, data_mode, tmp_path, analysis_age_hours):
    from test_oisst_query import DAY, service
    import weather_api.oisst_query as module
    app = importlib.import_module("weather_api.app")
    query, calls, _clock = service(tmp_path)
    _clock[0] = analysis_age_hours * 3600
    monkeypatch.setattr(module, "oisst_query_service", lambda: query)
    monkeypatch.setattr(app, "now", lambda: DAY + timedelta(hours=analysis_age_hours))
    data_mode("live")
    client = TestClient(app.app)
    params = {"latitude": 47.5, "longitude": -52.0, "valid_time": DAY.isoformat(), "product": "OISST SST"}
    body = client.get(f"{app.PREFIX}/point", params=params).json()
    assert body["data_mode"] == "live" and len(body["fields"]) == 2
    assert body["selection"]["mode"] == "evidence_only" and not body["observation_unavailable"]
    assert all(f["storage"] == "available-not-stored" and not f["provenance"]["source_display_primary"] for f in body["fields"])
    assert all(f["provenance"]["valid_time"] == DAY.isoformat().replace("+00:00", "Z") and f["provenance"]["run_time"] is None for f in body["fields"])
    assert all(f["provenance"]["original_units"] == "Celsius" for f in body["fields"])
    assert client.get(f"{app.PREFIX}/point", params=params).json()["fields"] == body["fields"]
    assert len(calls) == 2
    params["valid_time"] = (DAY - timedelta(days=5)).isoformat()
    assert client.get(f"{app.PREFIX}/point", params=params).status_code == 422
    assert len(calls) == 2
    params["valid_time"] = DAY.replace(hour=13).isoformat()
    assert client.get(f"{app.PREFIX}/point", params=params).json()["fields"] == []
    assert len(calls) == 2


def test_mounted_holyrood_routes_keep_prefix_and_data_mode(monkeypatch, data_mode):
    from test_holyrood_query import service
    from test_holyrood_api import SELECTED
    from test_experimental_holyrood_radar import GIF
    from weather_api.holyrood_api import holyrood_service
    app = importlib.import_module("weather_api.app")
    query, calls, _clock, _responses = service()
    app.app.dependency_overrides[holyrood_service] = lambda: query
    client = TestClient(app.app)
    path = f"{app.PREFIX}/sources/eccc-holyrood-cashr-dpqpe/images"
    try:
        catalog = client.get(f"{app.PREFIX}/catalog").json()
        record, = [item for item in catalog["sources"] if item["id"] == "eccc-holyrood-cashr-dpqpe"]
        assert record["native_image_endpoint"] == path and not record["display_primary"] and not record["schedulable"]
        assert client.get(path, params={"valid_time": SELECTED}).status_code == 503
        assert not calls
        data_mode("live")
        result = client.get(path, params={"valid_time": SELECTED})
        assert result.status_code == 200
        for item in result.json()["images"]:
            assert item["image_url"].startswith(path + "/")
            assert client.get(item["image_url"]).content == GIF
        assert len(calls) == 3
    finally:
        app.app.dependency_overrides.pop(holyrood_service, None)
