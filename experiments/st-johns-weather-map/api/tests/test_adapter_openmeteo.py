from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
import xarray
from fastapi.testclient import TestClient

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.openmeteo import BrightSkyMosmix71801Adapter, OpenMeteoAdapter
from weather_api.app import PREFIX, app
from weather_api.storage import ArtifactRevision, FixtureArtifactStore
from weather_api.store import LiveStore

UTC = timezone.utc


class Response:
    def __init__(self, value): self.content = value if isinstance(value, bytes) else json.dumps(value).encode()


class Client:
    def __init__(self, value=None, error=None): self.value, self.error, self.urls = value, error, []
    def get(self, url):
        self.urls.append(url)
        if self.error: raise self.error
        return Response(self.value)


def window(): return FetchWindow(datetime(2026, 9, 5, 1, tzinfo=UTC), back_hours=1, forward_hours=1)


def forecast(model="jma_gsm", *, omit=(), suffixed=False):
    names = {
        "temperature_2m": "°C", "dew_point_2m": "°C", "relative_humidity_2m": "%",
        "cloud_cover": "%", "cloud_cover_low": "%", "cloud_cover_mid": "%", "cloud_cover_high": "%",
        "wind_speed_10m": "m/s", "wind_direction_10m": "°", "pressure_msl": "hPa", "precipitation": "mm",
    }
    hourly = {"time": ["2026-09-05T00:00", "2026-09-05T01:00", "2026-09-05T02:00"]}
    units = {"time": "iso8601"}
    for index, (name, unit) in enumerate(names.items(), 1):
        if name in omit: continue
        key = f"{name}_{model}" if suffixed else name
        hourly[key], units[key] = [index, index + 1, index + 2], unit
    return {"latitude": 47.5, "longitude": -52.5, "elevation": 0, "hourly": hourly, "hourly_units": units}


@pytest.mark.parametrize("source,model", [
    ("openmeteo-jma-gsm", "jma_gsm"), ("openmeteo-arpege", "meteofrance_arpege_world025"),
    ("openmeteo-ukmo-global", "ukmo_global_deterministic_10km"),
])
def test_named_model_fixture_becomes_immutable_point_artifact(tmp_path, source, model):
    client = Client(forecast(model)); adapter = OpenMeteoAdapter(source, client=client)
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    assert result.complete and result.qc_passed and result.run_time is None
    artifact = result.artifacts[0]
    assert artifact.payload_path.is_file() and artifact.byte_size > 0
    assert artifact.provenance["model_selector"] == model
    assert artifact.provenance["run_identity"]["certainty"] == "unknown"
    assert artifact.provenance["field_disposition"]["relative_humidity_2m"].startswith("raw_retrieved")
    assert len(artifact.provenance["intermediary_transformations"]) == 6
    import zarr
    with xarray.open_zarr(zarr.storage.ZipStore(artifact.payload_path, mode="r"), consolidated=False) as dataset:
        assert set(dataset.data_vars) >= {"temperature_2m", "total_cloud_geometric", "wind_speed_10m"}
        assert dataset.precipitation_accumulation.attrs["reporting_interval"] == "preceding_hour"
    assert "models=" in client.urls[0] and "elevation=nan" in client.urls[0] and "cell_selection=nearest" in client.urls[0]


def test_selected_field_absence_fails_closed_before_writing_artifact(tmp_path):
    publication = FixtureArtifactStore()
    prior = ArtifactRevision("prior", 100, True, True)
    publication.stage("jma", prior); publication.publish("jma")
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(forecast(omit=("cloud_cover_high",))))
    with pytest.raises(AdapterUnavailable, match="missing_selected_field:cloud_cover_high"):
        adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    assert not list(tmp_path.glob("*.zarr.zip"))
    assert publication.visible["jma"] is prior


def test_complete_selected_model_suffix_shape_is_accepted(tmp_path):
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(forecast(suffixed=True)))
    assert adapter.fetch(adapter.discover(window())[0], window(), tmp_path).complete


@pytest.mark.parametrize("foreign,mixed,match", [
    (None, True, "mixed_model_response_shape"),
    ("meteofrance_arpege_world025", False, "foreign_model_arrays"),
    ("gfs_global", False, "foreign_model_arrays"),
])
def test_mixed_or_foreign_model_response_fails_closed(tmp_path, foreign, mixed, match):
    payload = forecast()
    if mixed: payload["hourly"]["temperature_2m_jma_gsm"] = payload["hourly"]["temperature_2m"]
    if foreign: payload["hourly"][f"temperature_2m_{foreign}"] = [1, 2, 3]
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(payload))
    with pytest.raises(AdapterUnavailable, match=match): adapter.fetch(adapter.discover(window())[0], window(), tmp_path)


@pytest.mark.parametrize("payload,match", [(b"{", "malformed provider JSON"), ({"hourly": {}}, "missing hourly")])
def test_malformed_and_partial_responses_fail_closed(tmp_path, payload, match):
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(payload))
    if isinstance(payload, bytes):
        with pytest.raises(AdapterUnavailable, match=match): adapter.discover(window())
    else:
        with pytest.raises(AdapterUnavailable, match=match): adapter.fetch(adapter.discover(window())[0], window(), tmp_path)


def test_throttling_is_unavailable_and_never_a_run():
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(error=httpx.HTTPStatusError("429", request=response.request, response=response)))
    with pytest.raises(AdapterUnavailable, match="request failed"): adapter.discover(window())


def bright_sky_payload():
    return {"sources": [{"id": 1228, "wmo_station_id": "71801", "lat": 47.62, "lon": -52.73, "station_name": "ST.JOHNS NEUFUNDL.", "observation_type": "forecast"}], "weather": [{
        "timestamp": "2026-09-05T01:00:00Z", "source_id": 1228, "temperature": 13.3, "dew_point": 10.2,
        "cloud_cover": 94, "visibility": 9800, "pressure_msl": 1014.2, "wind_speed": 18.0,
        "wind_direction": 118, "wind_gust_speed": 32.4, "precipitation": 0.0, "relative_humidity": None,
        "precipitation_probability": 25, "precipitation_probability_6h": None, "sunshine": None, "solar": None,
        "condition": "rain", "icon": "rain", "wind_gust_direction": None,
    }]}


def test_bright_sky_refuses_nearest_station_and_reads_exact_station(tmp_path):
    adapter = BrightSkyMosmix71801Adapter(Client({"sources": [{"wmo_station_id": "10147"}], "weather": []}))
    with pytest.raises(AdapterUnavailable, match="nearest-station fallback forbidden"): adapter.discover(window())
    exact = BrightSkyMosmix71801Adapter(Client(bright_sky_payload())); candidate = exact.discover(window())[0]
    result = exact.fetch(candidate, window(), tmp_path)
    assert result.complete and result.artifacts[0].provenance["station"]["source_id"] == 1228
    assert "wmo_station_id=71801" in candidate.urls[0]
    assert result.artifacts[0].provenance["field_disposition"]["condition"].startswith("raw_retrieved")
    assert result.artifacts[0].provenance["field_disposition"]["wind_gust_10m"] == "retrieved"


def test_all_null_required_field_is_incomplete_qc_valid_and_cannot_publish(tmp_path):
    payload = bright_sky_payload()
    payload["weather"][0]["wind_gust_speed"] = None
    adapter = BrightSkyMosmix71801Adapter(Client(payload))
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    assert result.complete is False
    assert result.qc_passed is True
    assert result.artifacts[0].provenance["quality"]["status"] == "suspect"
    assert "empty_field:wind_gust_10m" in result.artifacts[0].provenance["quality"]["flags"]

    publication = FixtureArtifactStore()
    prior = ArtifactRevision("prior", 100, True, True)
    publication.stage("mosmix", prior)
    publication.publish("mosmix")
    publication.stage("mosmix", ArtifactRevision("all-null-gust", result.artifacts[0].byte_size, result.complete, result.qc_passed))
    with pytest.raises(ValueError, match="complete and pass QC"):
        publication.publish("mosmix")
    assert publication.visible["mosmix"] is prior


@pytest.mark.parametrize("source_update,row_update", [
    ({"id": 999}, {}), ({"station_name": "WRONG"}, {}), ({"observation_type": "current"}, {}), ({}, {"source_id": 999}),
])
def test_bright_sky_rejects_wrong_exact_source_identity(tmp_path, source_update, row_update):
    payload = bright_sky_payload(); payload["sources"][0].update(source_update); payload["weather"][0].update(row_update)
    adapter = BrightSkyMosmix71801Adapter(Client(payload))
    if source_update:
        with pytest.raises(AdapterUnavailable, match="identity mismatch"): adapter.discover(window())
    else:
        with pytest.raises(AdapterUnavailable, match="row source_id"): adapter.fetch(adapter.discover(window())[0], window(), tmp_path)


def test_immutable_artifact_reads_back_through_real_artifact_reader_and_point_api(tmp_path, monkeypatch):
    import sys
    api_module = sys.modules["weather_api.app"]
    client = Client(forecast()); adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=client)
    artifact = adapter.fetch(adapter.discover(window())[0], window(), tmp_path).artifacts[0]

    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, _key, handle):
            with artifact.payload_path.open("rb") as source: shutil.copyfileobj(source, handle)

    record = SimpleNamespace(revision_id="live-proof-1", source_id="openmeteo-jma-gsm", logical_name="surface",
        media_type=artifact.media_type, object_key="proof/openmeteo.zip", byte_size=artifact.byte_size,
        provenance=artifact.provenance, run_time=None, retrieved_at=datetime(2026, 9, 5, 1, 5, tzinfo=UTC), native_crs="EPSG:4326")
    class ArtifactStore:
        s3 = S3(); config = SimpleNamespace(bucket="test")
        def current_artifacts(self): return [record]
        def source_activity(self): return {record.source_id: record.retrieved_at}

    store = LiveStore(ArtifactStore(), tmp_path / "cache")
    monkeypatch.setenv("WEATHER_DATA_MODE", "live"); monkeypatch.setattr(api_module, "live_store", lambda: store)
    monkeypatch.setitem(api_module.PRODUCT_SOURCE_IDS, "JMA-GSM-EXPERIMENT", "openmeteo-jma-gsm")
    response = TestClient(app).get(f"{PREFIX}/point", params={"product": "JMA-GSM-EXPERIMENT", "valid_time": "2026-09-05T01:00:00Z"})
    assert response.status_code == 200
    payload = response.json(); assert payload["operational"] is False and payload["data_mode"] == "live"
    temperature = next(field for field in payload["fields"] if field["field"] == "temperature")
    assert temperature["value"] == 2.0 and temperature["provenance"]["source_id"] == "openmeteo-jma-gsm"
