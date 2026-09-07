# RAP selected-time native forecast delivery

## Why

Owner-requested RAP scope is tracked in #271. Closed acquisition #81 is not an
Avalon integration: its `awp130pgrb` messages yielded zero native cells in the
45..50.5 N, -58..-46 W evidence box. The earlier optional-model proposal's
successful rectangular subset request did not prove actual footprint coverage.
A bounded 2026-09-07 awp236 VIS message also contains zero native box cells.
No tested product currently supports Avalon; this proposal establishes the
future delivery contract and honest refusal, not false local integration.
The existing candidate admits only MASSDEN/AOTK as raw-only, with unresolved
units/species. It cannot be promoted into a weather API by copying GFS code.

## What Changes

Propose RAP as a distinct native NOAA forecast source using an explicitly
identified published grid which actually covers the requested geography.
Start with instantaneous entire-atmosphere total cloud (TCDC, native percent)
and surface visibility (VIS, native metres), only after exact inventory and
GRIB metadata verification. Retain the full RAP objective: temperature,
humidity, native winds, profiles, smoke/aerosols and other requested fields
remain owned by #271, with mapped follow-ups rather than silently discarded.

Use timestamp-driven bounded acquisition and finite caching; no ArtifactStore,
full-run schedule, archive, model substitution or centre-vote promotion.

## Capabilities

### Added Capabilities

- `rap-timestamp-demand`: product/coverage admission, initial cloud/visibility
  delivery, finite-cache provenance and refusal semantics.

## Impact and authority

Proposed only. Owner acceptance is required before runtime implementation.
This proposal does not admit grid 130, register a source, promise coverage of
an unmeasured grid or promote operational/scientific status. Existing RAP
candidate evidence and all source scope remain intact. GOV-SPEC-001/002/004/005/006
own governance; timestamp-demand-query-cache, optional-forecast-centres,
field-catalogue and source-registry-catalogue are related executable contracts.
