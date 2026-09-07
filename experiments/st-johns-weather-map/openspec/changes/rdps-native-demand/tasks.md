# Tasks

- [x] Map owner-directed delivery to native science and demand-cache contracts before implementation.
- [x] Verify current primary documentation, URLs, grid, native fields and timestamps.
- [x] Implement source-local bounded loader/cache and existing point/profile/timeline routing.
- [x] Verify request identities, bounds, expiry, coalescing, missingness and no retained fallback.
- [x] Retain bounded native-to-API oracle proof and current-client readback outside Git.
- [x] Run API (2,088 passed/50 skipped), registry (237)/four profiles, web (452)/build, strict OpenSpec (75), and specctl (0 errors/0 warnings).
- [x] Obtain independent review of 644ff2: two provenance/failure-disclosure blockers recorded.
- [x] Preserve bounded typed canonical request/transport identity in public point/profile provenance.
- [x] Retain only bounded expired metadata and return typed unavailable outcomes after failed payload or directory refresh; no stale values or stored fallback.
- [x] Verify 21 focused RDPS cases and offline replay of all 25 retained native receipts; freeze two pre-existing GFS test clocks and pass their focused rerun.
- [ ] Obtain fresh independent re-review of the correction; PR234 remains unmerged.

Owned files: rdps_query.py, rdps_query_worker.py, test_rdps_query.py; narrow
shared changes in app.py and eccc_datamart.py. Marine worker has finished its
app.py seam; integrate its merged head before final gates.
