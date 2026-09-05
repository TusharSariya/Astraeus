# Design: one contract instance and one evidence bundle per access path

## Authority boundary

Accepted governance requirements control status, traceability, conflict handling
and verification. Proposed V1 evidence requirements are target shape only. The
experiment's current OpenSpec files document implemented behavior but cannot be
represented as accepted V1 authority.

The authority matrix therefore uses four states:

- `experiment-verification-candidate`: a registered, schedulable adapter exists;
  bounded isolated verification can proceed, but production conformance cannot
  be claimed.
- `owner-source-contract-required`: an eligible path lacks its exact source
  contract; isolated adapter development may proceed, while production
  registration, scheduling and admission wait.
- `access-or-licence-gate`: access, terms, geography or zero-charge facts must be
  resolved before the same source contract decision.
- `recorded-disposition`: preserve the rejection, deferral, unavailability or
  non-source finding without fabricating live evidence.

## Source contract instance

One instance identifies exactly one producer product plus one access path. It
must record:

1. stable source id, producer, product/version and access URI pattern;
2. authentication mechanism without a credential value, licence/terms evidence,
   and separate source/query/transfer/egress/compute charge findings;
3. all selected upstream fields plus every relevant missing, unsupported or
   deferred field; upstream-to-canonical mapping, native and normalized units,
   levels, geometry/projection/resolution, masks and quality flags;
4. producer run, member, lead, valid, publication and retrieval identity and the
   permitted cadence/window;
5. direct, reprocessed or generated identity with producer, intermediary,
   transformation chain, adapter version and source revision;
6. provider request/rate ceilings and finite metadata-derived request, byte,
   memory, temporary-disk, wall-time and concurrency bounds;
7. empty-result, missing-field, invalid-content, schema-drift, throttle, partial
   run, integrity, store-outage and quota behavior;
8. exact API endpoint and response shape, including source/product/run/valid/
   retrieval identity, units, quality, missingness, data mode and
   `operational: false`;
9. rollback to the last visible immutable revision without field/member thinning,
   product substitution or live-to-fixture fallback.

No `best_match`, vendor alias, newer product version or alternative access path
may substitute for the contracted identity.

## Evidence bundle

The verification record links exact reproducible commands and redacted output:

| Evidence | Required proof |
| --- | --- |
| Fixture | Discovery ordering, decode and normalization for every selected field; malformed, empty, fill-only, wrong-unit and missing-lead cases |
| Live retrieval | UTC retrieval time, upstream route, response status/content type/bytes, producer run/schema, full selected-field inventory and enforced bounds |
| Artifact | Computed completeness/QC, immutable key, SHA-256, byte size, run/revision identity and deterministic reopen/round-trip |
| API readback | Request and response proving the stored artifact's field, provenance, missingness, data mode and `operational: false` without upstream access |
| Failure/provenance | Empty success versus no retrieval, invalid HTTP-200 content, throttle/exhaustion, interrupted publication, integrity mismatch and unavailable/null response |

Evidence completion does not promote a source. Owner promotion is a separate
decision after the required environment has passed.

## Conflict fence

Source contract instances use the owner-selected experiment window and
ten-state ledger as draft inputs while making their unaccepted status explicit.
The owner must ratify those selected drafts as one coherent contract before
production registration, scheduling or admission relies on them. Isolated
experiments may implement and test adapters against the selected drafts; they
may not use the experiment label to bypass production governance.
