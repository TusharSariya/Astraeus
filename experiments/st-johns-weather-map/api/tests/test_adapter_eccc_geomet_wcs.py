"""Fixture, failure, artifact and opt-in live proof for numeric GeoMet WCS."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy
import pytest
import xarray
from PIL import Image, TiffImagePlugin
from fastapi.testclient import TestClient

from ingest.adapters.eccc_geomet_wcs import (
    GRID_CONTRACTS,
    MAX_FIELDS_PER_OPERATION,
    CoverageField,
    GeoMetWCSClient,
    WCSResponseError,
    audit_inventory,
    contract_fields,
    decode_geotiff,
    fetch_artifact,
    fetch_pressure_profile_artifact,
    raw_field,
)
from ingest.contract import AVALON_CORE_BOUNDS
from ingest.store import CurrentArtifact
from weather_api import store as api_store
from weather_api import models as api_models
from weather_api.app import app
from weather_api.store import LiveStore

UTC = timezone.utc
api_module = importlib.import_module("weather_api.app")
VALID = datetime(2026, 9, 5, 12, tzinfo=UTC)
RUN = datetime(2026, 9, 5, 0, tzinfo=UTC)
FIELD = CoverageField("RDPS_10km_SeeingIndex", "seeing_class_eccc")
REPRESENTATIVE_FIELDS = (
    ("hrdps", CoverageField("HRDPS.CONTINENTAL_HR_40m", "relative_humidity_40m")),
    ("hrdps", CoverageField("HRDPS-WEonG_2.5km_SkyState", "weong_sky_state")),
    ("rdps", FIELD),
    ("rdps", CoverageField("RDPS_10km_SkyTransparencyIndex", "transparency_class_eccc")),
    ("gdps", CoverageField("GDPS-WEonG_15km_LiquidFogVisibility", "weong_liquid_fog_visibility")),
)
EVIDENCE_PATH = Path(__file__).resolve().parents[2] / "docs/evidence/geomet-wcs-2026-09-05.json"


def _wms_capabilities(coverage_id: str = FIELD.coverage_id) -> bytes:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<WMS_Capabilities version='1.3.0' updateSequence='2026-09-05T12:10:00Z'
 xmlns='http://www.opengis.net/wms'><Capability><Layer><Layer queryable='1'>
<Name>{coverage_id}</Name><Title>{'Relative humidity [%]' if 'PRES_HR' in coverage_id else 'Seeing index'}</Title>
<EX_GeographicBoundingBox><westBoundLongitude>-180</westBoundLongitude>
<eastBoundLongitude>180</eastBoundLongitude><southBoundLatitude>-90</southBoundLatitude>
<northBoundLatitude>90</northBoundLatitude></EX_GeographicBoundingBox>
<Dimension name='time' units='ISO8601' default='{VALID.isoformat()}'>{VALID.replace(hour=11).isoformat()}/{VALID.replace(hour=13).isoformat()}/PT1H</Dimension>
<Dimension name='reference_time' units='ISO8601' default='{RUN.isoformat()}'>{RUN.isoformat()}/{RUN.replace(hour=6).isoformat()}/PT6H</Dimension>
</Layer></Layer></Capability></WMS_Capabilities>""".encode()


def _tiff(
    path: Path, *, width: int, height: int, value: float = 4.0,
    raster_type: int = 1, bounds=AVALON_CORE_BOUNDS,
) -> None:
    values = numpy.full((height, width), value, dtype=numpy.float32)
    image = Image.fromarray(values, mode="F")
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    x_divisor = width if raster_type == 1 else width - 1
    y_divisor = height if raster_type == 1 else height - 1
    tags[33550] = ((bounds["east"] - bounds["west"]) / x_divisor,
                   (bounds["north"] - bounds["south"]) / y_divisor, 0.0)
    tags[33922] = (0.0, 0.0, 0.0, bounds["west"], bounds["north"], 0.0)
    tags[34735] = (1, 1, 0, 2, 1025, 0, 1, raster_type, 2048, 0, 1, 4326)
    tags[42113] = "-9999"
    image.save(path, format="TIFF", tiffinfo=tags)


def _description(coverage_id: str = FIELD.coverage_id) -> bytes:
    spacing = 0.0225 if coverage_id.startswith("HRDPS") else (0.15 if coverage_id.startswith("GDPS") else 0.090298)
    return f"""<wcs:CoverageDescriptions xmlns:wcs='http://www.opengis.net/wcs/2.0'
 xmlns:gml='http://www.opengis.net/gml/3.2'><wcs:CoverageDescription>
<gml:boundedBy><gml:Envelope srsName='http://www.opengis.net/def/crs/EPSG/0/4326'
 axisLabels='lat long'><gml:lowerCorner>-3 -180</gml:lowerCorner>
<gml:upperCorner>90 180</gml:upperCorner></gml:Envelope></gml:boundedBy>
<wcs:CoverageId>{coverage_id}</wcs:CoverageId><gml:domainSet>
<gml:RectifiedGrid dimension='2'><gml:axisLabels>long lat</gml:axisLabels>
<gml:offsetVector>0 {spacing}</gml:offsetVector>
<gml:offsetVector>-{spacing} 0</gml:offsetVector></gml:RectifiedGrid>
</gml:domainSet></wcs:CoverageDescription></wcs:CoverageDescriptions>""".encode()


class FixtureHTTP:
    def __init__(self, tmp_path: Path, *, service_error: bool = False) -> None:
        self.tmp_path = tmp_path
        self.service_error = service_error
        self.urls: list[str] = []

    def download(self, url: str, destination: Path, *, max_bytes: int, **_kwargs) -> int:
        self.urls.append(url)
        lowered = url.lower()
        if "request=getcapabilities" in lowered and "service=wms" in lowered:
            coverage_id = httpx.URL(url).params["LAYERS"]
            payload = _wms_capabilities(coverage_id)
            destination.write_bytes(payload)
            return len(payload)
        if "request=describecoverage" in lowered:
            coverage_id = httpx.URL(url).params["COVERAGEID"]
            payload = _description(coverage_id)
            destination.write_bytes(payload)
            return len(payload)
        if "request=getcoverage" in lowered:
            if self.service_error:
                payload = b"<ServiceExceptionReport><ServiceException code='NoMatch'>No matching time</ServiceException></ServiceExceptionReport>"
                destination.write_bytes(payload)
                return len(payload)
            sizes = httpx.URL(url).params.get_list("SCALESIZE")
            width = int(sizes[0].removeprefix("long(").removesuffix(")"))
            height = int(sizes[1].removeprefix("lat(").removesuffix(")"))
            _tiff(destination, width=width, height=height)
            return destination.stat().st_size
        raise AssertionError(url)


def test_contract_enumerates_expanded_profiles_weong_and_class_diagnostics():
    hrdps = contract_fields("hrdps")
    rdps = contract_fields("rdps")
    assert len([field for field in hrdps if ".PRES_HR." in field.coverage_id]) == 28
    assert len([field for field in rdps if "RelativeHumidity_" in field.coverage_id]) == 31
    assert len([field for field in rdps if "RDPS-WEonG" in field.coverage_id]) == 34
    assert {field.variable for field in rdps} >= {"seeing_class_eccc", "transparency_class_eccc"}
    assert {field.variable for field in hrdps} >= {
        "temperature_40m", "dew_point_80m", "relative_humidity_120m",
        "specific_humidity_40m", "wind_speed_80m", "wind_direction_120m",
    }


def test_experimental_wcs_does_not_replace_the_registered_model_adapters():
    import ingest.adapters
    from ingest.registry import registered_adapters

    assert "eccc_geomet_wcs" not in ingest.adapters.LOADED
    adapters = registered_adapters()
    assert {type(adapters[source_id]).__name__ for source_id in ("eccc-hrdps", "eccc-rdps", "eccc-gdps")} == {
        "ECCCDataMartAdapter"
    }


def test_inventory_never_converts_an_absent_or_unadvertised_field_to_available():
    rows = audit_inventory({"RDPS_10km_SeeingIndex"}, "rdps")
    by_id = {row["coverage_id"]: row["disposition"] for row in rows}
    assert by_id["RDPS_10km_SeeingIndex"] == "advertised"
    assert by_id["RDPS_10km_SkyTransparencyIndex"] == "missing"
    assert by_id["rdps:cloud_ceiling"] == "not-published"
    assert raw_field("GDPS-GEML_25km_AirTemp_850mb").variable == "raw__gdps_geml_25km_air_temp_850mb"


def test_missing_selected_field_refuses_fetch_without_clobbering_prior_artifact(tmp_path):
    prior = tmp_path / "seeing.tif"
    prior.write_bytes(b"prior-good-artifact")
    missing = CoverageField(FIELD.coverage_id, FIELD.variable, "missing")
    http = FixtureHTTP(tmp_path)
    client = GeoMetWCSClient(client=http, base_url="https://fixture.invalid/geomet")
    with pytest.raises(WCSResponseError, match="is missing"):
        client.fetch(missing, valid_time=VALID, reference_time=RUN, bounds=AVALON_CORE_BOUNDS,
                     width=45, height=23, destination=prior)
    assert prior.read_bytes() == b"prior-good-artifact"
    assert http.urls == []


def test_fixture_fetch_requires_format_subset_scalesize_and_exact_run(tmp_path):
    http = FixtureHTTP(tmp_path)
    client = GeoMetWCSClient(client=http, base_url="https://fixture.invalid/geomet")
    output, _url = client.fetch(
        FIELD, valid_time=VALID, reference_time=RUN, bounds=AVALON_CORE_BOUNDS,
        width=GRID_CONTRACTS["rdps"].width, height=GRID_CONTRACTS["rdps"].height,
        destination=tmp_path / "seeing.tif",
    )
    assert output.exists()
    request = next(url for url in http.urls if "GetCoverage" in url)
    decoded = httpx.URL(request).params
    assert decoded["FORMAT"] == "image/tiff"
    assert decoded.get_list("SUBSET") == ["long(-55.0,-51.0)", "lat(46.5,48.5)"]
    assert decoded.get_list("SCALESIZE") == ["long(45)", "lat(23)"]
    assert decoded["TIME"] == "2026-09-05T12:00:00Z"
    assert decoded["DIM_REFERENCE_TIME"] == "2026-09-05T00:00:00Z"


def test_run_bearing_layer_refuses_omitted_reference_before_coverage_download(tmp_path):
    http = FixtureHTTP(tmp_path)
    client = GeoMetWCSClient(client=http, base_url="https://fixture.invalid/geomet")
    destination = tmp_path / "seeing.tif"
    with pytest.raises(WCSResponseError, match="requires an explicit advertised reference time"):
        client.fetch(FIELD, valid_time=VALID, reference_time=None, bounds=AVALON_CORE_BOUNDS,
                     width=45, height=23, destination=destination)
    assert not destination.exists()
    assert not any("request=getcoverage" in url.lower() for url in http.urls)


def test_layer_without_run_dimension_allows_unknown_reference(tmp_path, monkeypatch):
    from dataclasses import replace

    http = FixtureHTTP(tmp_path)
    client = GeoMetWCSClient(client=http, base_url="https://fixture.invalid/geomet")
    capability = replace(client.metadata(FIELD.coverage_id), reference_time=None)
    monkeypatch.setattr(client, "metadata", lambda _coverage_id: capability)
    receipt = client.fetch(FIELD, valid_time=VALID, reference_time=None, bounds=AVALON_CORE_BOUNDS,
                           width=45, height=23, destination=tmp_path / "seeing.tif")
    assert receipt.selected_reference_time is None
    assert "DIM_REFERENCE_TIME" not in httpx.URL(receipt.url).params
    assert receipt.path.exists()


def test_http_200_xml_nomatch_fails_closed_and_removes_partial_file(tmp_path):
    client = GeoMetWCSClient(client=FixtureHTTP(tmp_path, service_error=True), base_url="https://fixture.invalid/geomet")
    destination = tmp_path / "seeing.tif"
    with pytest.raises(WCSResponseError, match="non-TIFF"):
        client.fetch(FIELD, valid_time=VALID, reference_time=RUN, bounds=AVALON_CORE_BOUNDS,
                     width=45, height=23, destination=destination)
    assert not destination.exists()


def test_fixture_artifact_round_trips_through_the_astraeus_live_api_sampler(tmp_path, monkeypatch):
    client = GeoMetWCSClient(client=FixtureHTTP(tmp_path), base_url="https://fixture.invalid/geomet")
    artifact = fetch_artifact(client, FIELD, valid_time=VALID, reference_time=RUN, workdir=tmp_path, model="rdps")
    assert artifact.provenance["operational"] is False
    assert artifact.provenance["run_time"] == RUN.isoformat()
    assert artifact.provenance["sampling_geometry"] == "pixel_is_area_cell_centres"
    assert artifact.provenance["resampling"] == "server_resampled_method_unknown"
    assert hashlib.sha256(artifact.payload_path.read_bytes()).hexdigest() == artifact.provenance["sha256"]
    import zarr
    zipped = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(zipped, consolidated=False)
    monkeypatch.setitem(api_store.FIELD_BY_VARIABLE, FIELD.variable, FIELD.variable)
    current = CurrentArtifact(
        source_id="eccc-rdps", logical_name=artifact.logical_name, revision_id="fixture-wcs-1",
        object_key="unused", media_type=artifact.media_type, byte_size=artifact.byte_size,
        provenance=artifact.provenance, published_at=VALID, run_time=RUN, retrieved_at=VALID,
        provider_run_id="2026090500", native_crs="EPSG:4326",
    )

    class Harness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=tmp_path)
        def current(self):
            return [current]
        def open(self, _artifact):
            return dataset
        def assert_object_store_reachable(self):
            pass

    manifest = SimpleNamespace(class_for=lambda _name: "retrieved", evidence_classes=("retrieved",))
    monkeypatch.setattr(api_store, "artifact_manifest", lambda _artifact: manifest)
    samples = Harness().sample_point(47.56, -52.71, VALID)
    sample = next(item for item in samples if item.variable == FIELD.variable)
    assert sample.value == 4.0
    assert sample.run_time == RUN
    assert sample.evidence_class == "retrieved"


@pytest.mark.parametrize(("model", "field"), REPRESENTATIVE_FIELDS)
def test_every_representative_round_trips_raw_to_artifact_reader_and_http(
    tmp_path, monkeypatch, model, field,
):
    client = GeoMetWCSClient(client=FixtureHTTP(tmp_path), base_url="https://fixture.invalid/geomet")
    artifact = fetch_artifact(client, field, valid_time=VALID, reference_time=RUN,
                              workdir=tmp_path / field.variable, model=model)
    import zarr
    zipped = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(zipped, consolidated=False)
    monkeypatch.setitem(api_store.FIELD_BY_VARIABLE, field.variable, field.variable)
    current = CurrentArtifact(
        source_id=GRID_CONTRACTS[model].source_id, logical_name=artifact.logical_name,
        revision_id=f"fixture-{field.variable}", object_key="unused", media_type=artifact.media_type,
        byte_size=artifact.byte_size, provenance=artifact.provenance, published_at=VALID,
        run_time=RUN, retrieved_at=VALID, provider_run_id="requested-unverified",
        native_crs="EPSG:4326",
    )

    class Harness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=tmp_path)
        def current(self):
            return [current]
        def open(self, _artifact):
            return dataset
        def assert_object_store_reachable(self):
            pass

    harness = Harness()
    manifest = SimpleNamespace(class_for=lambda _name: "retrieved", evidence_classes=("retrieved",))
    monkeypatch.setattr(api_store, "artifact_manifest", lambda _artifact: manifest)
    samples = harness.sample_point(47.56, -52.71, VALID)
    assert any(sample.variable == field.variable and sample.value == 4.0 for sample in samples)
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    monkeypatch.setattr(api_models, "catalogue_key_for", lambda _field: "temperature_2m")
    response = TestClient(app).get(
        "/api/experiments/weather/v0/point",
        params={"latitude": 47.56, "longitude": -52.71, "valid_time": VALID.isoformat()},
    )
    assert response.status_code == 200, response.text
    returned = {item["field"]: item["value"] for item in response.json()["fields"]}
    assert returned[field.variable] == 4.0


@pytest.mark.parametrize(("model", "field"), REPRESENTATIVE_FIELDS)
def test_retained_live_representatives_match_ledger_reader_and_http(monkeypatch, tmp_path, model, field):
    evidence = json.loads(EVIDENCE_PATH.read_text())
    record = next(row for row in evidence["representative_artifacts"] if row["coverage_id"] == field.coverage_id)
    acquisition = next(row for row in evidence["selected_acquisition"]["results"] if row["coverage_id"] == field.coverage_id)
    artifact_path = EVIDENCE_PATH.parents[1] / record["retained_artifact"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == record["sha256"]
    import zarr
    zipped = zarr.storage.ZipStore(str(artifact_path), mode="r")
    dataset = xarray.open_zarr(zipped, consolidated=False)
    values = numpy.asarray(dataset[field.variable].values)
    finite = values[numpy.isfinite(values)]
    assert int(finite.size) == acquisition["finite_cells"]
    assert int(values.size - finite.size) == acquisition["nodata_cells"]
    assert dataset[field.variable].attrs["original_units"] == (acquisition["units_as_published"] or "unknown")
    valid = datetime.fromisoformat(record["valid_time"])
    run = datetime.fromisoformat(record["run_time"])
    monkeypatch.setitem(api_store.FIELD_BY_VARIABLE, field.variable, field.variable)
    current = CurrentArtifact(
        source_id=GRID_CONTRACTS[model].source_id, logical_name=field.variable,
        revision_id=f"retained-{field.variable}", object_key=str(artifact_path),
        media_type="application/zarr+zip", byte_size=artifact_path.stat().st_size,
        provenance={"units": dataset[field.variable].attrs["units"], "evidence_classes": ["retrieved"]},
        published_at=valid, run_time=run, retrieved_at=valid,
        provider_run_id="requested-unverified", native_crs="EPSG:4326",
    )

    class Harness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=tmp_path)
        def current(self):
            return [current]
        def open(self, _artifact):
            return dataset
        def assert_object_store_reachable(self):
            pass

    harness = Harness()
    manifest = SimpleNamespace(class_for=lambda _name: "retrieved", evidence_classes=("retrieved",))
    monkeypatch.setattr(api_store, "artifact_manifest", lambda _artifact: manifest)
    direct = float(dataset[field.variable].sel(latitude=47.56, longitude=-52.71, method="nearest").item())
    sample = next(item for item in harness.sample_point(47.56, -52.71, valid) if item.variable == field.variable)
    assert sample.value == direct
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    monkeypatch.setattr(api_models, "catalogue_key_for", lambda _field: "temperature_2m")
    response = TestClient(app).get(
        "/api/experiments/weather/v0/point",
        params={"latitude": 47.56, "longitude": -52.71, "valid_time": valid.isoformat()},
    )
    assert response.status_code == 200, response.text
    returned = {item["field"]: item for item in response.json()["fields"]}[field.variable]
    assert returned["value"] == direct
    assert returned["provenance"]["original_units"] == dataset[field.variable].attrs["units"]


def test_retained_live_two_level_profile_matches_reader_and_http(monkeypatch, tmp_path):
    evidence = json.loads(EVIDENCE_PATH.read_text())
    record = evidence["representative_profile_artifact"]
    artifact_path = EVIDENCE_PATH.parents[1] / record["retained_artifact"]
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == record["sha256"]
    import zarr
    zipped = zarr.storage.ZipStore(str(artifact_path), mode="r")
    dataset = xarray.open_zarr(zipped, consolidated=False)
    valid = datetime.fromisoformat(record["valid_time"])
    run = datetime.fromisoformat(record["run_time"])
    current = CurrentArtifact(
        source_id="eccc-hrdps", logical_name="relative_humidity_pressure",
        revision_id="retained-rh-profile", object_key=str(artifact_path),
        media_type="application/zarr+zip", byte_size=artifact_path.stat().st_size,
        provenance={"units": dataset.relative_humidity_pressure.attrs["units"], "evidence_classes": ["retrieved"]},
        published_at=valid, run_time=run, retrieved_at=valid,
        provider_run_id="requested-unverified", native_crs="EPSG:4326",
    )

    class Harness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=tmp_path)
        def current(self):
            return [current]
        def open(self, _artifact):
            return dataset
        def assert_object_store_reachable(self):
            pass

    harness = Harness()
    manifest = SimpleNamespace(class_for=lambda _name: "retrieved", evidence_classes=("retrieved",))
    monkeypatch.setattr(api_store, "artifact_manifest", lambda _artifact: manifest)
    sampled = harness.sample_profile(47.56, -52.71, valid, [850, 700])
    for level in (850, 700):
        direct = float(dataset.relative_humidity_pressure.sel(
            pressure=level, latitude=47.56, longitude=-52.71, method="nearest",
        ).item())
        assert any(item.value == direct for item in sampled[level])
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: harness)
    response = TestClient(app).get(
        "/api/experiments/weather/v0/profile",
        params={"latitude": 47.56, "longitude": -52.71, "valid_time": valid.isoformat()},
    )
    assert response.status_code == 200, response.text
    levels = {row["pressure_hpa"]: row for row in response.json()["levels"]}
    for level in (850, 700):
        direct = float(dataset.relative_humidity_pressure.sel(
            pressure=level, latitude=47.56, longitude=-52.71, method="nearest",
        ).item())
        assert any(item["value"] == direct for item in levels[level]["fields"])


def test_pressure_coverages_round_trip_as_one_level_addressable_profile(tmp_path):
    client = GeoMetWCSClient(client=FixtureHTTP(tmp_path), base_url="https://fixture.invalid/geomet")
    fields = [
        CoverageField("HRDPS.CONTINENTAL.PRES_HR.850", "relative_humidity_pressure"),
        CoverageField("HRDPS.CONTINENTAL.PRES_HR.700", "relative_humidity_pressure"),
    ]
    artifact = fetch_pressure_profile_artifact(
        client, fields, [850, 700], valid_time=VALID, reference_time=RUN,
        workdir=tmp_path, model="hrdps",
    )
    import zarr
    zipped = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(zipped, consolidated=False)
    assert dataset["pressure"].values.tolist() == [850, 700]
    assert dataset["relative_humidity_pressure"].dims == ("pressure", "valid_time", "latitude", "longitude")
    assert artifact.provenance["coverage_ids"] == [field.coverage_id for field in fields]


def test_decode_rejects_a_server_default_or_wrong_grid(tmp_path):
    path = tmp_path / "wrong.tif"
    _tiff(path, width=30, height=60)
    with pytest.raises(WCSResponseError, match="coverage shape"):
        decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                       expected_width=45, expected_height=23)


def test_pixel_is_area_coordinates_are_cell_centres_and_validate_southeast(tmp_path):
    path = tmp_path / "area.tif"
    _tiff(path, width=45, height=23)
    dataset = decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                             expected_width=45, expected_height=23)
    assert dataset.longitude.values[0] == pytest.approx(-55 + 2 / 45)
    assert dataset.latitude.values[0] == pytest.approx(48.5 - 1 / 23)
    wrong = dict(AVALON_CORE_BOUNDS, east=-50.9)
    with pytest.raises(WCSResponseError, match="coverage bounds"):
        decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=wrong,
                       expected_width=45, expected_height=23)


def test_pixel_is_point_coordinates_and_crs_are_validated(tmp_path):
    path = tmp_path / "point.tif"
    _tiff(path, width=45, height=23, raster_type=2)
    dataset = decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                             expected_width=45, expected_height=23)
    assert dataset.longitude.values[[0, -1]].tolist() == pytest.approx([-55, -51])
    with Image.open(path) as image:
        values = numpy.asarray(image)
    image = Image.fromarray(values.astype(numpy.float32), mode="F")
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    tags[33550] = (4 / 44, 2 / 22, 0.0)
    tags[33922] = (0.0, 0.0, 0.0, -55.0, 48.5, 0.0)
    tags[34735] = (1, 1, 0, 2, 1025, 0, 1, 2, 2048, 0, 1, 3857)
    image.save(path, format="TIFF", tiffinfo=tags)
    with pytest.raises(WCSResponseError, match="CRS"):
        decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                       expected_width=45, expected_height=23)


def test_provenance_records_selected_times_separately_from_caller_request(tmp_path):
    requested_valid = VALID.replace(minute=29)
    requested_run = RUN.replace(hour=2)
    client = GeoMetWCSClient(client=FixtureHTTP(tmp_path), base_url="https://fixture.invalid/geomet")
    artifact = fetch_artifact(client, FIELD, valid_time=requested_valid, reference_time=requested_run,
                              workdir=tmp_path, model="rdps")
    assert artifact.provenance["requested_valid_time"] == requested_valid.isoformat()
    assert artifact.provenance["valid_time"] == VALID.isoformat()
    assert artifact.provenance["requested_run_time"] == requested_run.isoformat()
    assert artifact.provenance["run_time"] == RUN.isoformat()


def test_unlabelled_class_zero_is_preserved_as_a_value(tmp_path):
    path = tmp_path / "zero.tif"
    _tiff(path, width=45, height=23, value=0.0)
    dataset = decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                             expected_width=45, expected_height=23)
    assert numpy.count_nonzero(dataset[FIELD.variable].values) == 0
    assert not numpy.isnan(dataset[FIELD.variable].values).any()


def test_published_nodata_becomes_nan(tmp_path):
    path = tmp_path / "nodata.tif"
    _tiff(path, width=45, height=23, value=-9999.0)
    dataset = decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                             expected_width=45, expected_height=23)
    assert numpy.isnan(dataset[FIELD.variable].values).all()


def test_nonfinite_geometry_infinite_values_and_bad_nodata_fail_closed(tmp_path):
    path = tmp_path / "bad.tif"
    _tiff(path, width=45, height=23, value=float("inf"))
    with pytest.raises(WCSResponseError, match="infinite numeric"):
        decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                       expected_width=45, expected_height=23)
    bad_bounds = dict(AVALON_CORE_BOUNDS, east=float("nan"))
    _tiff(path, width=45, height=23)
    with pytest.raises(WCSResponseError, match="non-finite coordinate"):
        decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=bad_bounds,
                       expected_width=45, expected_height=23)
    values = numpy.ones((23, 45), dtype=numpy.float32)
    image = Image.fromarray(values, mode="F")
    tags = TiffImagePlugin.ImageFileDirectory_v2()
    tags[33550] = (4 / 45, 2 / 23, 0.0)
    tags[33922] = (0.0, 0.0, 0.0, -55.0, 48.5, 0.0)
    tags[34735] = (1, 1, 0, 2, 1025, 0, 1, 1, 2048, 0, 1, 4326)
    tags[42113] = "not-a-number"
    image.save(path, format="TIFF", tiffinfo=tags)
    with pytest.raises(WCSResponseError, match="unparseable nodata"):
        decode_geotiff(path, FIELD, valid_time=VALID, expected_bounds=AVALON_CORE_BOUNDS,
                       expected_width=45, expected_height=23)


@pytest.mark.live_smoke
@pytest.mark.skipif(os.getenv("WEATHER_LIVE_SMOKE") != "1", reason="set WEATHER_LIVE_SMOKE=1")
def test_live_rdps_seeing_artifact_and_api_readback(tmp_path, monkeypatch):
    client = GeoMetWCSClient(scratch_dir=tmp_path)
    capability = client.metadata(FIELD.coverage_id)
    valid = capability.time.end
    run = capability.reference_time.end if capability.reference_time else None
    artifact = fetch_artifact(client, FIELD, valid_time=valid, reference_time=run, workdir=tmp_path, model="rdps")
    assert artifact.byte_size < 2 << 20
    assert artifact.provenance["coverage_id"] == FIELD.coverage_id
    assert artifact.provenance["operational"] is False
    import zarr
    zipped = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(zipped, consolidated=False)
    monkeypatch.setitem(api_store.FIELD_BY_VARIABLE, FIELD.variable, FIELD.variable)
    current = CurrentArtifact(
        source_id="eccc-rdps", logical_name=artifact.logical_name, revision_id="live-wcs-1",
        object_key="unused", media_type=artifact.media_type, byte_size=artifact.byte_size,
        provenance=artifact.provenance, published_at=valid, run_time=run, retrieved_at=valid,
        provider_run_id="wcs-requested-reference-time", native_crs="EPSG:4326",
    )
    manifest = SimpleNamespace(class_for=lambda _name: "retrieved", evidence_classes=("retrieved",))
    monkeypatch.setattr(api_store, "artifact_manifest", lambda _artifact: manifest)

    class LiveHarness(LiveStore):
        def __init__(self):
            super().__init__(artifact_store=None, cache_dir=tmp_path)
        def current(self):
            return [current]
        def open(self, _artifact):
            return dataset
        def assert_object_store_reachable(self):
            pass

    samples = LiveHarness().sample_point(47.56, -52.71, valid)
    assert any(sample.variable == FIELD.variable and sample.value is not None for sample in samples)
