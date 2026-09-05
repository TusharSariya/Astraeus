# Series data capture for Wayfinder #50

Classification: experiment. This is a bounded local API audit and captured evidence for a throwaway design, not a production contract or a conformance claim. Spec-Refs: GOV-SPEC-001, GOV-SPEC-005. No normative status changed.

`series-captures.json` stores unmodified point and probe JSON responses inside request envelopes; timeline and catalog are bare response objects. `captured_at` is the capture wall clock; `timeline` and `catalog` were fetched shortly before the points. The deployment/store changed during these requests, so this is not an atomic evidence revision. All responses state `operational: false` where that field exists.

## Requests and shape

Base: `http://localhost:8000`. Read-only GETs:

- `/openapi.json`: no Series endpoint advertised.
- `/api/experiments/weather/v0/catalog`: source categories and field families; catalogue presence does not prove local data availability.
- `/api/experiments/weather/v0/timeline`: 361 hourly instants, September 4 through September 19 UTC. First planning item is September 6 at 01:00Z; last core item is 00:00Z.
- `/api/experiments/weather/v0/point?latitude=47.5615&longitude=-52.7126&valid_time=...`: seven requests at September 4 00/01/02Z, September 5 00Z, September 6 00/01Z, September 7 00Z. Exact encoded URLs are in each envelope.
- Point probes add `member=all` or `statistic=ensemble_mean`, with and without `product=noaa-gefs`.

Top-level capture keys: `captured_at`, `base_url`, `focus`, `timeline`, `catalog`, `points`, `ensemble_probes`. Each point/probe request envelope has `request_url`, `status`, `response_bytes`, `response`. The response retains `fields[]` with `key`, `family`, `value`, `absence_state`, `blocked`, and complete `provenance`. Units are `provenance.normalized_units`. Some keys are null: do not invent a field identity for them.

## Findings that constrain the prototype

- Real numeric evidence in this capture is GFS. September 4 temperature at 00Z is 9.850006103515625 degrees C and at 01Z is 9.271392822265625 degrees C. Other actual fields include wind, cloud, humidity, pressure, visibility and column water. Same-family quantities can have different units and physical meanings; family membership alone does not authorize sharing a value axis.
- The retained 00Z, 01Z and 02Z responses have numeric fields stamped with their respective requested instants in `provenance.valid_time`. Many 02Z values equal 01Z values, but that does not establish duplicate provider times. Render all three captured instants. Earlier audit commentary inferred duplicate provenance from equal values; direct inspection of the final saved response disproves that inference. The raw responses have not been changed.
- Later sampled instants, including both sides of the captured core/planning transition, return null fields and an unavailable selection. These are sampled missing instants, not proof every intervening instant is missing. Unqueried spans must remain explicitly unsampled.
- AWC TAF appears as null fields with a notice that its artifact was skipped because the source declares no `evidence_classes`. No numeric observation against forecast comparison is available in this capture. Do not substitute example observations or turn null into zero.
- GFS `freshness.status` is `stale`. Its `run_time` is September 2 at 18Z, yet `run_stale` is null with a reason claiming the adapter declared no run time. Preserve the discrepancy: retrieval freshness is stale, run-stale assessment is unknown. Do not independently override either server field.
- Both unscoped ensemble probes return ordinary deterministic fields and no member-valued or ensemble-valued numeric evidence. Their notices do not explain absent ensemble results. Using the catalogued source ID `noaa-gefs` as the product returns HTTP 422 `unknown product: noaa-gefs`; source IDs and accepted product selectors cannot be assumed identical.
- Consequently real raw-member plumes, provider reductions beside members, and observation overlays cannot be validated here. Reserve separate visual lanes and show a specific unavailable explanation; never calculate a replacement ensemble from unrelated sources.
- The captured timeline lists GFS at 00/01Z while its coverage arrays are empty and say nothing covers the instant. This disagrees with numeric point evidence. Show endpoint-specific facts rather than inferring availability solely from timeline coverage.
- Initial probes returned 112 fields; retained captures returned 16 or 40 at available samples and 13 at unavailable samples. Sizes ranged roughly 32–156 KB for the seven retained point responses. Batch rendering is feasible for this small experiment, but a production full-window query needs a reviewed Series contract or explicit bounded batching and revision semantics.

## Prototype server

`serve.py` forwards `/api/` GET paths unchanged to `WEATHER_API` (default localhost:8000), including query strings, HTTP error JSON and `x-weather-*` headers. It does not assemble or transform series. Captured playback is reproducible even when the live store changes; it must be labelled captured evidence, never live.

Verification: read-only HTTP inspection and JSON parsing of every saved response; no backend changes, refresh jobs, provider fetches or secrets access.
