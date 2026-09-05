# Tasks

- [x] Map accepted authority and source-specific decision gaps.
- [x] Enumerate every selected surface field and profile level.
- [x] Add exact indexed HTTP range selection and complete-message checks.
- [x] Add native regular, projected, and icosahedral footprint proof.
- [x] Retain complete selected lead-0 bytes, immutable artifacts, hashes,
  provenance, real reader output, and explicit regional exclusions.
- [x] Test registration isolation, exact selectors, missing profile levels,
  malformed/unbounded indexes, and geometry exclusions.
- [ ] Accept source contracts, licence/admission decisions, cadence, later-lead
  accumulation semantics, and production failure behavior (owner only).
- [ ] Replace registered stubs, register candidates, or schedule runs.

Verification:

```text
cd experiments/st-johns-weather-map/api
uv run --extra grib pytest tests/test_native_deterministic_candidate.py -q
uv run --extra grib python ../scripts/native_deterministic_live_evidence.py --offline ../../../docs/research/wayfinder/evidence/native-deterministic-20260905
uv run --project tools/specs python tools/specs/specctl.py validate
```
