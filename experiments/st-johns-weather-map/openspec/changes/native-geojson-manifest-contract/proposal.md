# Native GeoJSON manifest and snapshot publication contract

## Problem

The ingestion contract validates gridded canonical fields through
`RunManifest`, but some providers publish authoritative native GeoJSON whose
properties have no canonical weather-field meaning. Translating an ECCC
thunderstorm category or hurricane geometry into an existing field would
invent science. Publishing it with hard-coded completeness or QC would bypass
the accepted manifest gate. Using retrieval time as a valid frame would invent
a producer observation time.

PR #164 therefore retained bounded, structurally checked snapshots but marked
them `complete: false` with `manifest_unresolved`. This proposal defines the
smallest contract needed to validate and publish that native representation
without interpreting it.

## Recommended decision

Approve the single recommended contract in `design.md`: extend `RunManifest`
with a mutually exclusive native-GeoJSON schema, keep `qc_passed` as the
shared validator's computed publication gate while explicitly reporting
provider QC as unknown, keep atomic run publication and latest-and-previous
retention unchanged, and add snapshot-identity lookup beside the frame-exact
features lookup. Provider properties remain source fields, not canonical
meteorological fields, and retrieval time never becomes a valid frame.

This is a proposal only. It does not change accepted specifications, registry
status, scheduling, admission, retention implementation, API behavior, or the
current `manifest_unresolved` verdict. Owner approval is required before any
implementation task is started or normative status changes.

Spec-Impact: proposed contract; no normative status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
