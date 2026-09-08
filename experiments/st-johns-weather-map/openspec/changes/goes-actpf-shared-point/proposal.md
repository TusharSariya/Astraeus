# GOES ACTPF shared native point evidence

Status: **draft, awaiting owner decision**. Classification: requirement change
for the isolated weather-map experiment; no production or source admission.
Tracking: #70, #85, #101. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-005, GOV-SPEC-006. This proposal changes no accepted status.

## Decision requested

Approve an additive typed satellite-provenance block for the existing
`cloud_top_phase` EvidenceField and require selection by **exact native scan
start**. Keep the existing rule that a CF categorical field's public value is
the producer's meaning string. Preserve the native integer phase and DQF in
provenance; do not introduce an ACTPF numeric-value exception.

The alternative of answering any requested instant contained in
`[scan_start, scan_end]` is **undecided and not authorized by this proposal**.
The proposed behavior below is exact-start only; no one-hour nearest-frame
rule, latest-frame substitution or inferred pixel time is permitted.

## Why a decision is needed

The existing [categorical contract](../cloud-and-fog-evidence/specs/point-evidence-sampling/spec.md)
requires the retrieved CF meaning string, not the integer. The
[GOES experiment](../experimental-goes-abi-glm/design.md) preserves native phase,
DQF, scan identity and geometry, and restricts gridded readability to declared
producer quality states. The current `NativePhasePoint` already retains much
of this context but is not the shared EvidenceField contract.

`Provenance.native_report` is station-based and requires `station_id`;
using it for a satellite granule would fabricate a station. `SourceAcquisition`
holds transport identity but cannot carry the native DQF, scan end and
projection. A small typed addition avoids either loss.

## Scope and boundaries

Only `noaa-goes-east` / `ABI-L2-ACTPF` / `cloud_top_phase` at `cloud top` is
proposed. No forecast run, member or native Series is introduced. The proposed
point-product selector is `GOES ACTPF`, distinct from the native product ID.
No other GOES product, VIIRS quality rule, field, score or fog inference follows.
This docs-only change adds no API route, descriptor, generated schema, source
activation or implementation claim. Acquisition and retained-byte proof are
already documented in [the source-local proof](../../../docs/goes-phase-api-first-proof.md);
there is no new capture in this proposal.

## Required follow-through after owner decision

Implement and verify the [proposed contract](specs/point-evidence-sampling/spec.md)
and [typed shape](design.md), then separately register the source-local reader
through shared delivery. Generate OpenAPI/TypeScript and shared fixtures from
Pydantic only after the contract decision. Owner acceptance of this experiment
would not authorize operational/V1 promotion.
