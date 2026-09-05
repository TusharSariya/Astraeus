# Design

## Accounting boundary

At run admission, `U` is the bytes in two normally retained visible runs, `S`
is the complete incoming staged run, `P` is only the bytes retained beyond
normal retention by unexpired snapshot pins, and `R` is measured format,
manifest, derived-artifact and estimate variance. Admission requires
`U + S + P + R <= 64 GiB` and compliance with each approved sub-envelope.

At snapshot admission, the same equation includes already committed staging
and the new pin's incremental bytes. Committed staging is the reserved
complete-run upper bound for an admitted run not yet published; it is zero
when no admission is outstanding and joins normal retained usage only after
publication. Page reads do not renew or enlarge a pin. Unexpired promises are
never evicted to admit a run.

## Measurement before download

The adapter first enumerates the complete producer inventory and records fields,
levels, members, leads, grid, cadence, index/chunk layout and access shape. It
then retrieves metadata and representative ranges/chunks under a small cap and
computes a conservative complete-run bound. Unknown or over-budget bounds stop
before the full download. Observed bytes and peak decode resources reconcile
the estimate after a successful staged run.

## Exhaustion

Provider limits and the lower local source/shared limits are checked before
requests. Metadata, failures and retries count. Budget exhaustion preserves the
last visible revision and reports `retrieval_failed` with
`upstream_budget_exhausted`. Quota exhaustion remains `quota_exceeded`. Neither
path reduces fields, levels, members, resolution or retention promises.

## Evidence limitations

The 18.23 GB widest scenario predates the completed roster. It demonstrates the
three-payload publication peak but is not used as a current aggregate forecast.
All target groups named in the research ledger remain unmeasured until their
integration tasks publish full ledgers.
