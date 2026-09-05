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
from weather_api.store import LiveStore

UTC = timezone.utc
EVIDENCE = Path(__file__).parents[4] / "docs" / "research" / "evidence" / "weathernext-20260801-avalon-box.json"
ALL_FIELDS_EVIDENCE = Path(__file__).parents[4] / "docs" / "research" / "evidence" / "weathernext-20260801-all-fields-lead6-values.json"


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


def test_adapter_writes_immutable_artifact_with_full_disposition_provenance(tmp_path):
    adapter = WeatherNext3StatisticsAdapter(EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    artifact = result.artifacts[0]
    assert result.source_id == SOURCE_ID and result.complete and result.qc_passed
    assert artifact.provenance["product"] == PRODUCT
    assert artifact.provenance["ensemble"]["member_id"] is None
    assert len(artifact.provenance["field_dispositions"]) == 126
    assert artifact.provenance["sha256"] == hashlib.sha256(artifact.payload_path.read_bytes()).hexdigest()
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    assert set(dataset.data_vars) == {item["field"] for item in evidence()["sample"]["fields"]}


class HarnessStore(LiveStore):
    def __init__(self, current, dataset):
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._current, self._dataset = current, dataset
    def current(self):
        return [self._current]
    def open(self, _item):
        return self._dataset
    def assert_object_store_reachable(self):
        pass


def test_actual_astraeus_api_reads_all_field_artifact_with_test_local_catalogue(tmp_path, monkeypatch):
    adapter = WeatherNext3StatisticsAdapter(ALL_FIELDS_EVIDENCE)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    artifact = next(item for item in result.artifacts if "total_cloud_cover_mean" in item.provenance["evidence_class_by_variable"])
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    current = CurrentArtifact(SOURCE_ID, artifact.logical_name, "wn3-live-proof", "unused", artifact.media_type,
                              artifact.byte_size, artifact.provenance, datetime.now(UTC), result.run_time,
                              result.retrieved_at, result.provider_run_id, "EPSG:4326")
    harness = HarnessStore(current, dataset)
    store_module = importlib.import_module("weather_api.store")
    test_mapping = dict(store_module.FIELD_BY_VARIABLE)
    test_mapping["total_cloud_cover_mean"] = "total_cloud_cover_mean"
    test_mapping["sea_surface_temperature_mean"] = "sea_surface_temperature_mean"
    monkeypatch.setattr(store_module, "FIELD_BY_VARIABLE", test_mapping)
    samples = harness.sample_point(47.5, -52.70001220703125, datetime(2026, 8, 1, 6, tzinfo=UTC))
    by_variable = {item.variable: item for item in samples}
    expected = next(item for item in evidence(ALL_FIELDS_EVIDENCE)["sample"]["fields"]
                    if item["field"] == "total_cloud_cover_mean")["values"][0]
    assert by_variable["total_cloud_cover_mean"].value == pytest.approx(expected)
    assert by_variable["total_cloud_cover_mean"].evidence_class == "retrieved"
    assert by_variable["total_cloud_cover_mean"].source_id == SOURCE_ID

    api_module = importlib.import_module("weather_api.app")
    from registry import fields as catalogue
    test_fields = dict(catalogue._FIELDS)
    test_fields["total_cloud_cover_mean"] = dataclasses.replace(
        catalogue.field("total_cloud_geometric"), key="total_cloud_cover_mean",
        units="(0 - 1)", range=(0.0, 1.0),
        description="Test-local WeatherNext 3 provider statistic; no production catalogue registration.",
    )
    test_fields["sea_surface_temperature_mean"] = dataclasses.replace(
        catalogue.field("sea_surface_temperature"), key="sea_surface_temperature_mean",
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
    fields = [item for item in response.json()["fields"] if item["field"] == "total_cloud_cover_mean"
              and item["provenance"]["source_id"] == SOURCE_ID]
    assert len(fields) == 1
    assert fields[0]["value"] == pytest.approx(expected)
    assert fields[0]["provenance"]["evidence_class"] == "retrieved"
    sst = next(item for item in response.json()["fields"] if item["field"] == "sea_surface_temperature_mean"
               and item["provenance"]["source_id"] == SOURCE_ID)
    assert sst["value"] is None and sst["absence_state"] == "null"


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
