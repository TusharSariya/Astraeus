---
id: ECL26-UX
title: Eclipse Planner UX and Visualization
type: ux-spec
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
  - RFC-002
  - ECL26-PRODUCT
  - ECL26-SAFETY
  - SITE-ACCESS-002
supersedes: []
---

# Eclipse planner UX and visualization

## ECL26-UX-001 — Use a decision-first screen hierarchy

Dynamic profiles provide Setup, Plan, Site, Compare, and Monitor screens.
Native additionally provides Downloads. The controlled preview opens directly
to the fixed plan and does not imitate dynamic setup.

- Setup captures location, availability, travel, accessibility, equipment, and
  safety acknowledgement.
- Plan shows stay/go/move, top eligible options, origin, route/isochrone, and
  freshness.
- Site shows geometry, itinerary, cloud evidence, ray proxy, horizon, access,
  safety, route, and fallback.
- Compare exposes component evidence and model/run sensitivity.
- Monitor presents a minimal safe action, cutoff, route hazard, trend, and next
  refresh without a moving-driver animated weather interface.

## ECL26-UX-002 — Render the minimum operational layers by default

Default layers are ranked eligible sites, selected route/isochrones, Sun track,
calculated magnitude/obscuration, supported quantitative or categorical cloud
evidence, scenario/source disagreement, and timestamp badges.

Optional layers include deterministic models, ensemble spread, GOES, radar,
surface observations, terrain/obstruction, access/parking, 511 evidence, and
explanatory 3-D. Daytime eclipse views keep light pollution off by default.

## ECL26-UX-003 — Make scores decomposable

Cards show planning score, components, evidence quality, scenario spread,
source disagreement, primary risk, and fallback. No card labels score as
probability. An exploratory access-unknown site is clearly badged, has no
planning score or go/navigation affordance, and is off by default on the
controlled preview. Lookout cards navigate to the entrance and state any walk
to the view node.

## ECL26-UX-004 — Keep time, evidence, and revision synchronized

Scrubbing updates every time-sensitive layer, Sun direction, card, route
deadline, and ray profile within one revision. Observation markers are not
connected as though forecasts. Run comparisons are explicitly separate.

## ECL26-UX-005 — Expose provenance and changes

Every result has a compact freshness strip and an expandable source view with
product/field, run/scan/valid/retrieval times, resolution, interpolation,
licence, checksum, masks, missingness, and fallback. Refreshes display a human-
readable diff.

## ECL26-UX-006 — Preserve mobile, offline, and accessibility fallbacks

GPS denial, approximate/stale position, renderer failure, unavailable sensors,
offline state, and permission denial retain manual/list/timeline functionality.
Accessibility uses known yes/no/unknown, never optimistic defaults. Downloads
show size, revision, freshness, progress, storage, and corrupt/partial states.

## ECL26-UX-007 — Make safety unavoidable but useful

Solar protection appears during setup, site details, monitor mode, navigation,
and export. A user without a compliant viewer receives indirect-viewing guidance
and no direct-view instruction. Exports embed generation/freshness timestamps so
a screenshot cannot look live indefinitely.
