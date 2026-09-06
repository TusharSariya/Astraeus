from datetime import datetime, timezone
import importlib
from types import SimpleNamespace

import numpy
import xarray
from fastapi.testclient import TestClient

api = importlib.import_module("weather_api.app")
UTC = timezone.utc
PREFIX = "/api/experiments/weather/v0"


class TafStore:
    def __init__(self, *, broken=False, artifacts=True):
        self.released = []
        self.artifact = SimpleNamespace(
            source_id="awc-taf", logical_name="surface", revision_id="revision-1",
            run_time=datetime(2026, 9, 6, 11, 41, tzinfo=UTC),
            provenance={"valid_times": ["2026-09-06T12:00:00+00:00", "2026-09-06T13:00:00+00:00"],
                        "quality": {"status": "passed"}},
        )
        values = numpy.array([[[10.0]], [[numpy.nan]]])
        cloud = numpy.array([[[numpy.nan]], [[50.0]]])
        self.dataset = xarray.Dataset({"wind_gust_10m": (("valid_time", "latitude", "longitude"), values),
                                       "total_cloud_okta": (("valid_time", "latitude", "longitude"), cloud)}, attrs={
            "taf_period_time_to": [1788714000, 1788714000], "taf_change_groups": ["", "TEMPO"],
            "taf_probabilities": [None, 30],
            "taf_group_presence_json": '[{"wind_gust_10m":"decoded_value","total_cloud_okta":"decoded_value"},{"wind_gust_10m":"not_stated_in_change_group","total_cloud_okta":"decoded_value"}]',
            "taf_native_groups_json": '[{"wspd":20,"wdir":"VRB","wgst":30,"visib":"1/4","wxString":"FG","vertVis":100,"clouds":[{"cover":"OVX","base":null}]},{"wspd":null,"wdir":null,"wgst":null,"visib":"2","wxString":"BR","vertVis":null,"clouds":[]}]',
            "taf_native_report_metadata_json": '{"icaoId":"CYYT","elev":128}',
            "taf_provider_field_dispositions_json": '{"wgst":"published_as_wind_gust"}',
            "taf_issue_time": "2026-09-06T11:41:00Z", "taf_valid_time_from": 1788696000,
            "taf_valid_time_to": 1788782400, "raw_taf": "TAF CYYT ...",
        })
        if broken:
            del self.dataset.attrs["taf_period_time_to"]
        self.artifacts = artifacts

    def current(self): return [self.artifact] if self.artifacts else []
    def open(self, _artifact): return self.dataset
    def release_artifact(self, artifact): self.released.append(artifact)


def test_taf_route_preserves_overlapping_sparse_groups_and_releases(monkeypatch):
    store = TafStore()
    monkeypatch.setattr(api, "live_store", lambda: store)
    response = TestClient(api.app).get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T14:00:00Z"})
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [group["change"] for group in groups] == ["", "TEMPO"]
    assert groups[0]["values"]["wind_gust_10m"] == 10.0
    assert groups[1]["values"]["wind_gust_10m"] is None
    assert groups[1]["presence"]["wind_gust_10m"] == "not_stated_in_change_group"
    assert groups[0]["native"]["wind_variable"] is True
    assert groups[0]["native"]["wind_speed_kt"] == 20
    assert groups[0]["native"]["weather"] == "FG"
    assert groups[0]["native"]["vertical_visibility_ft"] == 100
    assert groups[0]["values"]["total_cloud_okta"] is None
    assert groups[0]["presence"]["total_cloud_okta"] == "decoded_absence"
    assert groups[0]["native_presence"]["wind_variable"] == "decoded_value"
    assert response.json()["operational"] is False
    assert response.json()["native_report_metadata"]["elev"] == 128
    assert store.released == [store.artifact]


def test_taf_route_uses_half_open_group_intervals(monkeypatch):
    store = TafStore()
    monkeypatch.setattr(api, "live_store", lambda: store)
    client = TestClient(api.app)
    at_start = client.get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T12:00:00Z"})
    at_end = client.get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": datetime.fromtimestamp(1788714000, tz=UTC).isoformat()})
    assert [g["index"] for g in at_start.json()["groups"]] == [0]
    assert at_end.json()["groups"] == []


def test_taf_route_releases_after_read_failure(monkeypatch):
    store = TafStore(broken=True)
    monkeypatch.setattr(api, "live_store", lambda: store)
    response = TestClient(api.app).get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T14:00:00Z"})
    assert response.status_code == 503
    assert store.released == [store.artifact]


def test_taf_route_rejects_naive_time_and_uncontracted_station(monkeypatch):
    monkeypatch.setattr(api, "live_store", lambda: TafStore())
    client = TestClient(api.app)
    assert client.get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T14:00:00"}).status_code == 422
    assert client.get(f"{PREFIX}/aviation/taf", params={"station": "KBOS", "at": "2026-09-06T14:00:00Z"}).status_code == 422


def test_taf_route_returns_404_without_publication(monkeypatch):
    monkeypatch.setattr(api, "live_store", lambda: TafStore(artifacts=False))
    response = TestClient(api.app).get(f"{PREFIX}/aviation/taf", params={"station": "CYYT", "at": "2026-09-06T14:00:00Z"})
    assert response.status_code == 404
