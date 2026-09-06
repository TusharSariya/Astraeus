## 1. Worker selection

- [x] 1.1 Propagate exact missing valid times through the worker-to-adapter path.
- [x] 1.2 Prove a full hit performs no adapter fetch and unknown cache state fails closed.
- [x] 1.3 Prove an indexed GRIB adapter constructs a request only for the missing lead.

## 2. Coverage and identity

- [x] 2.1 Preserve provider run identity and refuse unsupported aggregate repair before payload retrieval.
- [ ] 2.2 Declare expected artifact/field/member coverage without breaking time-partitioned artifacts.
- [ ] 2.3 Define and verify immutable merge publication/API readback for aggregate time-series and field/member containers.
- [ ] 2.4 Move rolling JSON payload retrieval out of discovery or define a persisted metadata probe that permits zero-payload full hits.
