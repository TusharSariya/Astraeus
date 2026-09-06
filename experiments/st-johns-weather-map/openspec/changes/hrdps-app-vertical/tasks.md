## 1. Native resource enforcement

- [x] Bound listings, cycle count, lead count and each streamed GRIB response.
- [x] Detach loaded crops from full-grid coordinate backing allocations.
- [x] Record complete 25-lead memory, filesystem, receive and artifact evidence.

## 2. Existing application path

- [x] Queue HRDPS through the existing refresh API and record the terminal job.
- [x] Verify immutable publication and all 48 retained raw/artifact fields across all 25 lead times.
- [x] Verify live `/point`, `/timeline`, `/layers`, `/profile` and current web consumption.

## 3. Verification

- [x] Cover oversize, malformed, missing, quota, stale/full-cache and cleanup failures.
- [x] Run full API, registry, SQL, strict OpenSpec, specctl and CI gates.

## 4. Retained verification receipt

- Exact reviewed implementation head: `62b7c068457eeb4314d553dbf1762c25ce9ccf8e`.
- Raw oracle: 1,200 unique field-time inputs (48 fields by PT000-PT024),
  26,462,400 cells, zero value/unit/shape/hash mismatches; artifact SHA-256
  `df46703a73a2eb57cf64ce380593d1cda6a34a56eec5d9e84c85d5d005e69b2b`.
- Complete replay: 3,047,473,152-byte cgroup memory peak, 113,090,560-byte
  physical workspace peak, 39,157,631-byte artifact, complete and QC-passed.
- Live acceptance: two retained HRDPS runs; seven `/point` readings with exact
  field levels, 19 `/profile` readings at four pressure levels, consistent
  timeline/layer coverage, existing Brief/Workbench rendering, and explicit
  refresh completion with zero bulk payload for the complete retained run.
- Final gates: API 2,009 passed/43 skipped; registry 236 passed and four strict
  profiles valid; SQL invariants passed; strict OpenSpec 67/0; specctl 0/0;
  governance CI passed. Provider payloads and complete raw receipts remain
  outside Git.
