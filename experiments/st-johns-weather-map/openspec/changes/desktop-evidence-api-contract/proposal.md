# Desktop evidence API contract proposal

## Why

The owner selected a bounded evidence Series read, selection-specific new-data
checks, fuller identity/provenance on existing responses, read-only registered
site and camera metadata, separate imagery availability, and explicit absence
rather than zero placeholders. The current API is chiefly a one-instant
`/point`, `/timeline`, and `/layers` interface; the desktop proposal in PR #239
intentionally adds no new API routes. These missing wire contracts therefore
remain a separate contract under issues #54 and #55.

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
Those comments select behavior; the owner authorization below accepts this
implementation contract carrying those selections.

## Authority and scope

Accepted for implementation under the single [owner authorization in #239](https://github.com/TusharSariya/Astraeus/blob/main/experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/acceptance.md).
The owner authorized formalizing all recorded selected app behaviors, including
native Series, cursor continuation, fixed expiry, explicit refresh, supported
run selection, registry metadata, provenance and imagery availability. This
acceptance claims neither completed routes nor verified/operational status.
The September 7 desktop-first direction supersedes older persistence dependencies.

The accepted API surface is limited to:

- a bounded, paged evidence Series read and selection-specific change check;
- response identity and full per-reading provenance needed by the desktop;
- read-only registered site, horizon and camera metadata;
- imagery availability distinct from stored sample times; and
- machine-readable, truthful absence rather than omitted or zero-like claims.

Exact route spelling, body shape, cursor encoding, measured limit values,
finite-cache lifetime, error status mapping and bounded cache implementation
are routine implementation choices within the approved interactions above.
They still require mapped verification, but not another owner approval round.
Serve only public registered metadata using an explicit response allowlist;
private configuration and camera-image placement/delivery remain excluded.

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

Implementation work first defines the
schema and bounded backing behavior, then adds API contract tests, then client
use. PR #239 owns the frontend contract. Neither #173 nor the historical persistent
fragment/snapshot design is a prerequisite. Use a bounded selection response
cache over existing demand queries; introduce no general snapshot framework
or new database without a demonstrated requirement.

Spec-Impact: requirement change; owner-authorized acceptance.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
