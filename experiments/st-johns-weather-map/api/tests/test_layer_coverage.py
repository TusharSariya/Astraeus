"""Per-layer time axes and geometry: how a layer may be drawn, and when.

Two rules are under test. A layer is drawn only at a frame it actually
published, and an artifact is drawn as a field only when it holds a field.
Both exist because the alternative is a picture of weather that was never
measured.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy
import xarray

from ingest.store import CurrentArtifact
from weather_api.app import layer_kind, staleness_tolerance_seconds
from weather_api.store import LiveStore, layer_id_for

UTC = timezone.utc
START = datetime(2026, 8, 30, 3, 0, tzinfo=UTC)


def artifact(*, source_id: str, logical_name: str, media_type: str = "application/zarr+zip") -> CurrentArtifact:
    return CurrentArtifact(
        source_id=source_id,
        logical_name=logical_name,
        revision_id=f"revision-{source_id}-{logical_name}",
        object_key=f"artifacts/{source_id}/{logical_name}",
        media_type=media_type,
        byte_size=1024,
        provenance={},
        published_at=START,
        run_time=START,
        retrieved_at=START,
        provider_run_id="2026083003",
        native_crs="EPSG:4326",
    )


def series(*, latitudes: list[float], longitudes: list[float], stamps: list[datetime], value: float = 1.0) -> xarray.Dataset:
    shape = (len(stamps), len(latitudes), len(longitudes))
    return xarray.Dataset(
        {"radar_echo": (("valid_time", "latitude", "longitude"), numpy.full(shape, value), {"units": "flag"})},
        coords={
            "valid_time": numpy.array([numpy.datetime64(s.replace(tzinfo=None), "ns") for s in stamps]),
            "latitude": numpy.array(latitudes),
            "longitude": numpy.array(longitudes),
        },
    )


class StubStore(LiveStore):
    def __init__(self, pairs: list[tuple[CurrentArtifact, Any]]) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._pairs = pairs

    def current(self) -> list[CurrentArtifact]:
        return [item for item, _ in self._pairs]

    def open(self, item: CurrentArtifact) -> Any:
        return next(dataset for candidate, dataset in self._pairs if candidate.revision_id == item.revision_id)

    def assert_object_store_reachable(self) -> None:
        """Held open in memory; reachability has its own tests elsewhere."""


def test_each_layer_keeps_its_own_time_axis_and_cadence():
    six_minutely = [START + timedelta(minutes=6 * step) for step in range(5)]
    hourly = [START + timedelta(hours=step) for step in range(3)]
    store = StubStore(
        [
            (artifact(source_id="eccc-radar", logical_name="radar"), series(latitudes=[47.5], longitudes=[-52.7], stamps=six_minutely)),
            (artifact(source_id="awc-metar-speci", logical_name="surface"), series(latitudes=[47.6], longitudes=[-52.75], stamps=hourly)),
        ]
    )

    coverage = store.published_layer_times()

    assert coverage["eccc-radar-radar"].cadence_seconds == 360
    assert coverage["awc-metar-speci-surface"].cadence_seconds == 3600
    # The point of the refactor: two layers, two axes, neither resampled.
    assert coverage["eccc-radar-radar"].times == six_minutely
    assert coverage["awc-metar-speci-surface"].times == hourly


def test_cadence_is_modal_so_one_missing_frame_does_not_redefine_it():
    stamps = [START, START + timedelta(minutes=6), START + timedelta(minutes=12), START + timedelta(minutes=24)]
    store = StubStore([(artifact(source_id="eccc-radar", logical_name="radar"), series(latitudes=[47.5], longitudes=[-52.7], stamps=stamps))])

    # The mean gap here is 8 minutes, which the layer never publishes at.
    assert store.published_layer_times()["eccc-radar-radar"].cadence_seconds == 360


def test_a_small_station_outer_product_is_points_and_never_a_field():
    """AQHI stores three sampled stations as a 3x3 latitude/longitude product.

    Six of those nine cells were never measured. Calling it a grid would draw
    them, so geometry decides the representation and the small case is points.
    """
    dataset = series(latitudes=[47.08, 47.56, 48.93], longitudes=[-55.66, -55.17, -52.72], stamps=[START])
    store = StubStore([(artifact(source_id="eccc-aqhi", logical_name="aqhi"), dataset)])

    entry = store.published_layer_times()["eccc-aqhi-aqhi"]

    assert entry.gridded is False
    assert len(entry.sites) == 9
    assert layer_kind("application/zarr+zip", entry) == "point"


def test_a_real_field_is_a_raster():
    dataset = series(
        latitudes=[47.0 + 0.01 * step for step in range(20)],
        longitudes=[-53.0 + 0.01 * step for step in range(20)],
        stamps=[START],
    )
    store = StubStore([(artifact(source_id="eccc-hrdps", logical_name="surface"), dataset)])

    entry = store.published_layer_times()["eccc-hrdps-surface"]

    assert entry.gridded is True
    assert layer_kind("application/zarr+zip", entry) == "raster"


def test_an_artifact_whose_geometry_is_unknown_is_not_offered_as_a_layer():
    # No coverage entry means the geometry could not be established. Offering it
    # anyway would mean guessing how to draw it.
    assert layer_kind("application/zarr+zip", None) is None
    assert layer_kind("application/octet-stream", None) is None


def test_tolerance_is_one_native_interval_so_a_layer_answers_at_its_own_resolution():
    # One native interval, not half of one: within a layer's own resolution
    # there is a frame that genuinely belongs to the requested instant, so a
    # six-minute radar layer tolerates six minutes rather than three.
    assert staleness_tolerance_seconds(360) == 360
    assert staleness_tolerance_seconds(3600) == 3600
    # The coarser planning steps, where half a cadence was most wrong.
    assert staleness_tolerance_seconds(10800) == 10800
    assert staleness_tolerance_seconds(21600) == 21600
    # An underivable cadence still gets a bound rather than an open one.
    assert staleness_tolerance_seconds(None) == 900


def test_features_are_returned_only_for_a_frame_the_layer_published():
    stamps = [START, START + timedelta(minutes=6)]
    store = StubStore([(artifact(source_id="eccc-radar", logical_name="radar"), series(latitudes=[47.5], longitudes=[-52.7], stamps=stamps))])

    found, coverage = store.layer_features("eccc-radar-radar", START)
    assert coverage is not None
    assert [feature["properties"]["radar_echo"] for feature in found] == [1.0]

    # A time between frames yields nothing. The endpoint does not snap; the
    # caller chose the frame from the layer's own declared times.
    missing, _ = store.layer_features("eccc-radar-radar", START + timedelta(minutes=3))
    assert missing == []


def test_a_cell_with_no_value_produces_no_feature():
    dataset = series(latitudes=[47.08, 47.56], longitudes=[-55.66, -52.72], stamps=[START])
    dataset["radar_echo"].values[0, 0, 1] = numpy.nan
    dataset["radar_echo"].values[0, 1, 0] = numpy.nan
    store = StubStore([(artifact(source_id="eccc-aqhi", logical_name="aqhi"), dataset)])

    found, _ = store.layer_features("eccc-aqhi-aqhi", START)

    # Two of the four outer-product cells hold nothing, and are simply absent.
    assert len(found) == 2


def test_layer_ids_are_formed_in_one_place():
    assert layer_id_for("eccc-radar", "radar") == "eccc-radar-radar"
