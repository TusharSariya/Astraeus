"""Build deterministic native API fixtures through existing offline test seams.

Run from the experiment:
  uv run --project api python web/scripts/source-native-proof-fixture.py /tmp/native.json
Use --experiment-root to run this builder against an assembled worktree.

No raw live captures or provider access: ECMWF uses its existing MockTransport
and constructed one-cell decoder; Holyrood uses its existing constructed 1x1 GIF.
The images are contract fixtures, not representative radar or a legend proof.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
from io import BytesIO
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from zipfile import ZIP_STORED, ZipFile, ZipInfo


def build_native_fixtures(experiment_root: Path | None = None) -> dict:
    root = experiment_root or Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(root / "api"), str(root), str(root / "api/tests")]
    import pytest
    from fastapi.testclient import TestClient
    from test_ecmwf_query import Fixture, RUN, coordinator
    from test_source_point_integration import native_fixture
    import httpx
    from test_swob_query import Clocks, feature, fixture_document, query_service
    from test_holyrood_query import service
    from test_holyrood_api import SELECTED
    from test_experimental_holyrood_radar import GIF
    from weather_api.holyrood_api import holyrood_service
    from weather_api.store import DATA_MODE_ENV, reset_live_store
    from weather_api import source_delivery
    original_readers = source_delivery.source_readers

    app = importlib.import_module("weather_api.app")
    ecmwf = importlib.import_module("weather_api.ecmwf_query")
    store = importlib.import_module("weather_api.store")

    class FixtureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return RUN.astimezone(tz) if tz else RUN.replace(tzinfo=None)

    def stable_decoder(request):
        # Zip timestamps otherwise change the normalized artifact hash between
        # generator runs. Contents and native values come from the existing seam.
        metadata, encoded = native_fixture(request)
        stable = BytesIO()
        with ZipFile(BytesIO(encoded)) as original, ZipFile(stable, "w", compression=ZIP_STORED) as output:
            for name in sorted(original.namelist()):
                output.writestr(ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), original.read(name))
        return metadata, stable.getvalue()

    result, counts = {}, {}
    # The client ASGI transport remains in-process; any unexpected source socket
    # acquisition is refused independently of the intended mock transports.
    with pytest.MonkeyPatch.context() as monkey, patch("socket.create_connection", side_effect=AssertionError("Fixture provider transport forbidden")):
        monkey.setenv(DATA_MODE_ENV, "live")
        reset_live_store()
        monkey.setattr(app, "now", lambda: RUN)
        monkey.setattr(store, "datetime", FixtureDatetime)
        client = TestClient(app.app)
        for source, product, key in [("ecmwf-ifs", "IFS", "point_ifs"), ("ecmwf-aifs-single", "AIFS Single", "point_aifs_single")]:
            transport = Fixture(source)
            query = coordinator(transport, decoder=stable_decoder)
            def selected_query(selected_source, expected=source, query=query):
                if selected_source != expected:
                    raise AssertionError("Fixture source substituted")
                return query
            monkey.setattr(ecmwf, "ecmwf_query_coordinator", selected_query)
            # Preserve legacy point-adapter receipt coverage; Atlantic IFS has
            # separate native-grid fixtures in test_ifs_selection.py.
            def fixture_readers(source=source, query=query):
                readers = original_readers()
                if source == "ecmwf-ifs":
                    readers[source] = source_delivery.ECMWFSource(source, "ifs", lambda: query,
                        ("temperature_2m", "dew_point_2m", "relative_humidity_2m", "mean_sea_level_pressure", "total_cloud_geometric"), named_runs=False)
                return readers
            monkey.setattr(source_delivery, "source_readers", fixture_readers)
            params = {"latitude": 47.5, "longitude": -52.75, "valid_time": RUN.isoformat(), "product": product}
            response = client.get(f"{app.PREFIX}/point", params=params)
            response.raise_for_status()
            point = response.json()
            count = len(transport.calls)
            assert client.get(f"{app.PREFIX}/point", params=params).json()["fields"] == response.json()["fields"]
            assert len(transport.calls) == count
            point["data_mode"] = "fixture"
            point["notices"].append("Constructed native contract fixture; no provider request or live evidence")
            for field in point["fields"]:
                field["provenance"]["data_mode"] = "fixture"
                if field["provenance"]["source_acquisition"] is not None:
                    assert field["provenance"]["source_acquisition"]["source_id"] == source
            # Set-backed decoder fields have no ordering contract; serialize
            # their exact bodies in stable key order for shared-fixture drift.
            point["fields"].sort(key=lambda field: field["key"])
            result[key] = point
            counts[source] = count
            transport.client.close()

        swob = importlib.import_module("weather_api.swob_query")
        clocks, swob_calls = Clocks(), []
        swob_query = query_service(lambda request: swob_calls.append(str(request.url)) or httpx.Response(200, json=fixture_document(feature())), clocks)
        monkey.setattr(swob, "swob_query_service", lambda: swob_query)
        monkey.setattr(app, "now", lambda: clocks.wall)
        params = {"latitude": 47.5615, "longitude": -52.7126, "valid_time": clocks.wall.isoformat(), "product": "SWOB"}
        response = client.get(f"{app.PREFIX}/point", params=params)
        response.raise_for_status()
        point = response.json()
        assert len(point["fields"]) == 6 and not point["observation_unavailable"]
        point["data_mode"] = "fixture"
        point["notices"].append("Constructed SWOB contract fixture; no provider request or live evidence")
        for field in point["fields"]:
            field["provenance"]["data_mode"] = "fixture"
        point["fields"].sort(key=lambda field: field["key"])
        result["point_swob"] = point
        counts["eccc-swob"] = len(swob_calls)
        assert len(swob_calls) == 1

        query, calls, _clock, _responses = service()
        previous = app.app.dependency_overrides.get(holyrood_service)
        app.app.dependency_overrides[holyrood_service] = lambda: query
        try:
            path = f"{app.PREFIX}/sources/eccc-holyrood-cashr-dpqpe/images"
            response = client.get(path, params={"valid_time": SELECTED})
            response.raise_for_status()
            result["native_images_holyrood"] = response.json()
            encoded = {}
            for image in response.json()["images"]:
                byte_response = client.get(image["image_url"])
                byte_response.raise_for_status()
                assert byte_response.content == GIF
                encoded[image["image_url"]] = base64.b64encode(byte_response.content).decode("ascii")
            assert len(calls) == 3
            result["native_image_bodies_base64"] = encoded
            counts["eccc-holyrood-cashr-dpqpe"] = len(calls)
        finally:
            if previous is None:
                app.app.dependency_overrides.pop(holyrood_service, None)
            else:
                app.app.dependency_overrides[holyrood_service] = previous
            query._client.close()
        reset_live_store()
    result["native_fixture_proof"] = {"basis": "Constructed deterministic API fixtures; ECMWF native decoder seam and tiny 1x1 Holyrood GIF, not live evidence or representative radar", "provider_requests": 0, "mock_transport_reads": counts}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--experiment-root", type=Path)
    args = parser.parse_args()
    result = build_native_fixtures(args.experiment_root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["native_fixture_proof"]))
