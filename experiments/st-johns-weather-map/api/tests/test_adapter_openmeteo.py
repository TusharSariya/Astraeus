from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import xarray
from fastapi.testclient import TestClient

from ingest.experimental.openmeteo import BrightSkyMosmix71801Adapter, OpenMeteoAdapter
from ingest.contract import AdapterUnavailable, FetchWindow
from weather_api.app import PREFIX, app
from weather_api.store import Sample

UTC = timezone.utc


class Response:
    def __init__(self, value):
        self.content = value if isinstance(value, bytes) else json.dumps(value).encode()


class Client:
    def __init__(self, value=None, error=None): self.value, self.error, self.urls = value, error, []
    def get(self, url):
        self.urls.append(url)
        if self.error: raise self.error
        return Response(self.value)


def window():
    return FetchWindow(datetime(2026, 9, 5, 1, tzinfo=UTC), back_hours=1, forward_hours=1)


def forecast(model="jma_gsm", *, omit=()):
    names = {
        "temperature_2m": "°C", "dew_point_2m": "°C", "relative_humidity_2m": "%",
        "cloud_cover": "%", "cloud_cover_low": "%", "cloud_cover_mid": "%", "cloud_cover_high": "%",
        "wind_speed_10m": "m/s", "wind_direction_10m": "°", "pressure_msl": "hPa", "precipitation": "mm",
    }
    hourly = {"time": ["2026-09-05T00:00", "2026-09-05T01:00", "2026-09-05T02:00"]}
    units = {"time": "iso8601"}
    for index, (name, unit) in enumerate(names.items(), 1):
        if name in omit: continue
        hourly[f"{name}_{model}"] = [index, index + 1, index + 2]
        units[f"{name}_{model}"] = unit
    return {"latitude": 47.5, "longitude": -52.5, "elevation": 0, "hourly": hourly, "hourly_units": units}


@pytest.mark.parametrize("source,model", [
    ("openmeteo-jma-gsm", "jma_gsm"),
    ("openmeteo-arpege", "meteofrance_arpege_world025"),
    ("openmeteo-ukmo-global", "ukmo_global_deterministic_10km"),
])
def test_named_model_fixture_becomes_immutable_point_artifact(tmp_path, source, model):
    client = Client(forecast(model))
    adapter = OpenMeteoAdapter(source, client=client)
    candidate = adapter.discover(window())
    result = adapter.fetch(candidate[0], window(), tmp_path)
    assert result.complete and result.qc_passed and result.run_time is None
    assert result.provider_run_id.startswith("rolling-unknown-")
    artifact = result.artifacts[0]
    assert artifact.payload_path.is_file() and artifact.byte_size > 0
    assert artifact.provenance["model_selector"] == model
    assert artifact.provenance["run_identity"]["certainty"] == "unknown"
    assert artifact.provenance["field_disposition"]["relative_humidity_2m"].startswith("deferred:")
    assert artifact.provenance["evidence_classes"] == ["reprocessed"]
    import zarr
    with xarray.open_zarr(zarr.storage.ZipStore(artifact.payload_path, mode="r"), consolidated=False) as dataset:
        assert set(dataset.data_vars) >= {"temperature_2m", "total_cloud_geometric", "wind_speed_10m"}
        assert dataset.wind_speed_10m.attrs["units"] == "m s-1"
    assert "models=" in client.urls[0] and "elevation=nan" in client.urls[0] and "cell_selection=nearest" in client.urls[0]


def test_multi_model_suffixes_are_required_and_missing_array_is_disclosed(tmp_path):
    payload = forecast("jma_gsm", omit=("cloud_cover_high",))
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(payload))
    result = adapter.fetch(adapter.discover(window())[0], window(), tmp_path)
    assert result.artifacts[0].provenance["field_disposition"]["cloud_high"].startswith("missing:")


@pytest.mark.parametrize("payload,match", [
    (b"{", "malformed provider JSON"),
    ({"hourly": {}}, "missing hourly"),
])
def test_malformed_and_partial_responses_fail_closed(tmp_path, payload, match):
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(payload))
    if isinstance(payload, bytes):
        with pytest.raises(AdapterUnavailable, match=match): adapter.discover(window())
    else:
        candidate = adapter.discover(window())[0]
        with pytest.raises(AdapterUnavailable, match=match): adapter.fetch(candidate, window(), tmp_path)


def test_throttling_is_unavailable_and_never_a_run():
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))
    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(error=httpx.HTTPStatusError("429", request=response.request, response=response)))
    with pytest.raises(AdapterUnavailable, match="request failed"): adapter.discover(window())


def test_bright_sky_refuses_nearest_station_and_reads_exact_station(tmp_path):
    adapter = BrightSkyMosmix71801Adapter(Client({"sources": [{"wmo_station_id": "10147"}], "weather": []}))
    with pytest.raises(AdapterUnavailable, match="nearest-station fallback forbidden"): adapter.discover(window())

    exact_payload = {"sources": [{"id": 1228, "wmo_station_id": "71801", "lat": 47.62, "lon": -52.73, "station_name": "ST.JOHNS NEUFUNDL."}], "weather": [
        {"timestamp": "2026-09-05T01:00:00Z", "temperature": 13.3, "dew_point": 10.2, "cloud_cover": 94, "visibility": 9800, "pressure_msl": 1014.2, "wind_speed": 18.0, "wind_direction": 118, "precipitation": 0.0}
    ]}
    exact = BrightSkyMosmix71801Adapter(Client(exact_payload))
    candidate = exact.discover(window())[0]
    result = exact.fetch(candidate, window(), tmp_path)
    assert result.complete and result.artifacts[0].provenance["station"]["wmo_station_id"] == "71801"
    assert "wmo_station_id=71801" in candidate.urls[0]
    assert result.artifacts[0].provenance["field_disposition"]["condition"].startswith("deferred:")


def test_immutable_artifact_reads_back_through_the_astraeus_point_api(tmp_path, monkeypatch):
    import sys
    api_module = sys.modules["weather_api.app"]
    import zarr

    adapter = OpenMeteoAdapter("openmeteo-jma-gsm", client=Client(forecast()))
    artifact = adapter.fetch(adapter.discover(window())[0], window(), tmp_path).artifacts[0]

    class ArtifactBackedStore:
        skipped = []
        unmodelled = []
        def sample_point(self, latitude, longitude, valid_time, **_kwargs):
            with xarray.open_zarr(zarr.storage.ZipStore(artifact.payload_path, mode="r"), consolidated=False) as dataset:
                value = float(dataset.temperature_2m.sel(valid_time="2026-09-05T01:00:00").values[0, 0])
            return [Sample(source_id="openmeteo-jma-gsm", logical_name="surface", variable="temperature_2m", value=value, units="degC", evidence_class="reprocessed", level="2 m", valid_time=valid_time, run_time=None, retrieved_at=None, native_crs="EPSG:4326", provenance=artifact.provenance)]
        def source_activity(self): return {}

    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: ArtifactBackedStore())
    monkeypatch.setitem(api_module.PRODUCT_SOURCE_IDS, "JMA-GSM-EXPERIMENT", "openmeteo-jma-gsm")
    response = TestClient(app).get(f"{PREFIX}/point", params={"product": "JMA-GSM-EXPERIMENT", "valid_time": "2026-09-05T01:00:00Z"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["operational"] is False and payload["data_mode"] == "live"
    assert payload["fields"][0]["value"] == 2.0
    assert payload["fields"][0]["provenance"]["source_id"] == "openmeteo-jma-gsm"
