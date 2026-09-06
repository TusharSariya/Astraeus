## 1. Partial repair barrier

- [x] 1.1 Refuse aggregate partial cache fetch without a generic opt-in.
- [x] 1.2 Prove GFS discovery times reach actual run_source full-hit and partial-hit gates with zero GRIB range requests.
- [x] 1.3 Preserve cold-window fetching when unrelated retained times exist.
- [x] 1.4 Keep store-read failures distinct from an empty cache.

## 2. Required work, issue 158 remains open

- [ ] 2.1 Declare expected artifact/field/member coverage without breaking time-partitioned artifacts.
- [ ] 2.2 Define and verify immutable merge publication/API readback for aggregate time-series and field/member containers.
- [ ] 2.3 Move rolling JSON payload retrieval out of discovery or define a persisted metadata probe that permits zero-payload full hits.
- [ ] 2.4 Declare and verify exact candidate coverage for other adapters that currently omit valid_times; they remain outside this partial barrier's proof.
