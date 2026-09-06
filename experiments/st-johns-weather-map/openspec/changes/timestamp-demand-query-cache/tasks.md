# Tasks

- [ ] Revise CYYT TAF to conditional provider query plus native report cache and prove Workbench use.
- [ ] Revise GFS to fetch only the selected native valid time and requested eligible fields.
- [ ] Define the minimal shared cache key/outcome seam from those two concrete sources; do not introduce snapshots, background refresh jobs or a new archive.
- [ ] Migrate HRDPS, METAR/SPECI and Kp from scheduled bulk ingestion to bounded selected-time queries without deleting their prior evidence until replacement passes.
- [ ] Verify cache hit/miss/expiry, conditional revalidation, concurrent coalescing, bounded failure, exact provenance and current-client responses.
