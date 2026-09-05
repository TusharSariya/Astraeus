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

A corrective full selected-field run then retrieved all 245 advertised selected
coverages at one latest advertised valid time each over the exact small Avalon
API bbox (46.5–48.5 N, 55–51 W). All 245 TIFFs decoded and their artifacts
reopened; the run transferred 5,919,436 bytes in 392.041 seconds with no field
failures. This is one-time coverage evidence, not a production lead sweep. The
ledger records every field's selected times, published units, finite/nodata
counts, numeric range, artifact hash and elapsed time.

The retained representative artifacts are reproducible reader fixtures. Their
coordinates use the GeoTIFF RasterType: GeoMet's PixelIsArea tie point is the
northwest outer corner, so stored coordinates are cell centres. The requested
SCALESIZE output is explicitly recorded as server-resampled with an unknown
method and its actual per-axis resolution; it is not described as a native
grid. The generic experimental client can preserve any explicitly selected advertised coverage
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
