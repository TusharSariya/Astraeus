# Design: bounded desktop evidence reads without a data warehouse

## Existing seam and proposed envelope

`GET /point` stays the single-instant read. The proposed Series operation uses
explicit Focus coordinates, a UTC half-open window, and catalogue-backed source
and field selectors. It returns one row for each actual provider sample or
explicitly checked native absence. The response reuses `EvidenceField` and its
per-reading `Provenance`, so a second unit, valid-time, quality, evidence-class,
source, report/station or receipt representation is not invented.

A request is bounded in selectors, window, samples, bytes, duration and cache
residency. A cursor, if chosen, binds the canonical selection and finite
selection cache identity. It cannot carry altered selectors. Expiry requires a
new initial request. The exact values, cursor representation and whether a
short-lived selection cache is sufficient for all selected paging behavior are
unresolved design choices; this proposal does not pick durable artifact
snapshots or warehouse storage.

## Selected evidence semantics

Each source preserves actual timestamps and sparse publication. A row at a
native timestamp can carry a numeric value or an explicit absence with reason.
The API does not create hourly rows, cross-product one source against another
source's timestamps, interpolate, substitute another source, or turn unreadable
or unqueried intervals into empty coverage. A complete checked selection with
no samples is distinct from an unknown/unreadable selection.

A change check compares only the displayed selection's current relevant
identity, availability and interpretation versions against its original
baseline. Unrelated source updates and elapsed clock time do not count as a
change. It never mutates the shown result or renews the cache. Failure is
`unknown`; expiry is restart-required. Refresh is explicit and preserves Focus
and selectors while replacing the response as one new read.

## Existing response extensions

Existing layer records need explicit source-to-field relationships and an
imagery-availability object. Published sample `times` retain their current
meaning. Imagery availability declares what imagery times or intervals the
provider published, the check time and a reason when unknown; it never asserts
that a raster will be served. A returned raster continues to disclose its actual
served time and provenance.

Read-only site/horizon/camera responses expose registered, versioned records.
They do not write registries, expose private configuration, proxy camera imagery
or lend a nearby horizon to an arbitrary coordinate. Station/report identity
and feature geometry retain their existing basis. Missing astronomy, alert,
profile, camera or observation evidence is explicit and does not become a
numeric zero or all-clear.

## Unresolved owner decisions

This proposal deliberately leaves the following for owner acceptance or a later
schema decision: endpoint methods and path names; pagination and cache numeric
limits; stable cursor/error representation; whether any cross-read consistency
needs #173 fencing; site-coordinate conflict responses; which registered camera
metadata is safe to serve; exact imagery interval encoding; and any verdict
Series relationship. No claim in this document resolves those questions.
