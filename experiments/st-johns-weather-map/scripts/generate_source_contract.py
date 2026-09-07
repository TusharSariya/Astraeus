"""Generate source/Series OpenAPI and shared fixed fixtures from Pydantic.

Run: uv run --project api python scripts/generate_source_contract.py [--check]
Then: npm --prefix web run generate:source-types
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "api"), str(ROOT)]

from weather_api.app import app, PREFIX
from weather_api.desktop_series import Continuation, ReadingIdentity, SeriesResponse, SeriesRow, SeriesSelection, Snapshot
from weather_api.fixtures import point_fields
from weather_api.models import AQHIDemandUnavailable, CatalogResponse, DataMode, PointResponse, Selection, SourceStatusResponse
from weather_api.source_delivery import reading_identity
from weather_api.store import registry_source_records, registry_source_statuses


def contract():
    schema = app.openapi()
    paths = {path: value for path, value in schema["paths"].items()
             if path in {f"{PREFIX}/catalog", f"{PREFIX}/sources/status", f"{PREFIX}/point", f"{PREFIX}/point/series", f"{PREFIX}/point/series/changes"}}
    components = schema["components"]["schemas"]
    # The route keeps custom cursor/selection error codes by validating its
    # dictionary body itself. Its request schema still comes from those exact
    # Pydantic validators rather than an independently maintained wire model.
    continuation = Continuation.model_json_schema(ref_template="#/components/schemas/{model}")
    components["Continuation"] = continuation
    paths[f"{PREFIX}/point/series"]["post"]["requestBody"] = {
        "required": True, "content": {"application/json": {"schema": {"oneOf": [
            {"$ref": "#/components/schemas/SeriesSelection"}, {"$ref": "#/components/schemas/Continuation"}]}}}}
    needed = set()
    def collect(value):
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in needed:
                    needed.add(name)
                    collect(components[name])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(paths)
    return {"openapi": schema["openapi"], "info": {"title": "Astraeus experimental source delivery", "version": "1.0.0"},
            "paths": paths, "components": {"schemas": {key: components[key] for key in sorted(needed)}}}


def fixtures():
    now = datetime(2026, 9, 7, 12, tzinfo=UTC)
    source_ids = {"eccc-hrdps", "eccc-rdps", "eccc-gdps", "noaa-gfs", "eccc-aqhi", "openmeteo-cams-aod"}
    records = [record for record in registry_source_records() if record.id in source_ids]
    catalogue = CatalogResponse(data_mode=DataMode.FIXTURE, generated_at=now, sources=records)
    statuses = SourceStatusResponse(data_mode=DataMode.FIXTURE,
        statuses=[record for record in registry_source_statuses(reference=now) if record.source_id in source_ids],
        notices=["Deterministic contract fixture; no live retrieval is asserted"])
    selection = SeriesSelection(latitude=47.5123456789, longitude=-52.6987654321,
        start=now, end=now + timedelta(hours=3), page_size=12,
        selectors=[{"id": str(index), "source_id": "eccc-hrdps", "field": key}
                   for index, key in enumerate(("temperature_2m", "total_cloud_opacity"))])
    for selector in selection.selectors:
        capability = next(item for record in records if record.id == selector.source_id for item in record.capabilities if item.field == selector.field)
        selector.product_id, selector.variant, selector.level = capability.product_id, capability.variants[0], capability.levels[0]
    fields = point_fields(now)[0]
    rows = []
    identities = []
    for selector in selection.selectors:
        field = next(item for item in fields if item.key == selector.field).model_copy(deep=True)
        capability = next(item for record in records if record.id == selector.source_id for item in record.capabilities if item.field == selector.field)
        field.provenance.source_id = selector.source_id
        field.provenance.provider = field.provenance.forecast_centre = "ECCC"
        field.provenance.product = "HRDPS"
        field.provenance.run_time = now - timedelta(hours=6)
        field.provenance.retrieval_time = now
        field.provenance.vertical_level = capability.levels[0]
        field.provenance.native_resolution = "2.5 km"
        # Two actual fixture timestamps with a deliberate native gap. These
        # values are fixture evidence, never a capture of provider traffic.
        samples = [field]
        later = field.model_copy(deep=True)
        later.provenance.valid_time = now + timedelta(hours=2)
        samples.append(later)
        rows.append(SeriesRow(selector_id=selector.id, source_id=selector.source_id, field=selector.field,
            requested_run=selector.run, product_id=capability.product_id, variant=capability.variants[0], level=capability.levels[0],
            availability="available", reason="Fixed native-gap contract fixture", samples=samples))
        identities.extend(ReadingIdentity.model_validate(reading_identity(item, "hrdps").model_dump()) for item in samples)
    series = SeriesResponse(selection=selection, snapshot=Snapshot(id="source-contract-fixture",
        selected_at=now, expires_at=now + timedelta(minutes=5), change_token="fixture-only-token", identities=identities),
        series=rows, next_cursor=None, complete=True,
        notices=["Deterministic fixture. No provider request or live evidence."])
    point, failed_point = observation_fixtures(now, rows[0].samples[0])
    return {"catalog": catalogue.model_dump(mode="json"), "status": statuses.model_dump(mode="json"),
            "series": series.model_dump(mode="json"), "point_aqhi": point.model_dump(mode="json"),
            "point_aqhi_unavailable": failed_point.model_dump(mode="json"),
            "point_cams_aod": cams_fixture(now).model_dump(mode="json")}


def cams_fixture(now):
    """Offline named product fixture through the source adapter and point builder."""
    from unittest.mock import patch
    import importlib
    from weather_api.openmeteo_cams_aod_query import OpenMeteoCamsAodQueryService
    class Client:
        def download(self, url, path, **_options):
            body = ({"last_run_initialisation_time": now.timestamp()} if "meta.json" in url else {
                "latitude": 47.55, "longitude": -52.7, "utc_offset_seconds": 0,
                "hourly_units": {"time": "iso8601", "aerosol_optical_depth": ""},
                "hourly": {"time": [now.strftime("%Y-%m-%dT%H:%M")], "aerosol_optical_depth": [0.15]}})
            path.write_text(json.dumps(body))
    service = OpenMeteoCamsAodQueryService(client=Client(), clock=lambda: 0.0, utcnow=lambda: now)
    module = importlib.import_module("weather_api.app")
    with patch("weather_api.openmeteo_cams_aod_query.openmeteo_cams_aod_query_service", return_value=service):
        response = module._live_point(47.5615, -52.7126, now, product="CAMS AOD")
    response.data_mode = DataMode.FIXTURE
    response.notices.append("Deterministic fixture: no provider traffic or live evidence")
    for field in response.fields:
        field.provenance.data_mode = DataMode.FIXTURE
    return response


def observation_fixtures(now, forecast):
    """Exercise the actual companion composer with a fixed, offline transport.

    The serialized evidence is explicitly relabelled fixture after production
    composition; the source's admission predicate still receives its real type.
    """
    from unittest.mock import patch
    from types import SimpleNamespace
    import httpx
    from weather_api.aqhi_query import AQHIQueryService, AQHIStationObservation, AqhiQueryUnavailable
    from weather_api.observation_companions import with_aqhi_observation
    station = AQHIStationObservation("fixture-ABEFS", "Fixture St John's", now,
        47.5658, -52.7252, 2.7, "0", "fixture-native-report")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"{}"))) as client:
        service = AQHIQueryService(client=client, clock=lambda: 0.0, utcnow=lambda: now, decode=lambda _: (station,))
        response = PointResponse(data_mode=DataMode.FIXTURE, latitude=47.56, longitude=-52.72,
            valid_time=now + timedelta(minutes=30), fields=[forecast.model_copy(deep=True)],
            selection=Selection(mode="fallback", selected_source_id="eccc-hrdps", selected_product_id="hrdps",
                badge="HRDPS selected fixture", reason="Deterministic selected-model contract fixture"),
            notices=["Deterministic fixture: no provider traffic or live evidence"])
        with patch("weather_api.aqhi_query.aqhi_query_service", return_value=service):
            success = with_aqhi_observation(response)
    success.data_mode = DataMode.FIXTURE
    for field in success.fields:
        field.provenance.data_mode = DataMode.FIXTURE
    def failed(*args, **kwargs):
        raise AqhiQueryUnavailable("Fixed unavailable observation", outcome=AQHIDemandUnavailable(
            reason="query_failed", error_type="FixtureAcquisitionUnavailable"))
    with patch("weather_api.aqhi_query.aqhi_query_service", return_value=SimpleNamespace(point_field=failed)):
        unavailable = with_aqhi_observation(response)
    return success, unavailable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, value in [(ROOT / "contracts/source-api.openapi.json", contract()),
                        (ROOT / "contracts/fixtures/source-delivery.json", fixtures())]:
        content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Generated contract drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        print(f"{'Checked' if args.check else 'Generated'} {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
