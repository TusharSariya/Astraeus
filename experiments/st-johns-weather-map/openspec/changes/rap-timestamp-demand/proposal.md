# RAP selected-time native forecast delivery

## Why

Owner-requested RAP scope is tracked in #271. Closed acquisition #81 is not an
Avalon integration: its `awp130pgrb` messages yielded zero native cells in the
45..50.5 N, -58..-46 W evidence box. The earlier optional-model proposal's
successful rectangular subset request did not prove actual footprint coverage.
A bounded 2026-09-07 awp236 VIS message also contains zero native box cells.
The separately distributed `awip32` grid 221 now has retained native evidence
for Avalon: 516 in-box cells plus boundary support, instantaneous VIS metres
and entire-atmosphere TCDC percent at run 2026090723/f00. This updates the
product prerequisite; source-to-app acceptance and the remaining RAP fields
are not complete.
The existing candidate admits only MASSDEN/AOTK as raw-only, with unresolved
units/species. It cannot be promoted into a weather API by copying GFS code.

## What Changes

Propose RAP as a distinct native NOAA forecast source using an explicitly
identified `awip32` North American grid 221, preserving measured native
Lambert geometry (349 by 277, spacing 32,463 m) and a one-cell crop halo.
Start with instantaneous entire-atmosphere total cloud (TCDC, native percent)
and surface visibility (VIS, native metres), with exact inventory and
GRIB metadata validation on every acquired message. Retain the full RAP objective: temperature,
humidity, native winds, profiles, smoke/aerosols and other requested fields
remain owned by #271, with mapped follow-ups rather than silently discarded.

Use timestamp-driven bounded acquisition and finite caching; no ArtifactStore,
full-run schedule, archive, model substitution or centre-vote promotion.

## Capabilities

### Added Capabilities

- `rap-timestamp-demand`: product/coverage admission, initial cloud/visibility
  delivery, finite-cache provenance and refusal semantics.

## Impact and authority

Proposed only. Owner acceptance/reconciliation is required before the shared
RAP point API and catalogue mapping is enabled. The existing unregistered
source-local `RAPQueryCoordinator.point_native()` is an owner-authorized
experiment, not acceptance of this proposal or completion of #271.
This proposal does not admit grid 130, register a source, promise continuity or
coverage of an unmeasured grid or promote operational/scientific status. Existing RAP
candidate evidence and all source scope remain intact. GOV-SPEC-001/002/004/005/006
own governance; timestamp-demand-query-cache, optional-forecast-centres,
field-catalogue and source-registry-catalogue are related executable contracts.


## Concrete decision requested

Authorize only `noaa-rap` / `awip32` native `visibility` (surface, metres) and
`total_cloud_geometric` (entire atmosphere, percent) as retrieved,
available-not-stored, nonprimary evidence-only point fields. Preserve exact UTC
native hour, run and lead, actual sampled coordinates/distance, native bitmap
nulls and unknown scientific QC. Use the existing bounded two-cycle lookup and
receipt-anchored 600-second cache; do not promise a full run inventory or Series.
This does not accept aerosol/profile/wind semantics, promote source status,
change consensus or establish operational reliability.
