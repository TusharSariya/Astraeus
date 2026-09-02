"""What ``/point`` may derive, and what it may never promote.

A ``derived_here`` value is served only when all four conditions hold together:
every input is a retrieved value listed with its own provenance, the method is
an enabled entry in the derivation method registry named with its version and
citation, the result is bounded to the method's declared physical range, and
the quality is no better than the worst input's. A value failing any of them is
null with a notice naming the failed condition, and no fallback construction is
substituted.

A ``reprocessed``, ``intermediary_derived`` or ``uncalibrated_observation``
value is served beside the others, labelled, and is never the display primary
and never a derivation input.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/point-evidence-sampling/spec.md
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
from weather_api.store import RELATIVE_HUMIDITY_METHOD, LiveStore, live_point_fields

UTC = timezone.utc
VALID_TIME = datetime(2026, 9, 2, 15, tzinfo=UTC)
ST_JOHNS = (47.5615, -52.7126)
DIMS = ("valid_time", "latitude", "longitude")


def artifact(*, source_id: str = "eccc-hrdps", revision_id: str = "revision-1", classes: list[str] | None = None, quality: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> CurrentArtifact:
    return CurrentArtifact(
        source_id=source_id,
        logical_name="surface",
        revision_id=revision_id,
        object_key=f"artifacts/{source_id}/surface",
        media_type="application/zarr+zip",
        byte_size=1024,
        provenance={
            "adapter_version": "hrdps-v1",
            "evidence_classes": classes or ["retrieved"],
            "quality": quality or {"status": "passed", "flags": []},
            **(extra or {}),
        },
        published_at=datetime(2026, 9, 2, 13, tzinfo=UTC),
        run_time=datetime(2026, 9, 2, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 2, 12, 40, tzinfo=UTC),
        provider_run_id="2026090212",
        native_crs="EPSG:4326",
    )


def dataset(*, temperature: float = 14.5, dew_point: float | None = 11.0) -> xarray.Dataset:
    latitudes, longitudes = numpy.array([47.5, 47.6]), numpy.array([-52.8, -52.7])
    stamps = numpy.array([numpy.datetime64(VALID_TIME.replace(tzinfo=None), "ns")])

    def grid(value: float | None) -> numpy.ndarray:
        return numpy.full((1, 2, 2), numpy.nan if value is None else value, dtype="float64")

    return xarray.Dataset(
        {
            "temperature_2m": (DIMS, grid(temperature), {"units": "degC"}),
            "dew_point_2m": (DIMS, grid(dew_point), {"units": "degC"}),
        },
        coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
    )


class StubStore(LiveStore):
    def __init__(self, pairs: list[tuple[CurrentArtifact, xarray.Dataset]]) -> None:
        super().__init__(artifact_store=None, cache_dir=Path("/nonexistent"))
        self._pairs = pairs

    def current(self) -> list[CurrentArtifact]:
        return [item for item, _ in self._pairs]

    def open(self, item: CurrentArtifact) -> xarray.Dataset:
        return next(data for candidate, data in self._pairs if candidate.revision_id == item.revision_id)

    def assert_object_store_reachable(self) -> None:
        """Held in memory; reachability has its own tests."""


def point(store: StubStore) -> dict[str, Any]:
    fields, _consensus, _sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    by_name: dict[str, Any] = {}
    for item in fields:
        by_name.setdefault(item.field, item)
    return by_name


# --- the four conditions ---------------------------------------------------

def test_derived_here_is_served_when_all_four_conditions_hold(derivation_registry):
    humidity = point(StubStore([(artifact(), dataset())]))["relative_humidity"]

    assert humidity.value is not None
    assert humidity.provenance.evidence_class == "derived_here"
    assert humidity.provenance.derivation_version == "metpy-1.7.1-liquid-v1"
    assert "Bolton" in humidity.provenance.derivation_citation
    assert [item.field for item in humidity.provenance.derivation_inputs] == ["temperature", "dew_point"]
    assert {item.source_id for item in humidity.provenance.derivation_inputs} == {"eccc-hrdps"}
    assert {item.evidence_class for item in humidity.provenance.derivation_inputs} == {"retrieved"}
    assert humidity.provenance.quality.status == "passed"
    assert "derived" in humidity.provenance.quality.flags


def test_a_derived_here_value_is_never_better_than_its_worst_input(derivation_registry):
    store = StubStore([(artifact(quality={"status": "suspect", "flags": ["thin_run"]}), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.provenance.quality.status == "suspect"
    assert "derived" in humidity.provenance.quality.flags


def test_derived_here_is_refused_when_an_input_is_not_retrieved(derivation_registry):
    """A reprocessed input would compound one intermediary's transformation
    with this stack's own."""
    store = StubStore([(artifact(classes=["reprocessed"]), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.value is None
    assert humidity.provenance.data_mode == "unavailable"
    assert store.skipped and "reprocessed" in store.skipped[0].reason
    assert "only a retrieved value may be a derivation input" in store.skipped[0].reason


def test_derived_here_is_refused_when_the_method_is_disabled(derivation_registry):
    derivation_registry[RELATIVE_HUMIDITY_METHOD].enabled = False
    store = StubStore([(artifact(), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.value is None, "a disabled method must not fall back to an unregistered construction"
    assert store.skipped and RELATIVE_HUMIDITY_METHOD in store.skipped[0].reason
    assert "disabled" in store.skipped[0].reason


def test_derived_here_is_refused_when_the_method_is_not_registered():
    """No registry, or no entry: either way the method is not enabled, and
    nothing unregistered is served in its place."""
    store = StubStore([(artifact(), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.value is None
    assert store.skipped and "relative_humidity" in store.skipped[0].reason


def test_a_derived_here_result_outside_the_physical_range_is_clamped_and_flagged(derivation_registry):
    entry = derivation_registry[RELATIVE_HUMIDITY_METHOD]
    entry.physical_range = (0.0, 50.0)
    entry.range_rule = "clamp"

    humidity = point(StubStore([(artifact(), dataset())]))["relative_humidity"]

    assert humidity.value == 50.0
    assert "range_clamped" in humidity.provenance.quality.flags


def test_a_derived_here_result_outside_the_physical_range_may_be_refused(derivation_registry):
    entry = derivation_registry[RELATIVE_HUMIDITY_METHOD]
    entry.physical_range = (0.0, 50.0)
    entry.range_rule = "refuse"

    store = StubStore([(artifact(), dataset())])
    humidity = point(store)["relative_humidity"]

    assert humidity.value is None
    assert store.skipped and "physical range" in store.skipped[0].reason


def test_relative_humidity_a_source_published_is_never_replaced_by_a_derivation(derivation_registry):
    published = dataset().assign({"relative_humidity_2m": (DIMS, numpy.full((1, 2, 2), 62.0), {"units": "percent"})})

    humidity = point(StubStore([(artifact(), published)]))["relative_humidity"]

    assert humidity.value == 62.0
    assert humidity.provenance.evidence_class == "retrieved"
    assert humidity.provenance.derivation is None


def test_relative_humidity_names_its_registry_entry_and_class(derivation_registry):
    humidity = point(StubStore([(artifact(), dataset())]))["relative_humidity"]

    assert humidity.provenance.evidence_class == "derived_here"
    assert humidity.provenance.derivation_version == derivation_registry[RELATIVE_HUMIDITY_METHOD].version


# --- never primary, never an input -----------------------------------------

def test_a_reprocessed_value_is_served_as_non_primary(derivation_registry):
    temperature = point(StubStore([(artifact(classes=["reprocessed"]), dataset())]))["temperature"]

    assert temperature.value == 14.5, "a reprocessed value is served beside the others, not withheld"
    assert temperature.provenance.evidence_class == "reprocessed"
    assert temperature.provenance.display_primary_eligible is False


def test_an_intermediary_derived_value_is_served_as_non_primary_and_names_its_intermediary(derivation_registry):
    item = artifact(
        source_id="open-meteo-weathernext2",
        classes=["intermediary_derived"],
        extra={"intermediary": "Open-Meteo", "intermediary_method": "humidity-profile cloud closure"},
    )

    temperature = point(StubStore([(item, dataset())]))["temperature"]

    assert temperature.provenance.evidence_class == "intermediary_derived"
    assert temperature.provenance.display_primary_eligible is False
    assert temperature.provenance.intermediary == "Open-Meteo"
    assert temperature.provenance.intermediary_method == "humidity-profile cloud closure"


def test_an_uncalibrated_observation_is_served_as_non_primary(derivation_registry):
    temperature = point(StubStore([(artifact(source_id="citizen-station", classes=["uncalibrated_observation"]), dataset())]))["temperature"]

    assert temperature.provenance.evidence_class == "uncalibrated_observation"
    assert temperature.provenance.display_primary_eligible is False


def test_a_retrieved_value_is_primary_eligible_and_says_so(derivation_registry):
    temperature = point(StubStore([(artifact(), dataset())]))["temperature"]

    assert temperature.provenance.evidence_class == "retrieved"
    assert temperature.provenance.display_primary_eligible is True


@pytest.mark.parametrize("evidence_class", ["reprocessed", "intermediary_derived", "uncalibrated_observation"])
def test_a_non_primary_class_is_never_a_derivation_input(derivation_registry, evidence_class: str):
    store = StubStore([(artifact(classes=[evidence_class]), dataset())])

    assert point(store)["relative_humidity"].value is None
    assert store.skipped and evidence_class in store.skipped[0].reason
