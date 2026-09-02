"""The evidence class is a field, and the QC status set is still four.

A class inferred from three unrelated signals - a derivation name, an
``evidence_basis``, a generated flag - is how a generated repair reached
``/point`` on 2026-09-01. A required field with no default cannot be
forgotten: the failure becomes a validation error at publication rather than a
silent promotion at read time.

Spec-Refs: openspec/changes/evidence-classes-and-derived-here/specs/evidence-truth-boundary/spec.md
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from weather_api.models import (
    EVIDENCE_CLASSES,
    ArtifactManifest,
    Coverage,
    DataMode,
    Freshness,
    Provenance,
    Quality,
)

UTC = timezone.utc
VALID_TIME = datetime(2026, 9, 2, 12, tzinfo=UTC)


def provenance_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "data_mode": DataMode.LIVE,
        "evidence_class": "retrieved",
        "source_id": "eccc-hrdps",
        "provider": "Environment and Climate Change Canada",
        "product": "HRDPS",
        "forecast_centre": "ECCC",
        "run_time": VALID_TIME,
        "valid_time": VALID_TIME,
        "retrieval_time": VALID_TIME,
        "vertical_level": "2 m above ground",
        "original_units": "degC",
        "normalized_units": "degC",
        "native_resolution": "2.5 km",
        "native_crs": "EPSG:4326",
        "quality": Quality(status="passed"),
        "coverage": Coverage(status="complete", fraction=1.0),
        "freshness": Freshness.evaluate(60, 21600),
        "licence": "Open Government Licence - Canada",
        "attribution": "Environment and Climate Change Canada",
        "adapter_version": "hrdps-v1",
    }
    base.update(overrides)
    return base


def test_the_six_evidence_classes_are_the_declared_set():
    assert EVIDENCE_CLASSES == (
        "retrieved",
        "reprocessed",
        "derived_here",
        "intermediary_derived",
        "generated_display",
        "uncalibrated_observation",
    )


def test_a_provenance_without_an_evidence_class_is_refused():
    """Required, with no default: the field cannot be forgotten."""
    kwargs = provenance_kwargs()
    kwargs.pop("evidence_class")
    with pytest.raises(ValidationError) as error:
        Provenance(**kwargs)
    assert "evidence_class" in str(error.value)


def test_an_unknown_evidence_class_is_refused_rather_than_read_as_retrieved():
    with pytest.raises(ValidationError) as error:
        Provenance(**provenance_kwargs(evidence_class="consensus"))
    assert "evidence_class" in str(error.value)


@pytest.mark.parametrize("name", EVIDENCE_CLASSES)
def test_every_declared_evidence_class_is_accepted(name: str):
    assert Provenance(**provenance_kwargs(evidence_class=name)).evidence_class == name


def test_a_qc_status_of_derived_is_not_a_fifth_status():
    """``derived`` is a flag. A fifth status would break every consumer that
    switches on the four, and a ``derived`` status failed a whole ``/point``
    response on 2026-09-01."""
    with pytest.raises(ValidationError):
        Quality(status="derived")
    flagged = Quality(status="suspect", flags=["derived"])
    assert flagged.derived is True and flagged.status == "suspect"


def test_a_derived_quality_is_the_worst_of_its_inputs_and_carries_the_flag():
    worst = Quality.worst_of([Quality(status="passed"), Quality(status="suspect")])
    assert worst.status == "suspect" and "derived" in worst.flags
    assert Quality.worst_of([Quality(status="passed"), Quality(status="failed")]).status == "failed"
    assert Quality.worst_of([Quality(status="passed"), Quality(status="unknown")]).status == "unknown"
    assert Quality.worst_of([]).status == "unknown"


def test_only_retrieved_and_derived_here_may_be_the_display_primary():
    for name in ("retrieved", "derived_here"):
        assert Provenance(**provenance_kwargs(evidence_class=name)).display_primary_eligible is True
    for name in ("reprocessed", "intermediary_derived", "generated_display", "uncalibrated_observation"):
        assert Provenance(**provenance_kwargs(evidence_class=name)).display_primary_eligible is False


def test_the_class_is_carried_into_the_served_document():
    document = Provenance(**provenance_kwargs(evidence_class="reprocessed")).model_dump()
    assert document["evidence_class"] == "reprocessed"
    assert document["display_primary_eligible"] is False


# --- the artifact manifest ------------------------------------------------

def test_a_manifest_that_understates_its_classes_is_refused():
    with pytest.raises(ValidationError) as error:
        ArtifactManifest(
            source_id="eccc-hrdps",
            logical_name="surface",
            evidence_classes=["retrieved"],
            evidence_class_by_variable={"temperature_2m": "retrieved", "fog_closure": "derived_here"},
        )
    assert "evidence_class_mismatch" in str(error.value)


def test_an_artifact_that_declares_one_class_gives_every_value_that_class():
    manifest = ArtifactManifest(source_id="eccc-hrdps", logical_name="surface", evidence_classes=["retrieved"])
    assert manifest.class_for("temperature_2m") == "retrieved"


def test_a_mixed_artifact_that_says_nothing_about_a_value_cannot_resolve_it():
    manifest = ArtifactManifest(
        source_id="open-meteo-weathernext2",
        logical_name="surface",
        evidence_classes=["reprocessed", "intermediary_derived"],
        evidence_class_by_variable={"total_cloud": "intermediary_derived"},
    )
    assert manifest.class_for("total_cloud") == "intermediary_derived"
    with pytest.raises(ValueError, match="evidence_class_mismatch"):
        manifest.class_for("temperature_2m")


def test_a_manifest_must_declare_at_least_one_class():
    with pytest.raises(ValidationError):
        ArtifactManifest(source_id="eccc-hrdps", logical_name="surface", evidence_classes=[])
