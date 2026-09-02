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
