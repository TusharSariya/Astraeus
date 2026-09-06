from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ingest.contract import AdapterUnavailable, FetchWindow
from ingest.experimental.nl_air_quality import MAX_CSV_BYTES, NLAirQualityAdapter
from weather_api.app import PREFIX, app
from weather_api.store import LiveStore

UTC = timezone.utc
FIXTURE = Path(__file__).parent / "fixtures/nl_air_quality/stjohns-line.trimmed.csv"
WINDOW = FetchWindow(datetime(2026, 9, 6, 3, 0, tzinfo=UTC), back_hours=6, forward_hours=0)


class Client:
    def __init__(self, body: bytes | None = None, error: Exception | None = None):
        self.body = FIXTURE.read_bytes() if body is None else body
        self.error = error
        self.calls = []

    def download(self, url, path, *, max_bytes):
        self.calls.append((url, max_bytes))
        if self.error:
            raise self.error
        if len(self.body) > max_bytes:
            raise ValueError("too large")
        path.write_bytes(self.body)


def test_fixture_enumerates_fields_converts_time_and_preserves_units(tmp_path):
    client = Client()
    adapter = NLAirQualityAdapter(client=client)
    candidate = adapter.discover(WINDOW)[0]
    result = adapter.fetch(candidate, WINDOW, tmp_path)
    artifact = result.artifacts[0]
    assert client.calls == [(candidate.urls[0], MAX_CSV_BYTES)]
    assert candidate.provider_run_id.startswith("stjohns-provisional-202609052330-")
    assert result.complete and result.qc_passed and result.run_time is None
    assert artifact.provenance["quality"] == {"status": "unknown", "flags": ["provisional", "not_quality_controlled"]}
    assert artifact.provenance["evidence_classes"] == ["uncalibrated_observation"]
    assert artifact.provenance["operational"] is False
    assert artifact.provenance["redistribution"] is False
    assert set(artifact.provenance["field_disposition"]) == {
        "STAT_NUM", "DATE_TIME", "PM2_5_RUN_AVG", "PM10_RUN_AVG", "NO", "NO2", "NOX", "O3", "SO2", "CO",
    }

    import xarray
    import zarr
    store = zarr.storage.ZipStore(str(artifact.payload_path), mode="r")
    dataset = xarray.open_zarr(store, consolidated=False)
    assert dataset.pm2_5_surface_24h_mean.attrs == {
        "units": "kg m-3", "original_units": "ug m-3", "quality_control": "provisional_unvalidated",
        "reporting_interval": "trailing_24_hours", "reporting_interval_hours": 24,
    }
    assert dataset.pm2_5_surface_24h_mean.values[-1, 0, 0] == pytest.approx(5.7e-9)
    assert dataset.ozone_surface_mole_fraction.attrs["original_units"] == "ppb"
    assert dataset.ozone_surface_mole_fraction.values[-1, 0, 0] == pytest.approx(27.8)


@pytest.mark.parametrize("mutation,match", [
    (lambda text: text.replace("PROVISIONAL", "FINAL", 1), "provisional quality warning"),
    (lambda text: text.replace("STAT_NUM,", "UNKNOWN,", 1), "columns changed"),
    (lambda text: text.replace("StJohns,", "MountPearl,", 1), "foreign station"),
    (lambda text: text.replace(",27.8,", ",bad,"), "invalid O3"),
])
def test_schema_identity_quality_and_values_fail_closed(mutation, match):
    adapter = NLAirQualityAdapter(client=Client(mutation(FIXTURE.read_text()).encode()))
    with pytest.raises(AdapterUnavailable, match=match):
        adapter.discover(WINDOW)


def test_empty_window_and_oversized_or_failed_request_are_unavailable():
    old = FetchWindow(datetime(2026, 8, 1, tzinfo=UTC), back_hours=1, forward_hours=0)
    with pytest.raises(AdapterUnavailable, match="no rows"):
        NLAirQualityAdapter(client=Client()).discover(old)
    with pytest.raises(AdapterUnavailable, match="request failed"):
        NLAirQualityAdapter(client=Client(b"x" * (MAX_CSV_BYTES + 1))).discover(WINDOW)
    with pytest.raises(AdapterUnavailable, match="request failed"):
        NLAirQualityAdapter(client=Client(error=RuntimeError("503"))).discover(WINDOW)


@pytest.mark.parametrize("stamp,match", [
    ("3/8/2026 2:30:00 AM", "nonexistent local timestamp"),
    ("11/1/2026 1:30:00 AM", "ambiguous local timestamp"),
])
def test_dst_gap_and_fold_fail_without_a_provider_offset(stamp, match):
    body = FIXTURE.read_text().replace("9/5/2026 7:00:00 PM", stamp).encode()
    broad = FetchWindow(datetime(2026, 9, 6, tzinfo=UTC), back_hours=24 * 365, forward_hours=24 * 365)
    with pytest.raises(AdapterUnavailable, match=match):
        NLAirQualityAdapter(client=Client(body)).discover(broad)


def test_fetch_rechecks_window_and_uses_discovery_capture_time(tmp_path):
    adapter = NLAirQualityAdapter(client=Client())
    candidate = adapter.discover(WINDOW)[0]
    narrowed = FetchWindow(datetime(2026, 9, 5, 23, 30, tzinfo=UTC), back_hours=2, forward_hours=0)
    result = adapter.fetch(candidate, narrowed, tmp_path)
    assert result.retrieved_at == candidate.detail["captured_at"]
    assert result.artifacts[0].provenance["valid_times"] == ["2026-09-05T21:30:00Z", "2026-09-05T22:30:00Z", "2026-09-05T23:30:00Z"]
    with pytest.raises(AdapterUnavailable, match="current fetch window"):
        adapter.fetch(candidate, FetchWindow(datetime(2026, 9, 7, tzinfo=UTC), back_hours=1, forward_hours=0), tmp_path)


def test_missing_selected_value_is_partial_and_never_filled(tmp_path):
    body = FIXTURE.read_text().replace(",27.8,", ",,").encode()
    adapter = NLAirQualityAdapter(client=Client(body))
    result = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path)
    assert result.complete is False and result.qc_passed is True
    assert result.artifacts[0].provenance["missing_counts"]["ozone_surface_mole_fraction"] == 1


def test_artifact_reads_back_through_real_reader_and_http_point_api(tmp_path, monkeypatch):
    import sys
    api_module = sys.modules["weather_api.app"]
    adapter = NLAirQualityAdapter(client=Client())
    artifact = adapter.fetch(adapter.discover(WINDOW)[0], WINDOW, tmp_path).artifacts[0]

    class S3:
        def head_bucket(self, **_kwargs): return {}
        def download_fileobj(self, _bucket, _key, handle):
            with artifact.payload_path.open("rb") as source: shutil.copyfileobj(source, handle)

    record = SimpleNamespace(
        revision_id="nl-aq-proof-1", source_id=adapter.source_id, logical_name="air_quality",
        media_type=artifact.media_type, object_key="proof/nl-aq.zip", byte_size=artifact.byte_size,
        provenance=artifact.provenance, run_time=None, retrieved_at=datetime(2026, 9, 6, 3, 5, tzinfo=UTC),
        provider_run_id="stjohns-provisional", native_crs="EPSG:4326",
    )
    class ArtifactStore:
        s3 = S3(); config = SimpleNamespace(bucket="test")
        def current_artifacts(self): return [record]
        def source_activity(self): return {record.source_id: record.retrieved_at}

    store = LiveStore(ArtifactStore(), tmp_path / "cache")
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(api_module, "live_store", lambda: store)
    monkeypatch.setattr(api_module, "now", lambda: datetime(2026, 9, 6, 3, 0, tzinfo=UTC))
    monkeypatch.setitem(api_module.PRODUCT_SOURCE_IDS, "NL-AQ-EXPERIMENT", adapter.source_id)
    response = TestClient(app).get(f"{PREFIX}/point", params={"product": "NL-AQ-EXPERIMENT", "valid_time": "2026-09-05T23:30:00Z"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["operational"] is False and payload["data_mode"] == "live"
    fields = {item["field"]: item for item in payload["fields"]}
    assert fields["pm2_5_surface_24h_mean"]["value"] == pytest.approx(5.7e-9)
    assert fields["ozone_surface_mole_fraction"]["value"] == pytest.approx(27.8)
    for item in fields.values():
        assert item["provenance"]["evidence_class"] == "uncalibrated_observation"
        assert item["provenance"]["operational"] is False
