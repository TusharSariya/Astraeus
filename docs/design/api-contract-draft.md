# Evidence API: candidate contract

Discussion draft for [Settle the API contract additions the prototypes proved](https://github.com/TusharSariya/Astraeus/issues/54). The owner selected the scope in [the decision record](api-contract-review.md); the wire details below are **proposed**, not accepted or implemented. Band math remains a deferred dependency. No existing normative status changes.

## Series request and paging

Propose `POST /api/experiments/weather/v0/point/series` as a read-only operation. A structured body avoids encoding several field/source/level/member selections into ambiguous query strings. Existing `GET /point` stays unchanged.

Initial request shape (types, not captured weather data):

```text
{
  latitude: number,
  longitude: number,
  start: UTC datetime,
  end: UTC datetime,
  selectors: [{
    id: request-local unique string,
    source_id: string,
    key: catalogue field key,
    vertical_level?: existing provenance level identifier,
    phase?: existing phase enum,
    member?: provider member identifier | "all",
    statistic?: registered statistic name,
    quantile?: number,
    threshold?: number,
    comparison?: existing comparison enum
  }],
  page_size?: positive integer
}
```

`start` is inclusive and `end` exclusive. Coordinates use the existing evidence-box validation. Source and catalogue key are explicit; the API does not substitute another source. Omitted level/phase means all matching published variants, each separately identified in the response. Ensemble parameters reuse existing validation and refusal rules; a declared selector does not establish a currently available member/statistic capability. There is no client-selected interpolation step.

Continuation request uses the same route with `{cursor: opaque_string}` only. Do not accept changed selectors or coordinates beside a cursor. The cursor binds the original request, revision set and next position; the server validates it rather than trusting decoded client content. Cursor internals are not an API promise.

## Series response

```text
{
  data_mode: existing DataMode,
  operational: false,
  selection: {latitude, longitude, start, end, selectors},
  snapshot: {
    id: opaque string,
    selected_at: UTC datetime,
    expires_at: UTC datetime,
    artifact_revisions: [{source_id, revision_id}]
  },
  series: [{
    series_id: stable within this snapshot,
    identity: {source_id, key, vertical_level, phase, member, statistic},
    availability: {
      status: "samples" | "no_samples" | "unknown",
      reason: string | null
    },
    samples: [{
      selector_id: request-local selector id,
      revision_ids: [immutable artifact revision id],
      evidence: existing EvidenceField
    }]
  }],
  next_cursor: opaque string | null,
  complete: boolean,
  notices: [string]
}
```

Identity must distinguish statistic parameters as well as name where applicable. The echoed selector id connects expanded levels/members back to the requested selector. Actual field units and comparability travel through `EvidenceField`; equal units alone never authorize a shared axis. An empty `revision_ids` list is permitted only for an explicit absence that read no artifact, with a reason. Each sample time is `evidence.provenance.valid_time`, avoiding a second independently authored timestamp. Derived values need input revision identities as well as their output revision; reuse the same provenance extension across point and Series rather than hiding derivation inputs in cursor state.

A logical page contains a bounded number of sample records, ordered deterministically by valid time and a canonical identity order. Series envelopes can repeat across pages; sample identity is stable for de-duplication. A terminal page has `next_cursor: null` and `complete: true`. Request-level selection/availability metadata is present even when no samples exist. Metadata-only series appear once, on the first page; they must not consume an unbounded payload outside the selector limit.

Only actual published sample times become numeric samples. Evaluated absent samples retain existing absence states/reasons. Unqueried or unpublished intervals never become synthetic hourly nulls or implied continuous coverage. Availability here describes this selected source/field/location/window, not the deployment's generic source coverage and not alert clearance.

The snapshot pins an immutable set of artifact revisions, derived-input revisions, registry/derivation versions and the inventory state used to report absence. Fix the freshness assessment clock at `selected_at` as well, retaining original retrieval/run times. Derived calculations must not read newer inputs during continuation. New ingestion affects the next initial read, never later pages of this read. Retain pinned revisions until advertised expiry; do not extend expiry silently on every page. This is a request snapshot, not forecast-vintage history or a persistent comparison workspace.

If a revision becomes unreadable, preserve the selected explicit retryable failure behavior. Missing values inside readable artifacts remain per-field absences. Never silently replace an unreadable artifact with a newer revision.

## Errors and limits

Proposed shared error shape: `{error: {code, message, retryable, restart_required, details}}`. Exact status mapping is reviewable here:

| HTTP | Code | Client behavior |
| --- | --- | --- |
| 422 | `invalid_selection` | Correct coordinates, dates or selectors; no snapshot created |
| 422 | `query_limit_exceeded` | Narrow total selection/window; details name the declared limit |
| 400 | `invalid_cursor` | Do not continue with altered/unrecognized cursor |
| 410 | `snapshot_expired` | Offer a fresh read; discard continuation cursor |
| 503 | `snapshot_unreadable` | Explicit failure; retry within lifetime or restart if indicated |
| 503 | `snapshot_capacity_unavailable` | Retry later; do not evict an unexpired snapshot silently |

Page size limits bound individual responses. Separate selector, sample, byte, duration and concurrent-snapshot budgets bound the total read and retained data. Do not equate pagination with an unlimited query. Publish effective read limits in a small `series_read` capability block on the existing catalogue response. Numeric defaults and snapshot lifetime require a bounded retention/payload test; no measured capacity is claimed by this draft.

## New-data indicator and refresh

Propose a lightweight `evidence_revision` token on the existing catalogue response that changes when the current published evidence selection changes. It is a deployment-wide refresh hint, not an artifact revision or proof that selected fields changed. UI wording must say new evidence is available, without claiming the current selection changed. A failed or unattempted check is unknown, not checked-and-unchanged. A client can check it through its existing refresh cycle; no push transport or polling interval is selected.

The frontend keeps displaying its labelled snapshot until explicit refresh. Refresh preserves Focus and selections, starts a new read, and replaces the displayed snapshot as a unit; it never appends new pages to old pages. Expiry offers restart and old results are not labelled current. A selection-specific check would reduce irrelevant notices but requires a separately scoped read contract; that tradeoff remains an owner choice.

## Extend existing responses

| Representation | Proposed additions/corrections |
| --- | --- |
| `Layer` | `source_ids: string[]`, `field_keys: string[]`, plus explicit mapping status/reason. Arrays accommodate bundles; do not infer joins from product names or assign one class to mixed readings |
| `Layer` imagery availability | `imagery_availability: {status, checked_at, times, intervals, reason}`. Published-data `times` keeps its existing meaning. `intervals` must distinguish continuous producer support from producer-declared discrete cadence; unknown intervals do not imply frames. Served raster headers still identify the returned image |
| Station/alert features | Typed feature properties with source/report identity, observation time or forecast validity interval as appropriate, and `readings: EvidenceField[]`. Geometry retains its basis and existing GeoJSON shape. A report-less reference is distinct from an eligible observation |
| TAF | Preserve provider period start/end through ingest and serving; forecast classification, no inferred end from neighboring starts |
| Astronomy/space weather | Per-value evidence identity/provenance appropriate to the existing quantity and method. Explicit absent values/reasons replace failure-mode numeric zero placeholders. No new celestial azimuth or aurora derivation is introduced |
| Existing freshness | Use one authoritative run origin consistently across returned run time and freshness. Missing origin/cadence stays unknown with reason |

Do not publish a generic `available: true` that merges source admission, temporal coverage, coordinate coverage and actual field evidence. Do not treat empty CAP features as a verified all-clear. Exact feature union and machine-readable absence reason definitions need explicit schema work before implementation.

## Registered sites and cameras

Propose read-only `GET /sites` and `GET /cameras` under the same v0 prefix. Each returns `{operational: false, registry_revision, records, notices}` with typed existing audited registry records, not raw configuration files. The routes contain no registry writes or automatic admission.

Sites preserve registered coordinates, elevation/datum and the horizon's true-north reference, angular resolution, elevation samples and terrain-check disclosure. Camera summaries preserve declared geometry, registration/revision and eligibility/absence information needed by the selected view. Return only servable metadata; do not expose private configuration or bypass existing camera/privacy rules. A record does not itself authorize frame use. No camera-image proxy or placement decision is added.

An arbitrary point has no registered horizon; it never borrows a nearby site's. A site id and mismatching coordinate must not silently select the horizon. Exact site identity validation belongs in the schema.

## Existing verdict decisions and remaining scope

Carry the previously selected `/verdicts` and `/verdicts/series`, four-profile response, six states, declared/reachable/evaluated coverage, provenance, overrides and scoring decisions forward from their canonical issue resolutions. Do not redefine the pressure-level `/profile` endpoint or infer client scoring. Whether verdict Series should share the new cursor envelope must be reviewed; the evidence Series decisions do not silently change that earlier contract.

Machine-readable legend stops, a family-finder endpoint, server persistence for Compare/Saved stacks, camera-image delivery, new source admissions and new scientific derivations are not proved necessary by this draft. Structured imagery availability does not resolve numeric band-math inputs. The remaining camera-placement and arbitrary-point Map questions stay visible on the Wayfinder map.

## Proposed verification for the implementation proposal

- Ingest publishes a new revision between pages: continuation returns only pinned revisions; refresh returns the new selection.
- Expired, altered, over-budget and unreadable snapshot cases follow the selected error semantics; storage purge respects live pins.
- Multiple source cadences, levels, phases, members and statistic parameters remain distinct across page boundaries; no sample duplicates or losses, and final completion is explicit.
- Zero remains numeric; explicit absence and unknown/unpublished intervals remain distinguishable; failed evidence cannot become a favorable value.
- Station/reference/model geometry stays distinct; TAF periods and CAP absence never imply unsupported validity or clearance.
- Imagery and point axes differ: the Map uses advertised imagery availability and verifies the returned raster timestamp.
- Registry changes appear through read-only versioned responses; arbitrary coordinates never acquire a registered horizon.
- A bounded payload/retention exercise establishes the proposed numeric limits and snapshot lifetime before those values are frozen.

Documentation verification: source/route inspection and independent audit only; these implementation cases have not run. Spec-Impact: none for this draft; any API implementation requires the accepted specification/contracts and mapped verification through the repository gates.
