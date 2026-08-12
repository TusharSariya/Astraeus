---
id: ECL26-SAFETY
title: Eclipse Observation Safety
type: safety-spec
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
  - PRD-SAFE-001
  - SITE-ACCESS-001
  - SITE-ACCESS-002
supersedes: []
---

# Eclipse observation safety

NASA eclipse safety guidance is the authoritative copy source. Product wording
MUST NOT imply that acknowledging a warning makes unsafe equipment acceptable.

## ECL26-SAFE-001 — Require solar protection for the entire event

Every supported candidate is partial. ISO 12312-2-compliant solar viewers are
required for all direct visual observation. The product MUST never emit a
glasses-off state or infer safety from rounded magnitude, weather, darkness,
terrain obstruction, or cloud.

Ordinary sunglasses and improvised filters are unsafe. Users inspect and
discard damaged viewers, supervise children, and receive authoritative indirect
projection guidance if no valid viewer is available.

## ECL26-SAFE-002 — Protect optical equipment correctly

Camera, binocular, and telescope filters mount over the front/objective.
Handheld eclipse viewers do not make unfiltered magnifying optics safe. Product
copy directs users to expert equipment guidance and includes ordinary heat/Sun
protection.

## ECL26-SAFE-003 — Gate destinations independently of viewing utility

`SiteSafetyEvaluation` records official warnings and evidence/thresholds for
wind/gust, lightning/convection, heavy precipitation, driving/walking
visibility, coastal tide/surge/surf/cliff/harbour exposure, temperature, road
condition, walking slope/surface, and accessibility needs. Unsafe conditions
hard reject. Missing critical site-specific evidence blocks `go`.

`site-safety-v1.yaml` owns units, thresholds, missing-data behavior, and rule
version. Viewing score cannot offset a failed safety gate.

## ECL26-SAFE-004 — Require lawful access and stopping

Unknown, stale, private-without-permission, closed, gated, unsafe, or unlawfully
stopped destinations cannot receive a score, go state, deadline, or navigation.
Street View coverage, OSM or Overture type membership, Crown or shoreline
reservation, and school grounds do not authorize a destination. Library and
community-centre grounds require explicit public outdoor or parking use whose
hours cover the observation window. Lookouts navigate to the approved entrance,
not to an unmarked view node. The origin stay option still requires lawful
stopping, non-moving state, obstruction, and environmental safety, but
user-confirmed private permission is not treated as public destination access.

## ECL26-SAFE-005 — Enforce full travel safety

The complete outbound, walking, setup, critical viewing, teardown, and return
itinerary MUST fit availability with configured buffers. Route closure,
prohibited roads, unsafe shoulders, and critical 511 warnings hard reject.
Base routing is labelled traffic-blind unless current traffic evidence exists.

## ECL26-SAFE-006 — Prevent distracted rerouting

While motion indicates driving, destination-changing interaction is suppressed
unless passenger mode is explicitly confirmed. Driver output is minimal/audio
and requires parking before accepting a reroute. Closures and immediate hazards
may trigger a safe-stop instruction, never an interactive chase.

## ECL26-SAFE-007 — Fail safe on missing geometry or advice

Missing, stale, uncertain, or contradictory safety geometry retains the full
partial-eclipse protection state. A terrain block does not make direct solar
viewing safe. Exports and offline snapshots preserve safety copy and timestamps.
