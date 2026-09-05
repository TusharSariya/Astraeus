# Free-source capacity budgets

## Why

The 64 GiB store was justified from a smaller catalogue using two run-sized
payloads. The implemented retention rule can hold two visible runs while a
third complete run is staged, and the owner has since selected fixed-expiry
snapshot pins. For the older widest measured catalogue that peak is 50.93 GiB
before overhead or pins. The expanded free-source roster has no complete
storage, transfer, request or decode measurements, so it cannot honestly be
declared to fit.

## Owner direction recorded 2026-09-05

The owner answered: "yeah increase our budget then maybe set the budget to off
unless we are going to run out of storage". The resulting policy removes the
artificial shared daily receive cap. It preserves the existing 64 GiB hard hot
quota and requires measured full-run projections and conservative disk/free-
space gating. It does not authorize paid access or unbounded probes, requests,
memory, temporary disk, runtime or concurrency.

## What this draft proposes after normative approval

- Admit against the existing quota using measured product-specific overhead,
  complete staging and incremental snapshot-pin accounting, without inventing
  a fixed reserve percentage.
- Require metadata-first full-field/full-member measurement before source
  admission, including publication-peak, pin, decode and local temporary-disk
  accounting.
- Keep the shared daily receive ceiling off while giving each operation finite
  metadata-sized request, received-byte, decode-resource and time bounds below
  provider ceilings, with separate proof that source, query, transfer and
  compute charges are zero.
- Fail closed on exhaustion without thinning, substitution or silent eviction.

No requirement in this change is accepted by the capacity answer or its
presence here. Only `@TusharSariya` may authorize normative status under the
separate governance transition. Production implementation waits for that
authorization. Product-specific measurement continues in the acquisition
tickets without admitting unmeasured sources.

## Evidence

- `docs/research/wayfinder/free-source-capacity-budget.md`
- `docs/research/wayfinder/size-probe-full-fields.md`
- `docs/research/free-source-implementation-roster.json`
- `infra/STORAGE.md`

Spec-Impact: requirement change, draft only.
