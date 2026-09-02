"""The frame contract every drawable layer owes its client, layer by layer.

Two rules, asserted the same way for every layer that publishes a frame axis:

    **A frame the layer index advertises right now must render.**
    **An instant beyond the layer's tolerance is refused, naming what exists.**

A client learns which instants exist from ``/layers`` and then asks for one of
them by name. While the two agree, the frame draws. Between those two requests
the store may roll forward; a layer whose artifact holds a SINGLE scan then
loses the instant the client is holding the moment the next scan lands.

The server does not substitute a neighbour for it. Beyond the declared
staleness tolerance the answer is a 422 naming the nearest stored frame, per
the accepted map-layers requirement "A layer declares a staleness tolerance and
renders nothing beyond it" and the `goes19-cloud-mask-overlay` requirement
"Frames are observed scans only and staleness fails closed". Fallback is the
web map's job, not this API's: `frame-fallback-and-viewport-layout` puts it in
``web/src/`` behind a visible on-map disclosure, previous-only for observed
groups, and states that the server-side 422 rules are unchanged. So the 422
here is the contract holding, and its body is what lets the client disclose a
neighbour instead of guessing one.

Stub-driven, so this runs in ``make test`` with no stack. The sweep over the
real catalogue on a running stack is ``test_layer_contract_live.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy
import pytest
import xarray
from fastapi.testclient import TestClient

import weather_api.app  # noqa: F401
from weather_api import aurora, satellite
from weather_api.app import PREFIX, app
from tests.test_aurora_layer import (
    CELL_BOUNDS as AURORA_BOUNDS,
    FORECAST_INSTANT,
    LATS as AURORA_LATS,
    LONS as AURORA_LONS,
    PROBS as AURORA_PROBS,
    ovation_artifact,
)
from tests.test_rendered_grids import use_store
from tests.test_satellite_layer import (
    CELL_BOUNDS as MASK_BOUNDS,
    CLASSES,
    LATS as MASK_LATS,
    LONS as MASK_LONS,
    PROBS as MASK_PROBS,
    MaskStore,
    goes_artifact,
    scan_times,
)

client = TestClient(app)

#: A real ACMF cadence step, the interval the store actually rolls by.
TWO_SCANS = numpy.timedelta64(20, "m")


def _stamp(moment) -> numpy.datetime64:
    return numpy.datetime64(moment.replace(tzinfo=None), "ns")


def single_scan_mask(offset: numpy.timedelta64 = numpy.timedelta64(0, "m")) -> xarray.Dataset:
    """The cloud-mask artifact as the adapter really publishes it: ONE scan.

    ``mask_dataset()`` in the layer's own suite carries two, which is why that
    suite cannot see the race this module is about.
    """
    zero = numpy.zeros_like(CLASSES)
    return xarray.Dataset(
        {
            "cloud_class": (("valid_time", "latitude", "longitude"), CLASSES[None, ...].copy()),
            "cloud_probability": (("valid_time", "latitude", "longitude"), MASK_PROBS[None, ...].copy()),
            "parallax_uncorrected": (("valid_time", "latitude", "longitude"), zero[None, ...].copy()),
        },
        coords={
            "valid_time": [_stamp(scan_times()[-1]) + offset],
            "latitude": MASK_LATS,
            "longitude": MASK_LONS,
        },
    )


def single_frame_aurora(offset: numpy.timedelta64 = numpy.timedelta64(0, "m")) -> xarray.Dataset:
    return xarray.Dataset(
        {"aurora_probability": (("valid_time", "latitude", "longitude"), AURORA_PROBS[None, ...].copy(), {"units": "percent"})},
        coords={
            "valid_time": [_stamp(FORECAST_INSTANT) + offset],
            "latitude": AURORA_LATS,
            "longitude": AURORA_LONS,
        },
    )


class StubStore(MaskStore):
    """``MaskStore`` with the artifact the layer under test expects."""

    def __init__(self, dataset, artifact):
        super().__init__(dataset, artifact=artifact)


#: Every layer that renders from a published artifact through its own module,
#: with the store that backs it and the extent to ask over. Adding a layer here
#: subjects it to the whole contract below.
ARTIFACT_LAYERS = [
    pytest.param(satellite.LAYER_ID, single_scan_mask, goes_artifact, MASK_BOUNDS, id="goes19-cloud-mask"),
    pytest.param(aurora.LAYER_ID, single_frame_aurora, ovation_artifact, AURORA_BOUNDS, id="swpc-aurora-oval"),
]


def _advertised_times(layer_id: str) -> list[str]:
    """Exactly what the index tells a client it may ask for."""
    response = client.get(f"{PREFIX}/layers")
    assert response.status_code == 200
    for layer in response.json()["layers"]:
        if layer["id"] == layer_id:
            return list(layer["times"])
    return []


def _raster(layer_id: str, stamp: str, bounds):
    return client.get(
        f"{PREFIX}/layers/{layer_id}/raster",
        params={"valid_time": stamp, "width": 8, "height": 8, **bounds},
    )


@pytest.mark.parametrize(("layer_id", "dataset", "artifact", "bounds"), ARTIFACT_LAYERS)
def test_every_advertised_frame_renders(monkeypatch, data_mode, layer_id, dataset, artifact, bounds):
    """The index and the render path agree about what exists, right now."""
    use_store(monkeypatch, data_mode, StubStore(dataset(), artifact()))
    times = _advertised_times(layer_id)
    assert times, f"{layer_id} advertised no frames to test"
    for stamp in times:
        response = _raster(layer_id, stamp, bounds)
        assert response.status_code == 200, (
            f"{layer_id} advertised {stamp} but renders {response.status_code}: {response.text}"
        )


@pytest.mark.parametrize(("layer_id", "dataset", "artifact", "bounds"), ARTIFACT_LAYERS)
def test_a_frame_rolled_beyond_tolerance_is_refused_naming_the_nearest_scan(
    monkeypatch, data_mode, layer_id, dataset, artifact, bounds
):
    """The single-scan race is refused, not silently substituted.

    The client reads the index, holds the instant, and asks for it two cadence
    steps later, by which time the only stored scan has been replaced by one
    twenty minutes on - beyond the one native interval (600 s) the layer
    tolerates. The server neither draws that newer scan nor invents one: it
    answers 422 and names the instant it does hold, which is exactly what the
    web map needs to disclose a neighbouring frame under its own previous-only
    fallback rules.
    """
    use_store(monkeypatch, data_mode, StubStore(dataset(), artifact()))
    advertised = _advertised_times(layer_id)
    assert advertised, f"{layer_id} advertised no frames to test"
    held = advertised[-1]

    # Two cadence steps: later scans land and replace the only one stored.
    use_store(monkeypatch, data_mode, StubStore(dataset(TWO_SCANS), artifact()))

    response = _raster(layer_id, held, bounds)
    assert response.status_code == 422, (
        f"{layer_id} no longer stores {held}, which is beyond its tolerance, so it must be "
        f"refused rather than answered with a neighbouring scan: {response.status_code} {response.text}"
    )
    # The refusal has to say what DOES exist, or the client cannot disclose a
    # fallback frame without guessing at one.
    nearest = datetime.fromisoformat(held.replace("Z", "+00:00")) + timedelta(minutes=20)
    detail = response.json()["detail"]
    assert nearest.isoformat() in detail, (
        f"{layer_id} refused {held} without naming the nearest stored frame "
        f"{nearest.isoformat()}: {detail}"
    )
