---
id: RFC-004
title: Site Selection and Routing
type: rfc
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
  - RFC-001
  - PRD-ACC-001
supersedes: []
---

# RFC-004 — Site selection and routing

## SITE-CAND-001 — Generate reachable, diverse candidates

Candidate generation MUST:

1. Create a time-bounded Valhalla isochrone from the earliest feasible
   departure, bounded by `max_one_way_minutes`, and record traffic/closure
   assumptions.
2. Evaluate a distinct origin stay option.
3. Seed from declared public-facility classes and paired parking/entrances,
   not from DEM peaks, highway shoulders, or street-level imagery coverage.
4. Treat OSM, Overture Places, Crown or public polygons, cadastral parcels,
   and street-level imagery coverage as access unknown until approved.
5. Reject prohibited roads, unsafe slopes/shores, and impossible arrivals.
6. Deduplicate nearby sites while retaining materially different entrances.
7. Preserve geographic, coastal, elevation, access, forecast-disagreement, and
   evidence diversity during preliminary downselection.
8. Compare downselection recall against exhaustive fixture evaluation.

Horizon geometry (`SITE-HOR-001`) MAY score a curated point. It MUST NOT mint
a new recommendable destination.

## SITE-ACCESS-001 — Separate ownership from lawful use

`AccessEvidence` records claim type, site class, authoritative source,
observed/publication time, reviewer, review time, expiry, lawful entry and
stopping/parking, hours, gate/road constraints, evidence grade, approval
state, and notes. Only a signed, approved, unexpired catalogue revision can
authorize a destination result.

The following MUST NOT by themselves approve a destination, emit a planning
score, `go` state, deadline, or navigation link:

- OpenStreetMap tags, including `access=yes` or missing `access`;
- Overture or Google Places type membership;
- parcel ownership, Crown land, protected-area polygons, or a 15 m shoreline
  reservation;
- Google Street View or other street-level imagery coverage, including
  metadata that a panorama exists;
- absence of a private tag.

Unknown destinations are exploratory only. Google Street View imagery MUST NOT
be displayed on the operational MapLibre surface and MUST NOT be used to
derive access, obstruction, parking, or tree features. Reviewers MAY open
Street View in a separate Google surface. Mapillary or KartaView MAY be cached
under their licences as reviewer QA, not as permission.

## SITE-ACCESS-002 — Classify sites and pair entrances with view nodes

Every catalogue site MUST carry a `site_class`:

| Class | Default catalogue state |
|---|---|
| `origin_stay` | Evaluated at the user origin; not a public destination |
| `municipal_park` | Seed; recommendable after hours, parking, and safety review |
| `national_historic_site` | Seed; recommendable after published grounds hours review |
| `provincial_park` | Seed; recommendable after vehicle-access and hours review |
| `signed_lookout` | Seed only when a legal stop/parking exists; pair entrance and view |
| `library_grounds` | Seed; recommendable only when outdoor grounds or parking are explicitly public and hours cover the observation window |
| `community_centre` | Same rule as `library_grounds` |
| `trailhead` | Seed; recommendable only when the walk fits setup/teardown and the trail is a designated public route |
| `exploratory_unknown` | Never scored, `go`, or navigated |
| `rejected_school` | Hard reject; school grounds are not public property |
| `rejected_private` | Hard reject |
| `rejected_other` | Hard reject |

Schools, playgrounds, and school sports fields default to `rejected_school`
even when empty, Street View-visible, or tagged public. They MAY become
recommendable only after an explicit operator or municipality designation for
this occurrence.

Lookouts and viewpoints are two geometries. The recommendable navigation
target is the **entrance** (lawful parking or stop). The optional **view
node** is where horizon and Sun geometry are evaluated. The catalogue MUST
record `max_walk_minutes` between them. A viewpoint node without a legal
entrance remains `exploratory_unknown`. DEM-only ridges MUST NOT be stored as
lookouts.

`CandidateResult.location` is the entrance. `viewing_site.view_point` MAY be
null when observation is from the entrance.

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
meets the deadline, the complete observation interval fits, outbound drive
does not exceed `max_one_way_minutes`, the entrance-to-view walk fits
`max_walk_minutes` and the observation profile, and return arrival does not
exceed availability end.

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
