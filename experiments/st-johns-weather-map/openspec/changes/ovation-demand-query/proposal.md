# OVATION selected-time demand query

## Why

Issue #236 replaces the experimental OVATION map's stored-artifact delivery
path with the owner-selected timestamp-demand/cache architecture. It keeps the
existing normalized NOAA SWPC OVATION interpretation: a percent model-nowcast
grid, Atlantic-context crop, payload Observation Time and Forecast Time,
native 1-degree cells, and explicitly non-operational presentation.

## What changes

- The map raster makes one bounded canonical request to SWPC's current
  `ovation_aurora_latest.json` document on cache miss, normalizes it in an
  isolated bounded decoder, and keeps one finite current entry only.
- The selected UTC instant must lie within the existing single native
  10-minute interval of the document's Forecast Time. Outside that interval is
  unavailable; no nearest timestamp or stored artifact is substituted.
- The layer index advertises a requestable demand layer without fetching or
  claiming a current native frame exists. A successful raster declares
  `evidence_basis: demand_query`; expiry/retrieval failure withholds raster
  values and discloses only bounded cached receipt identity and expiry.

This is an experimental implementation record. It neither promotes the source
nor changes accepted/verified/superseded/operational status. It does not create
an archive, scheduled ingestion, or a forecast-skill claim.

Spec-Refs: GOV-SPEC-004; GOV-SPEC-006; `timestamp-demand-query-cache`;
`space-weather-aurora-evidence`.
