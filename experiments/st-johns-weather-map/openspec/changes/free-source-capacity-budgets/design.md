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

## Evidence limitations

The 18.23 GB widest scenario predates the completed roster. It demonstrates the
three-payload publication peak but is not used as a current aggregate forecast.
All target groups named in the research ledger remain unmeasured until their
integration tasks publish full ledgers.
