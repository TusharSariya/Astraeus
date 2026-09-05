# Experimental GeoMet WCS numeric integration

## Why

The catalogue describes GeoMet WCS coverages as stored, but the only active
deterministic ECCC model adapters read GRIB2 from Datamart.  The existing
GeoMet module reads WMS point and image responses.  Neither path can produce a
numeric WCS field artifact, so the WCS-only catalogue claims are ahead of the
runtime.

Issue 79 authorizes isolated experimental adapter, fixture, live-artifact and
API-readback work.  It does not authorize production registration,
scheduling, `operational: true`, or normative promotion.  This change keeps
`MODEL_SOURCE_OWNER = "eccc_datamart"` and does not import the WCS module from
the adapter registry.

## What this draft proposes after owner acceptance

- Treat GeoMet WCS 2.0.1 as a distinct access path for HRDPS, RDPS and GDPS.
- Require WMS leaf metadata before every numeric retrieval because WCS
  capabilities has no title, unit or time axes and WCS range units conflict
  with WMS titles on known fields.
- Require `FORMAT=image/tiff`, longitude and latitude `SUBSET`, explicit
  `SCALESIZE`, an advertised `TIME`, and an advertised
  `DIM_REFERENCE_TIME` whenever the layer publishes runs.
- Preserve ECCC seeing and transparency values as unlabelled integer class
  indices.  Zero remains a value with unresolved meaning; it is never relabelled
  as worst conditions or silently converted to nodata.
- Publish only after TIFF signature, requested shape, georeferencing, nodata,
  immutable Zarr round-trip and checksum validation.

## Current evidence

`docs/evidence/geomet-wcs-2026-09-05.json` records a bounded live probe.  The
service advertised 5,589 coverages, down from 6,123 on September 2, while the
full family inventory remained HRDPS 377, RDPS 438, and GDPS 474 including
GEML: 1,289 exact identifiers. The evidence file accounts for each one. It
maps 245 issue-selected coverages to exact experimental artifact destinations
(canonical catalogue fields where established, explicit `weong_*` names for
producer products otherwise) and marks the
remaining 1,044 as capability-only, deferred and unmapped because their
semantic normalization and production admission are not established. All 245
selected coverage identifiers remain advertised. Five
representative fields across 40 m humidity, WEonG sky state, seeing,
transparency and GDPS WEonG fog visibility were fetched sequentially,
validated and reopened as immutable artifacts.

The five retrieved fields are a representative live smoke, not evidence that
all 245 selected fields or all 1,289 family fields were downloaded. The generic
experimental client can preserve any explicitly selected advertised coverage
under a `raw__<coverage_id>` name without assigning canonical meaning; each
operation remains bounded to 64 sequential fields and requires metadata and
geometry validation.

## Owner decisions still required

1. Accept, revise or reject this source-specific contract before production
   registry or scheduler activation.
2. Decide whether the WCS access path receives distinct source identities or
   remains an access-path member beneath the current producer products.
3. Decide the operational field/lead window inside the 64 GiB hot quota.
4. Resolve class `0` semantics for the seeing and transparency products before
   any ranking, colour semantics or quality mask uses those cells.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
