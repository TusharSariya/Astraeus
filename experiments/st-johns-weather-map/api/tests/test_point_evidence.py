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


# --- delivery kind: whose cell a value is ----------------------------------
# A separate axis from the evidence class. The class says how a value came to
# exist; the kind says whether it is the producer's own cell, an
# intermediary's transformation of it, or something the intermediary computed.

def test_a_value_carries_its_records_delivery_kind_and_intermediary():
    """Copied from the registry record, never inferred from the id."""
    from ingest.registry import get_config

    config = get_config("open-meteo-weathernext-2")
    assert config is not None and config.delivery_kind == "intermediary_derived"

    item = artifact(source_id="open-meteo-weathernext-2", classes=["intermediary_derived"])
    temperature = point(StubStore([(item, dataset())]))["temperature"]

    assert temperature.provenance.delivery_kind == "intermediary_derived"
    assert temperature.provenance.intermediary == config.intermediary == "Open-Meteo"
    assert temperature.provenance.display_primary_eligible is False


def test_a_producer_direct_record_serves_a_published_cell_and_may_be_primary():
    temperature = point(StubStore([(artifact(), dataset())]))["temperature"]

    assert temperature.provenance.delivery_kind == "published_cell"
    assert temperature.provenance.intermediary is None
    assert temperature.provenance.display_primary_eligible is True


def test_a_record_that_refuses_the_display_primary_is_never_a_fields_primary():
    """`display_primary: false` in the record refuses the primary even where
    the class and the kind would allow it: a record may know a reason no other
    field states."""
    from weather_api.models import Coverage, DataMode, Freshness, Provenance, Quality

    base = dict(
        data_mode=DataMode.LIVE, evidence_class="retrieved", source_id="madis-mesonet",
        provider="NOAA MADIS", product="Mesonet", forecast_centre="NOAA", run_time=None,
        valid_time=VALID_TIME, retrieval_time=VALID_TIME, vertical_level="2 m above ground",
        original_units="degC", normalized_units="degC", native_resolution="station",
        native_crs="EPSG:4326", quality=Quality(status="passed"), coverage=Coverage(status="complete"),
        freshness=Freshness.evaluate(60, 21600), licence="open", attribution="NOAA", adapter_version="v1",
    )

    assert Provenance(**base, delivery_kind="published_cell").display_primary_eligible is True
    assert Provenance(**base, delivery_kind="published_cell", source_display_primary=False).display_primary_eligible is False
    assert Provenance(**base, delivery_kind="reprocessed").display_primary_eligible is False


def test_the_catalogue_names_each_records_delivery_kind_and_display_primary():
    from weather_api.store import registry_source_records

    by_id = {record.id: record for record in registry_source_records()}

    assert by_id["eccc-hrdps"].delivery_kind == "published_cell"
    assert by_id["eccc-hrdps"].display_primary is True and by_id["eccc-hrdps"].intermediary is None
    weathernext = by_id["open-meteo-weathernext-2"]
    assert weathernext.delivery_kind == "intermediary_derived"
    assert weathernext.intermediary == "Open-Meteo"
    assert weathernext.display_primary is False


# --- the field catalogue on a response -------------------------------------
# One quantity per key, families on top, phase as an attribute. Every served
# value says which catalogue field it is, which family the field belongs to,
# whether this deployment stores it at all, and - for humidity - which
# saturation phase it was measured against. The response then says, pair by
# pair, which served members of a family may be drawn as one thing.
#
# Spec-Refs: openspec/changes/field-catalogue-and-families/specs/point-evidence-sampling/spec.md
# Spec-Refs: openspec/changes/field-catalogue-and-families/specs/field-catalogue/spec.md

from registry import fields as catalogue  # noqa: E402
from weather_api.models import PointResponse, Selection, field_comparability  # noqa: E402
from weather_api.store import FIELD_BY_VARIABLE, storage_for  # noqa: E402

PERCENT = {"units": "percent"}


def grid(value: float | None) -> numpy.ndarray:
    return numpy.full((1, 2, 2), numpy.nan if value is None else value, dtype="float64")


def surface(**variables: tuple[float | None, dict[str, Any]]) -> xarray.Dataset:
    """A surface artifact carrying exactly the variables a test names."""
    return xarray.Dataset(
        {name: (DIMS, grid(value), attrs) for name, (value, attrs) in variables.items()},
        coords={
            "valid_time": numpy.array([numpy.datetime64(VALID_TIME.replace(tzinfo=None), "ns")]),
            "latitude": numpy.array([47.5, 47.6]),
            "longitude": numpy.array([-52.8, -52.7]),
        },
    )


def served(store: StubStore) -> list[Any]:
    fields, _consensus, _sources = live_point_fields(store, *ST_JOHNS, VALID_TIME)
    return fields


def response_of(store: StubStore) -> dict[str, Any]:
    """The served fields through ``PointResponse``, as a client receives them."""
    return PointResponse(
        latitude=ST_JOHNS[0], longitude=ST_JOHNS[1], valid_time=VALID_TIME,
        selection=Selection(mode="evidence_only", selected_source_id=None, selected_product_id=None, badge="test", reason="test"),
        fields=served(store),
    ).model_dump()


def test_every_served_field_carries_its_catalogue_key_and_family():
    """The API's own name for a field and the catalogue's key are two
    different strings for most fields; the key is the one that identifies the
    quantity, and the family follows from it and from nothing else."""
    store = StubStore([(artifact(), surface(
        temperature_2m=(14.5, {"units": "degC"}),
        total_cloud_opacity=(72.0, PERCENT),
    ))])

    fields = served(store)
    by_field = {item.field: item for item in fields}

    assert by_field["temperature"].key == "temperature_2m"
    assert by_field["temperature"].family == "temperature"
    assert by_field["total_cloud_opacity"].key == "total_cloud_opacity"
    assert by_field["total_cloud_opacity"].family == "cloud_cover"
    assert all(item.key is not None and item.family is not None for item in fields)


def test_a_family_with_mixed_members_reports_each_pair_and_why():
    """The defect this change exists to remove: opacity-weighted, geometric
    and observed dome cover are three quantities, and the response says so
    pair by pair rather than leaving a client to assume one ramp fits all."""
    store = StubStore([
        (artifact(source_id="eccc-hrdps", revision_id="r-hrdps"), surface(total_cloud_opacity=(72.0, PERCENT))),
        (artifact(source_id="noaa-gfs", revision_id="r-gfs"), surface(total_cloud_geometric=(88.0, PERCENT))),
        (artifact(source_id="awc-metar-speci", revision_id="r-metar"), surface(total_cloud_okta=(100.0, PERCENT))),
    ])

    pairs = {(item.a, item.b): item for item in field_comparability(served(store))}

    assert len(pairs) == 3, "three members make three unordered pairs"
    assert all(item.family == "cloud_cover" for item in pairs.values())
    assert all(item.comparable is False and item.reason == "definition" for item in pairs.values())
    detail = pairs[("total_cloud_geometric", "total_cloud_opacity")].detail
    assert "opacity" in detail and "geometric" in detail


def test_two_members_of_one_definition_are_comparable():
    """HRDPS and RDPS publish the same opacity-weighted quantity, so the pair
    is comparable and carries no reason."""
    store = StubStore([
        (artifact(source_id="eccc-hrdps", revision_id="r-hrdps"), surface(total_cloud_opacity=(72.0, PERCENT))),
        (artifact(source_id="eccc-rdps", revision_id="r-rdps"), surface(total_cloud_opacity=(68.0, PERCENT))),
    ])

    pairs = field_comparability(served(store))

    assert [(item.a, item.b, item.comparable) for item in pairs] == [
        ("total_cloud_opacity", "total_cloud_opacity", True)
    ]
    assert pairs[0].reason is None and pairs[0].detail is None


def test_two_families_are_never_paired_with_each_other():
    """Comparability lives inside a family; two families are not a pair at
    all, so nothing invites a client to difference them."""
    store = StubStore([(artifact(), surface(
        total_cloud_opacity=(72.0, PERCENT),
        mean_sea_level_pressure=(1004.0, {"units": "hPa"}),
    ))])

    assert field_comparability(served(store)) == []


def test_humidity_phase_is_read_off_the_value_and_only_humidity_carries_one():
    store = StubStore([(artifact(), surface(
        relative_humidity_2m=(82.0, {"units": "percent", catalogue.PHASE_ATTRIBUTE: "liquid_water"}),
        total_cloud_opacity=(72.0, PERCENT),
    ))])

    by_field = {item.field: item for item in served(store)}

    assert by_field["relative_humidity"].phase == "liquid"
    assert by_field["total_cloud_opacity"].phase is None
    assert catalogue.requires_phase("relative_humidity_2m") is True


def test_a_liquid_and_a_mixed_humidity_are_not_comparable_below_freezing():
    """Measured, not assumed: below 273.16 K the two saturation bases differ
    by up to about 24 percent for identical air."""
    store = StubStore([
        (artifact(source_id="eccc-hrdps", revision_id="r-hrdps"), surface(
            temperature_2m=(-5.0, {"units": "degC"}),
            relative_humidity_2m=(82.0, {"units": "percent", catalogue.PHASE_ATTRIBUTE: "liquid_water"}),
        )),
        (artifact(source_id="noaa-gfs", revision_id="r-gfs"), surface(
            relative_humidity_2m=(94.0, {"units": "percent", catalogue.PHASE_ATTRIBUTE: "mixed_linear_253K_273K"}),
        )),
    ])

    humidity = [item for item in field_comparability(served(store)) if item.family == "humidity"]

    assert [(item.a, item.b, item.comparable, item.reason) for item in humidity] == [
        ("relative_humidity_2m", "relative_humidity_2m", False, "phase")
    ]
    assert "273.16" in humidity[0].detail


def test_the_same_liquid_and_mixed_pair_is_comparable_above_freezing():
    store = StubStore([
        (artifact(source_id="eccc-hrdps", revision_id="r-hrdps"), surface(
            temperature_2m=(6.5, {"units": "degC"}),
            relative_humidity_2m=(82.0, {"units": "percent", catalogue.PHASE_ATTRIBUTE: "liquid_water"}),
        )),
        (artifact(source_id="noaa-gfs", revision_id="r-gfs"), surface(
            relative_humidity_2m=(94.0, {"units": "percent", catalogue.PHASE_ATTRIBUTE: "mixed_linear_253K_273K"}),
        )),
    ])

    humidity = [item for item in field_comparability(served(store)) if item.family == "humidity"]

    assert [(item.comparable, item.reason) for item in humidity] == [(True, None)]


def test_a_humidity_with_no_phase_refuses_the_comparison_rather_than_guessing():
    store = StubStore([
        (artifact(source_id="eccc-hrdps", revision_id="r-hrdps"), surface(
            temperature_2m=(-5.0, {"units": "degC"}),
            relative_humidity_2m=(82.0, {"units": "percent"}),
        )),
        (artifact(source_id="noaa-gfs", revision_id="r-gfs"), surface(
            relative_humidity_2m=(94.0, {"units": "percent", catalogue.PHASE_ATTRIBUTE: "mixed_linear_253K_273K"}),
        )),
    ])

    humidity = [item for item in field_comparability(served(store)) if item.family == "humidity"]

    assert [(item.comparable, item.reason) for item in humidity] == [(False, "phase_missing")]


def test_a_derived_humidity_carries_the_phase_its_registered_method_declares():
    """``relative_humidity_from_dewpoint_liquid`` evaluates Bolton's
    saturation vapour pressure over liquid water explicitly, so the phase is
    the method's declaration and not an assumption about the inputs."""
    humidity = {item.field: item for item in served(StubStore([(artifact(), dataset())]))}["relative_humidity"]

    assert humidity.provenance.evidence_class == "derived_here"
    assert humidity.phase == "liquid"


def test_a_served_value_says_stored_and_a_gap_says_what_the_catalogue_knows():
    """Three different answers a null must keep apart. GFS publishes
    ``APCP`` and this deployment does not fetch it, so the null is
    ``available-not-stored``, not a reading that went missing."""
    store = StubStore([(artifact(source_id="noaa-gfs"), surface(
        total_cloud_geometric=(88.0, PERCENT),
        precipitation_accumulation=(None, {"units": "mm"}),
    ))])

    by_field = {item.field: item for item in served(store)}

    assert by_field["total_cloud_geometric"].storage == "stored"
    assert by_field["precipitation_accumulation"].value is None
    assert by_field["precipitation_accumulation"].storage == "available-not-stored"
    assert storage_for("eccc-reps", "wind_direction_10m", None) == "not-published"


def test_the_point_response_carries_the_comparability_beside_the_fields():
    store = StubStore([
        (artifact(source_id="eccc-hrdps", revision_id="r-hrdps"), surface(total_cloud_opacity=(72.0, PERCENT))),
        (artifact(source_id="noaa-gfs", revision_id="r-gfs"), surface(total_cloud_geometric=(88.0, PERCENT))),
    ])

    payload = response_of(store)

    assert [(item["family"], item["a"], item["b"], item["comparable"]) for item in payload["comparability"]] == [
        ("cloud_cover", "total_cloud_geometric", "total_cloud_opacity", False)
    ]
    assert {item["key"] for item in payload["fields"]} == {"total_cloud_opacity", "total_cloud_geometric"}
    assert all(item["storage"] == "stored" for item in payload["fields"])


# --- a variable the catalogue does not carry -------------------------------

def test_an_uncatalogued_variable_is_not_served_and_a_notice_names_it(monkeypatch):
    """The API's served set is a table; the catalogue is the authority. A
    table entry the catalogue cannot resolve serves nothing, rather than
    serving a value under whatever the table happened to call it."""
    monkeypatch.setitem(FIELD_BY_VARIABLE, "sky_vibes", "sky_vibes")
    store = StubStore([(artifact(), surface(
        temperature_2m=(14.5, {"units": "degC"}),
        sky_vibes=(7.0, PERCENT),
    ))])

    by_field = {item.field: item for item in served(store)}
    vibes = by_field["sky_vibes"]

    assert vibes.value is None
    assert vibes.key is None and vibes.family is None
    assert vibes.provenance.data_mode == "unavailable"
    assert "uncatalogued_field" in vibes.provenance.quality.flags
    assert by_field["temperature"].value == 14.5, "one uncatalogued variable costs no other field"
    assert store.skipped and "sky_vibes" in store.skipped[0].reason
    assert "eccc-hrdps/surface" in store.skipped[0].reason


def test_an_uncatalogued_variable_is_left_out_of_every_comparability_pair(monkeypatch):
    monkeypatch.setitem(FIELD_BY_VARIABLE, "sky_vibes", "sky_vibes")
    store = StubStore([(artifact(), surface(
        total_cloud_opacity=(72.0, PERCENT),
        sky_vibes=(7.0, PERCENT),
    ))])

    assert field_comparability(served(store)) == []


# --- task 3.0: the API's own variable tables were re-keyed -----------------

def test_an_hrdps_keyed_artifact_reaches_point_with_its_cloud():
    """The live-artifact check for task 3.0, run through the store rather than
    against the running stack: the stack in the main checkout is built from
    code that predates the re-key, so asking it would measure the old tables.
    This builds the artifact the re-keyed adapters now publish - HRDPS cloud
    under ``total_cloud_opacity`` - and asserts it reaches ``/point`` under its
    catalogue key with its family."""
    store = StubStore([(artifact(source_id="eccc-hrdps"), surface(
        temperature_2m=(14.5, {"units": "degC"}),
        total_cloud_opacity=(72.0, PERCENT),
    ))])

    cloud = {item.field: item for item in served(store)}["total_cloud_opacity"]

    assert cloud.value == 72.0
    assert cloud.key == "total_cloud_opacity" and cloud.family == "cloud_cover"
    assert cloud.provenance.data_mode == "live" and cloud.provenance.source_id == "eccc-hrdps"
    assert catalogue.storage_of("eccc-hrdps", "total_cloud_opacity") == "stored"
    assert "total_cloud" not in FIELD_BY_VARIABLE, "the collided key is gone from the API's table"


# --- aged out: the third absence state, end to end ------------------------
#
# Five absence states reach a reader, and they are five different facts about
# this deployment. ``aged_out`` is the one that says evidence WAS here: it
# carries the last valid time the store held, so the reader is told the edge of
# what was available rather than merely that something is gone. These assert
# the wire shape the web renders from - the flag on ``quality.flags``, the
# instant on ``provenance.last_valid_time`` - and that no other absence
# borrows it.
#
# Spec-Refs: openspec/changes/storage-window-and-restart-cache/specs/evidence-window-timeline/spec.md

import sys as _sys  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from weather_api.app import PREFIX, app as _app  # noqa: E402
from weather_api.models import AGED_OUT_FLAG, Provenance  # noqa: E402
from weather_api.store import ABSENCE_STATES, StoreUnavailable, absence_state, unavailable_point_fields  # noqa: E402

_api_module = _sys.modules["weather_api.app"]
_client = TestClient(_app)
HELD_UNTIL = datetime(2026, 9, 1, 6, tzinfo=UTC)


class _EmptyStore:
    skipped: list[Any] = []
    unmodelled: list[Any] = []

    def published_products(self) -> dict[str, set[datetime]]:
        return {}

    def source_activity(self) -> dict[str, datetime]:
        return {}

    def current(self) -> list[Any]:
        return []

    def sample_point(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []


@pytest.fixture
def empty_live_store(monkeypatch, data_mode):
    """A reachable live store that holds nothing, with no history recorded."""
    data_mode("live")
    monkeypatch.setattr(_api_module, "live_store", lambda: _EmptyStore())
    monkeypatch.setattr(_api_module, "last_valid_times", lambda store: {})
    return monkeypatch


def test_the_five_absence_states_are_named_once_and_stay_distinct():
    assert ABSENCE_STATES == ("null", "blocked", "aged_out", "retrieval_failed", "available-not-stored")
    assert len(set(ABSENCE_STATES)) == 5


def test_aged_out_is_reported_with_the_last_valid_time_the_store_held(empty_live_store):
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-hrdps": HELD_UNTIL})

    payload = _client.get(f"{PREFIX}/point").json()

    assert payload["data_mode"] == "unavailable"
    assert HELD_UNTIL.isoformat() in payload["selection"]["reason"]
    for field in payload["fields"]:
        assert field["value"] is None
        assert AGED_OUT_FLAG in field["provenance"]["quality"]["flags"]
        assert "aged_out:eccc-hrdps" in field["provenance"]["quality"]["flags"]
        assert datetime.fromisoformat(field["provenance"]["last_valid_time"]) == HELD_UNTIL
        # The QC status keeps its four values; ageing out is a flag, never a
        # fifth status, because a value's verdict is not changed by its removal.
        assert field["provenance"]["quality"]["status"] in {"passed", "suspect", "failed", "unknown"}


def test_a_source_that_never_published_here_reports_null_not_aged_out(empty_live_store):
    payload = _client.get(f"{PREFIX}/point").json()

    assert payload["data_mode"] == "unavailable"
    for field in payload["fields"]:
        assert field["value"] is None
        assert AGED_OUT_FLAG not in field["provenance"]["quality"]["flags"]
        assert field["provenance"]["last_valid_time"] is None
        # ``no_retrieval`` is the null absence: nothing was ever held.
        assert "no_retrieval" in field["provenance"]["quality"]["flags"]


def test_aged_out_is_not_no_retrieval(empty_live_store):
    """They are different claims: one says we had it, the other says we never did."""
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-hrdps": HELD_UNTIL})
    payload = _client.get(f"{PREFIX}/point").json()
    flags = payload["fields"][0]["provenance"]["quality"]["flags"]
    assert AGED_OUT_FLAG in flags and "no_retrieval" not in flags


def test_a_selected_product_that_aged_out_names_itself(empty_live_store):
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-reps": HELD_UNTIL})

    payload = _client.get(f"{PREFIX}/point", params={"product": "REPS"}).json()

    assert "REPS" in payload["selection"]["reason"]
    assert HELD_UNTIL.isoformat() in payload["selection"]["reason"]
    for field in payload["fields"]:
        assert field["provenance"]["source_id"] == "eccc-reps"
        assert "aged_out:eccc-reps" in field["provenance"]["quality"]["flags"]
        assert datetime.fromisoformat(field["provenance"]["last_valid_time"]) == HELD_UNTIL


def test_a_selected_product_that_was_never_held_is_still_null(empty_live_store):
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-hrdps": HELD_UNTIL})

    payload = _client.get(f"{PREFIX}/point", params={"product": "REPS"}).json()

    for field in payload["fields"]:
        assert AGED_OUT_FLAG not in field["provenance"]["quality"]["flags"], "another source's history is not this one's"
        assert field["provenance"]["last_valid_time"] is None


def test_an_unreadable_last_valid_time_record_reports_unavailable_not_an_absence(empty_live_store):
    """Guessing between aged out and null is itself a fabrication."""

    def raising(store):
        raise StoreUnavailable("the last valid time table is unreachable")

    empty_live_store.setattr(_api_module, "last_valid_times", raising)
    payload = _client.get(f"{PREFIX}/point").json()

    assert payload["data_mode"] == "unavailable"
    assert all(AGED_OUT_FLAG not in field["provenance"]["quality"]["flags"] for field in payload["fields"])
    assert any("aged out" in notice for notice in payload["notices"])


def test_the_profile_reports_aged_out_the_same_way(empty_live_store):
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-hrdps": HELD_UNTIL})
    empty_live_store.setattr(_api_module, "live_profile_levels", lambda *args, **kwargs: [])

    payload = _client.get(f"{PREFIX}/profile").json()

    assert payload["data_mode"] == "unavailable"
    for level in payload["levels"]:
        for field in level["fields"]:
            assert field["value"] is None
            assert AGED_OUT_FLAG in field["provenance"]["quality"]["flags"]
            assert datetime.fromisoformat(field["provenance"]["last_valid_time"]) == HELD_UNTIL


def test_the_layer_index_names_its_aged_out_sources(empty_live_store):
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-hrdps": HELD_UNTIL})
    empty_live_store.setattr(_api_module, "_proxied_forecast_layers", lambda: ([], []))

    payload = _client.get(f"{PREFIX}/layers").json()

    assert payload["data_mode"] == "unavailable"
    assert payload["layers"] == []
    assert datetime.fromisoformat(payload["aged_out_sources"]["eccc-hrdps"]) == HELD_UNTIL


def test_the_timeline_reports_aged_out_beside_its_empty_hours(empty_live_store):
    empty_live_store.setattr(_api_module, "last_valid_times", lambda store: {"eccc-hrdps": HELD_UNTIL})

    payload = _client.get(f"{PREFIX}/timeline").json()

    assert len(payload["items"]) == 361
    named = payload["items"][0]["aged_out_sources"]
    assert datetime.fromisoformat(named["eccc-hrdps"]) == HELD_UNTIL


# --- the model refuses the half-stated claim -----------------------------

def test_aged_out_without_a_last_valid_time_is_refused_by_the_model():
    """A deployment that never held a frame must not claim it held one."""
    with pytest.raises(ValueError, match="last_valid_time"):
        unavailable_point_fields(VALID_TIME, flags=[AGED_OUT_FLAG])


def test_a_last_valid_time_must_carry_an_offset():
    fields = unavailable_point_fields(VALID_TIME, flags=[AGED_OUT_FLAG], last_valid_time=HELD_UNTIL)
    provenance = fields[0].provenance
    assert isinstance(provenance, Provenance)
    assert provenance.last_valid_time == HELD_UNTIL

    with pytest.raises(ValueError, match="offset"):
        unavailable_point_fields(VALID_TIME, flags=[AGED_OUT_FLAG], last_valid_time=HELD_UNTIL.replace(tzinfo=None))


def test_absence_state_answers_aged_out_only_where_a_record_exists():
    assert absence_state(None, "eccc-hrdps", held={"eccc-hrdps": HELD_UNTIL}) == ("aged_out", HELD_UNTIL)
    assert absence_state(None, "eccc-hrdps", held={}) == ("null", None)
