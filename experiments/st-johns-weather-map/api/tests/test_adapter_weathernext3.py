"""Five-part proof for the isolated WeatherNext 3 statistics adapter."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import xarray
import zarr
from fastapi.testclient import TestClient

from ingest.adapters.weathernext3_statistics import (
    ACCESS_SURFACE, EXPECTED_FIELDS, PRODUCT, SOURCE_ID,
    WeatherNext3StatisticsAdapter, WeatherNextManifestError, validate_acquisition,
)
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.store import CurrentArtifact
from ingest.store import ArtifactStore
from weather_api.store import LiveStore

UTC = timezone.utc
EVIDENCE = Path(__file__).parents[4] / "docs" / "research" / "evidence" / "weathernext-20260801-avalon-box.json"
ALL_FIELDS_EVIDENCE = Path(__file__).parents[4] / "docs" / "research" / "evidence" / "weathernext-20260801-all-fields-lead6-values.json"
ALL_FIELDS_BOX_EVIDENCE = Path(__file__).parents[4] / "docs" / "research" / "evidence" / "weathernext-20260801-all-fields-lead6-avalon-box.json"


def evidence(path: Path = EVIDENCE) -> dict:
    return json.loads(path.read_text())


def window() -> FetchWindow:
    return FetchWindow(now=datetime(2026, 8, 1, 12, tzinfo=UTC), back_hours=12, forward_hours=24)


def test_fixture_inventory_and_exact_product_identity_are_complete():
    item = evidence()
    validate_acquisition(item)
    assert len(item["fields"]) == len(EXPECTED_FIELDS) == 126
    assert item["identity"]["product_version"] == "3.0.0"
    assert item["identity"]["access_surface"] == ACCESS_SURFACE
    assert item["identity"]["member_id"] is None
    assert sum(value["status"] == "retrieved" for value in item["fields"].values()) == 6
    assert sum(value["status"] == "deferred" for value in item["fields"].values()) == 120


def test_real_upstream_evidence_has_immutable_object_identities_and_finite_values():
    item = evidence()
    assert item["result"] == "success" and item["objects"]
    assert all(obj["generation"] and obj["etag"] and obj["post_read_identity_verified"] for obj in item["objects"])
    assert item["usage"]["received_bytes"] == 375407160
    assert all(0 <= value <= 1 for field in item["sample"]["fields"] for value in field["values"])
    box = item["avalon_box_sample"]
    assert len(box["latitudes"]) == len(box["longitudes"]) == 16
    assert len(box["fields"]) == 6


@pytest.mark.parametrize("path", [EVIDENCE, ALL_FIELDS_EVIDENCE])
@pytest.mark.parametrize("mutation,match", [
    (lambda obj: obj.update(post_read_identity_verified=False), "no verified read mechanism"),
    (lambda obj: obj.update(generation="forged"), "generation"),
    (lambda obj: obj.update(etag=""), "ETag"),
    (lambda obj: obj.update(**({"name": "wrong/run/object"} if "name" in obj else {"object": "wrong/run/object"})),
     "outside the exact run"),
])
def test_actual_manifest_object_identity_mutations_fail_closed(path, mutation, match):
    item = evidence(path)
    mutation(item["objects"][-1])
    with pytest.raises(WeatherNextManifestError, match=match):
        validate_acquisition(item)


def test_all_field_identity_evidence_names_generation_pinning_not_a_post_read_recheck():
    objects = evidence(ALL_FIELDS_EVIDENCE)["objects"]
    assert all(item["identity_verification_method"] == "generation_qualified_read_with_size_check" for item in objects)
    assert all("post_read_identity_verified" not in item for item in objects)


@pytest.mark.parametrize("path,mutation,match", [
    (ALL_FIELDS_EVIDENCE, lambda item: item["objects"].pop(), "every selected field and lead"),
    (ALL_FIELDS_EVIDENCE, lambda item: item["objects"][-1].update(field="temperature_2m_mean"), "field identity"),
    (EVIDENCE, lambda item: item["objects"].pop(1), "metadata or coordinate"),
    (EVIDENCE, lambda item: item["objects"][-1].update(name=item["objects"][-2]["name"]), "duplicated"),
])
def test_missing_changed_or_duplicate_object_bindings_fail_closed(path, mutation, match):
    item = evidence(path)
    mutation(item)
    with pytest.raises(WeatherNextManifestError, match=match):
        validate_acquisition(item)


def test_all_126_live_fields_normalize_on_their_two_native_grids(tmp_path):
    item = json.loads(ALL_FIELDS_EVIDENCE.read_text())
    validate_acquisition(item)
    adapter = WeatherNext3StatisticsAdapter(ALL_FIELDS_EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    assert len(result.artifacts) == 2
    assert {artifact.logical_name for artifact in result.artifacts} == {
        "weathernext3-statistics-0p1", "weathernext3-statistics-0p05"
    }
    variables = set()
    for artifact in result.artifacts:
        store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
        dataset = xarray.open_zarr(store, consolidated=False)
        variables.update(map(str, dataset.data_vars))
        grid = artifact.logical_name.rsplit("-", 1)[1]
        expected_coordinates = {(sample["latitude"], sample["longitude"])
                                for sample in item["sample"]["fields"] if sample["grid"] == grid}
        assert expected_coordinates == {(float(dataset.latitude.values[0]), float(dataset.longitude.values[0]))}
        assert artifact.provenance["native_resolution"] == (
            "0.1 degree" if grid == "0p1" else "0.05 degree station-head grid")
        if "total_precipitation_1hr_p90" in dataset:
            attrs = dataset["total_precipitation_1hr_p90"].attrs
            assert attrs["provider_statistic"] == "p90"
            assert attrs["accumulation_interval_hours"] == 1.0
            assert attrs["period_semantics"] == "preceding hour ending at valid_time"
            assert artifact.provenance["accumulation_periods"] == [{
                "valid_time": "2026-08-01T06:00:00Z",
                "period_start": "2026-08-01T05:00:00Z",
                "period_end": "2026-08-01T06:00:00Z",
            }]
    assert variables == set(EXPECTED_FIELDS)
    null_fields = {sample["field"] for sample in item["sample"]["fields"] if sample["values"][0] is None}
    assert null_fields == {f"sea_surface_temperature_{stat}" for stat in ("mean", "p10", "p25", "p50", "p75", "p90")}
    assert {sample["unit"] for sample in item["sample"]["fields"]} == {
        "(0 - 1)", "J m**-2", "K", "Pa", "m", "m s**-1"
    }


def test_all_126_live_fields_cover_the_declared_box_on_both_native_grids():
    item = evidence(ALL_FIELDS_BOX_EVIDENCE)
    validate_acquisition(item)
    assert len(item["sample"]["fields"]) == 126
    grids = item["avalon_box_sample"]["grids"]
    assert {name: (len(grid["latitudes"]), len(grid["longitudes"])) for name, grid in grids.items()} == {
        "0p1": (56, 121), "0p05": (111, 241)
    }
    for grid in grids.values():
        assert (grid["latitudes"][0], grid["latitudes"][-1]) == pytest.approx((45.0, 50.5))
        assert (grid["longitudes"][0], grid["longitudes"][-1]) == pytest.approx((-58.0, -46.0))
    assert {name: field["null_count"] for name, field in item["fields"].items() if field["null_count"]} == {
        f"sea_surface_temperature_{stat}": 1587 for stat in ("mean", "p10", "p25", "p50", "p75", "p90")
    }


def test_all_field_box_reaches_real_reader_and_http_at_land_and_ocean_cells(tmp_path, monkeypatch):
    item = evidence(ALL_FIELDS_BOX_EVIDENCE)
    adapter = WeatherNext3StatisticsAdapter(ALL_FIELDS_BOX_EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    assert len(result.artifacts) == 2 and not result.complete and not result.qc_passed
    currents, datasets = [], {}
    for artifact in result.artifacts:
        datasets[artifact.logical_name] = xarray.open_zarr(
            zarr.storage.ZipStore(str(artifact.payload_path), mode="r"), consolidated=False)
        currents.append(CurrentArtifact(SOURCE_ID, artifact.logical_name, f"wn3-box-{artifact.logical_name}",
                                        "unused", artifact.media_type, artifact.byte_size, artifact.provenance,
                                        datetime.now(UTC), result.run_time, result.retrieved_at,
                                        result.provider_run_id, "EPSG:4326"))
    harness = HarnessStore(currents, datasets)
    store_module = importlib.import_module("weather_api.store")
    monkeypatch.setattr(store_module, "FIELD_BY_VARIABLE",
                        {**store_module.FIELD_BY_VARIABLE, **{name: name for name in EXPECTED_FIELDS}})
    from registry import fields as catalogue
    template = catalogue.field("total_cloud_geometric")
    units = {sample["field"]: sample["unit"] for sample in item["sample"]["fields"]}
    monkeypatch.setattr(catalogue, "_FIELDS", {**catalogue._FIELDS, **{
        name: dataclasses.replace(template, key=name, units=units[name], range=None,
                                  description="Test-local WeatherNext 3 provider statistic.")
        for name in EXPECTED_FIELDS
    }})
    api_module = importlib.import_module("weather_api.app")
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    monkeypatch.setattr(api_module, "now", lambda: datetime(2026, 8, 1, 12, tzinfo=UTC))
    by_field = {sample["field"]: sample for sample in item["sample"]["fields"]}
    grids = item["avalon_box_sample"]["grids"]

    sst = by_field["sea_surface_temperature_mean"]["leads"][0]["values"]
    in_core = lambda row, column: (46.5 <= grids["0p1"]["latitudes"][row] <= 48.5
                                   and -55.0 <= grids["0p1"]["longitudes"][column] <= -51.0)
    land_index = next((row_index, column_index) for row_index, row in enumerate(sst)
                      for column_index, value in enumerate(row) if in_core(row_index, column_index) and value is None)
    ocean_index = next((row_index, column_index) for row_index, row in enumerate(sst)
                       for column_index, value in enumerate(row) if in_core(row_index, column_index) and value is not None)
    for row_index, column_index in (land_index, ocean_index):
        latitude = grids["0p1"]["latitudes"][row_index]
        longitude = grids["0p1"]["longitudes"][column_index]
        expected = {}
        for name, sample in by_field.items():
            grid = grids[sample["grid"]]
            lat_index = min(range(len(grid["latitudes"])), key=lambda index: abs(grid["latitudes"][index] - latitude))
            lon_index = min(range(len(grid["longitudes"])), key=lambda index: abs(grid["longitudes"][index] - longitude))
            expected[name] = sample["leads"][0]["values"][lat_index][lon_index]
        sampled = {value.variable: value.value for value in harness.sample_point(
            latitude, longitude, datetime(2026, 8, 1, 6, tzinfo=UTC))}
        assert set(sampled) == set(EXPECTED_FIELDS)
        for name, value in expected.items():
            assert sampled[name] == (pytest.approx(value) if value is not None else None)
        response = TestClient(api_module.app).get("/api/experiments/weather/v0/point", params={
            "latitude": latitude, "longitude": longitude, "valid_time": "2026-08-01T06:00:00Z"})
        assert response.status_code == 200, response.text
        actual = {field["field"]: field for field in response.json()["fields"]
                  if field["provenance"]["source_id"] == SOURCE_ID}
        assert set(actual) == set(EXPECTED_FIELDS)
        for name, value in expected.items():
            assert actual[name]["value"] == (pytest.approx(value) if value is not None else None)
            assert actual[name]["absence_state"] == ("null" if value is None else None)


def test_adapter_writes_immutable_artifact_with_full_disposition_provenance(tmp_path):
    adapter = WeatherNext3StatisticsAdapter(EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    artifact = result.artifacts[0]
    assert result.source_id == SOURCE_ID and not result.complete and not result.qc_passed
    assert artifact.provenance["product"] == PRODUCT
    assert artifact.provenance["ensemble"]["member_id"] is None
    assert len(artifact.provenance["field_dispositions"]) == 126
    assert artifact.provenance["acquisition_scope"]["operational_publishable"] is False
    assert artifact.provenance["sha256"] == hashlib.sha256(artifact.payload_path.read_bytes()).hexdigest()
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    assert set(dataset.data_vars) == {item["field"] for item in evidence()["sample"]["fields"]}


class HarnessStore(LiveStore):
    def __init__(self, current, dataset):
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._current = current if isinstance(current, list) else [current]
        self._dataset = dataset
    def current(self):
        return self._current
    def open(self, item):
        return self._dataset[item.logical_name] if isinstance(self._dataset, dict) else self._dataset
    def assert_object_store_reachable(self):
        pass


def test_actual_astraeus_api_reads_all_126_fields_from_both_grids_with_test_local_catalogue(tmp_path, monkeypatch):
    adapter = WeatherNext3StatisticsAdapter(ALL_FIELDS_EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    currents, datasets = [], {}
    for artifact in result.artifacts:
        store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
        datasets[artifact.logical_name] = xarray.open_zarr(store, consolidated=False)
        currents.append(CurrentArtifact(SOURCE_ID, artifact.logical_name, f"wn3-{artifact.logical_name}", "unused",
                                        artifact.media_type, artifact.byte_size, artifact.provenance, datetime.now(UTC),
                                        result.run_time, result.retrieved_at, result.provider_run_id, "EPSG:4326"))
    harness = HarnessStore(currents, datasets)
    store_module = importlib.import_module("weather_api.store")
    test_mapping = dict(store_module.FIELD_BY_VARIABLE)
    test_mapping.update({name: name for name in EXPECTED_FIELDS})
    monkeypatch.setattr(store_module, "FIELD_BY_VARIABLE", test_mapping)
    samples = harness.sample_point(47.5, -52.70001220703125, datetime(2026, 8, 1, 6, tzinfo=UTC))
    by_variable = {item.variable: item for item in samples}
    expected = {item["field"]: item["values"][0] for item in evidence(ALL_FIELDS_EVIDENCE)["sample"]["fields"]}
    assert set(by_variable) == set(EXPECTED_FIELDS)
    for name, value in expected.items():
        assert by_variable[name].value == (pytest.approx(value) if value is not None else None)
        assert by_variable[name].evidence_class == "retrieved"
        assert by_variable[name].source_id == SOURCE_ID

    api_module = importlib.import_module("weather_api.app")
    from registry import fields as catalogue
    test_fields = dict(catalogue._FIELDS)
    template = catalogue.field("total_cloud_geometric")
    for name in EXPECTED_FIELDS:
        test_fields[name] = dataclasses.replace(
            template, key=name, units=next(item["unit"] for item in evidence(ALL_FIELDS_EVIDENCE)["sample"]["fields"]
                                           if item["field"] == name), range=None,
            description="Test-local WeatherNext 3 provider statistic; no production catalogue registration.",
        )
    monkeypatch.setattr(catalogue, "_FIELDS", test_fields)
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    monkeypatch.setattr(api_module, "now", lambda: datetime(2026, 8, 1, 12, tzinfo=UTC))
    response = TestClient(api_module.app).get(
        "/api/experiments/weather/v0/point",
        params={"latitude": 47.5, "longitude": -52.70001220703125, "valid_time": "2026-08-01T06:00:00Z"},
    )
    assert response.status_code == 200, response.text
    fields = {item["field"]: item for item in response.json()["fields"] if item["provenance"]["source_id"] == SOURCE_ID}
    assert set(fields) == set(EXPECTED_FIELDS)
    for name, value in expected.items():
        if value is None:
            assert fields[name]["value"] is None and fields[name]["absence_state"] == "null"
        else:
            assert fields[name]["value"] == pytest.approx(value)
            assert fields[name]["provenance"]["evidence_class"] == "retrieved"


def test_six_field_box_reaches_real_reader_and_http_with_every_selected_value(tmp_path, monkeypatch):
    adapter = WeatherNext3StatisticsAdapter(EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    artifact = result.artifacts[0]
    dataset = xarray.open_zarr(zarr.storage.ZipStore(str(artifact.payload_path), mode="r"), consolidated=False)
    current = CurrentArtifact(SOURCE_ID, artifact.logical_name, "wn3-box", "unused", artifact.media_type,
                              artifact.byte_size, artifact.provenance, datetime.now(UTC), result.run_time,
                              result.retrieved_at, result.provider_run_id, "EPSG:4326")
    harness = HarnessStore(current, dataset)
    store_module = importlib.import_module("weather_api.store")
    selected = evidence()["request"]["selected_fields"]
    monkeypatch.setattr(store_module, "FIELD_BY_VARIABLE", {**store_module.FIELD_BY_VARIABLE, **{name: name for name in selected}})
    from registry import fields as catalogue
    monkeypatch.setattr(catalogue, "_FIELDS", {**catalogue._FIELDS, **{
        name: dataclasses.replace(catalogue.field("total_cloud_geometric"), key=name, units="(0 - 1)", range=(0, 1))
        for name in selected
    }})
    expected = {item["field"]: item["leads"][0]["values"][10][13]
                for item in evidence()["avalon_box_sample"]["fields"]}
    sampled = {item.variable: item.value for item in harness.sample_point(47.5, -52.7, datetime(2026, 8, 1, 6, tzinfo=UTC))}
    assert sampled == pytest.approx(expected)
    api_module = importlib.import_module("weather_api.app")
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    monkeypatch.setattr(api_module, "now", lambda: datetime(2026, 8, 1, 12, tzinfo=UTC))
    response = TestClient(api_module.app).get(
        "/api/experiments/weather/v0/point",
        params={"latitude": 47.5, "longitude": -52.7, "valid_time": "2026-08-01T06:00:00Z"},
    )
    assert response.status_code == 200, response.text
    actual = {item["field"]: item["value"] for item in response.json()["fields"]
              if item["provenance"]["source_id"] == SOURCE_ID}
    assert actual == pytest.approx(expected)


def test_partial_experimental_result_cannot_advance_actual_store_publication(tmp_path, monkeypatch):
    result = WeatherNext3StatisticsAdapter(EVIDENCE).fetch(
        WeatherNext3StatisticsAdapter(EVIDENCE).discover(window())[0], window(), tmp_path)
    store = object.__new__(ArtifactStore)
    state = {"current": "prior-revision", "published": False}
    monkeypatch.setattr(store, "assert_run_identity", lambda _result: None)
    monkeypatch.setattr(store, "record_run", lambda _result: "experimental-run")
    monkeypatch.setattr(store, "discard_staged", lambda _run_id: 0)
    monkeypatch.setattr(store, "stage", lambda _result, artifact, run_id=None: artifact.logical_name)
    monkeypatch.setattr(store, "publish_run", lambda _run_id: state.update(published=True, current="experimental"))
    staged = store.stage_and_publish(result)
    assert staged and state == {"current": "prior-revision", "published": False}


@pytest.mark.parametrize("mutation,match", [
    (lambda item: item["identity"].update(product_version="2.0.0"), "wrong product"),
    (lambda item: item["identity"].update(member_id="0"), "not ensemble members"),
    (lambda item: item["fields"].pop(next(iter(item["fields"])), None), "exactly all 126"),
    (lambda item: item["fields"]["total_cloud_cover_mean"].update(statistic="p90"), "statistic identity"),
    (lambda item: item["sample"]["fields"].pop(), "sample payload differ"),
    (lambda item: item["request"].update(bucket="wrong"), "wrong WeatherNext bucket"),
    (lambda item: item["request"].update(selected_fields=[]), "selected field set"),
    (lambda item: (item["times"].update(initialization="2026-08-01T00:00:00"),
                   item["request"].update(initialization="2026-08-01T00:00:00")), "explicit UTC offset"),
    (lambda item: item["sample"]["fields"].append(copy.deepcopy(item["sample"]["fields"][0])), "duplicate sample"),
    (lambda item: item["sample"]["fields"][0]["values"].__setitem__(0, 1.5), "invalid cloud fraction"),
])
def test_invalid_metadata_and_values_fail_closed(mutation, match):
    item = copy.deepcopy(evidence())
    mutation(item)
    with pytest.raises(WeatherNextManifestError, match=match):
        validate_acquisition(item)


def test_missing_or_blocked_acquisition_is_explicit():
    item = evidence()
    item.update(result="blocked", blocker="requester billing required")
    with pytest.raises(AdapterUnavailable, match="requester billing required"):
        validate_acquisition(item)


def test_fill_mask_is_preserved_and_count_mismatch_fails_closed(tmp_path):
    item = evidence()
    item["sample"]["fields"][0]["values"][0] = None
    item["avalon_box_sample"]["fields"][0]["leads"][0]["values"][0][0] = None
    item["fields"]["total_cloud_cover_mean"]["null_count"] = 1
    path = tmp_path / "masked.json"
    path.write_text(json.dumps(item))
    adapter = WeatherNext3StatisticsAdapter(path)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    store = zarr.storage.ZipStore(str(result.artifacts[0].payload_path), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    assert bool(dataset["total_cloud_cover_mean"].isnull().values[0, 0, 0])

    item["fields"]["total_cloud_cover_mean"]["null_count"] = 0
    with pytest.raises(WeatherNextManifestError, match="fill-mask count mismatch"):
        validate_acquisition(item)


def test_invalid_manifest_creates_no_partial_artifact(tmp_path):
    item = evidence()
    item["identity"]["product_version"] = "2.0.0"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(item))
    adapter = WeatherNext3StatisticsAdapter(path)
    with pytest.raises(WeatherNextManifestError):
        adapter.discover(window())
    assert not list(tmp_path.glob("*.zarr.zip"))


@pytest.mark.parametrize("mutation,match", [
    (lambda item: item["sample"]["fields"][0].update(grid="0p05"), "native grid mismatch"),
    (lambda item: item["sample"]["fields"][1].update(latitude=0.0), "coordinate differs"),
    (lambda item: item["sample"]["fields"][0].update(unit="degC"), "native unit mismatch"),
    (lambda item: item["sample"]["fields"][0]["values"].__setitem__(0, float("inf")), "non-finite"),
])
def test_all_field_native_shape_and_values_fail_closed(mutation, match):
    item = json.loads(ALL_FIELDS_EVIDENCE.read_text())
    mutation(item)
    with pytest.raises(WeatherNextManifestError, match=match):
        validate_acquisition(item)


def test_candidate_identity_must_match_manifest(tmp_path):
    adapter = WeatherNext3StatisticsAdapter(EVIDENCE)
    candidate = dataclasses.replace(adapter.discover(window())[0], provider_run_id="wrong")
    with pytest.raises(WeatherNextManifestError, match="candidate and manifest"):
        adapter.fetch(candidate, window(), tmp_path)


@pytest.mark.parametrize("mutation,match", [
    (lambda item: item["avalon_box_sample"]["fields"].append(
        copy.deepcopy(item["avalon_box_sample"]["fields"][0])), "duplicate Avalon"),
    (lambda item: item["avalon_box_sample"]["latitudes"].__setitem__(1,
        item["avalon_box_sample"]["latitudes"][0]), "monotonic native"),
])
def test_avalon_box_native_shape_fails_closed(mutation, match):
    item = evidence()
    mutation(item)
    with pytest.raises(WeatherNextManifestError, match=match):
        validate_acquisition(item)


def test_adapter_is_not_registered():
    from ingest.registry import registered_adapters
    assert SOURCE_ID not in registered_adapters()
