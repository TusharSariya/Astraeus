"""The frame contract every drawable layer owes its client, layer by layer.

One rule, asserted the same way for every layer that publishes a frame axis:

    **A frame the layer index advertised must render.**

A client learns which instants exist from ``/layers`` and then asks for one of
them by name. Between those two requests the store may roll forward. A layer
that keeps its history still holds the old instant, so the rule costs it
nothing. A layer whose artifact holds a SINGLE scan loses the instant the
client is holding the moment the next scan lands, and the render path then
refuses it - so the layer blanks, having advertised it moments earlier.

That is a contract break rather than a staleness policy. Fail-closed means
refusing to draw what was not retrieved; the newest scan of an observed layer
IS retrieved evidence, and it is the nearest thing that exists to what was
asked for. Refusing it draws nothing while the truthful answer - this scan, at
this instant, named in ``X-Weather-Valid-Time`` - was in hand. The client
already discloses a snapped frame; it cannot disclose a 422.

Stub-driven, so this runs in ``make test`` with no stack. The sweep over the
real catalogue on a running stack is ``test_layer_contract_live.py``.
"""

from __future__ import annotations

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
TEN_MINUTES = numpy.timedelta64(10, "m")


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
def test_a_frame_advertised_before_the_artifact_rolled_still_draws(
    monkeypatch, data_mode, layer_id, dataset, artifact, bounds
):
    """The single-scan race, which is what blanks GOES-19 on a live map.

    The client reads the index, holds the instant, and asks for it one cadence
    later. Nothing about that sequence is unusual - it is every client that
    does not re-read ``/layers`` between frames, which is all of them between
    catalogue polls. The layer must answer with the scan it does hold, naming
    that scan's own instant, rather than refusing and drawing nothing.
    """
    use_store(monkeypatch, data_mode, StubStore(dataset(), artifact()))
    advertised = _advertised_times(layer_id)
    assert advertised, f"{layer_id} advertised no frames to test"
    held = advertised[-1]

    # One cadence step: the next scan lands and replaces the only one stored.
    use_store(monkeypatch, data_mode, StubStore(dataset(TEN_MINUTES), artifact()))

    response = _raster(layer_id, held, bounds)
    assert response.status_code == 200, (
        f"{layer_id} advertised {held}; one scan later it renders {response.status_code}, "
        f"so a client holding the previous index draws nothing: {response.text}"
    )
    # Whatever it drew, it must date it honestly: the scan it holds, not the
    # instant that was asked for.
    assert response.headers["X-Weather-Valid-Time"] != held
