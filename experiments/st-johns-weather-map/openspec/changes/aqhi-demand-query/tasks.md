# Tasks

- [x] Add a bounded current `AQHI-OBS` point-feature decoder and one-entry coalesced cache.
- [x] Select only actual nearby native station observations at or before the chosen instant with age less than one hour.
- [x] Expose native identity, unknown provider QC, sampled station coordinate/distance, and typed bounded acquisition metadata.
- [x] Compose AQHI only into the default unselected point response and preserve metadata-only expiry failures.
- [x] Replace the retained AQHI catalogue layer with cache-only demand capability metadata and disable scheduled ingestion.
- [x] Verify fixed-body/fixed-clock cache, time, distance, QC, provenance, expiry, API, and no-upstream catalogue behavior.
- [ ] Obtain owner resolution for the separate selected-product companion proposal before implementing that behavior.
