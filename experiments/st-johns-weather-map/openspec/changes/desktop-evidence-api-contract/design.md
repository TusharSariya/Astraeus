# Design: bounded desktop evidence reads without a data warehouse

## Existing seam and proposed envelope

`GET /point` stays the single-instant read. The proposed Series operation uses
explicit Focus coordinates, a UTC half-open window, and catalogue-backed source
and field selectors. It returns one row for each actual provider sample or
explicitly checked native absence. The response reuses `EvidenceField` and its
per-reading `Provenance`, so a second unit, valid-time, quality, evidence-class,
source, report/station or receipt representation is not invented.

A request is bounded in selectors, window, samples, bytes, duration and cache
residency. The proposed initial read is `POST /point/series` with
`{latitude, longitude, start, end, selectors, page_size?}`. `start` is
inclusive and `end` exclusive UTC. The proposed continuation is the same route
with `{cursor}` only; it SHALL reject selectors, coordinates, dates, or page
parameters beside a cursor. The response carries `{selection, snapshot,
series, next_cursor, complete, notices}`. `snapshot` has opaque `id`, fixed
`selected_at`, fixed `expires_at`, selection-bound `change_token`, and the
actual source/run/revision identities consulted. Each Series row has the
request-local selector id, complete source/field/run identity, availability,
and native `EvidenceField` samples.

Cursor pagination is selected behavior: the opaque cursor binds the canonical
selection, finite short-lived nonrenewing snapshot, and next position. A
continuation never changes its fixed selection/revisions; expiry returns the
proposed `snapshot_expired` restart-required error. Proposed errors are
`invalid_selection`, `query_limit_exceeded`, `invalid_cursor`,
`snapshot_expired`, `snapshot_unreadable`, and
`snapshot_capacity_unavailable`, each with `{code, message, retryable,
restart_required, details}`. Exact HTTP mapping, encoding and measured numeric
limits remain proposed. The finite backing may be a selection cache but SHALL
not be a durable warehouse or retained-artifact fallback.

## Selected evidence semantics

Each source preserves actual timestamps and sparse publication. A row at a
native timestamp can carry a numeric value or an explicit absence with reason.
The API does not create hourly rows, cross-product one source against another
source's timestamps, interpolate, substitute another source, or turn unreadable
or unqueried intervals into empty coverage. A complete checked selection with
no samples is distinct from an unknown/unreadable selection.

The proposed read-only `POST /point/series/changes` accepts `{change_token}`
and returns `{snapshot_id, checked_at, state, changed_selector_ids, reason}`.
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

## Run selection

The proposed Series inventory and read contract implements the eight selected
run behaviors only when a delivery path can serve them. Latest available is
automatic but may segment a valid-time selection across actual runs, with every
segment disclosed. Previous names one retained run and filters before frame
matching; missing frames stay missing. A run selection is scoped to its
source/run family across Map layers and Series, never to unrelated streams.
Pinned run identity lives beside Focus in the URL. Removed selections remain
visible as unavailable with a Use Latest available action. Temporary Series
Compare may overlay two retained/readable runs of one source with their native
samples, gaps and provenance; it changes neither Map nor Activity and is not
saved. Activity keeps its existing server-side evaluation policy. Ordinary
new-read inventory is latest plus previous; only an existing unexpired finite
selection may retain a displaced revision until its fixed expiry, within the
existing quota. No continuation renews that exception or makes a displaced run
newly selectable.

## Unresolved owner decisions

This proposal deliberately leaves the following for owner acceptance or a later
schema decision: exact HTTP mapping and cursor encoding; measured page/cache
limits and finite cache lifetime; whether any cross-read consistency needs #173
fencing; registered-camera privacy filtering; exact imagery interval encoding;
and any verdict Series relationship. No claim in this document resolves those
questions.
