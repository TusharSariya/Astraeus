# Free-source capacity budgets

## Why

The 64 GiB store was justified from a smaller catalogue using two run-sized
payloads. The implemented retention rule can hold two visible runs while a
third complete run is staged, and the owner has since selected fixed-expiry
snapshot pins. For the older widest measured catalogue that peak is 50.93 GiB
before overhead or pins. The expanded free-source roster has no complete
storage, transfer, request or decode measurements, so it cannot honestly be
declared to fit.

## What changes after owner approval

- Partition the existing quota into a payload envelope covering normal runs,
  complete staging and snapshot pins, plus an overhead/derived reserve, while
  preserving the hard total.
- Require metadata-first full-field/full-member measurement before source
  admission, including publication-peak and pin accounting.
- Give each source explicit request, received-byte, decode-resource and refresh
  limits below provider ceilings, with separate proof that source, query,
  transfer and compute charges are zero.
- Fail closed on exhaustion without thinning, substitution or silent eviction.

## Pending owner decisions

1. Proposed store envelopes: 51.2 GiB for normal retention, complete staging
   and snapshot-only pins together, plus a 12.8 GiB nonpayload reserve.
2. Proposed shared direct-feed receive ceiling: 128 GiB/day for the local
   experiment.

No requirement in this change is accepted by its presence here. Only
`@TusharSariya` may authorize normative status. Implementation waits for that
authorization and the source-specific measurements.

## Evidence

- `docs/research/wayfinder/free-source-capacity-budget.md`
- `docs/research/wayfinder/size-probe-full-fields.md`
- `docs/research/free-source-implementation-roster.json`
- `infra/STORAGE.md`

Spec-Impact: requirement change, draft only.
