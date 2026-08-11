## Summary

<!-- What changed and why? -->

## Change classification

- [ ] Conforming implementation
- [ ] Requirement change
- [ ] Experiment only
- [ ] No specification impact
- [ ] `spec-compatible-change` approved

## Specification traceability

<!-- Use direct links. Delete the example. -->

<!-- Example:
- [GOV-SPEC-001](../blob/main/docs/specv1/GOVERNANCE.md#gov-spec-001-specifications-are-authoritative)

Spec-Refs: GOV-SPEC-001
-->

<!-- For genuinely non-behavioral work, use: -->
<!-- Spec-Impact: none -->
<!-- No-Spec-Impact-Rationale: concrete explanation -->

Affected profiles: <!-- event_day_preview, v1_web, v1_native, none -->

## Verification

Verification: `exact command` — result

<!-- Link mapped verification IDs and attach/manual evidence where needed. -->

## Impact and failure behavior

- API/data/migration impact:
- Scientific/safety/provenance impact:
- Missing/stale/degraded behavior:
- Rollback or recovery:

## Status transition

- [ ] No protected status transition
- [ ] Owner authorization recorded and `spec-status-approved` applied

## Checklist

- [ ] I read the specification index and governance.
- [ ] Every behavior change references accepted requirements.
- [ ] Verification maps to every affected requirement.
- [ ] Contracts/rules and generated requirement index are current.
- [ ] `uv run --project tools/specs python tools/specs/specctl.py validate` passes.
- [ ] No secret, precise location, unsafe advice, or misleading probability was added.
