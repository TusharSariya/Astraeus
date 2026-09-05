# Sources evidence and API handoff notes

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005. This study does not authorize production behavior or change normative status.

## Capture

`sources-captures.json` contains four complete read-only HTTP 200 responses from `http://localhost:8000/api/experiments/weather/v0`. Capture began 2026-09-05T01:11:19.571692+00:00 and the final request completed 2026-09-05T01:11:35.891777+00:00. Every request retains its URL, requested/completed timestamps and HTTP status. These are independent reads while the store and upstream proxy indexes can change; they are not one evidence revision. No refresh job, provider admission, credential access or backend change was performed.

- `/catalog`: 118 sources, including sources with no field mappings. All are retained in the normalizer.
- `/sources/status`: 118 source status records. Retrieval freshness counts: {'stale': 14, 'unknown': 104}.
- `/timeline`: 361 hourly items from 2026-09-04T01:00:00Z to 2026-09-19T01:00:00Z. There are 0 items with retained-run coverage and 0 with aged-out source declarations.
- `/layers`: 35 layers. Fourteen remain unmatched to a catalogue source because the response has no source ID and their product labels cannot be unambiguously joined by the verified mappings used here. These remain inspectable outside source rows. The layer endpoint includes notices about stale GOES/OVATION products withheld, unmappable space-weather artifacts, radar imagery using one of two recorded layers, and live proxies outside ingest QC, `/point` and `/timeline`.

## Data boundaries

1. The actual catalogue does not include `field_families`; the 19 family options come from `sources[].fields[].family`. The normalizer exposes `familyBasis`, and will prefer `field_families` when supplied. A source's mapped field/storage declaration is not a measurement at Focus. `stored`, `available-not-stored` and `not-published` must retain their returned spelling and meanings; absence of a mapping is unknown, not not-published.
2. No catalogue source in this capture supplies an evidence class. Do not infer it from category, provider, layer group, product name or `evidence_basis`. The latter describes the delivery/ingest path and is not an evidence-class substitute.
3. Source status describes retrieval freshness, independently of layer/timeline run-stale assessments. Null run-stale remains unknown with its reason; no client recomputation. Layer run summaries and timeline coverage are kept as separate raw facts.
4. The first timeline item lists `noaa-gfs` in available products while coverage is empty and its notice says “nothing covers this instant.” The normalized state `product-listed` preserves this discrepancy and does not claim retained-run coverage. Do not collapse available products and coverage into one availability boolean.
5. These endpoints are not coordinate queries. Temporal coverage cannot assert that a source covers the current Focus coordinate, or that a particular mapped field has a non-null point sample. A family filter answers catalogue mapping; present retained-run temporal evidence beside it without upgrading it to field-at-location coverage.
6. Layer exact-frame presence is reported separately in `layerAtFocus`. No interpolation, continuous coverage band, nearest-frame substitution, or gap fill is made by the normalizer. No-times-declared does not mean coverage at every instant.
7. `agedAtFocus` and `agedAtLayers` preserve their different endpoint scope. `agedOut` is a convenience flag indicating either declaration exists; it must not be read as proof of absence at Focus. No aged-out fixture was invented.
8. Failed requests are unavailable and have no capture fallback. If catalogue fails, normalization returns no invented catalogue rows. Endpoint errors and successful sibling endpoints remain separate.

## Verified joins

`sources-data.js` uses exact catalogue source-ID matches (the backend's artifact-product fallback), exact unique catalogue product-name matches, and these explicitly inspected backend mappings:

- `api/weather_api/app.py:134`, `PRODUCT_SOURCE_IDS`: HRDPS, RDPS, REPS, GFS/NOAA, IFS/ECMWF and ICON/DWD.
- `ingest/adapters/noaa_s3.py:340,563`: `Global Forecast System (GFS 0.25 deg)` to `noaa-gfs`.
- `ingest/adapters/awc.py:350,539,579,710`: CYYT METAR/SPECI and TAF product labels to their source IDs.
- `ingest/adapters/eccc_geomet.py:1373,1573,1879,2013,2603,2617`: radar, lightning, CAP, AQHI and GeoMet model adapter product/source pairs.

The capture's `ECCC-HRDPS`, `ECCC-RDPS`, repaired WEonG product names and live WEonG/GOES product names are deliberately not guessed from their IDs. `wms.py` calls the GOES catalogue record the “closest registry record,” which is insufficient to claim the proxied product is identical to its admitted cloud products. These absent source IDs and authoritative product joins belong in the existing API-contract decision.

## Normalization interface

`normalize(bundle, instant)` consumes `{captured_at,base_url,requests:{catalog,status,timeline,layers}}`. Each request is `{request_url,requested_at,completed_at,status,response,error?}`.

It returns `records`, string `families`, `familyBasis`, array `timeline`, nullable `focusItem`, `endpoints`, endpoint-scoped `notices`, `unmatchedLayers`, `unmatchedProducts`, and `capturedAt`.

Each source record retains `source`, nullable `status`, joined `layers`, `fields`, `families`, `coverage`, `availableProducts`, `productMatches`, `evidenceClasses`, `missingMetadata`, `runAssessments`, `layerAtFocus`, and `raw`. Temporal state is one of `unavailable`, `unsampled`, `retained-run-coverage`, `product-listed`, `aged-out`, `no-retained-coverage`, `unknown`. Inspect raw endpoint notices before interpreting discrepancy states.

Verification: JavaScript syntax check; capture parses; one row per all 118 sources; 21 layers join and 14 remain unmatched; failed status request clears all source-status values without affecting catalogue; unavailable catalogue returns zero fabricated rows. No permanent test suite added.
