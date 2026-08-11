---
id: ECL26-VERIFICATION
title: Eclipse Planner Verification Matrix
type: verification
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - ECL26-PRODUCT
  - ECL26-SCIENCE
  - ECL26-DATA
  - ECL26-SAFETY
  - ECL26-UX
supersedes: []
---

# Eclipse planner verification matrix

Tests are profile-specific. Passing the controlled preview does not mean
`v1_web` or `v1_native` passed. Optional 3-D/volume tests run only when enabled.

| Case | Requirements | Profile | Evidence and pass condition |
|---|---|---|---|
| ECL26-GEO-001-T01 | ECL26-GEO-001 | all | St. John's partial regression: magnitude ≈0.617, obscuration ≈0.531, no C2/C3; contacts within documented ≤5 s cross-ephemeris tolerance and alt/az ≤0.1° |
| ECL26-GEO-002-T01 | ECL26-GEO-002 | web | Ephemeris, EOP, height, limb/radius, root, and display-refraction components remain separately reported |
| ECL26-TIME-001-T01 | ECL26-TIME-001, ECL26-PROD-004 | all | Frames/windows remain within contact, availability, source-validity, access, and itinerary bounds |
| ECL26-CLOUD-001-T01 | ECL26-CLOUD-001 | web | Multilayer, missing-base, broken-edge, subpixel, parallax, and low-Sun fixtures retain uncertainty/ordinal blockage |
| ECL26-CLOUD-002-T01 | ECL26-CLOUD-002 | all | Missing COD emits categorical evidence only; valid COD uses accepted approximation and provenance |
| ECL26-CLOUD-003-T01 | ECL26-CLOUD-003 | web | Stationary-cloud before/during/after eclipse fixtures cannot create false visible/NIR clearing or motion |
| ECL26-SCEN-001-T01 | ECL26-SCEN-001 | web | Members, cycles, models, and nowcasts remain labelled and un-cross-producted; no probability wording |
| ECL26-DATA-001-T01 | ECL26-DATA-001 | web | Required/fallback provider manifests, fields, units, checksums, and partial-run failures normalize deterministically |
| ECL26-DATA-003-T01 | ECL26-DATA-003 | web | GOES DQF, outage, parallax, day/night, and eclipse contamination cases degrade explicitly |
| ECL26-DATA-004-T01 | ECL26-DATA-004 | web | Radar no-echo never proves clear; station amendments deduplicate; recency alone cannot dominate |
| ECL26-NORM-001-T01 | ECL26-NORM-001 | web | Land/water, categorical/continuous, time-period, grid, projection, and elevation cases follow declared semantics |
| ECL26-FRESH-001-T01 | ECL26-FRESH-001, ECL26-DEGR-001 | all | Every stale/missing provider produces the specified grade/fallback/no-recommendation state |
| ECL26-SAFE-001-T01 | ECL26-SAFE-001, ECL26-SAFE-002 | all | No glasses-off path exists; sunglasses/improvised filters fail; no viewer gives indirect guidance; optics require objective filter |
| ECL26-SAFE-003-T01 | ECL26-SAFE-003 | all | Wind, lightning, precipitation, travel/walking fog, warning, tide/surge/surf, and accessibility fixtures exercise independent gates |
| ECL26-SAFE-004-T01 | ECL26-SAFE-004, SITE-ACCESS-001 | all | Unknown/stale/private/closed/gated/no-parking destination never gets score, go, deadline, or navigation |
| ECL26-SAFE-005-T01 | ECL26-SAFE-005, SITE-ROUTE-001 | all | Exact outbound/setup/view/return boundary cases enforce the canonical itinerary |
| ECL26-SAFE-006-T01 | ECL26-SAFE-006 | web/native | Driver interaction cannot accept a destination change; passenger/parked flow can |
| ECL26-PROD-002-T01 | ECL26-PROD-002 | all | Fixed origin returns eligible alternatives or explicit rejection reasons; current location can win |
| ECL26-PROD-002-T02 | ECL26-PROD-002, ECL26-PROD-004 | all | OpenAPI validation proves every returned candidate carries role/rank, decomposed score/evidence, local circumstances, viewing windows, cloud and horizon states, and a complete or explicitly null itinerary |
| ECL26-SCORE-001-T01 | ECL26-SCORE-001 | web | Golden hand calculations cover every mapping, missing rule, gate, clipping, tie, and boundary |
| SITE-CAND-001-T01 | SITE-CAND-001 | web | Downselection meets agreed recall against exhaustive geographic/coastal/access/evidence fixtures |
| SITE-HOR-001-T01 | SITE-HOR-001 | web | Synthetic terrain obstruction rejects; missing canopy/buildings keeps overall horizon unknown; datum mismatch fails |
| SITE-ROUTE-001-T01 | SITE-ROUTE-001 | web | 90-minute/arrival/return boundaries, GPS accuracy, water/off-road origin, closure, and graph fallback behave explicitly |
| ECL26-UX-001-T01 | ECL26-UX-001 | web | Mobile viewport, GPS denial, renderer failure, offline, and fixed-preview entry retain a usable decision flow |
| ECL26-UX-004-T01 | ECL26-UX-004, EVD-REV-001 | web/native | Timeline never mixes revisions and all views preserve site/frame/selection state |
| ECL26-UX-005-T01 | ECL26-UX-005 | all | Every result/export includes source, run/valid/retrieval time, resolution, licence, checksum, masks, and change explanation |
| MAP-OFF-002-T01 | MAP-OFF-002 | native | Interrupted/truncated/hash-mismatched/expired/full-storage packs never activate and prior good revision survives |
| OPS-REL-001-T01 | OPS-REL-001 | web | Golden staging plan, promotion/rollback, backup/object restore, outage, credential expiry, and cost kill switch pass |
| ECL26-REL-001-T01 | ECL26-REL-001 | preview | Snapshot signature, provenance/freshness, static rollback, CDN, offline-open, safety, and no-recommendation rehearse successfully |

## End-to-end evidence

An eligible result is reproducible from source checksums, model runs,
ephemeris/EOP, routing graph, catalogue, contracts, and rule versions. Web and
native open the same revision without renderer-dependent scientific changes.
The system can return stay or no reliable recommendation.
