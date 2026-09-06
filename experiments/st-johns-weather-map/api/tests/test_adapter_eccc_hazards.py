from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from ingest.adapters.eccc_hazards import ECCCHurricaneProductsAdapter, ECCCThunderstormOutlookAdapter, MAX_COLLECTION_BYTES
from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.http import PoliteClient, USER_AGENT
from weather_api.app import PREFIX, app
from weather_api.store import LiveStore

UTC = timezone.utc
NOW = datetime(2026, 9, 6, 3, tzinfo=UTC)
WINDOW = FetchWindow(NOW)


def client(documents):
    def handler(request: httpx.Request) -> httpx.Response:
        collection = request.url.path.split("/")[2]
        return httpx.Response(200, content=json.dumps(documents[collection]).encode())
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})
    return result


def collection(features):
    return {"type": "FeatureCollection", "features": features, "numberMatched": len(features)}


def test_thunderstorm_preserves_all_properties_and_geometry(tmp_path):
    feature = {"type": "Feature", "id": "atlantic-v2", "geometry": {"type": "Polygon", "coordinates": []},
               "properties": {"datetime": NOW.isoformat(), "ThunderstormOutlook": "Thunderstorm Outlook", "version": "v2", "category": "MRGL"}}
    adapter = ECCCThunderstormOutlookAdapter(client({"thunderstorm_outlook": collection([feature])}), base_url="https://fixture.invalid")
    candidate = adapter.discover(WINDOW)
    result = adapter.fetch(candidate[0], WINDOW, tmp_path)
    stored = json.loads(result.artifacts[0].payload_path.read_text())
    assert stored["features"] == [feature]
    assert not result.complete and result.qc_passed
    assert result.artifacts[0].provenance["operational"] is False
    assert result.artifacts[0].provenance["quality"]["status"] == "suspect"
    assert result.artifacts[0].provenance["quality"]["flags"] == ["manifest_unresolved"]
    dispositions = result.artifacts[0].provenance["field_dispositions"]
    assert dispositions["geometry"] == "retrieved"
    assert dispositions["publication_datetime"] == "missing-in-snapshot"
    assert result.artifacts[0].provenance["uncontracted_properties"] == ["ThunderstormOutlook", "category", "datetime", "version"]


def test_hurricane_seasonal_empty_is_success_for_all_four_collections(tmp_path):
    documents = {name: collection([]) for name in ECCCHurricaneProductsAdapter.collections}
    adapter = ECCCHurricaneProductsAdapter(client(documents), base_url="https://fixture.invalid")
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    assert candidate.run_time is None
    assert candidate.detail["valid_times"] == []
    assert candidate.detail["query_window"] == {"start": WINDOW.start.isoformat(), "end": WINDOW.end.isoformat()}
    assert result.run_time is None
    assert len(result.artifacts) == 4 and not result.complete and result.qc_passed
    assert all(item.provenance["empty_is_an_answer"] for item in result.artifacts)
    assert all(item.provenance["coverage"]["status"] == "observed-empty" for item in result.artifacts)
    assert all(set(item.provenance["field_dispositions"].values()) == {"observed-empty"} for item in result.artifacts)
    assert all(item.provenance["valid_times"] == [] for item in result.artifacts)
    assert all(item.provenance["query_window"] == candidate.detail["query_window"] for item in result.artifacts)


def test_missing_collection_fails_closed_before_artifact_write(tmp_path):
    documents = {name: collection([]) for name in ECCCHurricaneProductsAdapter.collections}
    adapter = ECCCHurricaneProductsAdapter(client(documents), base_url="https://fixture.invalid")
    candidate = adapter.discover(WINDOW)[0]
    del candidate.detail["documents"][ECCCHurricaneProductsAdapter.collections[-1]]
    with pytest.raises(AdapterUnavailable, match="missing a required collection"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_candidate_with_malformed_feature_fails_before_artifact_write(tmp_path):
    adapter = ECCCThunderstormOutlookAdapter(
        client({"thunderstorm_outlook": collection([])}), base_url="https://fixture.invalid"
    )
    candidate = adapter.discover(WINDOW)[0]
    candidate.detail["documents"]["thunderstorm_outlook"]["features"] = [
        {"type": "Feature", "properties": [], "geometry": None}
    ]
    with pytest.raises(AdapterUnavailable, match="properties are not an object"):
        adapter.fetch(candidate, WINDOW, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_oversized_response_is_unavailable():
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"x" * (MAX_COLLECTION_BYTES + 1))), headers={"User-Agent": USER_AGENT})
    with pytest.raises(AdapterUnavailable, match="invalid or oversized"):
        ECCCThunderstormOutlookAdapter(result).discover(WINDOW)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "not a GeoJSON FeatureCollection"),
        ({"type": "FeatureCollection", "features": ["bad"]}, "not a GeoJSON Feature"),
        ({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": [], "geometry": None}]}, "properties are not an object"),
        ({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": []}]}, "geometry is not an object or null"),
    ],
)
def test_malformed_collection_is_unavailable(document, message):
    adapter = ECCCThunderstormOutlookAdapter(client({"thunderstorm_outlook": document}), base_url="https://fixture.invalid")
    with pytest.raises(AdapterUnavailable, match=message):
        adapter.discover(WINDOW)


@pytest.mark.parametrize("status", [404, 503])
def test_http_failure_is_unavailable(status):
    result = PoliteClient(min_host_interval_seconds=0, attempts=1)
    result._client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, content=b"unavailable")),
        headers={"User-Agent": USER_AGENT},
    )
    with pytest.raises(AdapterUnavailable, match="invalid or oversized"):
        ECCCThunderstormOutlookAdapter(result).discover(WINDOW)


def test_nonpublishable_empty_snapshot_has_no_api_frame_or_source_time(tmp_path, monkeypatch):
    import importlib
    api_module = importlib.import_module("weather_api.app")

    adapter = ECCCThunderstormOutlookAdapter(client({"thunderstorm_outlook": collection([])}), base_url="https://fixture.invalid")
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path / "fetch")
    artifact = result.artifacts[0]

    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, _key, handle):
            with artifact.payload_path.open("rb") as source: shutil.copyfileobj(source, handle)

    record = SimpleNamespace(
        revision_id="hazard-proof-1", source_id="eccc-thunderstorm-outlooks",
        logical_name="thunderstorm_outlook", media_type=artifact.media_type,
        object_key="proof/thunderstorm.geojson", byte_size=artifact.byte_size,
        provenance=artifact.provenance, run_time=None, retrieved_at=result.retrieved_at,
        provider_run_id=result.provider_run_id, native_crs="OGC:CRS84",
    )
    class ArtifactStore:
        s3 = S3(); config = SimpleNamespace(bucket="test")
        def current_artifacts(self): return [record]
        def source_activity(self): return {record.source_id: record.retrieved_at}

    store = LiveStore(ArtifactStore(), tmp_path / "cache")
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)
    monkeypatch.setattr(api_module, "now", lambda: NOW)
    response = TestClient(app).get(
        f"{PREFIX}/layers/eccc-thunderstorm-outlooks-thunderstorm_outlook/features",
        params={"valid_time": NOW.isoformat()},
    )
    assert response.status_code == 404
    assert not result.complete
    assert json.loads(artifact.payload_path.read_text())["features"] == []
    assert artifact.provenance["valid_times"] == []
    assert artifact.provenance["query_window"] == {"start": WINDOW.start.isoformat(), "end": WINDOW.end.isoformat()}
    assert artifact.provenance["retrieved_at"] == result.retrieved_at.isoformat()
