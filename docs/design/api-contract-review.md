# API additions: evidence review for owner discussion

Prepared for [Settle the API contract additions the prototypes proved](https://github.com/TusharSariya/Astraeus/issues/54). **Discussion draft, not an accepted contract.** The band-math dependency remains open and deferred. This prepares independent decisions without declaring the ticket unblocked or resolved. The phone brief is also deferred; its later review may reveal additional needs.

Classification: no spec impact. Documentation only; no API implementation or normative status transition. The inspected running OpenAPI and root API source agree that no Series, verdict or sites route is exposed. Root source is the user's working tree on `execution/activity-profiles`; this document does not snapshot or commit its unrelated changes.

## Evidence and candidate scope

| Candidate | Evidence | Disposition for discussion |
| --- | --- | --- |
| Bounded point Series read | [Series decision](https://github.com/TusharSariya/Astraeus/issues/50#issuecomment-5548103502), `prototype/series` capture notes: requests span changing store state; seven retained point requests were approximately 32–156 KB each | Owner selected one bounded batch read with per-sample provenance and explicit revision consistency; retain sparse samples and sampled absence, never interpolate server data to fill the chart |
| Verdict reads | [Activity contract](https://github.com/TusharSariya/Astraeus/issues/48#issuecomment-5532460091), [scoring decision](https://github.com/TusharSariya/Astraeus/issues/49#issuecomment-5533313908); no routes in inspected OpenAPI | Carry the already selected `/verdicts` and `/verdicts/series` into the proposal; preserve four profiles, six states, coverage, inputs and overrides; scoring implementation still requires its specification gates |
| Layer/source identity and field vocabulary | [Map decision](https://github.com/TusharSariya/Astraeus/issues/46#issuecomment-5532224119); Layer schema lacks `source_id` and canonical catalogue field mapping | Explicit source and field joins are candidates. Short titles/family display labels alone do not justify an endpoint: the selected Map already derives them. A bundle may contain multiple fields/classes, so a scalar layer class must not mislabel every value |
| Structured provider imagery time extent | Map decision reports artifact time versus imagery time mismatch and discovery through a 422 message | Candidate delivery-specific time metadata on the existing layer representation, with served raster headers still authoritative for the returned image |
| Run and freshness | `Layer`, `LayerFrame`, `LayerRunSummary` already expose run fields; Series captures preserve contradictory freshness | Reuse existing fields; investigate population/consistency defects instead of inventing another run clock. Null remains unknown with reason |
| Coverage | `TimelineItem.coverage`, tier and coverage notices already exist | Reuse temporal summaries. Their existence does not establish availability for a field at the Focus coordinate or a verified alert all-clear |
| Station evidence | [Layer-led decision](https://github.com/TusharSariya/Astraeus/issues/58#issuecomment-5548645284); existing `/layers/{id}/features` returns GeoJSON | Existing `store.py` feature properties omit full per-reading provenance and station identity; reuse and strengthen this route. Empty captures do not prove a new station endpoint is necessary |
| Machine-readable legend stops | Map displays existing provider PNGs successfully | Not required by the selected design; defer unless a demonstrated consumer requires it |

The station audit distinguishes retained data from code: current `ingest/adapters/awc.py` already includes `TAF_MANIFEST.as_manifest_block()`. A captured rejected TAF artifact is not evidence that this code still lacks the manifest declaration. A stored forecast interval end remains a separate gap.

## Independent Sources, Sky and station audit

The subagent compared the [Sources decision](https://github.com/TusharSariya/Astraeus/issues/52#issuecomment-5548442947), [Sky decision](https://github.com/TusharSariya/Astraeus/issues/51#issuecomment-5548244041) and station decision with current code:

- `models.py:338` already defines full point provenance. Space-weather models at `1316` and `1327`, astronomy provenance at `1384`, and station feature properties do not expose the same evidence identity. Extend the affected representations rather than assigning one class to an entire mixed source.
- `models.py:1393` requires numeric astronomy values and `app.py:1838` returns zero placeholders when unavailable. A nullable or discriminated unavailable shape is a contract correction candidate; zero must remain a real value when measured/computed.
- Checked-in sites/horizons and camera registries exist but no corresponding GET routes are exposed. Decide whether embedded versioned registries suffice before adding routes. Neither new horizon estimation nor camera admission is established by this need.
- Celestial azimuth is absent, but the selected Sky prototype deliberately does not draw directional celestial positions. Treat directional placement as conditional scope, not automatically mandatory API work.
- `store.py:2148` uses provenance run time for staleness while the returned run time at `2165` comes from the sample. Reconcile this source of contradictory metadata rather than adding another freshness representation.
- Family filtering is derivable from catalogue field families. `/space-weather` already distinguishes observed and forecast Kp and timestamped Bz/Bt. No extra family or space-weather endpoint is justified.
- Non-atomic Sources and Sky reads corroborate the consistency problem. They do not establish that batching is the only solution; revision binding remains an alternative to consider.

## First decision: coherent Series reads

Owner-selected direction (explicit “yes” in live review): a bounded Series operation returning the existing evidence-field representation for selected fields/sources at one coordinate over a requested window. Preserve actual source cadence and valid times. Return evaluated absences explicitly, and distinguish unevaluated intervals from missing evidence. Per-sample provenance names the artifact revisions used; the envelope declares whether the batch used a consistent store snapshot. A changing input set must not silently appear to be one coherent comparison.

Alternative: continue bounded client fan-out of `/point`, label that the responses can come from different store states, and expose enough revision identity to let the client detect differences. This avoids a Series route but retains orchestration, repeated payload and consistency costs demonstrated by the prototype.

The owner selected the bounded Series operation over continued client fan-out. Exact route name, query bounds, field identity, sample limits, pagination/error behavior and snapshot lifetime remain subsequent decisions; no arbitrary values are frozen here.

Owner-selected consistency rule (explicit “yes” in live review): resolve one immutable set of artifact revisions for the request and use it throughout. Later ingestion becomes visible on the next read. Return the set identifier and per-sample revision identity. This is one coherent store selection, not one shared forecast run across different sources. If the selected evidence cannot remain readable, fail explicitly rather than silently substitute a newer revision. Missing fields within a readable selection remain explicit per-field absence, not whole-request failure. This does not commit to retaining historical snapshots or binding every view to a persistent session.

## Explicit exclusions and remaining dependencies

Do not add server persistence for temporary Compare, Saved stacks, theme or shared Focus. Do not rename the pressure-level `/profile` route. Do not infer evidence class from delivery kind, turn sparse samples into continuous evidence, borrow the nearest site's horizon, or manufacture alert clearance from no returned feature.

Band-math numeric raster inputs and renderer conclusions remain deferred and cannot be declared settled by this review. Positive station geometry, TAF intervals and combined raster/station rendering remain unverified. Outdoor red-night validation remains a separate owner task.

Verification: compare issue resolutions and committed prototype evidence against `weather_api/app.py`, `models.py` and running `http://localhost:8000/openapi.json`; independent subagent review of Sources, Sky and station evidence completed. `uv run --project tools/specs python tools/specs/specctl.py validate` passed with 0 errors and 0 warnings.


## Next decision: bounded response behavior

Proposed, not yet selected: a successful Series read returns the complete result for its accepted field/source/window selection, including explicit absence and actual sample times. If the selection exceeds the server's declared limits, reject it with a structured error naming the exceeded limit so the client can narrow the request. Do not silently truncate, downsample, or paginate into a different revision set. Exact limits and status codes remain contract drafting/validation work; no arbitrary numeric cap is selected here. Pagination could be added later with explicit snapshot retention if a demonstrated consumer requires it.
