# Tasks

- [x] Revise CYYT TAF to conditional provider query plus native report cache and prove Workbench use (PR207, independently verified against an actual 200/304 response and current Workbench).
- [ ] Revise GFS to fetch only the selected native valid time and requested eligible fields.
- [ ] Define the minimal shared cache key/outcome seam from those two concrete sources; do not introduce snapshots, background refresh jobs or a new archive.
- [x] Migrate HRDPS point and profile consumers from scheduled bulk ingestion to bounded selected-time queries, retain the existing GeoMet live raster proxies, hide stale stored HRDPS layers, and disable HRDPS full-run scheduling only after real point/profile readback passed.
- [ ] Migrate METAR/SPECI and Kp from scheduled bulk ingestion to bounded selected-time queries without deleting their prior evidence until replacement passes.
- [x] Verify HRDPS cache miss/hit, expiry, concurrent coalescing, bounded failure, exact transport and native-time provenance, real point/profile responses, and current-client consumption.
- [ ] Verify conditional revalidation where the provider exposes a validator; the measured HRDPS immutable run/lead objects did not expose an ETag in this slice.
