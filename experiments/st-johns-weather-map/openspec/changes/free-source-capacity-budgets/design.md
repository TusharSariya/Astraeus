# Design

## Accounting boundary

At run admission, `U` is the bytes in two normally retained visible runs, `S`
is the complete incoming staged run, `P` is only the bytes retained beyond
normal retention by unexpired snapshot pins, and `R` is measured format,
manifest, derived-artifact and estimate variance. Admission requires
`U + S + P + R <= 64 GiB`. There is no fixed payload/reserve partition.

At snapshot admission, the same equation includes already committed staging
and the new pin's incremental bytes. Committed staging is the reserved
complete-run upper bound for an admitted run not yet published; it is zero
when no admission is outstanding and joins normal retained usage only after
publication. Page reads do not renew or enlarge a pin. Unexpired promises are
never evicted to admit a run. Retrieval and decode also require conservative
metadata-derived bounds for every additional allocation on each local
filesystem: download/decode temporaries and staged or published files stored on
that filesystem, without double-counting bytes already represented by `S`.
Those allocations and a conservative measured filesystem overhead and sizing-
variance allowance must fit actual free space. Admission reserves them
atomically against concurrent work. An unmeasured allowance blocks admission.

## Measurement before download

The adapter first enumerates the complete producer inventory and records fields,
levels, members, leads, grid, cadence, index/chunk layout and access shape. It
then retrieves metadata and representative ranges/chunks under a finite bound
sized from that metadata and computes conservative complete-run and operation-
resource bounds. The small discovery defaults apply when metadata cannot
establish a larger safe representative-artifact bound. Unknown or over-budget
bounds stop before the full download. Observed bytes and peak decode resources
reconcile the estimate after a successful staged run.

## Transfer policy

The shared daily direct-feed receive ceiling is disabled. Provider request and
rate ceilings remain hard limits, and every probe or retrieval has finite
operation-specific request, byte, memory, temporary-disk and wall-time bounds.
Concurrency is bounded; cancellation and provider throttle responses stop work
and use bounded backoff. Once the relevant acquisition contract and these gates
permit it, ordinary bounded full-field verification needs no additional
capacity approval. Removing the daily ceiling does not authorize paid access,
automatic downloads or unbounded resource use.

## Exhaustion

Provider limits and finite per-operation bounds are checked before requests.
Metadata, failures and retries count. Budget exhaustion preserves the
last visible revision and reports `retrieval_failed` with
`upstream_budget_exhausted`. Quota exhaustion remains `quota_exceeded`. Neither
path reduces fields, levels, members, resolution or retention promises.

## Durable reservation contract recommendation

The process-local maps are insufficient once two worker processes can admit
work against the same hot store or filesystem. The recommended experimental
replacement is a database ledger with one row per operation and allocation
target. One database transaction MUST lock the applicable target rows, sum
every reservation that has not completed proven cleanup, compare store and
filesystem projections, and insert all allocations for the operation or none.
Store and filesystem admission therefore share one commit; a process MUST NOT
hold one capacity reservation while failing to acquire the other.

Each operation identity consists of an immutable UUID plus a monotonically
increasing fencing token issued by the database. Release is idempotent and
requires both values. Every side effect after admission, including staging and
publication compare-and-swap, verifies the current token. A worker that passes
its deadline cannot publish or release a successor's reservation. Passing a
deadline changes the row from `active` to `revoking`; it does not subtract any
reserved capacity. Expiry alone cannot prove that a paused process stopped
writing a local file or completing an in-flight remote upload.

The recommended first contract is a fixed, nonrenewable deadline based on
database server time. A task-worker attempt receives the accepted 15-minute
maximum and an ingestion job the accepted 2-hour maximum. At the deadline, a
fenced reaper must prove that the old allocator has stopped, abort remote
multipart uploads and incomplete staging, exclusively remove the bounded local
workspace, and reconcile each actual allocation to zero before changing the
row to `releasable`. Cleanup has a proposed 15-minute objective. Missing that
objective keeps capacity charged, blocks admissions that no longer fit, and
raises an operator alert for manual recovery; it never reclaims by TTL alone.

Two alternatives remain documented but are not the recommendation. A fixed
reservation with no automatic deadline is safest but requires manual recovery
after every crash. A renewable short lease could reduce detection time, but a
30-second heartbeat and 2-minute expiry are unmeasured placeholders requiring
scheduler-pause and database-outage evidence; even then, expiry must enter
`revoking` and retain capacity until fenced cleanup proves allocations gone.

Allocation targets use the hot-store database URL and bucket as the global
store identity. Local filesystem rows additionally use a configured stable
worker-host identity and filesystem device identity; a transient process ID is
not sufficient. Multi-host workers cannot reserve another host's local disk.
Missing stable identity, unavailable ledger database, ambiguous lease state,
transaction timeout, or fencing mismatch fails closed before transfer. Store
exhaustion remains `quota_exceeded`; local-allocation, lease-loss and ledger-
availability failures report `upstream_budget_exhausted`, preserve the last
visible revision and leave no publishable staging record.

On same-host startup, a worker first takes an exclusive durable lock for its
stable host epoch and device, stops or fences prior-epoch allocators, removes
their bounded workspaces, and reconciles local rows before admitting new work.
An unreachable host's local reservation cannot consume another host's local
target, but its global object-store reservation remains charged until central
cleanup proves every remote allocation absent. Host clocks and process-liveness
observations are supporting evidence only; they never authorize release.

## Evidence limitations

The 18.23 GB widest scenario predates the completed roster. It demonstrates the
three-payload publication peak but is not used as a current aggregate forecast.
All target groups named in the research ledger remain unmeasured until their
integration tasks publish full ledgers.
