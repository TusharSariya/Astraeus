---
id: ECL26-SCIENCE
title: Eclipse Geometry and Atmospheric Evaluation
type: science-spec
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - ECL26-DATA
  - EVD-REV-001
supersedes: []
---

# Eclipse geometry and atmospheric evaluation

## ECL26-GEO-001 — Calculate local circumstances per candidate

Use WGS84 geodetic latitude/longitude and ellipsoid height, UTC→TT/TDB and UT1
with pinned leap seconds and IERS EOP, Skyfield with pinned DE440s, and frozen
solar/lunar radii of 695700 km and 1737.4 km. Compute apparent topocentric Sun
and Moon directions/distances separately at every candidate.

Let `d` be angular center separation. Root-find C1/C4 from
`d - (r_sun + r_moon)` and C2/C3 from `d - abs(r_moon - r_sun)` only where
central eclipse is possible. Find maximum by minimizing `d`. Calculate
magnitude by the frozen angular-diameter convention and obscuration by exact
circle-overlap area.

Geometric Sun altitude/azimuth is independent of optional display refraction.
Refraction MUST NOT affect contacts. Every supported Avalon site has
`totality_safe_interval = null`.

## ECL26-GEO-002 — Report geometry uncertainty honestly

Output decomposes ephemeris/version, predicted/final EOP status, observer
horizontal/height accuracy, radius convention, smooth/named lunar-limb model,
root tolerance, and display refraction. Values are modelled local circumstances,
not exact physical contacts.

## ECL26-TIME-001 — Evaluate the event-specific interval

Evaluate five-minute frames over `[C1 - 60 min, C4 + 60 min]`. Rank primarily
over local maximum ±30 minutes and emphasize ±10 minutes. Retain and display
the full C1–C4 interval.

## ECL26-CLOUD-001 — Model a line-of-sight proxy, not full cloud truth

For observer position, geometric Sun direction, and plausible cloud layer/base/
top envelopes, intersect a curved atmospheric ray and report inferred distance,
ray altitude, layer evidence, contribution, source, and uncertainty. GOES top
height is not a cloud base or precise intersection. Missing base/thickness,
multilayer occlusion, parallax, coastal footprint, and subpixel edges propagate
to ordinal blockage or wider spread.

## ECL26-CLOUD-002 — Restrict quantitative optical claims

With valid, QC-passing cloud optical depth, the model MAY compute the versioned
approximation `1 - exp(-COD / mu)` using capped path factor `mu`, while clearly
labelling it approximate. Without valid COD, output only
`likely_clear`, `thin_or_broken`, `likely_blocked`, or `unknown` from the
accepted rule table. It MUST NOT fabricate numeric transmission or opacity.

## ECL26-CLOUD-003 — Handle eclipse-contaminated satellite evidence

Generate a geometry-derived eclipse illumination mask. During affected scans,
disable or downweight solar-reflectance retrievals and visible/NIR optical flow
unless product-specific validation proves them usable. Prefer IR, surface
observations, and NWP; DQF alone is insufficient.

## ECL26-SCEN-001 — Keep scenario families explicit

REPS members, deterministic cycles, fallback models, and perturbed nowcasts are
separate correlated families. Do not cross-product or count them as independent.
Return family-labelled member fractions, quantiles/spread, run disagreement,
rank frequency, and evidence quality. None is success probability.

## ECL26-SCORE-001 — Use versioned explainable scoring

`solar-eclipse-v1.yaml` owns transformations, ordinal mappings, weights,
clipping, hard/soft thresholds, missing-data rules, evidence caps, and ties.
The score combines direct-sun/cloud evidence, visibility, secondary
transparency, precipitation-free utility, and robust scenario/time aggregation
only after access, route, geometry, and environmental-safety hard gates pass.

Rank by robust lower-tail utility first, median second, travel feasibility
third. Opaque/likely-blocked cloud hard-limits recommendation utility. Fog and
horizontal visibility primarily affect travel/site safety and evidence quality;
they enter optical utility only through an accepted validated relation.

## ECL26-EVID-001 — Define minimum cloud evidence

- `quantitative`: time/ray-matched valid COD/CTH or a validated model field for
  the declared utility;
- `qualitative`: time-matched IR/cloud mask plus a current deterministic
  forecast, supporting categorical guidance only;
- `insufficient`: stale, failed-QC, outside coverage, time-unmatched, or below
  the accepted independent-source minimum.

All candidates with insufficient critical cloud evidence produce
`no_reliable_recommendation`.
