# Tasks

This proposal is not implementation authority until the owner approves its
normative transition under `GOV-SPEC-002`.

- [ ] 1.1 Add typed selection-snapshot request/response/error models and expose
  the fixed 15-minute nonrenewing lifetime.
- [ ] 1.2 Bind `/timeline`, `/layers` and `/point` to one snapshot id and reject
  selection changes, expiry and unreadable revisions explicitly.
- [ ] 1.3 Add contract tests proving all three reads return one revision set,
  later publication does not mutate it, and explicit replacement swaps all
  three or none.
- [ ] 2.1 Register finite expected fragment shapes for each participating
  adapter; an adapter without one remains non-schedulable for fetch-on-miss.
- [ ] 2.2 Store immutable fragments and publish complete manifest revisions in
  one transaction, retaining the prior manifest on crash or validation failure.
- [ ] 2.3 Add fragment tests for cache hit, one missing key, wholly absent
  logical artifact, conflicting digest, partial failure and concurrent repair.
- [ ] 3.1 Extend durable refresh jobs with canonical selection idempotency and
  per-source/per-fragment outcomes without allowing read routes upstream.
- [ ] 3.2 Integrate issue #173 operation UUID/fencing verification and durable
  capacity reservations before transfer, staging and snapshot admission.
- [ ] 3.3 Prove expiry remains charged through revocation and is released only
  after fenced remote/local cleanup; stale owners cannot publish or release.
- [ ] 4.1 Wire the existing client to open one snapshot, show acquisition job
  progress, and replace timeline/layers/point only after explicit refresh.
- [ ] 4.2 Prove a failed member read leaves the earlier labelled snapshot intact
  and an expired snapshot is never labelled current.
- [ ] 4.3 Verify latest-at-or-before, strict less-than-one-hour Map matching and
  refusal of future frames across stored and live-proxy layers.
- [ ] 5.1 Run API, worker, SQL, web, OpenSpec and specctl suites; record mapped
  results before claiming implementation.

Dependency order: issue #173 durable reservations; this accepted contract;
fragment/store and selection-job implementation; API snapshot reads; existing
client wiring. The five-view rebuild remains a later independent change.
