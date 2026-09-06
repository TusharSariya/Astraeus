# Open-Meteo GFS-Wave selected-time demand query

## Why

Issue #99 has an admitted catalogue record but no live provider-to-existing-app
path. The selected timestamp architecture requires a finite canonical request,
not scheduled ingestion, archive publication, horizon prefetch, or retained
artifact fallback.

## What changes

- Serve the catalogue's nine native GFS-Wave point fields through one exact
  selected UTC hour, `ncep_gfswave016`, and `cell_selection=sea` request.
- Keep only a finite source-local canonical cache and coalesce identical misses.
- Preserve individual native field absence, sea-grid coordinates, units,
  direction convention, Open-Meteo intermediary attribution, and the fact that
  the Marine response exposes no producer-run identity.
- Offer the existing `GFS Wave` product control and existing marine card
  mapping. The source remains reprocessed, non-primary, and `operational:false`.

This is an experimental implementation record. It does not accept or promote a
normative status, source state, commercial-use right, archive, or deployment.

Spec-Refs: GOV-SPEC-004; `evidence-truth-boundary`;
`source-registry-catalogue`; `point-evidence-sampling`.
