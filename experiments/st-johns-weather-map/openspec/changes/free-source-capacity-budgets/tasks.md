# Tasks

## 1. Human decisions and specification gate

- [x] 1.1 Record the owner's 2026-09-05 direction without inferring a fixed
  reserve: "yeah increase our budget then maybe set the budget to off unless we
  are going to run out of storage". Result: retain 64 GiB and require measured
  product overhead plus conservative disk/free-space gates.
- [x] 1.2 Remove the artificial shared daily receive ceiling. Provider ceilings
  and finite metadata-sized operation bounds remain mandatory.
- [ ] 1.3 Obtain separate normative status authorization under GOV-SPEC-002.
  The capacity answer resolves issue 74's policy choice but does not accept
  this draft or authorize production runtime/scheduler changes.
- [x] 1.4 Validate the revised draft with `openspec validate
  free-source-capacity-budgets --strict` and validate the repository
  specification graph. Result on 2026-09-05: the change is valid; `specctl`
  reports 0 errors and 0 warnings.

## 2. Complete source ledgers

- [ ] 2.1 For every issue 77-96 product/access path, enumerate every relevant
  field, level, member, lead, valid time and native grid, preserving explicit
  missing/unsupported/deferred dispositions.
- [ ] 2.2 Measure metadata/index/payload requests and bytes, original and
  normalized storage, derived/rendered bytes, peak RSS/temp disk/CPU/wall time,
  cadence and availability lag using representative real artifacts.
- [ ] 2.3 Prove source fees, requester-pays transfer, query, egress and compute
  charges separately zero; otherwise keep the source blocked.
- [ ] 2.4 Record worst-case complete-run and publication-peak bounds. Never
  extrapolate a tiny sample without inspecting remote chunk or whole-file shape.

## 3. Admission and enforcement

- [ ] 3.1 Add atomic accounting for normal retained bytes, committed complete
  staging, incremental snapshot pins, measured reserve and all additional local
  filesystem allocations without double-counting. Concurrent admissions must
  reserve projected filesystem allocations atomically.
- [ ] 3.2 Refuse source/run or snapshot admission before transfer when the
  projected 64 GiB total, temporary-disk bound or local free-space safety gate
  would be exceeded.
- [ ] 3.3 Enforce provider weights/rates and finite per-operation request,
  received-byte, decode-resource and time bounds; include metadata, failures
  and retries. Do not introduce a shared daily receive ceiling.
- [ ] 3.4 Return `upstream_budget_exhausted` or `quota_exceeded` with the last
  visible revision preserved and no field/member/resolution thinning.

## 4. Verification

- [ ] 4.1 Test two visible runs plus one complete staged run and incremental
  snapshot-only pins at every boundary and one byte over it.
- [ ] 4.2 Test restart accounting, expired-pin release, nonrenewable page reads,
  local free-space refusal, cancellation, provider 429/backoff and exhausted
  operation byte/compute/time bounds. Test concurrent admissions competing for
  the same filesystem bytes.
- [ ] 4.3 For each admitted source, attach real upstream retrieval, immutable
  artifact validation, Astraeus API readback and failure/provenance evidence.
- [ ] 4.4 Run `openspec validate free-source-capacity-budgets --strict`, the
  mapped product tests, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.

## 5. Experimental payload preflight

- [x] 5.1 Add the issue 159 worker/store preflight seam: an adapter must return
  a measured discovery received-byte bound before discovery and measured
  complete-operation store, local-filesystem, margin and received-byte bounds
  before `fetch`; missing or invalid bounds fail with
  `upstream_budget_exhausted` before payload retrieval. The worker reserves the
  hot-store and local allocation for the operation and reconciles temporary and
  staged bytes before publication. Owned files: `ingest/contract.py`,
  `ingest/resources.py`, `ingest/store.py`, `worker/runtime.py`.
  Verify: `cd api && uv run pytest -o addopts='' -q tests/test_worker_outcomes.py
  tests/test_ingest_store.py`.
- [x] 5.2 Stream byte-range responses before accepting them, enforce the
  operation-wide received-byte bound across requests and retry/error bodies,
  refuse ranges that cannot fit before their request, validate `Content-Range`
  identity and length, and retain per-response ceilings and partial-file
  cleanup. This also separates the previously
  shadowed bytes-with-headers method used by WCS retrieval. Owned files:
  `ingest/http.py`, `ingest/adapters/eccc_geomet_ensemble.py`,
  `ingest/adapters/eccc_geomet_reductions.py`. Verify: `cd api && uv run pytest
  -o addopts='' -q tests/test_ingest_http.py tests/test_http_client.py
  tests/test_adapter_ensemble.py`.
- [ ] 5.3 Supply source-specific measured `DiscoveryBounds` and `ResourceBounds`
  from each acquisition ticket before that adapter is scheduled. No current
  registered adapter may infer these values from generic constants or a
  percentage.
- [ ] 5.4 Replace the process-local reservation ledger before any multi-process
  or multi-host ingestion is enabled. The current worker deliberately executes
  one source at a time; separate experimental capture scripts remain outside
  its reservation boundary and must continue to coordinate capacity externally.
