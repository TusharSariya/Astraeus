# Tasks

- [x] Map owner-directed delivery to native science and demand-cache contracts before implementation.
- [x] Verify current primary documentation, URLs, grid, native fields and timestamps.
- [x] Implement source-local bounded loader/cache and existing point/profile/timeline routing.
- [x] Verify request identities, bounds, expiry, coalescing, missingness and no retained fallback.
- [x] Retain bounded native-to-API oracle proof and current-client readback outside Git.
- [ ] Run API, registry/profile, web, strict OpenSpec and specctl gates, then independent review.

Owned files: rdps_query.py, rdps_query_worker.py, test_rdps_query.py; narrow
shared changes in app.py and eccc_datamart.py. Marine worker has finished its
app.py seam; integrate its merged head before final gates.
