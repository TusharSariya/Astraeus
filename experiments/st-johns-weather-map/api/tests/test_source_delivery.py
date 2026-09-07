"""Maps api-first-source-delivery identity, capability and shared wire scenarios."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from weather_api.desktop_series import NativeForecastReader, SeriesResponse, SeriesSelection
from weather_api.fixtures import point_fields
from weather_api.models import CatalogResponse, PointResponse, SourceStatusResponse
from weather_api.source_contract import SourceVariant
from weather_api.source_delivery import AQHISource, ForecastSource, reading_identity, source_readers

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def test_shared_fixture_validates_actual_response_models():
    path = Path(__file__).parents[2] / "contracts/fixtures/source-delivery.json"
    fixture = json.loads(path.read_text())
    contract = json.loads((path.parents[1] / "source-api.openapi.json").read_text())
    # Wire responses include Pydantic computed output properties, which are
    # deliberately not accepted back as model constructor inputs.
    for key, model in [("catalog", CatalogResponse), ("status", SourceStatusResponse), ("series", SeriesResponse),
                       ("point_aqhi", PointResponse), ("point_aqhi_unavailable", PointResponse)]:
        Draft202012Validator({"$ref": f"#/components/schemas/{model.__name__}",
                              "components": contract["components"]}).validate(fixture[key])
    stamps = [sample["provenance"]["valid_time"] for sample in fixture["series"]["series"][0]["samples"]]
    assert len(stamps) == 2 and stamps[0] != stamps[1]


def test_descriptors_do_not_instantiate_provider_clients(monkeypatch):
    import weather_api.gfs_query as gfs
    import weather_api.aqhi_query as aqhi
    def forbidden():
        pytest.fail("catalogue caused provider work")
    monkeypatch.setattr(gfs, "gfs_query_coordinator", forbidden)
    monkeypatch.setattr(aqhi, "aqhi_query_service", forbidden)
    readers = source_readers()
    assert readers["noaa-gfs"].descriptors()[0].native_series
    assert readers["eccc-aqhi"].descriptors()[0].point
    assert not readers["eccc-aqhi"].descriptors()[0].native_series


def test_both_existing_point_shapes_share_one_seam():
    field = point_fields(NOW)[0][0]
    field.provenance.source_id = "noaa-gfs"
    calls = []
    class Forecast:
        def run_inventory(self):
            return ()
        def point_fields(self, lat, lon, at, **options):
            calls.append((lat, lon, at, options))
            return [field], None, ["noaa-gfs"]
    reader = ForecastSource("noaa-gfs", "gfs", Forecast, ("temperature_2m",), named_runs=True)
    result = reader.read_point(47.5, -52.7, NOW)
    assert calls[-1][-1] == {}  # Latest is source default, never a fabricated named run.
    reader.read_point(47.5, -52.7, NOW, run="2026090706", refresh=True)
    assert calls[-1][-1] == {"run_id": "2026090706", "refresh": True}
    result[0].value = 999
    assert field.value != 999
    field.provenance.source_id = "eccc-aqhi"
    aqhi = AQHISource(lambda: SimpleNamespace(point_field=lambda *a, **k: field))
    assert aqhi.read_point(47.5, -52.7, NOW)[0] == field
    assert aqhi.plan_series(NOW, NOW + timedelta(hours=1)) is None


def test_explicit_unsupported_identity_is_refused_before_acquisition(monkeypatch):
    import weather_api.gfs_query as gfs
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    monkeypatch.setattr(gfs, "gfs_query_coordinator", lambda: pytest.fail("unsupported identity fetched"))
    request = SeriesSelection(latitude=47.5, longitude=-52.7, start=NOW, end=NOW + timedelta(hours=1),
        selectors=[{"id": "a", "source_id": "noaa-gfs", "field": "temperature_2m", "product_id": "different-product"}])
    row = NativeForecastReader()(request, lambda: False)[0]
    assert row.availability == "unavailable" and not row.samples


def test_variant_parameters_do_not_alias():
    base = dict(kind="provider_statistic", statistic="ensemble_threshold_probability", comparison="ge")
    assert SourceVariant(**base, threshold=1) != SourceVariant(**base, threshold=2)
    with pytest.raises(ValidationError):
        SourceVariant(kind="deterministic", member="0")
    with pytest.raises(ValidationError):
        SourceVariant(kind="provider_statistic", statistic="ensemble_threshold_probability", threshold=1)
    field = point_fields(NOW)[0][0]
    first = reading_identity(field, "hrdps")
    field.provenance.valid_time += timedelta(hours=1)
    assert reading_identity(field, "hrdps") != first


def test_native_read_cannot_substitute_a_member_for_a_deterministic_selector(monkeypatch):
    import weather_api.source_delivery as delivery
    monkeypatch.setenv("WEATHER_DATA_MODE", "live")
    field = point_fields(NOW)[0][0]
    field.provenance.source_id = "noaa-gfs"
    field.provenance.valid_time = NOW
    field.provenance.run_time = NOW - timedelta(hours=6)
    field.provenance.member = "provider-member-0"
    reader = ForecastSource("noaa-gfs", "gfs", lambda: None, ("temperature_2m",), named_runs=True)
    reader.plan_series = lambda *args, **kwargs: delivery.NativePlan((delivery.NativeFrame(NOW),))
    reader.read_point = lambda *args, **kwargs: (field,)
    monkeypatch.setattr(delivery, "source_readers", lambda: {reader.source_id: reader})
    request = SeriesSelection(latitude=47.5, longitude=-52.7, start=NOW, end=NOW + timedelta(hours=1),
        selectors=[{"id": "a", "source_id": reader.source_id, "field": "temperature_2m",
                    "product_id": "gfs", "variant": {"kind": "deterministic"}, "level": "2m"}])
    # Use the catalogue's canonical spelling, independent from native GRIB labels.
    request.selectors[0].level = reader.descriptors()[0].levels[0]
    row = NativeForecastReader()(request, lambda: False)[0]
    assert row.availability == "unknown" and not row.samples
