---
id: ECL26-PRODUCT
title: Eclipse Planner Product Behavior
type: feature
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
  - PRD-001
  - ECL26-SCIENCE
  - ECL26-SAFETY
  - SITE-ACCESS-002
supersedes: []
---

# Eclipse planner product behavior

## ECL26-PROD-001 — Accept a constrained observation request

Dynamic profiles accept the `solar-eclipse` module ID/version, `sun` subject,
August 12 occurrence, objective, foreground GPS or manual origin, origin
accuracy/time, availability, maximum travel, filtered observation mode,
duration/continuity, accessibility needs, walking tolerance, route avoids, and
setup/return constraints. The controlled preview uses its fixed origin and
collects no GPS.

## ECL26-PROD-002 — Return ranked contiguous opportunities

The result MUST contain the best eligible site/window, current-origin stay
option, up to two additional eligible destinations, and a geographically
distinct fallback where available. If fewer exist, return explicit rejection
reasons rather than adding unsafe or unverified sites.

Each result includes:

- site name, `site_class`, entrance coordinates, and optional view node;
- route, departure, arrival, setup, observation, and return times;
- local eclipse contacts, magnitude, obscuration, and Sun direction;
- planning score and components;
- evidence quality, scenario spread, and source disagreement;
- cloud/visibility evidence and limiting layer/time;
- horizon, access, environmental safety, and route status;
- primary risk, fallback action, freshness, and provenance.

## ECL26-PROD-003 — Use decision states, not data dumps

The primary state is one of `stay`, `go`, `monitor`, or
`no_reliable_recommendation`. Raw meteorological layers remain inspectable but
cannot replace a direct recommendation and explanation.

## ECL26-PROD-004 — Aggregate useful time windows

Evaluate every candidate on a five-minute grid and return contiguous viewing
windows, not isolated timestamps. A window cannot extend outside user
availability, event geometry, source validity, access hours, or route
feasibility.

## ECL26-PROD-005 — Preserve honest alternatives

A farther site wins only when robust viewing utility justifies its travel and
safety burden. A fragile high median may lose to a stronger lower-tail result.
The current location may correctly win. Travel cost MUST NOT make a known
obscured site outrank a reliably clear reachable site.

## ECL26-PROD-006 — Explain recommendation changes

Every refresh that changes rank, evidence grade, departure advice, or safety
state MUST show what changed: source/run, cloud movement, disagreement, route
incident, access status, or rule revision. A rank change cannot appear as an
unexplained replacement.

## ECL26-PROD-007 — Preserve freshness and offline truth

The UI MUST display calculation, forecast run, observation scan/report,
access-review, routing-graph, and retrieval times. Offline or fallback plans
MUST say they are not live, disable chase rerouting, and remain usable for
geometry and safety guidance.
