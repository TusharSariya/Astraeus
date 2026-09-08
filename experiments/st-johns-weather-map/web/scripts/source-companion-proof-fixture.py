"""Emit fixed TestClient companion responses outside Git using existing API test seams.

Run from the experiment with uv run --project api python
web/scripts/source-companion-proof-fixture.py /tmp/companion-proof.json.
No provider request is possible: AQHI uses the existing test MockTransport and
all forecast reads are replaced with the shared deterministic backend fixture.
"""
import importlib
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import pytest

root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / "api"), str(root)]
fixtures = runpy.run_path(str(root / "api/tests/test_observation_companions.py"))
from weather_api.models import PointResponse, Selection, DataMode, EvidenceField, AQHIDemandUnavailable
from weather_api.store import DATA_MODE_ENV, reset_live_store
from weather_api.aqhi_query import AqhiQueryUnavailable
from fastapi.testclient import TestClient

at = fixtures["NOW"]
shared = json.loads((root / "contracts/fixtures/source-delivery.json").read_text())
sample = shared["series"]["series"][0]["samples"][0]
# Output-only computed flag is restored by Pydantic when the response is emitted.
sample["provenance"].pop("display_primary_eligible", None)
field = EvidenceField.model_validate(sample)
response = PointResponse(data_mode=DataMode.FIXTURE, latitude=47.56, longitude=-52.72,
    valid_time=at, fields=[field], selection=Selection(mode="fallback", selected_source_id="eccc-hrdps",
    selected_product_id="hrdps", badge="HRDPS selected", reason="Deterministic TestClient proof, no provider retrieval"),
    notices=["CONSTRUCTED BACKEND CONTRACT PROOF; NOT LIVE EVIDENCE"])
with pytest.MonkeyPatch.context() as patch:
    patch.setenv(DATA_MODE_ENV, "live")
    reset_live_store()
    app = importlib.import_module("weather_api.app")
    aqhi = importlib.import_module("weather_api.aqhi_query")
    patch.setattr(app, "_live_point", lambda *args, **kwargs: response)
    service, requests = fixtures["aqhi"].__wrapped__(patch)
    client = TestClient(app.app)
    params = {"latitude":47.56, "longitude":-52.72, "valid_time":at.isoformat(), "product":"HRDPS"}
    success = client.get(f"{app.PREFIX}/point", params=params)
    success.raise_for_status()
    def fail(*args, **kwargs):
        raise AqhiQueryUnavailable("private-provider-exception", outcome=AQHIDemandUnavailable(reason="refresh_failed", error_type="HTTPStatusError"))
    patch.setattr(aqhi, "aqhi_query_service", lambda: SimpleNamespace(point_field=fail))
    failure = client.get(f"{app.PREFIX}/point", params=params)
    failure.raise_for_status()
    assert len(requests) == 1
    assert "private-provider-exception" not in failure.text
    Path(sys.argv[1]).write_text(json.dumps({"success":success.json(), "failure":failure.json(),
        "proof":{"basis":"fixed TestClient responses using existing test seam", "fixture_transport_requests":len(requests), "provider_requests":0}}, indent=2))
reset_live_store()
