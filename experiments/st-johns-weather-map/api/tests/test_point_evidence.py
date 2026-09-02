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

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy
import pytest
import xarray

from ingest.derive import registry as derive_registry
from ingest.store import CurrentArtifact
from weather_api.store import FOG_STATE_METHOD, RELATIVE_HUMIDITY_METHOD, WIND_METHOD, LiveStore, live_point_fields

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


@pytest.fixture
def registry_without(monkeypatch: pytest.MonkeyPatch):
    """Swap the loaded registry for one this test shapes.

    The registry is the real one everywhere else in this module: a test that
    stubbed it would prove nothing about the entries the API actually names.
    Where a refusal has to be provoked, the entry set is rebuilt through the
    registry's own validation, so an invalid shape fails here too.
    """

    def rebuild(**replacements: dict[str, object]) -> None:
        entries = []
        for entry in derive_registry.ENTRIES:
            if entry.name in replacements:
                changes = dict(replacements[entry.name])
                if changes.pop("drop", False):
                    continue
                entry = dataclasses.replace(entry, **changes)
            entries.append(entry)
        monkeypatch.setattr(derive_registry, "REGISTRY", derive_registry.DerivationRegistry(tuple(entries)))

    return rebuild


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

def test_the_method_names_the_api_serves_are_the_registry_entry_names():
    """One interface: an entry under another name is an unregistered method,
    so the two spellings are pinned against each other."""
    assert RELATIVE_HUMIDITY_METHOD == derive_registry.RELATIVE_HUMIDITY
    assert WIND_METHOD == derive_registry.WIND_SPEED_AND_DIRECTION
    assert FOG_STATE_METHOD == derive_registry.FOG_STATE


def test_derived_here_is_served_when_all_four_conditions_hold():
    humidity = point(StubStore([(artifact(), dataset())]))["relative_humidity"]

    assert humidity.value is not None
    assert humidity.provenance.evidence_class == "derived_here"
    assert humidity.provenance.derivation == RELATIVE_HUMIDITY_METHOD
    assert humidity.provenance.derivation_version == "metpy-1.7.1-liquid-v1"
    assert "Bolton" in humidity.provenance.derivation_citation
    assert [item.field for item in humidity.provenance.derivation_inputs] == ["temperature", "dew_point"]
    assert {item.source_id for item in humidity.provenance.derivation_inputs} == {"eccc-hrdps"}
    assert {item.evidence_class for item in humidity.provenance.derivation_inputs} == {"retrieved"}
    assert humidity.provenance.quality.status == "passed"
    assert "derived" in humidity.provenance.quality.flags


def test_a_derived_here_value_is_never_better_than_its_worst_input():
    store = StubStore([(artifact(quality={"status": "suspect", "flags": ["thin_run"]}), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.provenance.quality.status == "suspect"
    assert "derived" in humidity.provenance.quality.flags


def test_derived_here_is_refused_when_an_input_is_not_retrieved():
    """A reprocessed input would compound one intermediary's transformation
    with this stack's own."""
    store = StubStore([(artifact(classes=["reprocessed"]), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.value is None
    assert humidity.provenance.data_mode == "unavailable"
    assert store.skipped and "reprocessed" in store.skipped[0].reason
    assert "only a retrieved value may be a derivation input" in store.skipped[0].reason


def test_derived_here_is_refused_when_the_method_is_disabled(registry_without):
    registry_without(**{RELATIVE_HUMIDITY_METHOD: {"enabled": False}})
    store = StubStore([(artifact(), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.value is None, "a disabled method must not fall back to an unregistered construction"
    assert store.skipped and RELATIVE_HUMIDITY_METHOD in store.skipped[0].reason
    assert "method_disabled" in store.skipped[0].reason


def test_derived_here_is_refused_when_the_method_is_not_registered(registry_without):
    """An entry that is not there is not a licence to compute anyway."""
    registry_without(**{RELATIVE_HUMIDITY_METHOD: {"drop": True}})
    store = StubStore([(artifact(), dataset())])

    humidity = point(store)["relative_humidity"]

    assert humidity.value is None
    assert store.skipped and "unregistered_method" in store.skipped[0].reason


def test_derived_here_is_refused_when_the_deployment_switches_derivations_off(monkeypatch):
    """The deployment-level switch refuses every derived value and leaves
    retrieved values untouched."""
    monkeypatch.setenv(derive_registry.DERIVED_HERE_ENV, "off")
    store = StubStore([(artifact(), dataset())])

    fields = point(store)

    assert fields["relative_humidity"].value is None
    assert fields["temperature"].value == 14.5, "retrieved values are unaffected"
    assert store.skipped and "deployment_refused" in store.skipped[0].reason


def test_a_derived_here_result_outside_the_physical_range_is_clamped_and_flagged(registry_without):
    narrowed = dataclasses.replace(
        derive_registry.require(RELATIVE_HUMIDITY_METHOD).outputs[0], maximum=50.0, range_rule="clamp"
    )
    registry_without(**{RELATIVE_HUMIDITY_METHOD: {"outputs": (narrowed,)}})

    humidity = point(StubStore([(artifact(), dataset())]))["relative_humidity"]

    assert humidity.value == 50.0
    assert "range_clamped" in humidity.provenance.quality.flags


def test_a_derived_here_result_outside_the_physical_range_may_be_refused(registry_without):
    refusing = dataclasses.replace(
        derive_registry.require(RELATIVE_HUMIDITY_METHOD).outputs[0], maximum=50.0, range_rule="null"
    )
    registry_without(**{RELATIVE_HUMIDITY_METHOD: {"outputs": (refusing,)}})

    store = StubStore([(artifact(), dataset())])
    humidity = point(store)["relative_humidity"]

    assert humidity.value is None
    assert store.skipped and "physical range" in store.skipped[0].reason


def test_a_derived_here_bearing_outside_its_interval_is_wrapped_not_clamped():
    """A bearing is circular, so the wind entry folds it into 0-360 rather
    than pinning it to an end of the interval."""
    value, flags = derive_registry.bound(WIND_METHOD, "wind_direction", 370.0)

    assert value == 10.0 and flags == ("range_wrapped",)


def test_relative_humidity_a_source_published_is_never_replaced_by_a_derivation():
    published = dataset().assign({"relative_humidity_2m": (DIMS, numpy.full((1, 2, 2), 62.0), {"units": "percent"})})

    humidity = point(StubStore([(artifact(), published)]))["relative_humidity"]

    assert humidity.value == 62.0
    assert humidity.provenance.evidence_class == "retrieved"
    assert humidity.provenance.derivation is None


def test_relative_humidity_names_its_registry_entry_and_class():
    entry = derive_registry.require(RELATIVE_HUMIDITY_METHOD)
    humidity = point(StubStore([(artifact(), dataset())]))["relative_humidity"]

    assert humidity.provenance.evidence_class == "derived_here"
    assert humidity.provenance.derivation == entry.name
    assert humidity.provenance.derivation_version == entry.version
    assert humidity.provenance.derivation_citation == entry.citation


# --- never primary, never an input -----------------------------------------

def test_a_reprocessed_value_is_served_as_non_primary():
    temperature = point(StubStore([(artifact(classes=["reprocessed"]), dataset())]))["temperature"]

    assert temperature.value == 14.5, "a reprocessed value is served beside the others, not withheld"
    assert temperature.provenance.evidence_class == "reprocessed"
    assert temperature.provenance.display_primary_eligible is False


def test_an_intermediary_derived_value_is_served_as_non_primary_and_names_its_intermediary():
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


def test_an_uncalibrated_observation_is_served_as_non_primary():
    temperature = point(StubStore([(artifact(source_id="citizen-station", classes=["uncalibrated_observation"]), dataset())]))["temperature"]

    assert temperature.provenance.evidence_class == "uncalibrated_observation"
    assert temperature.provenance.display_primary_eligible is False


def test_a_retrieved_value_is_primary_eligible_and_says_so():
    temperature = point(StubStore([(artifact(), dataset())]))["temperature"]

    assert temperature.provenance.evidence_class == "retrieved"
    assert temperature.provenance.display_primary_eligible is True


@pytest.mark.parametrize("evidence_class", ["reprocessed", "intermediary_derived", "uncalibrated_observation"])
def test_a_non_primary_class_is_never_a_derivation_input(evidence_class: str):
    store = StubStore([(artifact(classes=[evidence_class]), dataset())])

    assert point(store)["relative_humidity"].value is None
    assert store.skipped and evidence_class in store.skipped[0].reason
