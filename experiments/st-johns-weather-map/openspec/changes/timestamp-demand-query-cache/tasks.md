# Tasks

- [x] Revise CYYT TAF to conditional provider query plus native report cache and prove Workbench use (PR207, independently verified against an actual 200/304 response and current Workbench).
- [x] Revise GFS to fetch only the selected native valid time and requested eligible fields, under a locked bounded child, and prove a cache miss then hit through `/point` and the current model control (issue #208).
- [ ] Define the minimal shared cache key/outcome seam from those two concrete sources; do not introduce snapshots, background refresh jobs or a new archive.
- [ ] Migrate HRDPS, METAR/SPECI and Kp from scheduled bulk ingestion to bounded selected-time queries without deleting their prior evidence until replacement passes.
- [ ] Verify cache hit/miss/expiry, conditional revalidation, concurrent coalescing, bounded failure, exact provenance and current-client responses for every migrated source (GFS miss/hit/coalescing/bounded failure and current-client response verified in #208).
