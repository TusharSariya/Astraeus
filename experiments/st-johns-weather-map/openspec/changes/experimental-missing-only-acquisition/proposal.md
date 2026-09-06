# Experimental missing-only acquisition repair

## Why

The restart-cache requirement forbids re-fetching retained frames, but GFS
discovery omitted its expected valid times and the worker passed partial
cache candidates to aggregate adapters. Both paths could fetch held data again.

## Experimental repair

- Declare the existing GFS lead schedule in discovery so the worker can check
  its retained times; prove full and partial cache outcomes through `run_source`.
- Refuse `adapter.fetch` when any requested times are retained and others are
  missing. No generic capability flag can bypass this barrier.
- Preserve ordinary cold-window fetches when retained keys do not overlap the
  requested times. The retained revision remains visible.

## Explicit limits

Aggregate Zarr, JSON/time-series and granule-container adapters do not yet
have a safe partial repair representation. Their immutable whole-artifact digest cannot be
replaced by a selected subset without a merge representation and API readback
contract. Rolling JSON sources that retrieve their bounded response during
`discover` also cannot claim a zero-payload full hit. Both remain follow-up
work; this change records and fails closed at the unsafe publication seam.
The current time-union store query also lacks the candidate's expected logical
artifacts, fields and members: it cannot detect a wholly absent required
container, while a blanket intersection would incorrectly mark independent
time-partitioned artifacts missing. Coverage-shape metadata is required before
that case can be repaired safely.

No registry state, retention window, storage tier, source admission, or
`operational: false` behavior changes.

Spec-Impact: experiment; no normative status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
