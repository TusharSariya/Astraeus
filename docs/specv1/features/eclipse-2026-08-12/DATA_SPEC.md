---
id: ECL26-DATA
title: Eclipse Provider and Normalization Contract
type: data-spec
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - EVD-PROV-001
  - SITE-ACCESS-001
  - SITE-ACCESS-002
supersedes: []
---

# Eclipse provider and normalization contract

## ECL26-DATA-001 — Use the declared weather stack

| Evidence | Controlled preview | Dynamic web |
|---|---|---|
| HRDPS | Manually verified snapshot | Required primary |
| RDPS | Optional cross-check | Required fallback/second opinion |
| REPS | Omit unless validated | Optional spread; absence caps grade |
| GOES-East | Timestamped IR/mask | Required for event-day nowcast |
| SWOB/METAR | Timestamped anchor where available | Required ingest; absence explicit |
| Radar | Optional precipitation context | Supporting only |
| RAQDPS/RDAQA | Omitted | Optional transparency evidence |

Each adapter contract declares exact product/field identifiers, discovery
pattern, cycle/cadence, expected grid/projection, native/normalized units,
temporal semantics, completeness manifest, staleness, operational role,
fixture URI/checksum, licence, and schema-change behavior.

## ECL26-DATA-002 — Ingest required HRDPS evidence

Required primary fields include total cloud, column cloud water, sky state,
fog/general visibility, 2 m RH/dewpoint depression/dewpoint/temperature, wind
and gust, precipitation, and pressure-level RH/depression/specific humidity
where published from 1000–300 hPa. Derived layer-saturation evidence MUST NOT be
labelled provider low/mid/high cloud fraction.

RDPS is a deterministic second opinion and MUST NOT synthesize or invent the
HRDPS fog-visibility field. REPS preserves every member; ensemble mean is not a
scenario.

## ECL26-DATA-003 — Use GOES full-disk evidence with QC

Use operational GOES-East full disk with scan times, DQF, projection, platform,
and algorithm version. Prefer cloud mask, top height/pressure/temperature,
phase, optical depth, layers where validated, derived motion winds, and
retained IR/visible channels needed for documented fallbacks.

Reject failed DQF and report coverage/outages. Satellite observes cloud top,
not base; fog versus stratus needs surface evidence. GOES parallax, eastern
Newfoundland footprint, multilayer occlusion, thin cirrus, day/night changes,
and eclipse contamination remain explicit limitations.

## ECL26-DATA-004 — Use observations for their measured quantities

SWOB/METAR supplies timestamped visibility, ceiling/layers where reported,
temperature/dewpoint/RH, wind, precipitation, and weather with corrections and
amendments preserved. Influence is age, distance, elevation, coastal regime,
representativeness, variable error, and QC weighted; recency alone cannot
dominate. Visibility MUST NOT be spatially interpolated as a smooth truth.

Radar confirms precipitation/convection and motion but no echo does not prove
clear sky. RAQDPS/RDAQA and AOD evidence remain secondary; surface PM is not
directly converted to extinction without an accepted humidity/vertical model.

## ECL26-NORM-001 — Normalize without inventing precision

Reproject candidates to native grids. Bilinear interpolation is permitted only
for continuous fields when contributing cells pass QC and share land/water
regime; otherwise use nearest valid same-regime evidence and flag it.
Categorical masks use nearest-neighbor. Correct elevation for temperature/
dewpoint only, never by lapse-rate-adjusting cloud or fog.

Hourly continuous fields may interpolate in time within valid support.
Categorical and accumulation fields obey their interval semantics. REPS
three-hour evidence remains three-hour information even when displayed on a
finer timeline. Satellite retains fixed-grid/DQF identity and evaluates local
and upstream sectors without claiming resampled precision.

## ECL26-FRESH-001 — Enforce freshness policy

Freshness age is evaluated at the recommendation evaluation clock. GOES and
radar use scan end; station evidence uses observation time; deterministic and
ensemble forecasts use initialization time plus completeness of the required
valid-time manifest; RAQDPS uses initialization time. Retrieval time is shown
and may reveal delivery delay, but MUST NOT replace the scientific reference
timestamp.

- GOES ideal ≤12 minutes; stale after 20.
- Radar stale after 15 minutes.
- SWOB/METAR stale after 90 minutes unless a stricter hazard rule applies.
- HRDPS/RDPS initialization stale after 8 hours or incomplete manifest.
- REPS stale after 10 hours.
- RAQDPS stale after 15 hours.

Stale evidence remains labelled and cannot enter the fresh consensus.

## ECL26-DEGR-001 — Degrade explicitly

No HRDPS uses RDPS+REPS with reduced spatial evidence. No REPS labels scenario
spread incomplete. No GOES disables nowcast. No local observation leaves fog/
ceiling unverified. No COD/CTH prohibits quantitative optical claims. Conflicts
remain visible. No critical cloud evidence returns no reliable recommendation.

## ECL26-DATA-005 — Maintain a signed Avalon access catalogue

The eclipse site catalogue is an immutable, signed revision referenced by
`site_catalogue_revision`. Preview uses only a human-approved Avalon subset
(approximately 20–40 sites). Dynamic web may seed additional candidates but
MUST NOT score or navigate them until `SITE-ACCESS-001` approval.

Allowed seed sources, none of which are permission by themselves:

- City of St. John's parks and recreation GIS and named parking;
- Parks Canada national historic sites with published grounds hours;
- provincial park vehicle-access areas;
- OSM `tourism=viewpoint`, `amenity=parking`, picnic sites, and trailheads,
  and Overture Places library/park records, as exploratory seeds;
- Mapillary or KartaView imagery for reviewer QA under their licences.

Forbidden as access evidence or feature extraction: Google Street View
imagery, Street View metadata coverage, and Google Places lat/lng used to
build a substitute catalogue.

Each approved row records `site_class`, entrance coordinates, optional view
node, `max_walk_minutes`, hours/gate evidence, reviewer, review time, expiry,
licence, and source checksum. Schools default to `rejected_school`. Access
review older than the catalogue expiry cannot enter a fresh recommendation.
