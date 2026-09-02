"""Sampling published artifacts: a missing value must stay missing.

These tests build an xarray dataset in memory rather than reaching MinIO, so
the rule under test is the one that matters: absence surfaces as ``null`` with
provenance saying so, and is never interpolated into existence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy
import pytest
import xarray

from ingest.store import CurrentArtifact
from weather_api.store import LiveStore, Sample, StoreUnavailable, live_point_fields, live_provenance

UTC = timezone.utc
VALID_TIME = datetime(2026, 8, 29, 15, tzinfo=UTC)
ST_JOHNS = (47.5615, -52.7126)


def make_artifact(*, source_id: str = "eccc-hrdps", provenance: dict[str, Any] | None = None) -> CurrentArtifact:
    return CurrentArtifact(
        source_id=source_id,
        logical_name="surface",
        revision_id="revision-1",
        object_key=f"artifacts/{source_id}/surface",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance=provenance if provenance is not None else {"native_resolution": "2.5 km", "adapter_version": "hrdps-v1"},
        published_at=datetime(2026, 8, 29, 13, tzinfo=UTC),
        run_time=datetime(2026, 8, 29, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 29, 12, 40, tzinfo=UTC),
        provider_run_id="2026082912",
        native_crs="EPSG:4326",
    )


def make_dataset(*, temperature: float | None = 14.5, dew_point: float | None = None, wind_u: float | None = None, wind_v: float | None = None) -> xarray.Dataset:
    """A two-by-two grid around St. John's at a single valid time."""
    latitudes = numpy.array([47.5, 47.6])
    longitudes = numpy.array([-52.8, -52.7])
    stamps = numpy.array([numpy.datetime64(VALID_TIME.replace(tzinfo=None), "ns")])

    def grid(value: float | None) -> numpy.ndarray:
        filled = numpy.nan if value is None else value
        return numpy.full((1, 2, 2), filled, dtype="float64")

    variables = {
        "temperature_2m": (("valid_time", "latitude", "longitude"), grid(temperature), {"units": "degC"}),
        "dew_point_2m": (("valid_time", "latitude", "longitude"), grid(dew_point), {"units": "degC"}),
    }
    if wind_u is not None or wind_v is not None:
        variables["wind_u_10m"] = (("valid_time", "latitude", "longitude"), grid(wind_u), {"units": "m s-1"})
        variables["wind_v_10m"] = (("valid_time", "latitude", "longitude"), grid(wind_v), {"units": "m s-1"})
    return xarray.Dataset(variables, coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes})


class StubStore(LiveStore):
    """A live store whose artifacts are already open, so no object store is touched."""

    def __init__(self, pairs: list[tuple[CurrentArtifact, xarray.Dataset]]) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._pairs = pairs

    def current(self) -> list[CurrentArtifact]:
        return [artifact for artifact, _ in self._pairs]

    def open(self, artifact: CurrentArtifact) -> xarray.Dataset:
        return next(dataset for candidate, dataset in self._pairs if candidate.revision_id == artifact.revision_id)

    def assert_object_store_reachable(self) -> None:
        """This double holds its datasets directly and has no object store.

        Reachability is exercised by its own tests below, not implicitly by
        every sampling test.
        """


def test_cloud_steering_winds_never_reach_a_reading():
    """The 850/700/500 hPa winds are ingested for one purpose: informing the
    display-time cloud-motion derivation. They are not evidence a reader
    asked for, and the carve-out that allows them says explicitly that they
    reach no data path. The served-field map is the enforcement, so it is
    pinned here rather than left to the absence of a mapping."""
    from weather_api.store import DERIVATION_INPUTS, FIELD_BY_VARIABLE

    for level in (850, 700, 500):
        for component in ("u", "v"):
            name = f"wind_{component}_{level}hPa"
            assert name not in FIELD_BY_VARIABLE
            assert name not in DERIVATION_INPUTS


def test_a_missing_grid_value_surfaces_as_null_rather_than_being_invented():
    store = StubStore([(make_artifact(), make_dataset(temperature=14.5, dew_point=None))])
    samples = store.sample_point(*ST_JOHNS, VALID_TIME)
    by_variable = {sample.variable: sample for sample in samples}

    assert by_variable["temperature_2m"].value == 14.5
    assert by_variable["dew_point_2m"].value is None
    assert by_variable["dew_point_2m"].units == "degC"


def test_a_null_value_still_carries_full_live_provenance():
    store = StubStore([(make_artifact(), make_dataset(temperature=None, dew_point=None))])
    fields, consensus, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    by_field = {item.field: item for item in fields}

    assert sources == ["eccc-hrdps"]
    assert consensus.available is False
    assert by_field["temperature"].value is None
    assert by_field["dew_point"].value is None
    for item in fields:
        assert item.provenance.data_mode == "live"
        assert item.provenance.operational is False
        assert item.provenance.valid_time == VALID_TIME
        assert item.provenance.run_time == datetime(2026, 8, 29, 12, tzinfo=UTC)
        assert item.provenance.native_crs == "EPSG:4326"


def test_relative_humidity_is_not_derived_when_either_input_is_missing():
    """Deriving from a null dew point would manufacture a reading."""
    store = StubStore([(make_artifact(), make_dataset(temperature=14.5, dew_point=None))])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    assert "relative_humidity" not in {item.field for item in fields}


def test_relative_humidity_is_derived_and_labelled_when_both_inputs_are_present():
    store = StubStore([(make_artifact(), make_dataset(temperature=14.5, dew_point=11.0))])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    derived = next(item for item in fields if item.field == "relative_humidity")
    assert derived.value is not None
    assert derived.provenance.derivation is not None
    assert derived.provenance.derivation_version == "metpy-1.7.1-liquid-v1"


def test_derived_relative_humidity_carries_percent_units_not_the_temperature_sample_units():
    """The RH provenance was stamped with the temperature sample's degC."""
    store = StubStore([(make_artifact(), make_dataset(temperature=14.5, dew_point=11.0))])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    derived = next(item for item in fields if item.field == "relative_humidity")
    assert derived.provenance.original_units == "percent"
    assert derived.provenance.normalized_units == "percent"


def test_wind_speed_and_direction_are_derived_from_stored_components_and_labelled():
    store = StubStore([(make_artifact(), make_dataset(wind_u=0.0, wind_v=-5.0))])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    by_field = {item.field: item for item in fields}

    speed, direction = by_field["wind_speed"], by_field["wind_direction"]
    assert speed.value == 5.0
    assert direction.value in (0.0, 360.0)
    assert speed.provenance.normalized_units == "m s-1" and speed.provenance.original_units == "m s-1"
    assert direction.provenance.normalized_units == "degree" and direction.provenance.original_units == "degree"
    for item in (speed, direction):
        assert item.provenance.derivation is not None and "MetPy" in item.provenance.derivation
        assert item.provenance.derivation_version == "metpy-1.7.1-wind-v1"
        assert item.provenance.source_id == "eccc-hrdps"
    # The reader asked for wind, not vector components; the components are
    # inputs to the derivation and not published as readings of their own.
    assert "wind_u" not in by_field and "wind_v" not in by_field


def test_wind_is_not_derived_when_either_component_is_missing():
    store = StubStore([(make_artifact(), make_dataset(wind_u=3.0, wind_v=None))])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    names = {item.field for item in fields}
    assert "wind_speed" not in names and "wind_direction" not in names


def test_a_coordinate_far_from_the_published_grid_returns_no_evidence():
    store = StubStore([(make_artifact(), make_dataset())])
    assert store.sample_point(40.0, -70.0, VALID_TIME) == []


def test_a_time_outside_the_published_steps_returns_no_evidence():
    store = StubStore([(make_artifact(), make_dataset())])
    assert store.sample_point(*ST_JOHNS, VALID_TIME + timedelta(hours=6)) == []


def test_an_unmeasured_retrieval_age_stays_unknown_rather_than_fresh():
    sample = Sample(
        source_id="eccc-hrdps", logical_name="surface", variable="temperature_2m", value=None,
        units="degC", level="2 m above ground", valid_time=VALID_TIME, run_time=None,
        retrieved_at=None, native_crs="EPSG:4326", provenance={},
    )
    provenance = live_provenance(sample, field_name="temperature", reference=datetime(2026, 8, 29, 16, tzinfo=UTC))

    assert provenance.freshness.status == "unknown"
    assert provenance.freshness.age_seconds is None
    assert provenance.quality.status == "unknown"
    assert provenance.coverage.status == "unknown"
    assert provenance.operational is False
    assert provenance.data_mode == "live"


def test_a_measured_retrieval_age_is_compared_against_the_registry_threshold():
    sample = Sample(
        source_id="eccc-hrdps", logical_name="surface", variable="temperature_2m", value=14.5,
        units="degC", level="2 m above ground", valid_time=VALID_TIME,
        run_time=datetime(2026, 8, 29, 12, tzinfo=UTC), retrieved_at=datetime(2026, 8, 29, 12, 40, tzinfo=UTC),
        native_crs="EPSG:4326", provenance={"quality": {"status": "passed", "flags": []}, "coverage": {"status": "complete", "fraction": 1.0}},
    )
    fresh = live_provenance(sample, field_name="temperature", reference=datetime(2026, 8, 29, 13, tzinfo=UTC))
    stale = live_provenance(sample, field_name="temperature", reference=datetime(2026, 8, 30, 13, tzinfo=UTC))

    assert fresh.freshness.status == "fresh"
    assert fresh.freshness.age_seconds == 20 * 60
    assert stale.freshness.status == "stale"
    assert fresh.quality.status == "passed"
    assert fresh.coverage.fraction == 1.0
    assert fresh.provider == "Environment and Climate Change Canada"


def test_a_broken_artifact_does_not_remove_evidence_from_the_others():
    class HalfBroken(StubStore):
        def open(self, artifact: CurrentArtifact) -> xarray.Dataset:
            if artifact.source_id == "noaa-gfs":
                raise RuntimeError("corrupt zarr")
            return super().open(artifact)

    working = make_artifact()
    broken = make_artifact(source_id="noaa-gfs")
    broken = CurrentArtifact(**{**broken.__dict__, "revision_id": "revision-2"})
    store = HalfBroken([(working, make_dataset()), (broken, make_dataset())])

    assert {sample.source_id for sample in store.sample_point(*ST_JOHNS, VALID_TIME)} == {"eccc-hrdps"}


def test_a_generated_derivation_is_never_sampled_onto_a_data_path():
    """The WEonG low-cloud repair holds cloud values no provider published.

    Rule (d) lets a generated value be drawn and forbids it on a data path.
    It reached /point once because the skip was matched by logical name, and
    the response then failed whole: the derivation records its own QC status,
    which is not one of the four the evidence contract allows.
    """
    retrieved = make_artifact()
    generated = make_artifact(
        source_id="eccc-hrdps",
        provenance={"derived": True, "generated": True, "quality": {"status": "passed", "flags": ["generated"]}},
    )
    generated = CurrentArtifact(**{**generated.__dict__, "logical_name": "low_cloud_weong", "revision_id": "revision-2"})
    motion = make_artifact(source_id="eccc-hrdps", provenance={"derived": True})
    motion = CurrentArtifact(**{**motion.__dict__, "logical_name": "cloud_motion_low_cloud_weong", "revision_id": "revision-3"})
    store = StubStore([(retrieved, make_dataset()), (generated, make_dataset()), (motion, make_dataset())])

    samples = store.sample_point(*ST_JOHNS, VALID_TIME)

    assert {sample.logical_name for sample in samples} == {"surface"}
    assert store.skipped == [], "a derivation that was never evidence is not a lost artifact"
    fields, _, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    assert fields and sources == ["eccc-hrdps"]


def test_an_empty_store_produces_no_fields_and_no_consensus():
    store = StubStore([])
    fields, consensus, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    assert fields == [] and sources == [] and consensus.available is False


# --- integrity on read ---------------------------------------------------
# Downloaded bytes are checked against what was recorded at publication. A
# mismatch is an outage, not a reading, and must not erase other sources.

def test_bytes_that_do_not_match_the_recorded_digest_are_refused():
    from weather_api.store import ArtifactIntegrityError

    artifact = make_artifact(provenance={"sha256": "a" * 64})
    LiveStore._verify(artifact, 1024, "a" * 64)  # matching size and digest is accepted
    with pytest.raises(ArtifactIntegrityError, match="sha256"):
        LiveStore._verify(artifact, 1024, "b" * 64)
    with pytest.raises(ArtifactIntegrityError, match="byte size"):
        LiveStore._verify(artifact, 999, "a" * 64)


def test_an_artifact_with_no_recorded_digest_is_unverifiable_and_so_unavailable():
    from weather_api.store import ArtifactIntegrityError

    with pytest.raises(ArtifactIntegrityError, match="no recorded sha256"):
        LiveStore._verify(make_artifact(provenance={}), 1024, "a" * 64)


def test_a_corrupt_artifact_is_dropped_with_a_flag_while_the_others_survive():
    from weather_api.store import ArtifactIntegrityError

    class Corrupt(StubStore):
        def open(self, artifact: CurrentArtifact) -> xarray.Dataset:
            if artifact.source_id == "noaa-gfs":
                raise ArtifactIntegrityError("revision-2 sha256 does not match the recorded digest")
            return super().open(artifact)

    working = make_artifact()
    broken = CurrentArtifact(**{**make_artifact(source_id="noaa-gfs").__dict__, "revision_id": "revision-2"})
    store = Corrupt([(working, make_dataset()), (broken, make_dataset())])

    fields, _, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    assert sources == ["eccc-hrdps"]
    assert fields, "one corrupt artifact must not erase the evidence that did read"
    assert [skip.source_id for skip in store.skipped] == ["noaa-gfs"]
    assert "ArtifactIntegrityError" in store.skipped[0].reason


# --- storage reachability -------------------------------------------------
# The in-memory dataset cache made the truth boundary depend on process age:
# a long-running API kept serving values from RAM after MinIO went away, while
# a freshly started one correctly reported unavailable. Same request, two
# answers. Worse, with the object store unreachable a superseded revision
# cannot be detected, so withdrawn evidence would be served as current.


class _FakeS3:
    def __init__(self, reachable: bool) -> None:
        self.reachable = reachable
        self.head_calls = 0

    def head_bucket(self, **_kwargs: object) -> dict[str, object]:
        self.head_calls += 1
        if not self.reachable:
            raise OSError("connection refused")
        return {}


class _FakeArtifactStore:
    def __init__(self, reachable: bool) -> None:
        self.s3 = _FakeS3(reachable)
        self.config = SimpleNamespace(bucket="weather-artifacts")


class ProbingStore(StubStore):
    """A stub that keeps the real reachability probe against a fake object store."""

    def __init__(self, pairs, *, reachable: bool) -> None:
        super().__init__(pairs)
        self._store = _FakeArtifactStore(reachable)

    def assert_object_store_reachable(self) -> None:
        LiveStore.assert_object_store_reachable(self)


def test_sampling_fails_closed_when_the_object_store_is_unreachable():
    store = ProbingStore([(make_artifact(), make_dataset(temperature=14.5, dew_point=12.0))], reachable=False)
    with pytest.raises(StoreUnavailable):
        store.sample_point(*ST_JOHNS, VALID_TIME)


def test_a_cached_dataset_does_not_mask_an_unreachable_object_store():
    """The bug: warm cache kept answering after storage went away."""
    pairs = [(make_artifact(), make_dataset(temperature=14.5, dew_point=12.0))]
    store = ProbingStore(pairs, reachable=True)

    assert store.sample_point(*ST_JOHNS, VALID_TIME), "warm the process first"

    store._store.s3.reachable = False
    with pytest.raises(StoreUnavailable):
        store.sample_point(*ST_JOHNS, VALID_TIME)


def test_profile_and_timeline_paths_probe_storage_too():
    """All three sampling entry points, or the boundary has a hole in it."""
    pairs = [(make_artifact(), make_dataset(temperature=14.5, dew_point=12.0))]
    store = ProbingStore(pairs, reachable=False)

    with pytest.raises(StoreUnavailable):
        store.sample_profile(*ST_JOHNS, VALID_TIME, (1000,))
    with pytest.raises(StoreUnavailable):
        store.published_products()


def test_a_dataset_for_a_superseded_revision_is_dropped_from_the_cache():
    artifact = make_artifact()
    dataset = make_dataset(temperature=14.5, dew_point=12.0)
    store = ProbingStore([(artifact, dataset)], reachable=True)
    store.sample_point(*ST_JOHNS, VALID_TIME)
    store._datasets[str(artifact.revision_id)] = dataset
    store._datasets["a-revision-that-is-no-longer-current"] = dataset

    store.sample_point(*ST_JOHNS, VALID_TIME)

    assert "a-revision-that-is-no-longer-current" not in store._datasets


def test_the_dataset_cache_is_bounded():
    """Every new run mints a new revision id, so an unbounded cache never stops growing."""
    from weather_api.store import MAX_CACHED_DATASETS

    assert MAX_CACHED_DATASETS > 0


def make_upper_air(*, u200: float | None = 40.0, v200: float | None = -10.0, u300: float | None = 30.0, v300: float | None = -6.0) -> tuple[CurrentArtifact, xarray.Dataset]:
    """A GFS-shaped upper_air artifact: flat level-suffixed jet-wind components."""
    latitudes = numpy.array([47.5, 47.6])
    longitudes = numpy.array([-52.8, -52.7])
    stamps = numpy.array([numpy.datetime64(VALID_TIME.replace(tzinfo=None), "ns")])

    def grid(value: float | None) -> numpy.ndarray:
        return numpy.full((1, 2, 2), numpy.nan if value is None else value, dtype="float64")

    variables = {
        name: (("valid_time", "latitude", "longitude"), grid(value), {"units": "m s-1"})
        for name, value in (
            ("wind_u_200hPa", u200), ("wind_v_200hPa", v200),
            ("wind_u_300hPa", u300), ("wind_v_300hPa", v300),
        )
    }
    dataset = xarray.Dataset(variables, coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes})
    artifact = CurrentArtifact(
        source_id="noaa-gfs",
        logical_name="upper_air",
        revision_id="revision-upper-1",
        object_key="artifacts/noaa-gfs/upper_air",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"native_resolution": "0.25 deg", "adapter_version": "noaa-gfs-v2", "vertical_levels": "200/300 hPa isobaric"},
        published_at=datetime(2026, 8, 29, 13, tzinfo=UTC),
        run_time=datetime(2026, 8, 29, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 29, 12, 40, tzinfo=UTC),
        provider_run_id="2026082912",
        native_crs="EPSG:4326",
    )
    return artifact, dataset


def test_upper_air_winds_are_served_only_as_level_suffixed_derivations():
    store = StubStore([make_upper_air(u200=0.0, v200=-40.0, u300=0.0, v300=-30.0)])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    by_field = {item.field: item for item in fields}

    assert by_field["wind_speed_200hPa"].value == 40.0
    assert by_field["wind_speed_300hPa"].value == 30.0
    assert by_field["wind_direction_200hPa"].value in (0.0, 360.0)
    for name in ("wind_speed_200hPa", "wind_direction_200hPa"):
        item = by_field[name]
        assert item.provenance.derivation is not None and "MetPy" in item.provenance.derivation
        assert item.provenance.vertical_level == "200 hPa"
    assert by_field["wind_speed_300hPa"].provenance.vertical_level == "300 hPa"
    # The stored components are derivation inputs, never readings.
    for raw in ("wind_u_200hPa", "wind_v_200hPa", "wind_u_300hPa", "wind_v_300hPa"):
        assert raw not in by_field


def test_upper_air_wind_is_absent_when_a_component_is_missing():
    store = StubStore([make_upper_air(u300=None)])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    names = {item.field for item in fields}
    assert "wind_speed_200hPa" in names
    assert "wind_speed_300hPa" not in names and "wind_direction_300hPa" not in names


def test_no_upper_air_artifact_means_no_upper_wind_fields():
    store = StubStore([(make_artifact(), make_dataset(wind_u=1.0, wind_v=1.0))])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    names = {item.field for item in fields}
    assert names.isdisjoint({"wind_speed_200hPa", "wind_direction_200hPa", "wind_speed_300hPa", "wind_direction_300hPa"})


def test_precipitable_water_is_served_as_stored_with_a_column_level():
    latitudes = numpy.array([47.5, 47.6])
    longitudes = numpy.array([-52.8, -52.7])
    stamps = numpy.array([numpy.datetime64(VALID_TIME.replace(tzinfo=None), "ns")])
    dataset = xarray.Dataset(
        {"precipitable_water": (("valid_time", "latitude", "longitude"), numpy.full((1, 2, 2), 12.5), {"units": "kg m-2"})},
        coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
    )
    store = StubStore([(make_artifact(source_id="noaa-gfs"), dataset)])
    fields, _, _ = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    by_field = {item.field: item for item in fields}
    item = by_field["precipitable_water"]
    assert item.value == 12.5
    assert item.provenance.normalized_units == "kg m-2"
    assert item.provenance.vertical_level == "entire atmosphere (column)"
    assert item.provenance.derivation is None
