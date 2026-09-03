"""The six ensemble family declarations, as the registry states them and as the
scheduler sees them through ``IngestConfig``.

Two things are proved here. First, that every number in the declarations is the
one measured on wayfinder ticket 22 and written down in
``docs/research/wayfinder/ensemble-access.md``: a member count, a control rule
or a storage scope that drifted from the research would put an adapter on an
assumed access path. Second, that declaring a family does not schedule it:
``IngestConfig.ingestible`` is false for every ensemble record here, so
registering an adapter can never start a retrieval the owner has not accepted.
"""

from __future__ import annotations

import dataclasses

import pytest

from ingest.registry import (
    EnsembleControl,
    EnsembleDeclaration,
    get_config,
    ingest_configs,
)

import sys
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

from registry.source_data import (  # noqa: E402
    ENSEMBLE_BUILD_ORDER,
    ensemble_families,
    registry,
)

MEMBER_FAMILIES = ("eccc-reps", "ecmwf-aifs-ens", "ecmwf-ens", "noaa-gefs", "dwd-icon-eps")


def _records() -> dict[str, dict]:
    return {record["id"]: record for record in registry()["sources"]}


def test_the_build_order_is_the_owners_order_and_nothing_reorders_it() -> None:
    assert ENSEMBLE_BUILD_ORDER == (
        "eccc-reps", "ecmwf-aifs-ens", "ecmwf-ens", "noaa-gefs", "eccc-geps", "dwd-icon-eps",
    )
    families = ensemble_families()
    assert [block["family"] for block in families] == [
        "REPS", "AIFS-ENS", "IFS ENS", "GEFS", "GEPS reductions", "ICON-EPS",
    ]
    assert [block["build_order"] for block in families] == [1, 2, 3, 4, 5, 6]


def test_every_ensemble_record_carries_a_declaration_and_no_other_record_does() -> None:
    records = _records()
    ensembles = {sid for sid, record in records.items() if record["category"] == "ensemble"}
    assert ensembles == set(ENSEMBLE_BUILD_ORDER)
    for sid, record in records.items():
        assert ("ensemble" in record) is (sid in ensembles), sid


def test_ensemble_families_hands_back_copies_not_the_registry() -> None:
    """A reader holding a block must not be able to edit the registry through it."""
    ensemble_families()[0]["member_count"] = 99
    assert ensemble_families()[0]["member_count"] == 21


def test_storage_scope_follows_the_declared_subsettability() -> None:
    blocks = {block["family"]: block for block in ensemble_families()}
    for family in ("REPS", "GEPS reductions"):
        assert blocks[family]["subsetting"] == "server_side"
        assert blocks[family]["storage_scope"] == "every_published_field"
    for family in ("AIFS-ENS", "IFS ENS", "GEFS", "ICON-EPS"):
        assert blocks[family]["subsetting"] == "none"
        assert blocks[family]["storage_scope"] == "family_fields_only"


def test_the_declared_scope_matches_the_field_catalogues_own_source_scope() -> None:
    """One access shape, declared once: the catalogue and the registry agree."""
    from registry.fields import SOURCE_SCOPE

    scope = {entry["source_id"]: entry for entry in SOURCE_SCOPE}
    records = _records()
    for source_id in ENSEMBLE_BUILD_ORDER:
        block = records[source_id]["ensemble"]
        assert block["subsetting"] == scope[source_id]["subsetting"], source_id
        assert block["storage_scope"] == scope[source_id]["policy"], source_id


def test_member_counts_are_the_measured_ones() -> None:
    records = _records()
    assert records["eccc-reps"]["ensemble"]["member_count"] == 21
    assert records["ecmwf-aifs-ens"]["ensemble"]["member_count"] == 51
    assert records["ecmwf-ens"]["ensemble"]["member_count"] == 51
    assert records["noaa-gefs"]["ensemble"]["member_count"] == 31


def test_a_reduction_family_declares_no_members_and_no_control() -> None:
    block = _records()["eccc-geps"]["ensemble"]
    assert block["shape"] == "reduction"
    assert block["member_count"] is None
    assert block["control"] is None
    assert block["reductions"] == ["mean", "spread", "percentile", "threshold_probability"]


def test_only_the_reduction_family_lists_reductions() -> None:
    for source_id in MEMBER_FAMILIES:
        assert _records()[source_id]["ensemble"]["reductions"] == [], source_id


def test_the_gefs_control_is_a_flagged_member_not_a_source() -> None:
    control = get_config("noaa-gefs").ensemble.control
    assert isinstance(control, EnsembleControl)
    assert control.identifier == "gec00"
    assert control.separate_retrieval is False
    assert "gep01" in control.rule and "gep30" in control.rule
    # The control is inside the declared count, not beside it.
    assert get_config("noaa-gefs").ensemble.member_count == 31
    assert "noaa-gefs-control" not in ingest_configs()


def test_the_aifs_control_arrives_in_its_own_file_and_stays_one_record() -> None:
    config = get_config("ecmwf-aifs-ens")
    assert config.ensemble.control.identifier == "0"
    assert config.ensemble.control.separate_retrieval is True
    assert config.ensemble.member_count == 51
    assert "ecmwf-aifs-ens-cf" not in ingest_configs()


def test_the_ifs_ens_control_location_is_declared_unverified() -> None:
    declaration = get_config("ecmwf-ens").ensemble
    assert declaration.control.identifier == "0"
    assert declaration.verification.access_path == "unverified"
    assert declaration.verification.fully_verified is False


def test_reps_declares_no_control_identifier_because_none_was_measured() -> None:
    """A control that was never located is not the same as no control at all."""
    declaration = get_config("eccc-reps").ensemble
    assert declaration.control is not None
    assert declaration.control.identifier is None
    assert "not schedulable" in declaration.control.rule or "not identified" in declaration.control.rule
    assert declaration.schedulable is False


def test_reps_declares_the_wind_direction_gap_and_nothing_offers_to_fill_it() -> None:
    gaps = {gap.field: gap.reason for gap in get_config("eccc-reps").ensemble.gaps}
    assert set(gaps) == {"wind_direction_10m"}
    reason = gaps["wind_direction_10m"]
    assert "WSPD" in reason
    assert "not derived" in reason


def test_gefs_declares_the_instantaneous_cloud_gap_and_publishes_the_mean_instead() -> None:
    gaps = {gap.field for gap in get_config("noaa-gefs").ensemble.gaps}
    assert gaps == {"total_cloud_geometric"}
    assert "total_cloud_mean_6h" in get_config("noaa-gefs").variables


def test_ifs_ens_declares_the_layered_cloud_gap() -> None:
    gaps = {gap.field for gap in get_config("ecmwf-ens").ensemble.gaps}
    assert gaps == {"cloud_low", "cloud_middle", "cloud_high"}


def test_a_declared_gap_is_never_also_a_stored_field() -> None:
    from registry.fields import SOURCE_FIELDS

    stored = {
        (entry["source_id"], entry["key"])
        for entry in SOURCE_FIELDS
        if entry["storage"] == "stored"
    }
    for source_id in ENSEMBLE_BUILD_ORDER:
        declaration = get_config(source_id).ensemble
        for gap in declaration.gaps:
            assert (source_id, gap.field) not in stored, f"{source_id}:{gap.field}"


def test_icon_eps_is_unmeasured_declares_no_count_and_is_never_schedulable() -> None:
    record = _records()["dwd-icon-eps"]
    declaration = get_config("dwd-icon-eps").ensemble
    assert record["status"] != "implementing"
    assert record["fixture_status"] == "not_applicable"
    assert record["live_smoke_test_status"] == "not_applicable"
    assert declaration.build_order == 6
    assert declaration.member_count is None
    assert declaration.verification.evidence == "none"
    assert declaration.verification.member_count == "unverified"
    assert declaration.verification.access_path == "unverified"
    assert declaration.verification.cadence == "unverified"
    assert declaration.schedulable is False
    assert get_config("dwd-icon-eps").ingestible is False


def test_every_verified_family_names_the_research_that_measured_it() -> None:
    for source_id in ENSEMBLE_BUILD_ORDER:
        verification = get_config(source_id).ensemble.verification
        if verification.evidence == "none":
            assert not verification.fully_verified, source_id
        else:
            assert verification.evidence == "docs/research/wayfinder/ensemble-access.md", source_id


def test_an_unverified_family_is_never_schedulable() -> None:
    for source_id in ENSEMBLE_BUILD_ORDER:
        declaration = get_config(source_id).ensemble
        if not declaration.verification.fully_verified:
            assert declaration.schedulable is False, source_id


def test_no_family_is_schedulable_and_no_ensemble_record_is_ingestible() -> None:
    """Nothing is scheduled by this change, and the gate is what enforces it."""
    for source_id in ENSEMBLE_BUILD_ORDER:
        config = get_config(source_id)
        assert config.ensemble.schedulable is False, source_id
        assert config.ensemble.schedulable_reason.strip(), source_id
        assert config.ingestible is False, source_id


def test_an_ensemble_record_with_a_horizon_still_needs_its_family_declared() -> None:
    """The gate is the declaration, not the horizon: reach alone must not schedule."""
    config = get_config("noaa-gefs")
    assert config.reach is not None and config.run_cadence_seconds is not None
    assert dataclasses.replace(config, ensemble=None).ingestible is False
    schedulable = dataclasses.replace(
        config, ensemble=dataclasses.replace(config.ensemble, schedulable=True)
    )
    assert schedulable.ingestible is True


def test_a_non_ensemble_record_is_unaffected_by_the_ensemble_gate() -> None:
    config = get_config("eccc-hrdps")
    assert config.ensemble is None
    assert config.ingestible is True


@pytest.mark.parametrize("source_id", ENSEMBLE_BUILD_ORDER)
def test_the_scheduler_view_mirrors_the_record_field_for_field(source_id: str) -> None:
    block = _records()[source_id]["ensemble"]
    declaration = get_config(source_id).ensemble
    assert isinstance(declaration, EnsembleDeclaration)
    assert declaration.family == block["family"]
    assert declaration.build_order == block["build_order"]
    assert declaration.shape == block["shape"]
    assert declaration.subsetting == block["subsetting"]
    assert declaration.storage_scope == block["storage_scope"]
    assert declaration.member_count == block["member_count"]
    assert list(declaration.reductions) == block["reductions"]
    assert [{"field": gap.field, "reason": gap.reason} for gap in declaration.gaps] == block["gaps"]
    assert declaration.schedulable == block["schedulable"]
    assert declaration.schedulable_reason == block["schedulable_reason"]
    if block["control"] is None:
        assert declaration.control is None
    else:
        assert declaration.control.identifier == block["control"]["identifier"]
        assert declaration.control.separate_retrieval == block["control"]["separate_retrieval"]
