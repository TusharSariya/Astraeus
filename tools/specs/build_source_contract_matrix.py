#!/usr/bin/env python3
"""Build and validate the free-source authority matrix from the checked roster."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROSTER = ROOT / "docs/research/free-source-implementation-roster.json"
OUTPUT = ROOT / "docs/research/source-contract-authority-matrix.json"
SUMMARY = ROOT / "docs/research/source-contract-authority-matrix.md"

ACCEPTED_AUTHORITY = [
    "GOV-SPEC-001",
    "GOV-SPEC-002",
    "GOV-SPEC-004",
    "GOV-SPEC-005",
    "GOV-SPEC-006",
]

PROPOSED_V1_TARGET_SHAPE = ["EVD-PROV-001", "EVD-MASK-001", "EVD-API-001"]

CURRENT_EXPERIMENT_CONTRACTS = [
    "openspec/specs/artifact-ingestion/spec.md",
    "openspec/specs/artifact-storage-integrity/spec.md",
    "openspec/specs/evidence-truth-boundary/spec.md",
    "openspec/specs/ingestion-worker-scheduling/spec.md",
    "openspec/specs/source-registry-catalogue/spec.md",
]

REQUIRED_SOURCE_DECISIONS = [
    "producer_product_and_access_path",
    "selected_fields_and_canonical_mapping",
    "native_units_levels_grid_and_masks",
    "run_member_lead_valid_publication_and_retrieval_identity",
    "licence_terms_and_zero_charge_surfaces",
    "cadence_provider_limits_and_operation_bounds",
    "absence_quality_and_failure_semantics",
    "api_surface_and_readback_shape",
    "rollback_and_last_visible_revision_behavior",
]

PROOF = [
    "representative_fixture",
    "bounded_live_upstream_retrieval",
    "validated_immutable_artifact",
    "Astraeus_API_readback",
    "absence_failure_and_provenance_tests",
]


def classify(row: dict) -> tuple[str, list[str]]:
    implementation = row["implementation"]
    prior = row["prior_decision"]
    free = row["free_access"]["roster_disposition"]
    if row["kind"] == "registered-source":
        state = prior["registry_state"]
        if (
            implementation["category"] == "functional_dispatch"
            and implementation["adapter_registered"]
            and prior["schedulable"]
        ):
            return "experiment-verification-candidate", REQUIRED_SOURCE_DECISIONS
        if state in {"rejected", "superseded", "unavailable", "link-only", "partnership-only"}:
            return "recorded-disposition", []
        if state in {"credential-required", "licence-blocked"} or "pending" in free:
            return "access-or-licence-gate", REQUIRED_SOURCE_DECISIONS
        return "owner-source-contract-required", REQUIRED_SOURCE_DECISIONS

    if free.startswith("deferred-paid") or free in {
        "deferred-commercial-or-workflow",
        "recorded-blocked-or-excluded",
        "recorded-exclusion-or-unresolved-lead",
        "recorded-permission-or-no-feed",
        "recorded-research-disposition",
        "recorded-unavailable-probe",
        "superseded-alternatives",
        "tools-not-sources",
        "tool-or-method",
        "insufficient-product-identity",
        "no-unrestricted-automated-right",
        "out-of-geography-or-unproved",
        "outside-current-horizon",
        "unsuitable-primary-local-source",
    }:
        return "recorded-disposition", []
    if "account" in free or "permission" in free or "access-unverified" in free:
        return "access-or-licence-gate", REQUIRED_SOURCE_DECISIONS
    return "owner-source-contract-required", REQUIRED_SOURCE_DECISIONS


def build() -> dict:
    roster = json.loads(ROSTER.read_text())
    rows = []
    for source in [*roster["registered_sources"], *roster["research_candidates"]]:
        authority_class, missing = classify(source)
        rows.append(
            {
                "roster_id": source["roster_id"],
                "kind": source["kind"],
                "source_id": source["source_id"],
                "product_access_path": source["product_access_path"],
                "target_task": source["target_task"],
                "registry_state": source["prior_decision"]["registry_state"],
                "adapter_registered": source["implementation"].get("adapter_registered", False),
                "implementation_category": source["implementation"]["category"],
                "schedulable": source["prior_decision"]["schedulable"],
                "free_access_disposition": source["free_access"]["roster_disposition"],
                "authority_class": authority_class,
                "accepted_governance_authority": ACCEPTED_AUTHORITY,
                "proposed_v1_target_shape": PROPOSED_V1_TARGET_SHAPE,
                "current_experiment_contracts": CURRENT_EXPERIMENT_CONTRACTS,
                "missing_source_specific_decisions": missing,
                "required_completion_proof": PROOF if authority_class != "recorded-disposition" else [],
                "operational": False,
            }
        )

    counts = Counter(row["authority_class"] for row in rows)
    result = {
        "schema_version": 1,
        "generated_from": str(ROSTER.relative_to(ROOT)),
        "classification_rule": (
            "Only registered rows with functional adapter dispatch and schedulable state are experiment verification candidates. "
            "All other eligible rows require the listed owner source contract or access/licence decision; "
            "excluded rows preserve their recorded disposition."
        ),
        "blocking_contract_conflicts": [
            {
                "topic": "evidence_window",
                "current_openspec": "now-3h .. now+24h",
                "runtime_and_unarchived_proposal": "now-24h .. now+14d",
                "decision": "owner must select one authoritative window before production ingestion",
            },
            {
                "topic": "source_registry_and_admission",
                "current_openspec": "legacy registry status and provenance surface",
                "unarchived_proposal_and_runtime": "ten-state ledger plus richer delivery/provenance fields",
                "decision": "owner must accept or revise one coherent state and provenance contract",
            },
        ],
        "counts": dict(sorted(counts.items())),
        "rows": rows,
    }
    validate(result, roster)
    return result


def validate(matrix: dict, roster: dict) -> None:
    expected = roster["registered_sources"] + roster["research_candidates"]
    assert len(expected) == 288, f"expected fixed 288-row roster, got {len(expected)}"
    expected_ids = [row["roster_id"] for row in expected]
    actual_ids = [row["roster_id"] for row in matrix["rows"]]
    assert actual_ids == expected_ids, "matrix must preserve every roster row exactly once and in order"
    assert len(set(actual_ids)) == len(actual_ids), "duplicate roster_id in authority matrix"
    for row in matrix["rows"]:
        assert row["operational"] is False
        if row["authority_class"] == "experiment-verification-candidate":
            assert row["kind"] == "registered-source"
            assert row["implementation_category"] == "functional_dispatch"
            assert row["adapter_registered"] and row["schedulable"]
            assert row["missing_source_specific_decisions"] == REQUIRED_SOURCE_DECISIONS
        elif row["authority_class"] == "recorded-disposition":
            assert not row["required_completion_proof"]
        else:
            assert row["missing_source_specific_decisions"] == REQUIRED_SOURCE_DECISIONS


def markdown(matrix: dict) -> str:
    candidates = [
        row for row in matrix["rows"]
        if row["authority_class"] == "experiment-verification-candidate"
    ]
    lines = [
        "# Source contract authority matrix",
        "",
        "Generated from the exhaustive free-source roster on September 5, 2026. This is a",
        "traceability and implementation-gate artifact, not normative authority. The complete",
        "288-row result is in `source-contract-authority-matrix.json`.",
        "",
        "## Result",
        "",
        "| Authority class | Rows | What may happen now |",
        "| --- | ---: | --- |",
    ]
    descriptions = {
        "experiment-verification-candidate": "Run isolated bounded fixture/live/artifact/API/failure verification; production conformance still waits for accepted behavior authority.",
        "owner-source-contract-required": "Prepare the exact product/access/field contract while isolated adapter work proceeds; owner acceptance gates production registration and scheduling.",
        "access-or-licence-gate": "Resolve access, terms, geography and zero-charge gates, then obtain the same source contract acceptance.",
        "recorded-disposition": "Preserve the rejection, deferral, unavailability or non-source disposition; no fabricated live proof is required.",
    }
    for key in sorted(matrix["counts"]):
        lines.append(f"| `{key}` | {matrix['counts'][key]} | {descriptions[key]} |")
    lines += [
        "",
        "Accepted authority is governance only: GOV-SPEC-001/002/004/005/006. EVD-PROV-001,",
        "EVD-MASK-001 and EVD-API-001 are proposed target shape, not authority. The current",
        "experiment contracts describe shared adapter,",
        "manifest, bounded transport, publication, scheduler and truth-boundary behavior. They",
        "do not choose a new producer product, access path or field mapping. The draft",
        "`shared-source-integration-contract` change makes that per-source decision record and",
        "five-part proof gate explicit for owner review.",
        "",
        "## Experiment verification candidates",
        "",
        "No production integration is a conforming candidate because no behavior-bearing V1",
        "source contract is accepted. These rows already have a registered schedulable adapter,",
        "so bounded isolated experiment verification can start while the owner reviews the contract:",
        "",
        "| Source | Product | Target task |",
        "| --- | --- | --- |",
    ]
    for row in candidates:
        task = row["target_task"]
        lines.append(f"| `{row['source_id']}` | {row['product_access_path']} | [{task['title']}]({task['url']}) |")
    lines += [
        "",
        "A live success alone does not authorize `operational`. Each candidate still needs a",
        "representative fixture, bounded upstream retrieval, immutable artifact validation,",
        "Astraeus API readback, and absence/failure/provenance evidence for every selected field.",
        "",
        "## Owner decision requested",
        "",
        "Accept, revise or reject the draft `shared-source-integration-contract` change. If",
        "accepted through the GOV-SPEC-002 status workflow, each missing integration can supply",
        "one source contract instance with exact product/access identity, fields, mappings,",
        "units, masks, runs, members, leads, cadence, limits, charge surfaces, API shape,",
        "failure semantics and rollback. No blanket acceptance of all roster rows is requested.",
        "",
        "Spec-Impact: none; generated traceability evidence only.",
        "Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    matrix = build()
    OUTPUT.write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n")
    SUMMARY.write_text(markdown(matrix))
    print(f"validated {len(matrix['rows'])} rows: {dict(sorted(matrix['counts'].items()))}")
