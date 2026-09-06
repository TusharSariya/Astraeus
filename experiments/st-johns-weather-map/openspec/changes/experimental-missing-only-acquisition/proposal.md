# Experimental missing-only acquisition repair

## Why

The accepted restart-cache requirement computes missing frame keys, but the
worker passed the original full window to adapters. It could therefore request
retained indexed GRIB leads again.

## Experimental repair

- Pass exact missing valid-time keys through `FetchWindow.covers`, the existing
  request-construction guard used by selectable adapters.
- Fail before provider payload retrieval when a partial cache is found for an
  adapter that has not explicitly declared a safe partial-artifact merge path.
  The retained revision remains visible.

## Explicit limits

Aggregate Zarr, JSON/time-series and granule-container adapters do not yet
declare partial repair support. Their immutable whole-artifact digest cannot be
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
