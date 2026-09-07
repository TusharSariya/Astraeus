# Desktop evidence API contract proposal

## Why

The owner selected a bounded evidence Series read, selection-specific new-data
checks, fuller identity/provenance on existing responses, read-only registered
site and camera metadata, separate imagery availability, and explicit absence
rather than zero placeholders. The current API is chiefly a one-instant
`/point`, `/timeline`, and `/layers` interface; the desktop proposal in PR #239
intentionally adds no new API routes. These missing wire contracts therefore
remain a separate proposal under issues #54 and #55.

This proposal reuses the current response models and selected-time demand
services as its starting seam. It does not revive retained-artifact fallback,
warehouse retention, scheduled source acquisition, or source promotion. A
source remains a bounded selected-time query with its own native time,
provenance, receipt, finite cache, expiry and unavailable semantics.

## Decision traceability

The proposal carries the API inputs from the owner-selected [Sources
resolution](https://github.com/TusharSariya/Astraeus/issues/52#issuecomment-5548442947),
[station and point resolution](https://github.com/TusharSariya/Astraeus/issues/58#issuecomment-5548645284),
[API discussion handoff](https://github.com/TusharSariya/Astraeus/issues/54#issuecomment-5548786349),
[arbitrary-point resolution](https://github.com/TusharSariya/Astraeus/issues/67#issuecomment-5548841040),
and [forecast-run resolution](https://github.com/TusharSariya/Astraeus/issues/68#issuecomment-5548937642).
Those comments select behavior; this change supplies a reviewable proposed
contract and does not change their normative status.

## Authority and scope

### Owner decision, September 7, 2026

In the active implementation conversation, the owner answered "2yes" to the
concrete data-interaction decision: preserve native Series timestamps and gaps;
keep a displayed/paged selection stable with explicit refresh and finite expiry;
and support readable latest/previous runs and temporary two-run comparison
without manufacturing missing values or calculated differences. The question
also delegated routine cursor encoding, request limits and cache sizing to the
implementer using existing tooling and measured bounds. This is explicit
authorization for those behaviors and implementation choices, not blanket
acceptance of every remaining proposed API capability or a verified-status claim.
Camera visibility remains held separately. Do not ask the owner to approve the
same Series, refresh, run-selection or routine engineering choices again.

This is a **requirement change with scoped owner approval** for the isolated
St. John's experiment. It records the owner decisions in #54 and #55 and the
approval above, but does not claim whole-package acceptance, API implementation
or an operational profile. The merged PR #195 is design input only: its
persistent fragment/snapshot mechanism has not become accepted authority here.

The proposed API surface is limited to:

- a bounded, paged evidence Series read and selection-specific change check;
- response identity and full per-reading provenance needed by the desktop;
- read-only registered site, horizon and camera metadata;
- imagery availability distinct from stored sample times; and
- machine-readable, truthful absence rather than omitted or zero-like claims.

Exact route spelling, body shape, cursor encoding, measured limit values,
finite-cache lifetime, error status mapping and bounded cache implementation
are routine implementation choices within the approved interactions above.
They still require mapped verification, but not another owner approval round.
Camera privacy filtering remains an owner decision; any additional behavior
outside those approved interactions retains its existing proposal status.

The proposal excludes verdict/scoring mechanics, band math, phone work,
camera-image delivery, registry writes or admission, new science, source
licensing, provider access, interpolation, persistent comparison workspaces,
and deployment or operational promotion.

## Reuse and ordering

Reuse `EvidenceField`, `Provenance`, `PointResponse`, `Layer`, `TimelineItem`,
and existing `/point`, `/layers`, and `/timeline` semantics before adding a
parallel identity format. Series data is built only from source responses
obtained for the requested native timestamps through the existing demand seams;
it does not turn archived artifacts into live values. Finite request/cache
bounds and explicit expiry are mandatory, while measured numbers are deferred.

After an owner accepts the change, implementation work should first settle the
schema and bounded backing behavior, then add API contract tests, then client
use. PR #239 remains the frontend-only proposal. Issue #173 and the draft
live-query snapshot design remain separate dependencies where an accepted
cross-read consistency mechanism is needed.

Spec-Impact: requirement change; proposal only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
