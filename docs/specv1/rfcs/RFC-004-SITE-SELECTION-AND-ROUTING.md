---
id: RFC-004
title: Site Selection and Routing
type: rfc
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-001
supersedes: []
---

# RFC-004 — Site selection and routing

## SITE-CAND-001 — Generate reachable, diverse candidates

Candidate generation MUST:

1. Create a time-bounded Valhalla isochrone from the earliest feasible
   departure and record traffic/closure assumptions.
2. Evaluate a distinct origin stay option.
3. Seed approved public destinations and entrances.
4. Treat OSM and sampled road-accessible cells as access unknown until
   approved.
5. Reject prohibited roads, unsafe slopes/shores, and impossible arrivals.
6. Deduplicate nearby sites while retaining materially different entrances.
7. Preserve geographic, coastal, elevation, access, forecast-disagreement, and
   evidence diversity during preliminary downselection.
8. Compare downselection recall against exhaustive fixture evaluation.

## SITE-ACCESS-001 — Separate ownership from lawful use

`AccessEvidence` records claim type, authoritative source, observed/publication
time, reviewer, review time, expiry, lawful entry and stopping/parking, hours,
gate/road constraints, evidence grade, approval state, and notes. Only a signed,
approved, unexpired catalogue revision can authorize a destination result.

OSM, parcel ownership, Crown/public ownership, or absence of a private tag is
not permission. Unknown destinations are exploratory only.

## SITE-HOR-001 — Compute obstruction from owned analytic sources

Terrain priority is Canadian HRDEM/local lidar DTM, then Copernicus DEM.
Buildings use official footprints/heights then approved Overture/OSM fallback.
Canopy uses classified lidar or DSM–DTM, otherwise a documented inferred model.

Server-side azimuthal ray casting records Earth-curvature, refraction, CRS,
vertical datum, resolution, acquisition date, and coverage. Output separates
`terrain_clear`, `surface_obstructions_clear`, and `overall_clear`. Missing
building/canopy evidence keeps overall clearance unknown.

## SITE-ROUTE-001 — Evaluate the complete itinerary

The pinned Newfoundland Valhalla graph returns ETA, distance, geometry, road
classes/surface, walking legs, graph date/checksum, and evidence quality. It is
traffic-blind unless an explicit live adapter is present.

All services use:

```text
arrival_deadline = critical_window_start - setup_minutes
latest_departure = arrival_deadline
  - outbound_drive - outbound_walk - outbound_route_buffer
return_arrival = critical_window_end + teardown
  + return_walk + return_drive + return_route_buffer
outbound_route_buffer = max(10 minutes, 15% of outbound_drive ETA)
return_route_buffer = max(10 minutes, 15% of return_drive ETA)
```

A candidate is eligible only when departure is within availability, arrival
meets the deadline, the complete observation interval fits, and return arrival
does not exceed availability end.

## SITE-SAFE-001 — Prevent cloud-chasing hazards

Apply the versioned `rerouting-policy-v1.yaml` rule. While it remains draft,
dynamic destination-changing recommendations are disabled. Closures and safety
hazards MAY still trigger a safe-stop or fallback instruction. Suppress
destination-changing interaction after the event-specific safe cutoff and
while a user appears to be driving unless passenger mode is explicitly
confirmed.

## Routing deployment

Valhalla runs on a private Montreal GCE VM with reserved internal address,
systemd-supervised container, persistent balanced disk, probes, snapshots, and
alerts. Initial ceiling is 2 vCPU, 8 GiB RAM, and 50 GiB disk pending benchmark.
Graphs are immutable, dated, checksummed, health-tested, and blue/green
promoted. A circuit breaker falls back to signed precomputed curated routes.
