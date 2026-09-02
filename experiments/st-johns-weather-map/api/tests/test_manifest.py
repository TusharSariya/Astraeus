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
from ingest.manifest import ManifestError, RequiredField, RunManifest, validate_run

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
