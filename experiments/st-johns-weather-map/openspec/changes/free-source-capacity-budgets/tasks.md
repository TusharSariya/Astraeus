# Tasks

## 1. Human decisions and specification gate

- [ ] 1.1 Owner approves or replaces the 51.2/12.8 GiB payload/nonpayload envelopes.
- [ ] 1.2 Owner approves a numeric shared direct-feed receive allowance.
- [ ] 1.3 Update the delta requirements to the owner's exact answers and obtain
  the required normative status authorization; do not infer it from silence.

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
  staging, incremental snapshot pins and measured reserve without double-counting.
- [ ] 3.2 Refuse source/run or snapshot admission before transfer when any
  approved envelope or the 64 GiB total would be exceeded.
- [ ] 3.3 Meter provider weights, requests, received bytes and decode resources;
  include metadata, failures and retries.
- [ ] 3.4 Return `upstream_budget_exhausted` or `quota_exceeded` with the last
  visible revision preserved and no field/member/resolution thinning.

## 4. Verification

- [ ] 4.1 Test two visible runs plus one complete staged run and incremental
  snapshot-only pins at every boundary and one byte over it.
- [ ] 4.2 Test restart accounting, expired-pin release, nonrenewable page reads,
  provider 429/backoff and exhausted daily byte/compute allowances.
- [ ] 4.3 For each admitted source, attach real upstream retrieval, immutable
  artifact validation, Astraeus API readback and failure/provenance evidence.
- [ ] 4.4 Run `openspec validate free-source-capacity-budgets --strict`, the
  mapped product tests, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
