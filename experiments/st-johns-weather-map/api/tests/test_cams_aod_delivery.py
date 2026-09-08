"""GOV-SPEC-004/006: named experimental CAMS point delivery without admission."""
from datetime import timedelta
import importlib

from fastapi.testclient import TestClient
import pytest

from test_openmeteo_cams_aod_query import NOW, payload, service
from weather_api.source_delivery import CAMSAODSource


@pytest.fixture
def cams(monkeypatch, data_mode):
    import weather_api.openmeteo_cams_aod_query as module
    query, client, elapsed = service()
    monkeypatch.setattr(module, "openmeteo_cams_aod_query_service", lambda: query)
    data_mode("live")
    return query, client, elapsed


def read_point(at=NOW):
    module = importlib.import_module("weather_api.app")
    return TestClient(module.app).get(f"{module.PREFIX}/point", params={
        "latitude": 47.5615, "longitude": -52.7126,
        "valid_time": at.isoformat(), "product": "CAMS AOD"})


def test_point_preserves_named_intermediary_evidence(cams):
    query, client, _ = cams
    value = 0.15
    client.payload = payload(values=[value])
    first = read_point()
    assert first.status_code == 200
    body = first.json()
    field, = body["fields"]
    assert field["value"] == value and field["key"] == "aerosol_optical_depth_550nm"
    provenance = field["provenance"]
    assert provenance["source_id"] == "openmeteo-cams-aod"
    assert provenance["run_time"] is None and provenance["valid_time"] == "2026-09-07T12:00:00Z"
    assert provenance["original_units"] == "" and provenance["normalized_units"] == "1"
    assert provenance["evidence_class"] == "reprocessed" and provenance["intermediary"] == "Open-Meteo"
    assert provenance["sampled_latitude"] == 47.55 and provenance["sampled_longitude"] == -52.7
    assert provenance["source_display_primary"] is False
    assert body["selection"]["mode"] == "evidence_only"
    assert body["selection"]["selected_source_id"] is None
    assert "three-hourly" in " ".join(body["notices"])
    assert body["observation_unavailable"][0]["source_id"] == "eccc-aqhi"
    assert read_point().json()["fields"] == body["fields"]
    assert len(client.calls) == 2  # One metadata and one point body; no repeat payload.
    assert query.query(47.5615, -52.7126, NOW).expires_at == NOW + timedelta(seconds=300)


@pytest.mark.parametrize("failure", ["non_hour", "missing_hour", "null", "failed"])
def test_missing_selected_hour_never_substitutes_other_evidence(cams, failure):
    _, client, _ = cams
    at = NOW
    if failure == "non_hour":
        at += timedelta(minutes=1)
    elif failure == "missing_hour":
        client.payload = payload(times=["2026-09-07T13:00"])
    elif failure == "null":
        client.payload = payload(values=[None])  # Existing all-null QC refusal stays closed.
    else:
        client.fail = True
    result = read_point(at)
    assert result.status_code == 200
    body = result.json()
    assert body["data_mode"] == "unavailable" and body["fields"] == []
    assert body["selection"]["badge"] == "CAMS AOD unavailable"
    assert "fixture unavailable" not in str(body)
    if failure == "non_hour":
        assert client.calls == []


def test_cams_descriptor_is_lazy_point_only_and_refuses_run_before_io():
    from weather_api.native_runs import RunUnavailable
    reader = CAMSAODSource(lambda: pytest.fail("unsupported run instantiated a client"))
    capability, = reader.descriptors()
    assert capability.point_product == "CAMS AOD" and capability.point
    assert not capability.native_series and capability.run_selection == "not_applicable"
    assert reader.plan_series(NOW, NOW + timedelta(hours=1)) is None
    with pytest.raises(RunUnavailable):
        reader.read_point(47.5, -52.7, NOW, run="invented-run")
