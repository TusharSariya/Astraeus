# Tasks

- [x] Add a selection-derived AWC `date`/`hours` request, finite LRU, per-key coalescing, conditional revalidation, and bounded failure handling.
- [x] Validate the complete response window and select latest-at-or-before with strict age less than one hour.
- [x] Route default and selected forecast `/point` responses through demand METAR without ArtifactStore fallback.
- [x] Reconcile every retained native field and absence through normalized point evidence and the existing UI.
- [x] Prove Linux bounds, real provider miss/hit, API/Brief/Workbench readback, unavailable paths, and no scheduled provider request.
- [x] Run focused and full API, registry, web, OpenSpec strict, and specctl gates; retain exact logs.
