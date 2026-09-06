# HRDPS existing-app vertical slice

## Why

The registered native HRDPS adapter is refused by the worker because it lacks
complete-operation bounds. The current API and workbench therefore cannot show
artifact-backed HRDPS point or timeline evidence even though the source and
reader contracts already exist.

## What changes

- Bound all discovery listings and all 00-24 hour native GRIB transfers before
  retrieval, and require finite worker memory and temporary-filesystem limits.
- Detach cropped coordinates from continental-grid backing arrays so retained
  fields account only for the selected Avalon geometry.
- Preserve all 48 mapped field dispositions and publish one complete immutable
  surface artifact through the existing worker/store/API path.
- Make preserved database volumes accept the current experimental registry
  vocabulary without rewriting or promoting legacy rows.

This is an experimental source integration. It does not make HRDPS operational,
extend the selected 24-hour slice, implement partial-cache repair, or change the
64 GiB/two-run/24-hour-observation/14-day-forecast policies.

Spec-Impact: experimental implementation under existing accepted storage and
ingestion contracts; no normative status transition.

Spec-Refs: STO-002, ING-006, CAP-003, CAP-004, CAP-005
