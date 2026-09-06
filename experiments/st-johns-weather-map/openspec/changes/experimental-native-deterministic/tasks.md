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
# Payload bundles are not stored in Git (owner decision 2026-09-05, issue 70).
# Capture one locally first, then replay against that directory:
uv run --extra grib python ../scripts/native_deterministic_live_evidence.py /tmp/astraeus-native-capture
uv run --extra grib python ../scripts/native_deterministic_live_evidence.py --offline /tmp/astraeus-native-capture /tmp/astraeus-native-replay
uv run --project tools/specs python tools/specs/specctl.py validate
```

- [x] Preserve original retrieval timestamps during retained replay; `tests/test_native_deterministic_candidate.py` and offline replay against a locally captured bundle verify provenance, with replay time recorded separately.
