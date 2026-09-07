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

## Authority and scope

This is a **proposed requirement change** for the isolated St. John's
experiment. It records the owner decisions in #54 and #55, but does not claim
that the owner accepted a normative contract, that an API is implemented, or
that any profile is operational. The merged PR #195 is design input only: its
persistent fragment/snapshot mechanism has not become accepted authority here.

The proposed API surface is limited to:

- a bounded, paged evidence Series read and selection-specific change check;
- response identity and full per-reading provenance needed by the desktop;
- read-only registered site, horizon and camera metadata;
- imagery availability distinct from stored sample times; and
- machine-readable, truthful absence rather than omitted or zero-like claims.

Exact route spelling, body shape, cursor encoding, limit values, finite-cache
lifetime, error status mapping, snapshot backing, camera privacy filtering and
version representation remain proposed choices. They need owner acceptance and
mapped implementation verification before code may depend on them.

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
