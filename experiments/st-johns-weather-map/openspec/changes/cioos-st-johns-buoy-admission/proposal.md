# CIOOS Atlantic St. John's buoy admission and demand contract

## Why

Issue [#112](https://github.com/TusharSariya/Astraeus/issues/112) includes
buoy observations. The current registry has only
`smartatlantic-st-johns`, whose declared SmartAtlantic endpoint has a pending
per-dataset rights review and a stale coverage condition. Its record therefore
cannot authorize a live query.

This proposal records one distinct, named candidate:
`cioos-atlantic-sma-st-johns`, delivered by CIOOS Atlantic ERDDAP dataset
`SMA_st_johns`. The publisher's metadata identifies a Marine Institute
TimeSeries with `station_name`, latitude and longitude and records CC BY 4.0;
the CIOOS catalogue also states CC BY 4.0. The canonical metadata observed on
2026-09-07 reports `time_coverage_end: 2026-04-13T18:30:01Z`. It is evidence of
an accessible, named source, not evidence that the source is presently live. This
draft reads metadata only; it makes no current data request and therefore does
not claim the latest published observation.

No existing registry record, ERDDAP client, fixture, adapter, cache, API route
or catalogue capability implements this CIOOS delivery. The local research
mentioning earlier CIOOS data is non-normative. This proposal adds no code or
status transition and keeps the experiment `operational: false`.

## What this proposes

- Admit a *draft* registry record for the named CIOOS delivery, distinct from
  the stale SmartAtlantic path, with canonical endpoint, CC BY 4.0 attribution
  and its exact observed metadata identity.
- Define a smallest metadata-first, selected-time ERDDAP request whose response
  can prove source/station identity, coverage, literal variable schema and
  native values. It is a station report, never a synthetic grid or
  interpolation.
- Propose a finite source-local cache and receipt/expiry boundary. It has no
  schedule, archive, stale fallback, retained artifact, forecast vote or
  automatic registry promotion.
- Make the known gaps explicit: metadata currently fails the proposed
  current-context freshness gate, metadata exposes no provider quality field,
  and no accepted rule currently selects an at-or-before buoy report for an
  arbitrary selected timestamp.

## Proposed choices requiring owner acceptance

These are concrete alternatives for review, not accepted behavior:

1. **Time.** For a current-context selected instant, use the newest native
   record at or before the instant only when its age is strictly below one hour;
   otherwise report unavailable. Do not use a future record, interpolation or a
   neighbouring station. This follows the observed 30-minute reporting history
   but is not inferred as a publisher guarantee.
2. **Freshness.** Before any current-context value is served, require the
   metadata `time_coverage_end` to be no more than two hours before acquisition
   completion. The April 2026 metadata fails this proposed gate today. A future
   acceptance may choose a different documented ceiling, but implementation
   cannot substitute one.
3. **Quality.** Preserve numeric values and the absence of a published quality
   field. Local quality is `unknown`; missing values are null individually. No
   range check, inferred `pass`, or numeric-to-QC mapping is permitted.
4. **Scope.** Start with the literal named surface and wave variables listed in
   the schema delta. Current-profile bins, cameras, spectral products and the
   dormant `SMA_st_johns_wharf` water-level dataset are out of scope.

## Capabilities

### Added capabilities

- `source-registry-catalogue`: proposed CIOOS source identity, licence and
  stale-coverage admission boundary.
- `point-evidence-sampling`: proposed named-station report identity and
  selected-time semantics.
- `demand-query-cache`: proposed bounded ERDDAP request, receipt, cache and
  expiry behavior.

## Impact and non-impact

Future implementation would add a source-local ERDDAP demand reader and fixed
ERDDAP fixtures, then compose only fresh named-station observations as
non-primary evidence. It must reuse the existing demand-query receipt/cache
shape where it fits, without treating a previous source's time or QC rule as
authority.

It does not change SmartAtlantic's pending/stale disposition, registry state,
source admission status, science, public deployment, archive policy, paid
access, selected-product composition, profile support or any held proposal.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005,
GOV-SPEC-006.
