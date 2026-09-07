from __future__ import annotations

import json

import pytest

from ingest.contract import ATLANTIC_CONTEXT_BOUNDS
from weather_api.ovation_query_worker import BOUNDS, normalized


def payload(coordinates):
    return json.dumps({
        "type": "FeatureCollection", "Data Format": "[Longitude, Latitude, Aurora]",
        "Observation Time": "2026-09-07T01:00:00Z", "Forecast Time": "2026-09-07T01:40:00Z",
        "coordinates": coordinates,
    }).encode()


def test_current_document_uses_the_existing_atlantic_crop_and_preserves_zero():
    assert BOUNDS == ATLANTIC_CONTEXT_BOUNDS
    decoded = normalized(payload([
        [-53, 47, 0], [307, 48, 11], [-71, 47, 99], [-53, 56, 99], [0, -90, 1],
    ]))
    assert decoded["cells"] == [[47.0, -53.0, 0.0], [48.0, -53.0, 11.0]]
    assert decoded["observation_time"] == "2026-09-07T01:00:00+00:00"
    assert decoded["forecast_time"] == "2026-09-07T01:40:00+00:00"


@pytest.mark.parametrize("coordinates", [
    [[-53, 47, 1], [-53, 47, 2]],
    [[-53, 47, -1]],
    [[-53, 47, 101]],
    [[-53, 47]],
])
def test_malformed_or_ambiguous_native_cells_are_rejected(coordinates):
    with pytest.raises(ValueError):
        normalized(payload(coordinates))


def test_tuple_axis_declaration_is_required_before_coordinates_are_decoded():
    body = json.loads(payload([[-53, 47, 1]]))
    body["Data Format"] = "[Latitude, Longitude, Aurora]"
    with pytest.raises(ValueError, match="Data Format"):
        normalized(json.dumps(body).encode())
