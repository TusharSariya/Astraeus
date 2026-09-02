"""What ``/point`` and ``/profile`` may open, and how they find a grid cell.

Two failures are pinned here, both of which made real evidence look absent.

The first is a category error: the CAP-alerts artifact is GeoJSON, and every
point sample tried to open it as a Zarr zip. The read failed, the failure was
correctly reported as a skipped artifact, and every live ``/point`` therefore
carried a notice saying evidence had been lost when none had.

The second is a coordinate error: HRDPS and RDPS publish on a rotated grid, so
latitude and longitude arrive as 2-D fields over anonymous ``y``/``x`` dims.
``.sel`` by label is invalid there and raises, so a correctly published,
QC-passed HRDPS artifact answered with nothing at all.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy
import pytest
import xarray

from ingest.store import CurrentArtifact
from weather_api.store import (
    MAX_GRID_DISTANCE_DEGREES,
    LiveStore,
    _corrected_distance_degrees,
    _nearest_curvilinear_cell,
)

UTC = timezone.utc
STAMP = datetime(2026, 8, 30, 3, 0, tzinfo=UTC)
# St. John's, the coordinate every live probe in this experiment uses.
LATITUDE, LONGITUDE = 47.5615, -52.7126


def artifact(*, source_id: str, logical_name: str, media_type: str = "application/zarr+zip") -> CurrentArtifact:
    return CurrentArtifact(
        source_id=source_id,
        logical_name=logical_name,
        revision_id=f"revision-{source_id}-{logical_name}",
        object_key=f"artifacts/{source_id}/{logical_name}",
        media_type=media_type,
        byte_size=1024,
        provenance={"units": "degC", "evidence_classes": ["retrieved"]},
        published_at=STAMP,
        run_time=STAMP,
        retrieved_at=STAMP,
        provider_run_id="2026083003",
        native_crs="EPSG:4326",
    )


class StubStore(LiveStore):
    """A live store holding already-open datasets, so nothing touches S3."""

    def __init__(self, pairs: list[tuple[CurrentArtifact, Any]]) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._pairs = pairs
        self.opened: list[str] = []

    def current(self) -> list[CurrentArtifact]:
        return [item for item, _ in self._pairs]

    def open(self, item: CurrentArtifact) -> Any:
        self.opened.append(item.revision_id)
        found = next((dataset for candidate, dataset in self._pairs if candidate.revision_id == item.revision_id), None)
        if found is None:
            # Exactly what ``zarr.storage.ZipStore`` does to a GeoJSON object.
            raise ValueError("BadZipFile: File is not a zip file")
        return found

    def assert_object_store_reachable(self) -> None:
        """Held in memory; reachability has its own tests."""


def rectilinear(value: float = 11.5) -> xarray.Dataset:
    latitudes = numpy.linspace(47.0, 48.0, 20)
    longitudes = numpy.linspace(-53.5, -52.0, 20)
    shape = (1, latitudes.size, longitudes.size)
    return xarray.Dataset(
        {"temperature_2m": (("valid_time", "latitude", "longitude"), numpy.full(shape, value), {"units": "degC"})},
        coords={
            "valid_time": numpy.array([numpy.datetime64(STAMP.replace(tzinfo=None), "ns")]),
            "latitude": latitudes,
            "longitude": longitudes,
        },
    )


def rotated(centre_lat: float = 47.5, centre_lon: float = -52.7, span: float = 0.6, size: int = 20) -> xarray.Dataset:
    """A grid with genuinely 2-D latitude/longitude over anonymous y/x dims.

    This is the shape cfgrib returns for HRDPS. The rotation is what makes the
    coordinates 2-D; the existing datamart test used a 1-D grid *and*
    monkeypatched the cropper away, which is exactly why this stayed invisible.
    """
    axis = numpy.linspace(-span, span, size)
    grid_y, grid_x = numpy.meshgrid(axis, axis, indexing="ij")
    angle = numpy.deg2rad(12.0)
    latitudes = centre_lat + grid_y * numpy.cos(angle) - grid_x * numpy.sin(angle)
    longitudes = centre_lon + grid_x * numpy.cos(angle) + grid_y * numpy.sin(angle)
    values = numpy.arange(size * size, dtype="float64").reshape(1, size, size) / 100.0 + 16.0
    return xarray.Dataset(
        {"temperature_2m": (("valid_time", "y", "x"), values, {"units": "degC"})},
        coords={
            "valid_time": numpy.array([numpy.datetime64(STAMP.replace(tzinfo=None), "ns")]),
            "latitude": (("y", "x"), latitudes),
            "longitude": (("y", "x"), longitudes),
        },
    )


# --- the GeoJSON guard ---------------------------------------------------

def test_a_geojson_artifact_is_not_opened_as_a_zip_when_sampling_a_point():
    """The alerts collection holds no gridded value, so it is not a skip."""
    alerts = artifact(source_id="eccc-cap-alerts", logical_name="alerts", media_type="application/geo+json")
    grid = artifact(source_id="eccc-hrdps", logical_name="surface")
    store = StubStore([(alerts, None), (grid, rectilinear())])

    samples = store.sample_point(LATITUDE, LONGITUDE, STAMP)

    assert store.opened == [grid.revision_id], "the GeoJSON artifact must never be opened as a Zarr"
    assert store.skipped == [], "a vector artifact carrying no grid is not lost evidence"
    assert [sample.source_id for sample in samples] == ["eccc-hrdps"]


def test_a_geojson_artifact_is_not_opened_as_a_zip_when_sampling_a_profile():
    alerts = artifact(source_id="eccc-cap-alerts", logical_name="alerts", media_type="application/geo+json")
    store = StubStore([(alerts, None)])

    assert store.sample_profile(LATITUDE, LONGITUDE, STAMP, (850,)) == {}
    assert store.opened == []
    assert store.skipped == []


def test_an_artifact_that_genuinely_cannot_be_read_is_still_reported():
    """The guard must not become a way to hide a real failure."""
    broken = artifact(source_id="eccc-hrdps", logical_name="surface")
    store = StubStore([(broken, None)])

    assert store.sample_point(LATITUDE, LONGITUDE, STAMP) == []
    assert [item.source_id for item in store.skipped] == ["eccc-hrdps"]
    assert "not a zip file" in store.skipped[0].reason


# --- curvilinear sampling ------------------------------------------------

def test_a_rotated_grid_is_sampled_by_index_rather_than_raising():
    grid = artifact(source_id="eccc-hrdps", logical_name="surface")
    store = StubStore([(grid, rotated())])

    samples = store.sample_point(LATITUDE, LONGITUDE, STAMP)

    assert store.skipped == []
    assert len(samples) == 1
    sample = samples[0]
    assert sample.variable == "temperature_2m"
    assert sample.value is not None
    assert sample.sample_method == "curvilinear_nearest_cell"


def test_a_rotated_grid_would_raise_under_label_selection():
    """Pins the actual upstream failure, so the branch cannot be removed."""
    dataset = rotated()
    with pytest.raises(Exception):
        dataset.sel({"latitude": LATITUDE, "longitude": LONGITUDE}, method="nearest")


def test_the_sampled_cell_is_reported_rather_than_the_requested_coordinate():
    """At 2.5 km the two differ, and echoing the request back would overstate it."""
    grid = artifact(source_id="eccc-hrdps", logical_name="surface")
    store = StubStore([(grid, rotated())])

    sample = store.sample_point(LATITUDE, LONGITUDE, STAMP)[0]

    assert sample.sampled_latitude is not None and sample.sampled_longitude is not None
    assert (sample.sampled_latitude, sample.sampled_longitude) != (LATITUDE, LONGITUDE)
    assert sample.sample_distance_km is not None and sample.sample_distance_km >= 0
    # And it is a cell the artifact actually holds, not an interpolation.
    dataset = rotated()
    cells = {
        (round(float(lat), 6), round(float(lon), 6))
        for lat, lon in zip(
            numpy.asarray(dataset["latitude"].values).ravel(),
            numpy.asarray(dataset["longitude"].values).ravel(),
        )
    }
    assert (round(sample.sampled_latitude, 6), round(sample.sampled_longitude, 6)) in cells


def test_longitude_is_scaled_by_latitude_so_the_nearest_cell_is_the_right_one():
    """A degree of longitude is ~0.68 of a degree of latitude at 47.5 N.

    Two candidate cells sit one degree away, one north and one east. Under raw
    Euclidean degrees they tie; corrected, the eastern cell is nearer, and that
    is the one a distance in kilometres would pick.
    """
    north = _corrected_distance_degrees(47.5, -52.7, 48.5, -52.7)
    east = _corrected_distance_degrees(47.5, -52.7, 47.5, -51.7)
    assert east < north
    assert east == pytest.approx(numpy.cos(numpy.deg2rad(47.5)), rel=1e-6)


def test_a_distant_grid_fails_closed_and_says_so():
    """A cell far outside the requested area is not evidence about it."""
    grid = artifact(source_id="eccc-hrdps", logical_name="surface")
    # Centred over the Pacific; the nearest cell is thousands of kilometres off.
    store = StubStore([(grid, rotated(centre_lat=47.5, centre_lon=-125.0))])

    assert store.sample_point(LATITUDE, LONGITUDE, STAMP) == []
    assert len(store.skipped) == 1
    assert "nearest published cell" in store.skipped[0].reason
    assert "km from the requested" in store.skipped[0].reason


def test_a_regular_grid_still_takes_the_rectilinear_path():
    """GFS and GDPS are unaffected; the label path is untouched."""
    grid = artifact(source_id="noaa-gfs", logical_name="surface")
    store = StubStore([(grid, rectilinear(value=9.25))])

    sample = store.sample_point(LATITUDE, LONGITUDE, STAMP)[0]

    assert sample.sample_method == "rectilinear"
    assert sample.value == pytest.approx(9.25)
    assert sample.sampled_latitude is not None


def test_the_nearest_cell_helper_returns_positional_indexers_for_one_cell():
    dataset = rotated()
    found = _nearest_curvilinear_cell(dataset, "latitude", "longitude", LATITUDE, LONGITUDE)
    assert found is not None
    indexers, cell_latitude, cell_longitude, distance = found
    assert set(indexers) == {"y", "x"}
    assert distance <= MAX_GRID_DISTANCE_DEGREES
    picked = dataset.isel(indexers)
    assert float(picked["latitude"]) == pytest.approx(cell_latitude)
    assert float(picked["longitude"]) == pytest.approx(cell_longitude)
