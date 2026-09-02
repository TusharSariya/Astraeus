"""Admission by class, and one artifact's provenance failure staying its own.

Two rules are pinned here.

An artifact is excluded from a data path by the classes it declares, never by
a match on its logical name. The name match is what stopped matching when a
generated artifact's name grew a layer suffix, and a generated cloud repair
reached ``/point`` and ``/profile`` on 2026-09-01.

And an artifact whose provenance the model refuses loses only its own fields.
``open`` already skips a corrupt artifact and keeps answering from the rest;
``live_provenance`` did not, so one unmodelled field took down every source in
a response.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/evidence-truth-boundary/spec.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy
import pytest
import xarray

from ingest.store import CurrentArtifact
from weather_api.store import LiveStore, live_point_fields

UTC = timezone.utc
VALID_TIME = datetime(2026, 9, 2, 15, tzinfo=UTC)
ST_JOHNS = (47.5615, -52.7126)


def artifact(*, source_id: str = "eccc-hrdps", logical_name: str = "surface", revision_id: str = "revision-1", provenance: dict[str, Any] | None = None) -> CurrentArtifact:
    return CurrentArtifact(
        source_id=source_id,
        logical_name=logical_name,
        revision_id=revision_id,
        object_key=f"artifacts/{source_id}/{logical_name}",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={"adapter_version": "hrdps-v1", "evidence_classes": ["retrieved"], **(provenance or {})},
        published_at=datetime(2026, 9, 2, 13, tzinfo=UTC),
        run_time=datetime(2026, 9, 2, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 2, 12, 40, tzinfo=UTC),
        provider_run_id="2026090212",
        native_crs="EPSG:4326",
    )


def dataset(temperature: float = 14.5) -> xarray.Dataset:
    latitudes, longitudes = numpy.array([47.5, 47.6]), numpy.array([-52.8, -52.7])
    stamps = numpy.array([numpy.datetime64(VALID_TIME.replace(tzinfo=None), "ns")])
    grid = numpy.full((1, 2, 2), temperature, dtype="float64")
    return xarray.Dataset(
        {"temperature_2m": (("valid_time", "latitude", "longitude"), grid, {"units": "degC"})},
        coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
    )


class StubStore(LiveStore):
    """A store whose artifacts are already open, so no object store is touched."""

    def __init__(self, pairs: list[tuple[CurrentArtifact, xarray.Dataset]]) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._pairs = pairs

    def current(self) -> list[CurrentArtifact]:
        return [item for item, _ in self._pairs]

    def open(self, item: CurrentArtifact) -> xarray.Dataset:
        return next(data for candidate, data in self._pairs if candidate.revision_id == item.revision_id)

    def assert_object_store_reachable(self) -> None:
        """Held in memory; reachability has its own tests."""


# --- admission by class ----------------------------------------------------

def test_a_generated_artifact_is_excluded_from_a_point_by_its_class():
    store = StubStore([
        (artifact(), dataset()),
        (artifact(logical_name="low_cloud_weong", revision_id="revision-2", provenance={"evidence_classes": ["generated_display"]}), dataset(3.0)),
    ])

    samples = store.sample_point(*ST_JOHNS, VALID_TIME)

    assert {sample.logical_name for sample in samples} == {"surface"}
    assert store.skipped == [], "a display construction that was never evidence is not a lost artifact"


def test_a_generated_artifact_under_a_renamed_logical_name_is_still_excluded():
    """Exclusion reads the class, so a rename changes nothing. This is the
    2026-09-01 failure: the name list stopped covering the artifact the moment
    its name grew a layer suffix."""
    renamed = artifact(logical_name="a_name_the_sampler_has_never_seen", revision_id="revision-3", provenance={"evidence_classes": ["generated_display"]})
    store = StubStore([(artifact(), dataset()), (renamed, dataset(3.0))])

    samples = store.sample_point(*ST_JOHNS, VALID_TIME)

    assert [sample.value for sample in samples] == [14.5], "the renamed generated artifact answered a data path"
    assert store.skipped == []


def test_a_generated_artifact_is_excluded_from_a_profile_by_its_class_too():
    generated = artifact(logical_name="cloud_motion_low_cloud_weong", revision_id="revision-4", provenance={"evidence_classes": ["generated_display"]})
    store = StubStore([(generated, dataset())])

    assert store.sample_profile(*ST_JOHNS, VALID_TIME, (1000,)) == {}


def test_a_sampled_value_carries_the_class_its_artifact_declared():
    store = StubStore([(artifact(provenance={"evidence_classes": ["reprocessed"]}), dataset())])

    assert {sample.evidence_class for sample in store.sample_point(*ST_JOHNS, VALID_TIME)} == {"reprocessed"}


# --- provenance isolation --------------------------------------------------

def test_provenance_isolation_keeps_one_unmodelled_artifact_from_failing_the_response():
    """Four sources answer; the fifth's fields are null with a notice naming
    the artifact and the reason."""
    good = artifact()
    silent = artifact(source_id="noaa-gfs", revision_id="revision-5", provenance={"evidence_classes": []})
    store = StubStore([(good, dataset()), (silent, dataset(9.0))])

    fields, _consensus, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    by_source: dict[str, list[Any]] = {}
    for item in fields:
        by_source.setdefault(item.provenance.source_id, []).append(item)

    assert sources == ["eccc-hrdps"]
    assert [item.value for item in by_source["eccc-hrdps"]] == [14.5]
    assert [item.value for item in by_source["noaa-gfs"]] == [None]
    assert by_source["noaa-gfs"][0].provenance.data_mode == "unavailable"
    assert "provenance_unmodelled" in by_source["noaa-gfs"][0].provenance.quality.flags
    assert [skip.source_id for skip in store.skipped] == ["noaa-gfs"]
    assert "revision-5" in store.skipped[0].revision_id
    assert "evidence_classes" in store.skipped[0].reason


def test_provenance_isolation_names_the_reason_for_an_unknown_class():
    store = StubStore([(artifact(), dataset()), (artifact(source_id="noaa-gfs", revision_id="revision-6", provenance={"evidence_classes": ["consensus"]}), dataset(9.0))])

    fields, _consensus, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)

    assert sources == ["eccc-hrdps"]
    assert any(item.provenance.source_id == "noaa-gfs" and item.value is None for item in fields)
    assert store.skipped and "consensus" in store.skipped[0].reason


def test_provenance_isolation_refuses_a_value_whose_class_the_artifact_never_stated():
    """A mixed artifact that says nothing about a variable cannot resolve that
    value's class, and guessing would serve an unknown class as retrieved."""
    mixed = artifact(
        source_id="open-meteo-weathernext2",
        revision_id="revision-7",
        provenance={"evidence_classes": ["reprocessed", "intermediary_derived"], "evidence_class_by_variable": {"total_cloud": "intermediary_derived"}},
    )
    store = StubStore([(artifact(), dataset()), (mixed, dataset(9.0))])

    fields, _consensus, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)

    assert sources == ["eccc-hrdps"]
    assert store.skipped and "temperature_2m" in store.skipped[0].reason


def test_provenance_isolation_of_every_artifact_leaves_the_caller_to_report_unavailable():
    """With nothing modelled there is no evidence to answer from, so the point
    path returns no fields and the caller reports unavailable - never a
    fixture value."""
    store = StubStore([(artifact(provenance={"evidence_classes": []}), dataset())])

    fields, _consensus, sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)

    assert fields == [] and sources == []
    assert [skip.source_id for skip in store.skipped] == ["eccc-hrdps"]
