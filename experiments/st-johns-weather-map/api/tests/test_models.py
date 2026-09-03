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

from registry import fields as catalogue
from weather_api.models import (
    ABSENCE_STATES,
    AGED_OUT_FLAG,
    BLOCKED_FLAG,
    CONTRACT_INCOMPLETE_FLAG,
    EVIDENCE_CLASSES,
    PARTIAL_MEMBER_SET_FLAG,
    STATISTIC_REFUSED_FLAG,
    THRESHOLD_COMPARISONS,
    ArtifactManifest,
    BlockedReason,
    Coverage,
    DataMode,
    EnsembleMemberSet,
    EnsembleProvenance,
    EvidenceField,
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


# --- ensemble members and the statistics over them ------------------------
# Every ensemble number names its family, its run, which statistic it is, the
# member set it covers and whether it was computed here (Seam D). These are the
# invariants the model itself can see: the ones it cannot - one family, one run
# - are enforced at derive time, where the artifacts are.

def full_member_set(**overrides: object) -> EnsembleMemberSet:
    base: dict[str, object] = {
        "family": "REPS",
        "source_id": "eccc-reps",
        "run_time": VALID_TIME,
        "members_declared": 21,
        "members_used": 21,
        "members_missing": [],
        "control_included": True,
        "partial": False,
    }
    base.update(overrides)
    return EnsembleMemberSet(**base)


def statistic_provenance(ensemble: EnsembleProvenance, **overrides: object) -> Provenance:
    """A statistic's provenance, labelled the way a computed one must be."""
    base: dict[str, object] = {
        "source_id": "eccc-reps",
        "product": "REPS",
        "evidence_class": "derived_here",
        "derivation": ensemble.statistic,
        "quality": Quality(status="passed", flags=["derived"]),
        "ensemble": ensemble,
    }
    base.update(overrides)
    return Provenance(**provenance_kwargs(**base))


def test_a_member_value_names_its_member_and_whether_it_is_the_control():
    value = Provenance(**provenance_kwargs(source_id="eccc-reps", product="REPS", member="01", member_control=True))
    assert value.member == "01" and value.member_control is True
    assert value.ensemble is None


def test_a_control_flag_without_a_member_identifier_names_nothing():
    with pytest.raises(ValidationError, match="member_control requires member"):
        Provenance(**provenance_kwargs(member=None, member_control=False))


def test_a_member_statistic_computed_here_must_be_derived_here():
    """The class and the ensemble block cannot disagree about who built the
    number."""
    ensemble = EnsembleProvenance(family="REPS", statistic="ensemble_mean", computed_here=True, member_set=full_member_set())
    assert statistic_provenance(ensemble).evidence_class == "derived_here"
    with pytest.raises(ValidationError, match="derived_here"):
        Provenance(**provenance_kwargs(evidence_class="retrieved", derivation="ensemble_mean", ensemble=ensemble))


def test_a_member_statistic_names_the_registry_entry_that_produced_it():
    ensemble = EnsembleProvenance(family="REPS", statistic="ensemble_spread", computed_here=True, member_set=full_member_set())
    with pytest.raises(ValidationError, match="derivation must name the statistic entry"):
        statistic_provenance(ensemble, derivation="ensemble_mean")


def test_a_member_statistic_cannot_name_an_unregistered_entry():
    """``mean`` is the caller's short name, not an entry; the umbrella is not
    an entry either."""
    for name in ("mean", "ensemble_statistics_within_run", "ensemble_median"):
        with pytest.raises(ValidationError, match="unregistered_method"):
            EnsembleProvenance(family="REPS", statistic=name, computed_here=True, member_set=full_member_set())


def test_a_provider_reduction_over_members_is_retrieved_and_not_computed_here():
    """GEPS publishes its own mean. It is the provider's cell, so it is
    ``retrieved`` and says the provider computed it."""
    ensemble = EnsembleProvenance(
        family="GEPS reductions", statistic="ensemble_mean", computed_here=False,
        member_set=full_member_set(family="GEPS reductions", source_id="eccc-geps"),
    )
    served = Provenance(**provenance_kwargs(source_id="eccc-geps", product="GEPS", evidence_class="retrieved", ensemble=ensemble))
    assert served.ensemble.computed_here is False and served.derivation is None
    with pytest.raises(ValidationError, match="provider's own published reduction"):
        Provenance(**provenance_kwargs(evidence_class="derived_here", derivation="ensemble_mean", ensemble=ensemble))


def test_a_per_member_value_may_say_it_was_not_computed_here():
    """``computed_here`` false with no statistic is a plain member reading, not
    a reduction, so the retrieved-class rule does not bite it."""
    ensemble = EnsembleProvenance(family="REPS", statistic=None, computed_here=False, member_set=None)
    value = Provenance(**provenance_kwargs(evidence_class="reprocessed", member="01", ensemble=ensemble))
    assert value.ensemble.statistic is None


def test_a_partial_member_set_is_flagged_on_the_quality_not_only_counted():
    partial = full_member_set(members_used=19, members_missing=["07", "12"], partial=True)
    ensemble = EnsembleProvenance(family="REPS", statistic="ensemble_mean", computed_here=True, member_set=partial)
    with pytest.raises(ValidationError, match=PARTIAL_MEMBER_SET_FLAG):
        statistic_provenance(ensemble)
    flagged = statistic_provenance(ensemble, quality=Quality(status="passed", flags=["derived", PARTIAL_MEMBER_SET_FLAG]))
    assert flagged.ensemble.member_set.members_missing == ["07", "12"]


def test_a_member_set_that_claims_more_members_than_declared_is_refused():
    with pytest.raises(ValidationError, match="member_set_overcounts"):
        full_member_set(members_used=22)


def test_a_member_set_partial_verdict_must_match_its_own_counts():
    with pytest.raises(ValidationError, match="member_set_partial_mismatch"):
        full_member_set(members_used=19, partial=False)
    with pytest.raises(ValidationError, match="member_set_partial_mismatch"):
        full_member_set(members_used=21, partial=True)


def test_a_member_statistic_is_judged_stale_by_the_run_stale_field_it_already_has():
    """Staleness is ``Provenance.run_stale`` from the horizon-tiers change. The
    member set deliberately carries no second one, so one value can never say
    two things about one run."""
    assert "run_stale" not in EnsembleMemberSet.model_fields
    ensemble = EnsembleProvenance(family="REPS", statistic="ensemble_mean", computed_here=True, member_set=full_member_set())
    stale = statistic_provenance(ensemble, run_stale=True, run_stale_reason="run is older than twice the declared cadence")
    assert stale.run_stale is True and stale.ensemble.member_set.run_time == VALID_TIME


def test_a_refused_member_statistic_names_the_condition_and_carries_no_number():
    ensemble = EnsembleProvenance(
        family="REPS", statistic="ensemble_mean", computed_here=True, member_set=full_member_set(),
        refusal="one_family:GEFS,REPS",
    )
    refused = statistic_provenance(ensemble, quality=Quality(status="unknown", flags=["derived", STATISTIC_REFUSED_FLAG]))
    assert EvidenceField(field="temperature", value=None, provenance=refused).value is None
    with pytest.raises(ValidationError, match="statistic_refused"):
        EvidenceField(field="temperature", value=15.2, provenance=refused)


def test_a_refused_member_statistic_must_be_flagged_as_refused():
    ensemble = EnsembleProvenance(
        family="REPS", statistic="ensemble_mean", computed_here=True, member_set=full_member_set(),
        refusal="provider_reduction_mixed",
    )
    with pytest.raises(ValidationError, match=STATISTIC_REFUSED_FLAG):
        statistic_provenance(ensemble)


def test_a_refusal_without_a_member_statistic_has_nothing_to_refuse():
    with pytest.raises(ValidationError, match="statistic_refused requires the statistic"):
        EnsembleProvenance(family="REPS", statistic=None, computed_here=True, member_set=None, refusal="no_member_resolved")


def test_a_threshold_probability_over_members_states_a_known_comparison():
    assert THRESHOLD_COMPARISONS == ("ge", "gt", "le", "lt")
    for name in THRESHOLD_COMPARISONS:
        block = EnsembleProvenance(
            family="GEFS", statistic="ensemble_threshold_probability", computed_here=True,
            member_set=full_member_set(family="GEFS", source_id="noaa-gefs", members_declared=31, members_used=31),
            threshold=0.0, threshold_units="degC", comparison=name,
        )
        assert block.comparison == name
    with pytest.raises(ValidationError):
        EnsembleProvenance(family="GEFS", statistic="ensemble_threshold_probability", computed_here=True, member_set=None, comparison="above")


def test_a_member_quantile_stays_inside_the_unit_interval():
    for value in (-0.1, 1.5):
        with pytest.raises(ValidationError):
            EnsembleProvenance(family="REPS", statistic="ensemble_quantile", computed_here=True, member_set=None, quantile=value)


def test_a_time_averaged_member_field_states_its_window():
    block = EnsembleProvenance(
        family="GEFS", statistic="ensemble_mean", computed_here=True,
        member_set=full_member_set(family="GEFS", source_id="noaa-gefs", members_declared=31, members_used=31),
        averaging_window_hours=6.0,
    )
    assert block.averaging_window_hours == 6.0
    with pytest.raises(ValidationError):
        EnsembleProvenance(family="GEFS", statistic="ensemble_mean", computed_here=True, member_set=None, averaging_window_hours=0.0)


def test_the_member_fields_are_carried_into_the_served_document():
    ensemble = EnsembleProvenance(family="REPS", statistic="ensemble_mean", computed_here=True, member_set=full_member_set())
    document = statistic_provenance(ensemble).model_dump()
    assert document["ensemble"]["family"] == "REPS"
    assert document["ensemble"]["statistic"] == "ensemble_mean"
    assert document["ensemble"]["computed_here"] is True
    assert document["ensemble"]["member_set"]["members_used"] == 21
    assert document["ensemble"]["member_set"]["control_included"] is True
    assert document["member"] is None and document["member_control"] is None


# The output contract and the three disjoint absence states.
#
# Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/activity-profile/spec.md
# Spec-Refs: openspec/changes/activity-profiles-sites-and-cameras/specs/point-evidence-sampling/spec.md


LICENCE_BLOCK = BlockedReason(
    kind="licence",
    source_id="falchi-light-pollution-atlas",
    terms="non-commercial use only; no redistribution of derived rasters",
    request=None,
)


def blocked_provenance(**overrides: object) -> Provenance:
    quality = Quality(status="unknown", flags=[BLOCKED_FLAG, "blocked:licence"])
    return Provenance(**provenance_kwargs(quality=quality, **overrides))


def test_the_absence_states_are_three_and_disjoint():
    assert ABSENCE_STATES == ("null", "blocked", "aged_out")
    assert len(set(ABSENCE_STATES)) == len(ABSENCE_STATES)
    assert BLOCKED_FLAG == "blocked"
    assert CONTRACT_INCOMPLETE_FLAG == "contract_incomplete"
    assert AGED_OUT_FLAG not in {"null", "blocked"}


def test_a_present_value_carries_the_output_contract_and_no_absence_state():
    served = EvidenceField(field="temperature", value=4.0, provenance=Provenance(**provenance_kwargs()))
    assert served.absence_state is None and served.blocked is None
    assert served.key == "temperature_2m" and served.family == "temperature"
    assert served.comparability == catalogue.family("temperature").note
    assert served.provenance.evidence_class == "retrieved"
    assert served.provenance.freshness.status == "fresh"
    assert served.provenance.source_id == "eccc-hrdps"


def test_no_output_contract_element_is_omitted_from_the_wire():
    document = EvidenceField(field="temperature", value=4.0, provenance=Provenance(**provenance_kwargs())).model_dump()
    for element in ("value", "absence_state", "comparability", "blocked"):
        assert element in document
    assert document["provenance"]["evidence_class"] == "retrieved"
    assert document["provenance"]["quality"]["status"] == "passed"
    assert document["provenance"]["freshness"]["status"] == "fresh"
    assert document["provenance"]["source_id"] == "eccc-hrdps"


def test_an_unflagged_absence_takes_the_null_absence_state():
    absent = EvidenceField(field="temperature", value=None, provenance=Provenance(**provenance_kwargs()))
    assert absent.absence_state == "null" and absent.blocked is None
    assert absent.comparability == catalogue.family("temperature").note


def test_a_reason_flag_stays_a_reason_on_a_null_absence_state():
    for reason in ("retrieval_failed", "no_retrieval"):
        absent = EvidenceField(
            field="temperature", value=None,
            provenance=Provenance(**provenance_kwargs(quality=Quality(status="unknown", flags=[reason]))),
        )
        assert absent.absence_state == "null"
        assert reason in absent.provenance.quality.flags


def test_a_storage_value_is_never_read_as_an_absence_state():
    for storage in ("available-not-stored", "not-published"):
        assert storage not in ABSENCE_STATES
        absent = EvidenceField(
            field="temperature", value=None, storage=storage,
            provenance=Provenance(**provenance_kwargs()),
        )
        assert absent.storage == storage and absent.absence_state == "null"


def test_a_blocked_absence_state_carries_its_reason_and_the_flag_carrier():
    field = EvidenceField(field="temperature", value=None, blocked=LICENCE_BLOCK, provenance=blocked_provenance())
    assert field.absence_state == "blocked"
    assert field.blocked is not None and field.blocked.kind == "licence"
    document = field.model_dump()
    assert document["value"] is None
    assert document["absence_state"] == "blocked"
    assert document["blocked"]["source_id"] == "falchi-light-pollution-atlas"
    assert "blocked" in document["provenance"]["quality"]["flags"]
    assert "blocked:licence" in document["provenance"]["quality"]["flags"]


def test_blocked_and_null_absence_states_are_told_apart_without_reading_text():
    blocked = EvidenceField(field="temperature", value=None, blocked=LICENCE_BLOCK, provenance=blocked_provenance())
    plain = EvidenceField(
        field="temperature", value=None,
        provenance=Provenance(**provenance_kwargs(quality=Quality(status="unknown", flags=["no_retrieval"]))),
    )
    assert blocked.absence_state != plain.absence_state
    assert (blocked.absence_state, plain.absence_state) == ("blocked", "null")


def test_a_blocked_absence_state_without_a_reason_or_a_flag_is_refused():
    with pytest.raises(ValidationError, match="blocked_without_reason"):
        EvidenceField(field="temperature", value=None, provenance=blocked_provenance())
    with pytest.raises(ValidationError, match="blocked_without_flag"):
        EvidenceField(
            field="temperature", value=None, absence_state="blocked", blocked=LICENCE_BLOCK,
            provenance=Provenance(**provenance_kwargs()),
        )


def test_an_aged_out_absence_state_keeps_the_flag_and_the_last_valid_time():
    aged = EvidenceField(
        field="temperature", value=None,
        provenance=Provenance(**provenance_kwargs(
            quality=Quality(status="passed", flags=[AGED_OUT_FLAG]), last_valid_time=VALID_TIME,
        )),
    )
    assert aged.absence_state == "aged_out"
    with pytest.raises(ValidationError, match="aged_out_without_flag"):
        EvidenceField(
            field="temperature", value=None, absence_state="aged_out",
            provenance=Provenance(**provenance_kwargs()),
        )
    with pytest.raises(ValidationError, match="last_valid_time"):
        Provenance(**provenance_kwargs(quality=Quality(status="passed", flags=[AGED_OUT_FLAG])))


def test_the_aged_out_absence_state_is_derived_before_blocked():
    field = EvidenceField(
        field="temperature", value=None,
        provenance=Provenance(**provenance_kwargs(
            quality=Quality(status="passed", flags=[AGED_OUT_FLAG, BLOCKED_FLAG]), last_valid_time=VALID_TIME,
        )),
    )
    assert field.absence_state == "aged_out" and field.blocked is None


def test_an_absence_state_beside_a_value_is_refused():
    with pytest.raises(ValidationError, match="absence_with_value"):
        EvidenceField(field="temperature", value=4.0, absence_state="null", provenance=Provenance(**provenance_kwargs()))
    with pytest.raises(ValidationError, match="absence_with_value"):
        EvidenceField(field="temperature", value=4.0, blocked=LICENCE_BLOCK, provenance=blocked_provenance())


def test_a_block_reason_without_the_blocked_absence_state_is_refused():
    with pytest.raises(ValidationError, match="blocked_without_state"):
        EvidenceField(
            field="temperature", value=None, absence_state="null", blocked=LICENCE_BLOCK,
            provenance=blocked_provenance(),
        )


def test_an_uncatalogued_field_carries_no_comparability_in_its_output_contract():
    field = EvidenceField(field="road_state", value=None, provenance=Provenance(**provenance_kwargs()))
    assert field.key is None and field.family is None and field.comparability is None
    assert field.absence_state == "null"


def test_a_stated_comparability_is_left_alone_by_the_output_contract():
    field = EvidenceField(
        field="temperature", value=4.0, comparability="stated by the caller",
        provenance=Provenance(**provenance_kwargs()),
    )
    assert field.comparability == "stated by the caller"


def test_a_blocked_absence_state_names_one_of_the_three_kinds():
    for kind in ("licence", "credential", "partnership"):
        assert BlockedReason(kind=kind, source_id="nl-511", terms="terms").kind == kind
    with pytest.raises(ValidationError):
        BlockedReason(kind="paywall", source_id="nl-511", terms="terms")
