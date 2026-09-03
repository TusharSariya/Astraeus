"""What an artifact declares about the classes it contains.

A data path admits or excludes an artifact on its declared classes, so a
manifest that understates them would let a value through a gate that read the
declaration and believed it. The declaration is checked against the values
before anything publishes.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/evidence-truth-boundary/spec.md
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy
import pytest
import xarray

from ingest.contract import FetchWindow
from ingest.manifest import (
    ManifestError,
    RequiredField,
    RunManifest,
    StorageScopeReport,
    apply_storage_scope,
    validate_run,
)

UTC = timezone.utc
T0 = datetime(2026, 9, 2, 12, tzinfo=UTC)
WINDOW = FetchWindow(now=T0)


def dataset(*, classes: dict[str, str] | None = None) -> xarray.Dataset:
    """A two-variable run: a retrieved temperature and a fog closure."""
    stamps = numpy.array([numpy.datetime64(T0.replace(tzinfo=None), "ns")])
    latitudes, longitudes = numpy.array([47.0, 48.0]), numpy.array([-53.0, -52.0])
    shape = (1, 2, 2)
    stated = classes or {}
    return xarray.Dataset(
        {
            "temperature_2m": (
                ("valid_time", "latitude", "longitude"),
                numpy.full(shape, 10.0),
                {"units": "degC", **({"evidence_class": stated["temperature_2m"]} if "temperature_2m" in stated else {})},
            ),
            "fog_closure": (
                ("valid_time", "latitude", "longitude"),
                numpy.full(shape, 0.4),
                {"units": "1", **({"evidence_class": stated["fog_closure"]} if "fog_closure" in stated else {})},
            ),
        },
        coords={"valid_time": stamps, "latitude": latitudes, "longitude": longitudes},
    )


def manifest(*, fog_class: str = "derived_here", declared: tuple[str, ...] = ()) -> RunManifest:
    return RunManifest(
        source_id="eccc-hrdps",
        fields=(
            RequiredField(name="temperature_2m", units="degC"),
            RequiredField(name="fog_closure", units="1", evidence_class=fog_class),
        ),
        evidence_classes=declared,
    )


def test_evidence_classes_that_understate_the_run_fail_with_evidence_class_mismatch():
    result = validate_run(manifest(declared=("retrieved",)), dataset(), window=WINDOW)

    assert result.publishable is False
    assert any(flag.startswith("evidence_class_mismatch:derived_here") for flag in result.flags), result.flags
    assert result.qc_passed is False


def test_evidence_classes_that_cover_every_field_publish():
    result = validate_run(manifest(declared=("retrieved", "derived_here")), dataset(), window=WINDOW)

    assert result.publishable is True
    assert result.flags == ()


def test_the_declared_evidence_classes_default_to_the_set_the_fields_state():
    """An adapter that says nothing publishes exactly what its fields declare,
    which for every retrieval adapter is ``retrieved`` alone."""
    entry = manifest()
    assert entry.declared_classes == ("derived_here", "retrieved")
    assert manifest(fog_class="retrieved").declared_classes == ("retrieved",)
    assert validate_run(manifest(), dataset(), window=WINDOW).publishable is True


def test_a_value_outside_the_declared_evidence_classes_is_refused():
    """The value speaks: a variable stamped ``generated_display`` under a
    field declared ``retrieved`` is the mismatch this gate exists for."""
    result = validate_run(
        manifest(fog_class="retrieved"),
        dataset(classes={"fog_closure": "generated_display"}),
        window=WINDOW,
    )

    assert result.publishable is False
    assert any(flag.startswith("evidence_class_mismatch:fog_closure:generated_display") for flag in result.flags), result.flags


def test_values_carrying_their_declared_evidence_classes_pass():
    result = validate_run(
        manifest(declared=("retrieved", "derived_here")),
        dataset(classes={"temperature_2m": "retrieved", "fog_closure": "derived_here"}),
        window=WINDOW,
    )

    assert result.publishable is True


def test_evidence_classes_outside_the_six_are_refused_at_declaration():
    with pytest.raises(ManifestError, match="six evidence classes"):
        RequiredField(name="temperature_2m", units="degC", evidence_class="consensus")
    with pytest.raises(ManifestError, match="six evidence classes"):
        RunManifest(source_id="eccc-hrdps", fields=(RequiredField(name="temperature_2m", units="degC"),), evidence_classes=("blend",))


def test_the_manifest_block_records_evidence_classes_per_variable():
    """This block is what the API reads to admit an artifact and to give each
    sampled value its class, so its shape is pinned here."""
    block = manifest(declared=("retrieved", "derived_here")).as_manifest_block()

    assert block == {
        "evidence_classes": ["derived_here", "retrieved"],
        "evidence_class_by_variable": {"temperature_2m": "retrieved", "fog_closure": "derived_here"},
    }


# --- catalogue key and unit validation ------------------------------------
#
# Spec-Refs: openspec/changes/field-catalogue-and-families/specs/field-catalogue/spec.md
#            openspec/changes/field-catalogue-and-families/specs/artifact-ingestion/spec.md


def humidity_dataset(*, convention: str | None = "liquid_water", units: str = "percent") -> xarray.Dataset:
    """A one-variable run carrying a screen humidity, with or without its phase."""
    stamps = numpy.array([numpy.datetime64(T0.replace(tzinfo=None), "ns")])
    attrs: dict[str, str] = {"units": units}
    if convention is not None:
        attrs["rh_phase_convention"] = convention
    return xarray.Dataset(
        {
            "relative_humidity_2m": (
                ("valid_time", "latitude", "longitude"),
                numpy.full((1, 2, 2), 80.0),
                attrs,
            )
        },
        coords={
            "valid_time": stamps,
            "latitude": numpy.array([47.0, 48.0]),
            "longitude": numpy.array([-53.0, -52.0]),
        },
    )


def humidity_manifest() -> RunManifest:
    return RunManifest(
        source_id="eccc-hrdps",
        fields=(RequiredField(name="relative_humidity_2m", units="percent"),),
    )


def test_a_manifest_naming_a_key_the_catalogue_lacks_is_refused_at_declaration():
    """``total_cloud`` is the collision this catalogue exists to stop: three
    adapters declared it and two of them meant different quantities. It is not a
    key any more, and a manifest that names it cannot be built at all, so the
    adapter is never schedulable."""
    with pytest.raises(ManifestError, match="uncatalogued_field:total_cloud"):
        RequiredField(name="total_cloud", units="percent")


def test_a_catalogue_key_with_the_wrong_unit_is_refused_at_declaration():
    with pytest.raises(ManifestError, match="bad_units:temperature_2m"):
        RequiredField(name="temperature_2m", units="K")


def test_the_split_cloud_keys_all_resolve_against_the_catalogue():
    for name in ("total_cloud_opacity", "total_cloud_geometric", "total_cloud_mean_6h", "total_cloud_okta"):
        field = RequiredField(name=name, units="percent")
        assert field.catalogue_field.family == "cloud_cover"


def test_a_level_expanded_variable_resolves_to_its_profile_key():
    """The GRIB adapters write one variable per pressure level; the catalogue
    keeps one key with a level coordinate, and the two meet here."""
    field = RequiredField(name="relative_humidity_850hPa", units="percent")
    assert field.catalogue_field.key == "relative_humidity_pressure"
    assert field.catalogue_field.level_coordinate == "pressure"


def test_a_humidity_without_its_phase_fails_qc():
    """A threshold calibrated on one saturation phase is not transferable to the
    other, so a humidity that cannot say which it is is not evidence."""
    result = validate_run(humidity_manifest(), humidity_dataset(convention=None), window=WINDOW)

    assert result.publishable is False
    assert result.qc_passed is False
    assert any(flag.startswith("missing_phase:relative_humidity_2m") for flag in result.flags), result.flags


def test_a_humidity_with_an_unrecognised_phase_convention_fails_qc():
    result = validate_run(
        humidity_manifest(), humidity_dataset(convention="whatever_felt_right"), window=WINDOW
    )

    assert result.publishable is False
    assert any(flag.startswith("missing_phase:") for flag in result.flags), result.flags


def test_a_humidity_carrying_a_measured_phase_publishes():
    result = validate_run(humidity_manifest(), humidity_dataset(), window=WINDOW)

    assert result.publishable is True
    assert result.flags == ()


def test_a_catalogue_unit_the_data_contradicts_fails_qc_as_bad_units():
    result = validate_run(humidity_manifest(), humidity_dataset(units="1"), window=WINDOW)

    assert result.qc_passed is False
    assert any(flag.startswith("bad_units:relative_humidity_2m") for flag in result.flags), result.flags


def test_an_uncatalogued_upstream_coverage_is_reported_and_does_not_block_the_run():
    """A GeoMet source is subset server side, so its scope is every published
    field. A coverage the catalogue does not know must be named, and must not
    stop the fields it does know from publishing."""
    result = validate_run(
        humidity_manifest(),
        humidity_dataset(),
        window=WINDOW,
        upstream_fields=("HRDPS.CONTINENTAL_HR", "HRDPS.CONTINENTAL_SOMETHING_NEW"),
    )

    assert result.publishable is True, result.flags
    assert result.notices == ("uncatalogued_upstream_field:HRDPS.CONTINENTAL_SOMETHING_NEW",)
    assert result.as_quality()["notices"] == ["uncatalogued_upstream_field:HRDPS.CONTINENTAL_SOMETHING_NEW"]


def test_a_run_with_nothing_uncatalogued_carries_no_notices_block():
    """The provenance quality block keeps its existing shape when there is
    nothing to report; a notices key that is always present would be noise."""
    result = validate_run(
        humidity_manifest(), humidity_dataset(), window=WINDOW, upstream_fields=("HRDPS.CONTINENTAL_HR",)
    )

    assert result.notices == ()
    assert "notices" not in result.as_quality()


# --- the per-family storage scope -----------------------------------------
#
# Spec-Refs: openspec/changes/ensemble-families-and-member-statistics/specs/artifact-ingestion/spec.md
#            ("Storage scope is applied per family at ingest, and the difference
#            is recorded")
#
# The names below are the producer's own: GeoMet coverage ids for REPS, GRIB
# record labels for GEFS, exactly as ``registry/fields.py`` maps them. Nothing
# here re-derives which fields a source stores.

REPS_PUBLISHED = (
    "REPS.MEM.ETA_TT.01",
    "REPS.MEM.ETA_NT.01",
    "REPS.MEM.ETA_WSPD.01",
)

#: Every record GEFS publishes that the catalogue maps to a stored key.
GEFS_STORED = (
    "TMP:2 m above ground",
    "DPT:2 m above ground",
    "RH:2 m above ground",
    "UGRD:10 m above ground",
    "VGRD:10 m above ground",
    "PRMSL:mean sea level",
    "TCDC:entire atmosphere (n-n+6 hour ave fcst)",
)

#: Three of the 621 records the same run publishes and this deployment does not
#: keep: the single-level instantaneous cloud, a convective cloud-top pressure
#: the catalogue maps nothing to, and one pressure-level humidity.
GEFS_NOT_STORED = ("TCDC:475 mb", "PRES:cloud top", "RH:500 mb")


def member_dataset(*, members: tuple[str, ...] = ("gec00", "gep01"), units: str = "degC") -> xarray.Dataset:
    """A member-shaped run, so the scope rules see an ensemble family."""
    stamps = numpy.array([numpy.datetime64(T0.replace(tzinfo=None), "ns")])
    shape = (len(members), 1, 2, 2)
    return xarray.Dataset(
        {
            "temperature_2m": (
                ("member", "valid_time", "latitude", "longitude"),
                numpy.full(shape, 10.0),
                {"units": units},
            )
        },
        coords={
            "member": numpy.array(members, dtype=object).astype(str),
            "control": ("member", numpy.array([name == members[0] for name in members])),
            "valid_time": stamps,
            "latitude": numpy.array([47.0, 48.0]),
            "longitude": numpy.array([-53.0, -52.0]),
        },
    )


def scoped_manifest(source_id: str, scope: str | None) -> RunManifest:
    return RunManifest(
        source_id=source_id,
        fields=(RequiredField(name="temperature_2m", units="degC"),),
        member_count=2,
        control="gec00",
        storage_scope=scope,
    )


def test_a_subsettable_family_stores_every_published_field_and_lists_nothing_as_available_not_stored():
    """REPS is subset server side, so wire and stored are the same set: there is
    no such thing as a REPS field that exists upstream and is not kept."""
    report = apply_storage_scope(
        "eccc-reps",
        scope="every_published_field",
        published=REPS_PUBLISHED,
        retrieved=REPS_PUBLISHED,
    )

    assert report == StorageScopeReport(applied="every_published_field")
    assert report.as_provenance() == {
        "applied": "every_published_field",
        "available_not_stored": [],
        "not_retrieved": [],
    }


def test_a_published_field_missing_under_the_every_field_scope_is_refused():
    """A subsetting source has no available-not-stored list to put it on, so a
    published coverage that did not arrive is the adapter contradicting its own
    scope rather than a storage decision."""
    with pytest.raises(ManifestError, match="REPS.MEM.ETA_WSPD.01"):
        apply_storage_scope(
            "eccc-reps",
            scope="every_published_field",
            published=REPS_PUBLISHED,
            retrieved=REPS_PUBLISHED[:2],
        )


def test_a_non_subsettable_family_stores_the_family_fields_and_lists_the_rest():
    """GEFS costs its whole file per record, so only the catalogue's family
    fields are fetched and every other published record is catalogued."""
    report = apply_storage_scope(
        "noaa-gefs",
        scope="family_fields_only",
        published=(*GEFS_STORED, *GEFS_NOT_STORED),
        retrieved=GEFS_STORED,
    )

    assert report.applied == "family_fields_only"
    assert report.available_not_stored == GEFS_NOT_STORED
    assert report.not_retrieved == ()
    assert "TCDC:entire atmosphere (n-n+6 hour ave fcst)" not in report.available_not_stored, (
        "the six-hour mean cloud is a stored family field, not an exclusion"
    )


def test_the_available_not_stored_list_carries_the_producers_own_names():
    """A catalogue key would not name the thing a reader would have to go and
    fetch, so the exclusions are recorded as upstream record labels."""
    report = apply_storage_scope(
        "noaa-gefs",
        scope="family_fields_only",
        published=(*GEFS_STORED, *GEFS_NOT_STORED),
        retrieved=GEFS_STORED,
    )

    assert report.as_provenance()["available_not_stored"] == list(GEFS_NOT_STORED)


def test_a_stored_field_that_did_not_arrive_lands_in_not_retrieved_as_a_catalogue_key():
    """Distinct from the fields the scope excluded on purpose: this one was
    inside the scope and is a gap, so it is named by catalogue key."""
    report = apply_storage_scope(
        "noaa-gefs",
        scope="family_fields_only",
        published=(*GEFS_STORED, *GEFS_NOT_STORED),
        retrieved=tuple(name for name in GEFS_STORED if not name.startswith("TCDC:")),
    )

    assert report.not_retrieved == ("total_cloud_mean_6h",)
    assert report.available_not_stored == GEFS_NOT_STORED
    assert "total_cloud_mean_6h" not in report.available_not_stored


def test_a_scope_value_outside_the_two_is_refused():
    with pytest.raises(ManifestError, match="every_published_field, family_fields_only"):
        apply_storage_scope("noaa-gefs", scope="whatever_fits", published=(), retrieved=())
    with pytest.raises(ManifestError, match="every_published_field, family_fields_only"):
        RunManifest(
            source_id="noaa-gefs",
            fields=(RequiredField(name="temperature_2m", units="degC"),),
            storage_scope="most_of_it",
        )


def test_a_source_the_catalogue_declares_no_scope_for_retrieves_nothing():
    """Where the subsettability declaration is absent, nothing is retrieved for
    that family, rather than defaulting to either scope."""
    with pytest.raises(ManifestError, match="declares no storage scope"):
        apply_storage_scope("made-up-source", scope="family_fields_only", published=(), retrieved=())


def test_a_scope_that_contradicts_the_catalogue_is_refused():
    """The scope is declared once in the catalogue and copied into the registry;
    a manifest that picks the other one is refused rather than obeyed."""
    with pytest.raises(ManifestError, match="declares 'every_published_field'"):
        apply_storage_scope(
            "eccc-reps", scope="family_fields_only", published=REPS_PUBLISHED, retrieved=REPS_PUBLISHED
        )


def test_validate_run_records_the_storage_scope_beside_the_members():
    """The two blocks sit together in provenance: what the member axis held and
    what the scope kept, so a reader never has to infer either."""
    result = validate_run(
        scoped_manifest("noaa-gefs", "family_fields_only"),
        member_dataset(),
        window=WINDOW,
        upstream_fields=(*GEFS_STORED, *GEFS_NOT_STORED),
        retrieved_fields=GEFS_STORED,
        declared_members=("gec00", "gep01"),
        control_retrieval="separate_file",
    )

    assert result.as_storage_scope() == {
        "applied": "family_fields_only",
        "available_not_stored": list(GEFS_NOT_STORED),
        "not_retrieved": [],
    }
    assert result.as_members()["present"] == ["gec00", "gep01"]
    assert not any(flag.startswith("scope_incomplete") for flag in result.flags), result.flags


def test_a_run_short_of_the_applied_scope_publishes_incomplete_naming_the_field():
    result = validate_run(
        scoped_manifest("noaa-gefs", "family_fields_only"),
        member_dataset(),
        window=WINDOW,
        upstream_fields=(*GEFS_STORED, *GEFS_NOT_STORED),
        retrieved_fields=tuple(name for name in GEFS_STORED if not name.startswith("PRMSL")),
        declared_members=("gec00", "gep01"),
    )

    assert result.complete is False
    assert "scope_incomplete:mean_sea_level_pressure" in result.flags, result.flags
    # A completeness failure, not a QC one: the data that arrived is not wrong.
    assert result.qc_passed is True
    assert result.as_storage_scope()["not_retrieved"] == ["mean_sea_level_pressure"]


def test_an_ensemble_family_manifest_with_no_scope_fails_qc_storage_scope_unstated():
    result = validate_run(
        scoped_manifest("noaa-gefs", None),
        member_dataset(),
        window=WINDOW,
        upstream_fields=(*GEFS_STORED, *GEFS_NOT_STORED),
        declared_members=("gec00", "gep01"),
    )

    assert result.qc_passed is False
    assert "storage_scope_unstated" in result.flags, result.flags
    assert result.as_storage_scope() is None


def test_a_deterministic_run_that_states_no_scope_is_unchanged():
    """Every existing adapter states no scope and must validate exactly as
    before; the scope block is absent rather than invented."""
    result = validate_run(manifest(), dataset(), window=WINDOW)

    assert result.publishable is True
    assert result.storage_scope is None
    assert result.as_storage_scope() is None


def test_a_class_the_catalogue_forbids_on_a_field_fails_qc():
    """Sun altitude is computed here from a pinned ephemeris; no producer issues
    it, so a manifest calling it retrieved is refused."""
    manifest_entry = RunManifest(
        source_id="nasa-jpl-de442",
        fields=(RequiredField(name="sun_altitude", units="degree", evidence_class="retrieved"),),
    )
    stamps = numpy.array([numpy.datetime64(T0.replace(tzinfo=None), "ns")])
    data = xarray.Dataset(
        {
            "sun_altitude": (
                ("valid_time", "latitude", "longitude"),
                numpy.full((1, 2, 2), 12.0),
                {"units": "degree"},
            )
        },
        coords={
            "valid_time": stamps,
            "latitude": numpy.array([47.0, 48.0]),
            "longitude": numpy.array([-53.0, -52.0]),
        },
    )
    result = validate_run(manifest_entry, data, window=WINDOW)

    assert result.qc_passed is False
    assert any(
        flag.startswith("evidence_class_not_permitted:sun_altitude:retrieved") for flag in result.flags
    ), result.flags
