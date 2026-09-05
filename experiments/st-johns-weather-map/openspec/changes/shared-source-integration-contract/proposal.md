# Shared source integration contract and verification gate

## Why

The free-source roster routes 288 registry and research rows, but neither that
planning inventory nor a successful upstream request authorizes production
behavior. The accepted V1 corpus currently supplies governance only. The
behavior-bearing evidence RFCs and executable contracts remain proposed, while
the experiment's current OpenSpec baseline has no formal normative status.

There is also a concrete conflict to resolve: the current evidence-window
OpenSpec requires `now-3h .. now+24h`, while runtime code follows the unarchived
storage proposal's `now-24h .. now+14d`. The source-admissions proposal likewise
contains registry states and provenance behavior that differ from the current
OpenSpec baseline. GOV-SPEC-005 forbids selecting either side silently.

## What this draft proposes after owner acceptance

- Require one reviewable contract instance for each producer product and actual
  access path before its production adapter or scheduler is enabled.
- Make the contract enumerate every selected upstream field and disposition,
  canonical mapping, native units and geometry, masks, run/member/lead identity,
  provenance, cadence, provider limits, finite operation bounds, licence and
  charge surfaces, API readback, failure behavior and rollback.
- Require the same five evidence classes for every integration: representative
  fixture, bounded live retrieval, immutable artifact validation, Astraeus API
  readback, and absence/failure/provenance tests.
- Preserve `operational: false` and separate evidence completion from owner
  promotion.

This proposal deliberately does not accept every roster row. A source-specific
contract instance remains small enough to review on its own and may be accepted,
revised or rejected independently.

## Owner decisions required

1. Ratify the already selected experiment window, `24h back / 14d forward`, in
   one coherent contract that supersedes the stale `3h back / 24h forward`
   baseline before production ingestion relies on it.
2. Accept or revise this shared contract and verification gate as an
   experiment contract, promote equivalent requirements into V1, or revise the
   boundary.
3. Ratify the already selected ten-state source-admissions ledger and richer
   provenance surface as the coherent replacement for the stale registry
   baseline before production admission depends on them.

Only `@TusharSariya` may authorize normative status. Until then, source work is
limited to isolated adapter development, tests and evidence gathering; no
adapter is promoted or enabled as production behavior by this change.

## Evidence

- `docs/research/source-contract-authority-matrix.md`
- `docs/research/source-contract-authority-matrix.json`
- `docs/research/free-source-implementation-roster.json`

Spec-Impact: requirement change, draft only.
