# Tasks

- [x] Verify current official Marine API fields, model selector, sea-cell
  selection, unit/direction/time semantics, free non-commercial limits, and
  response identity constraints.
- [x] Add a source-local exact-hour nine-field request/cache path with bounded
  body, structural parser inventory, aggregate metadata budget, provider freshness cap,
  coalescing, and no stale fallback.
- [x] Map every native field as retrieved or explicitly unavailable; refuse an
  all-null sea response and do not infer a GFS-Wave run identity.
- [x] Wire `/point?product=GFS+Wave` and the existing product selector/marine
  field mapper with reprocessed Open-Meteo/NOAA-NCEP provenance.
- [x] Add bounded cache, concurrency, native-time, unit, individual-null,
  all-null, API and web mapping verification.
- [x] Record a compact live receipt and DQC without committing raw provider
  payload.
- [x] Run focused API, registry, generated-field-catalogue, UI build, OpenSpec, and repository specification validation; obtain independent review before merge.
