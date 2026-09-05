# API additions: evidence review for owner discussion

Prepared for [Settle the API contract additions the prototypes proved](https://github.com/TusharSariya/Astraeus/issues/54). **Discussion draft, not an accepted contract.** The band-math dependency remains open and deferred. This prepares independent decisions without declaring the ticket unblocked or resolved. The phone brief is also deferred; its later review may reveal additional needs.

Classification: no spec impact. Documentation only; no API implementation or normative status transition. The inspected running OpenAPI and root API source agree that no Series, verdict or sites route is exposed. Root source is the user's working tree on `execution/activity-profiles`; this document does not snapshot or commit its unrelated changes.

## Evidence and candidate scope

| Candidate | Evidence | Disposition for discussion |
| --- | --- | --- |
| Bounded point Series read | [Series decision](https://github.com/TusharSariya/Astraeus/issues/50#issuecomment-5548103502), `prototype/series` capture notes: requests span changing store state; seven retained point requests were approximately 32–156 KB each | Owner selected one bounded batch read with per-sample provenance and explicit revision consistency; retain sparse samples and sampled absence, never interpolate server data to fill the chart |
| Verdict reads | [Activity contract](https://github.com/TusharSariya/Astraeus/issues/48#issuecomment-5532460091), [scoring decision](https://github.com/TusharSariya/Astraeus/issues/49#issuecomment-5533313908); no routes in inspected OpenAPI | Carry the already selected `/verdicts` and `/verdicts/series` into the proposal; preserve four profiles, six states, coverage, inputs and overrides; scoring implementation still requires its specification gates |
| Layer/source identity and field vocabulary | [Map decision](https://github.com/TusharSariya/Astraeus/issues/46#issuecomment-5532224119); Layer schema lacks `source_id` and canonical catalogue field mapping | Owner selected explicit source and field joins. Short titles/family display labels alone do not justify an endpoint: the selected Map already derives them. A bundle may contain multiple fields/classes, so a scalar layer class must not mislabel every value |
| Structured provider imagery time extent | Map decision reports artifact time versus imagery time mismatch and discovery through a 422 message | Owner selected delivery-specific time metadata on the existing layer representation, with served raster headers still authoritative for the returned image |
| Run and freshness | `Layer`, `LayerFrame`, `LayerRunSummary` already expose run fields; Series captures preserve contradictory freshness | Reuse existing fields; investigate population/consistency defects instead of inventing another run clock. Null remains unknown with reason |
| Coverage | `TimelineItem.coverage`, tier and coverage notices already exist | Reuse temporal summaries. Their existence does not establish availability for a field at the Focus coordinate or a verified alert all-clear |
| Station evidence | [Layer-led decision](https://github.com/TusharSariya/Astraeus/issues/58#issuecomment-5548645284); existing `/layers/{id}/features` returns GeoJSON | Existing `store.py` feature properties omit full per-reading provenance and station identity; reuse and strengthen this route. Empty captures do not prove a new station endpoint is necessary |
| Machine-readable legend stops | Map displays existing provider PNGs successfully | Not required by the selected design; defer unless a demonstrated consumer requires it |

The station audit distinguishes retained data from code: current `ingest/adapters/awc.py` already includes `TAF_MANIFEST.as_manifest_block()`. A captured rejected TAF artifact is not evidence that this code still lacks the manifest declaration. A stored forecast interval end remains a separate gap.

## Independent Sources, Sky and station audit

The subagent compared the [Sources decision](https://github.com/TusharSariya/Astraeus/issues/52#issuecomment-5548442947), [Sky decision](https://github.com/TusharSariya/Astraeus/issues/51#issuecomment-5548244041) and station decision with current code:

- `models.py:338` already defines full point provenance. Space-weather models at `1316` and `1327`, astronomy provenance at `1384`, and station feature properties do not expose the same evidence identity. Extend the affected representations rather than assigning one class to an entire mixed source.
- `models.py:1393` requires numeric astronomy values and `app.py:1838` returns zero placeholders when unavailable. A nullable or discriminated unavailable shape is a contract correction candidate; zero must remain a real value when measured/computed.
- Checked-in sites/horizons and camera registries exist but no corresponding GET routes are exposed. The owner subsequently selected read-only API exposure of those registries. Neither new horizon estimation nor camera admission is established by this need.
- Celestial azimuth is absent, but the selected Sky prototype deliberately does not draw directional celestial positions. Treat directional placement as conditional scope, not automatically mandatory API work.
- `store.py:2148` uses provenance run time for staleness while the returned run time at `2165` comes from the sample. Reconcile this source of contradictory metadata rather than adding another freshness representation.
- Family filtering is derivable from catalogue field families. `/space-weather` already distinguishes observed and forecast Kp and timestamped Bz/Bt. No extra family or space-weather endpoint is justified.
- Non-atomic Sources and Sky reads corroborate the consistency problem. They did not by themselves establish that batching was the only solution; the owner subsequently selected a bounded paginated Series operation with revision binding.

## First decision: coherent Series reads

Owner-selected direction (explicit “yes” in live review): a bounded Series operation returning the existing evidence-field representation for selected fields/sources at one coordinate over a requested window. Preserve actual source cadence and valid times. Return evaluated absences explicitly, and distinguish unevaluated intervals from missing evidence. Per-sample provenance names the artifact revisions used; the envelope declares whether the batch used a consistent store snapshot. A changing input set must not silently appear to be one coherent comparison.

Alternative: continue bounded client fan-out of `/point`, label that the responses can come from different store states, and expose enough revision identity to let the client detect differences. This avoids a Series route but retains orchestration, repeated payload and consistency costs demonstrated by the prototype.

The owner selected the bounded Series operation over continued client fan-out. Exact route name, query bounds, field identity, sample limits, detailed error shape and snapshot lifetime remain subsequent decisions; no arbitrary values are frozen here.

Owner-selected consistency rule (explicit “yes” in live review): resolve one immutable set of artifact revisions for the request and use it throughout. Later ingestion becomes visible on the next read. Return the set identifier and per-sample revision identity. This is one coherent store selection, not one shared forecast run across different sources. If the selected evidence cannot remain readable, fail explicitly rather than silently substitute a newer revision. Missing fields within a readable selection remain explicit per-field absence, not whole-request failure. This does not commit to retaining historical snapshots or binding every view to a persistent session.

## Explicit exclusions and remaining dependencies

Do not add server persistence for temporary Compare, Saved stacks, theme or shared Focus. Do not rename the pressure-level `/profile` route. Do not infer evidence class from delivery kind, turn sparse samples into continuous evidence, borrow the nearest site's horizon, or manufacture alert clearance from no returned feature.

Band-math numeric raster inputs and renderer conclusions remain deferred and cannot be declared settled by this review. Positive station geometry, TAF intervals and combined raster/station rendering remain unverified. Outdoor red-night validation remains a separate owner task.

Verification: compare issue resolutions and committed prototype evidence against `weather_api/app.py`, `models.py` and running `http://localhost:8000/openapi.json`; independent subagent review of Sources, Sky and station evidence completed. `uv run --project tools/specs python tools/specs/specctl.py validate` passed with 0 errors and 0 warnings.


## Owner decision: cursor pagination

The owner suggested pagination and explicitly selected cursor pagination with a short-lived snapshot. This replaces the earlier unselected proposal to reject requests solely because they exceed one response page.

An opaque cursor binds the original coordinate, field/source selection and window to the fixed artifact-revision set and next position. All pages preserve that selection and revision set; new ingestion does not alter later pages. Responses preserve actual sample times, provenance and explicit absence, with no silent truncation or downsampling. A continuation signals remaining results; completion is explicit.

The server retains the selected revisions briefly. If the snapshot expires, the API explicitly requires a fresh read; it must not silently resume against new revisions. If a pinned revision becomes unreadable before expiry, the previously selected explicit retryable failure still applies. Ordinary field absence stays an explicit gap. Overall request limits still apply independently of page size.

Exact lifetime, page/sample limits, cursor encoding, status codes and retention mechanics remain proposed-contract work, not selected values. This decision authorizes no production implementation or indefinite historical retention.

## Owner decision: refresh while browsing

Owner-selected (explicit “yes” in live review): an in-progress Series comparison continues using its snapshot. New data availability is indicated, but adopting it requires an explicit refresh that starts a new read and replaces the displayed snapshot together. Existing pages must never be silently combined with pages from the new snapshot. Retain field/source choices and Focus during refresh. Snapshot expiry clearly offers restart; it does not present old results as current.


## Owner decision: existing response corrections

Owner-selected package (explicit “yes” in live review): reuse existing routes and extend their representations where the selected views demonstrated missing information. Add authoritative layer/source and canonical field associations; expose station/report identity and full per-reading provenance through the existing feature response; preserve TAF forecast validity intervals and classification; expose evidence identity on astronomy and space-weather values; replace unavailable astronomy zero placeholders with explicit absence; and reconcile existing run/freshness metadata with its authoritative origin.

These are candidate contract changes and implementation corrections, not claims of completed capability. Missing report data is not repaired by a schema change. Exact shapes and verification belong in the proposal. This package does not add duplicate station, family, freshness or space-weather routes, infer a universal evidence class for mixed sources, or enable new scientific derivations.


## Owner decision: registered sites and cameras

Owner-selected (explicit “yes” in live review): expose read-only, versioned site/horizon and camera-registry metadata from the API so the shared Focus and Sky use the deployment's registered definitions. The prototypes currently embed checked-in registry copies. Reuse those registries without new admission, authoring, horizon estimation or directional reconstruction. Camera records retain their declared eligibility and absence reasons; a registry record alone does not make a frame eligible. Arbitrary points never inherit the nearest site's horizon.

The alternative of continuing to ship registry copies with the frontend was not selected. Exact route shapes and revision association remain subsequent contract work. This does not authorize camera-image delivery or resolve the remaining camera-placement design questions.


## Owner decision: imagery availability times

Owner-selected (explicit “yes” in live review): expose structured imagery availability on the existing layer response separately from stored data sample times when the two differ. Preserve the existing published-data time semantics; clients must not discover imagery bounds by parsing error text or assume that a point sample implies an image at that instant. The returned raster's served-time provenance remains authoritative for the image actually drawn. An unknown or unavailable imagery extent stays explicit; never invent frames from an enclosing interval. Exact metadata shape must distinguish discrete times from any provider-declared interval/cadence before implementation.

This addresses the selected Map's captured two-time-axis gap. It does not resolve the deferred numeric band-math inputs or select new rendering/scientific behavior.


Concrete candidate wire shapes and open choices are collected in [API contract draft](api-contract-draft.md). They remain proposed until owner review; the selections above are the authority for drafting scope.


## Owner decisions: native sampling and relevant refresh notices

The owner answered “yes for both” to these two behavior choices:

- Preserve each source's actual timestamps instead of forcing all sources onto hourly rows. Preserve sparse samples and explicitly checked absences. Do not manufacture missing values at another source's timestamps or imply that unqueried intervals were evaluated.
- Show a new-data notice only when data relevant to the current selection changes. A deployment-wide token that changes for unrelated sources is not sufficient. The check compares the fixed snapshot's selection with current relevant evidence without mutating or renewing the snapshot. Refresh remains explicit.

The proposed wire draft now describes a selection-specific check. Its transport, numeric limits and exact error/schema definitions remain reviewable implementation-proposal details. No backend behavior or normative status has changed.
