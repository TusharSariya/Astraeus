## Why

The existing ECMWF ensemble adapters proved assembly only with fixtures and
always refused discovery. Issue 82 requires real anonymous Open Data discovery,
bounded indexed retrieval, immutable artifact proof and API readback without
activating either owner-gated family.

Classification: Experiment. Spec-Impact: none. Accepted authority is limited
to GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005 and GOV-SPEC-006;
the source-specific behavior remains outside production.

## What changes

- Add an explicit unregistered discovery seam that enumerates all advertised
  leads in a requested window under a finite metadata request ceiling.
- Retrieve only catalogue-family fields by exact `.index` byte ranges and
  validate response identity, run/member/lead identity, instantaneous cloud
  semantics, units and one exact native grid.
- Preserve the verified AIFS control and the verified IFS missing-control state.
- Record actual per-range bytes and checksums in artifact provenance and prove
  real Zarr/API readback.

## Impact

Registry, scheduler, status, production API schema and the 64 GiB hot quota do
not change. Rollback removes the experiment seam and tests; neither family can
enter scheduling because the existing gate remains false.
