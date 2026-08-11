# August 12, 2026 Eclipse Planner — Implementation Specification

Last reviewed: 2026-08-11

## Summary and product contract

Build a reusable `EclipseEvent` vertical slice that recommends the best
reachable location for observing the August 12, 2026 partial solar eclipse from
the user's GPS origin.

### Fixed planning assumptions

- Seed origin: `47.609032, -52.692213`, near St. John's.
- Runtime location: browser GPS with manual-pin fallback.
- Timezone: `America/St_Johns`; UTC internally.
- Availability: noon–7:00 p.m. NDT.
- Maximum travel: 90-minute one-way drive.
- Observation mode: filtered visual observation plus solar-filtered
  photography.
- Priority interval: maximum eclipse ±30 minutes.
- Approximate St. John's reference:
  - C1: 2:28:44 p.m. NDT.
  - Maximum: 3:34:55 p.m.
  - C4: 4:36:55 p.m.
  - Magnitude: approximately `0.617`.
  - Obscuration: approximately `53.1%`.
- Calculate exact circumstances separately at every candidate; do not reuse
  city-level values.
- Unknown-access sites remain visible but receive a major ranking penalty.
- Open/public data is the required baseline; paid providers remain optional
  adapters.
- Primary deliverable: mobile-first React PWA with local FastAPI backend.
- Deployment: Docker Compose.
- Geographic package: Avalon Peninsula.
- Routing: self-hosted Valhalla.
- Visualization: map, synchronized timeline, and Sun-ray/cloud-opacity profile.
- Output: planning score and confidence band, never a calibrated success
  probability.

### Core user outcome

The primary screen must answer:

1. Should I remain at my current location or travel?
2. Which reachable site offers the strongest robust view around maximum
   eclipse?
3. When must I leave and arrive?
4. Where will the Sun be?
5. How much cloud opacity is expected along the Sun ray?
6. What evidence supports the recommendation?
7. What is the main risk and best fallback?

The optimizer should be able to return:

> Stay at your current location. The best alternative is only marginally
> clearer and does not justify the drive.

### Safety invariant

The eclipse is partial throughout the supported region. The application must
never display a “glasses off” state.

- ISO 12312-2-compliant solar viewers are required for all direct visual
  observation.
- Camera, binocular, and telescope filters must be mounted over the
  front/objective.
- Eclipse glasses do not make it safe to look through unfiltered optics.
- Weather, cloud opacity, magnitude, or apparent darkness never relaxes these
  rules.
- Missing or uncertain geometry must fail safe.
- Show the warning during setup, on site details, in monitor mode, and before
  navigation/export.

Use [NASA eclipse safety guidance](https://science.nasa.gov/eclipses/safety/)
as the authoritative copy source.

## System, interfaces, and data flow

### Runtime architecture

Docker Compose services:

- `web`: React, TypeScript, Vite, PWA service worker.
- `api`: FastAPI/Pydantic application.
- `worker`: ingestion, normalization, scoring, and refresh jobs using Postgres
  advisory locks; no Celery/Redis initially.
- `db`: PostgreSQL/PostGIS for sites, routes, metadata, evaluations, and
  provenance.
- `valhalla`: Newfoundland OSM routing graph and isochrones.
- `titiler`: COG-backed forecast, satellite, terrain, and uncertainty tiles.
- Static PMTiles: offline Avalon basemap.

Libraries:

- MapLibre GL JS for mapping.
- deck.gl for opacity and uncertainty raster overlays.
- Observable Plot for the eclipse/cloud timeline and ray profile.
- TanStack Query for API state and refreshes.
- Skyfield with pinned `de440s.bsp` for eclipse geometry.
- SciPy root finding for contacts and maximum.
- xarray, cfgrib, and ecCodes for NWP.
- Rasterio, GDAL, pyproj, Shapely, and GeoPandas for geospatial processing.

Storage:

```text
/data/raw/{provider}/{product}/{run-or-scan}/{checksum}
    immutable source bytes

/data/normalized/
    Zarr or Parquet for multidimensional/point data
    COG for display rasters
    PMTiles for offline basemap

PostGIS
    source manifests
    candidate sites
    access evidence
    horizon profiles
    routes
    plan requests
    scored opportunities
```

Never overwrite an issued forecast run or mutable upstream response. Every
normalized object retains the raw checksum.

### Public request contract

`POST /v1/eclipse/plans`

```json
{
  "event_id": "solar-eclipse-2026-08-12",
  "origin": {
    "latitude_deg": 47.609032,
    "longitude_deg": -52.692213,
    "accuracy_m": 25,
    "observed_at_utc": "..."
  },
  "availability": {
    "start_local": "2026-08-12T12:00:00-02:30",
    "end_local": "2026-08-12T19:00:00-02:30"
  },
  "travel": {
    "max_one_way_minutes": 90,
    "mode": "drive",
    "avoid_ferries": true,
    "avoid_unpaved": false,
    "max_walk_m": 500
  },
  "observation": {
    "modes": ["filtered_visual", "solar_filtered_camera"],
    "critical_window_before_max_minutes": 30,
    "critical_window_after_max_minutes": 30,
    "setup_minutes": 20
  },
  "site_policy": {
    "include_access_unknown": true
  }
}
```

Return `202 Accepted` with `plan_id` and progress URL. Use server-sent events
for ingestion/evaluation progress.

Supporting interfaces:

- `GET /v1/eclipse/plans/{plan_id}`: complete ranked result.
- `GET /v1/eclipse/plans/{plan_id}/events`: progress and refresh stream.
- `POST /v1/eclipse/evaluate`: deterministic geometry for one site.
- `POST /v1/isochrones`: Valhalla road-time polygon.
- `GET /v1/sites/{site_id}`: access and obstruction evidence.
- `GET /v1/sites/{site_id}/horizon`: directional horizon profile.
- `GET /v1/routes`: route, ETA, road properties, and hazards.
- `GET /v1/conditions`: normalized point/time evidence.
- `GET /v1/tiles/{layer}/{z}/{x}/{y}`: owned/generated raster layers.
- `GET /v1/provenance/{evaluation_id}`: immutable source manifest.

GeoJSON uses longitude/latitude. Domain/API objects use named latitude and
longitude fields. All machine timestamps require UTC offsets.

### Core domain types

- `EclipseEvent`
- `EclipseCircumstances`
- `EclipseContact`
- `PlanRequest`
- `CandidateSite`
- `AccessEvidence`
- `HorizonProfile`
- `AtmosphericEvidence`
- `CloudRayEvaluation`
- `WeatherScenario`
- `RouteEvaluation`
- `ScoredOpportunity`
- `RecommendationWindow`
- `RecommendationPlan`
- `SourceProvenance`

Every time-varying record includes:

```text
provider
product
product_version
model_init_utc
lead_time
valid_time_utc
ingested_at_utc
source_uri
raw_checksum
quality_flags
normalization_version
```

### End-to-end flow

```text
GPS/manual origin
    -> Valhalla 90-minute isochrone
    -> curated + official + OSM candidate generation
    -> exact eclipse geometry per candidate
    -> hard geometry/access/arrival filtering
    -> HRDPS/RDPS/REPS extraction
    -> GOES/SWOB/METAR/radar/aerosol conditioning
    -> Sun-ray cloud-opacity evaluation every 5 minutes
    -> scenario scoring over maximum ±30 minutes
    -> route/access/uncertainty adjustment
    -> ranked current location + destinations + fallbacks
    -> map/timeline/ray-profile visualization
    -> event-day refresh with hysteresis
```

## Scientific and data specification

### Eclipse geometry

Authoritative event baseline:

- [NASA/GSFC Besselian elements](https://eclipse.gsfc.nasa.gov/SEsearch/SEdata.php?Ecl=20260812)
- [NASA eclipse overview](https://science.nasa.gov/eclipses/future-eclipses/total-solar-eclipse-on-august-12-2026/)
- USNO as an external validator, not a runtime dependency.

Production algorithm:

1. Normalize WGS84 latitude, longitude, and ellipsoid height.
2. Convert UTC to TT/TDB and UT1 using pinned leap seconds and IERS EOP.
3. Compute apparent topocentric Sun and Moon directions/distances with Skyfield
   and DE440s.
4. Compute angular radii using frozen constants:
   - solar radius: `695700 km`;
   - lunar mean radius: `1737.4 km`.
5. Let `d` be angular centre separation:
   - C1/C4 roots: `d - (r_sun + r_moon) = 0`;
   - C2/C3 roots: `d - abs(r_moon - r_sun) = 0`, only where central eclipse is
     possible.
6. Find maximum by minimizing `d`.
7. Calculate magnitude under the frozen angular-diameter convention.
8. Calculate obscuration using exact circle-overlap area.
9. Calculate geometric Sun altitude/azimuth independently.
10. Optionally calculate standard-refracted altitude for display; never use
    refraction in contact geometry.
11. Store algorithm, ephemeris, EOP, leap-second, constants, and reference
    provenance.

Local output:

```text
local_type
C1, C2, maximum, C3, C4
time_utc and display time
Sun geometric/apparent altitude
Sun azimuth
magnitude
obscuration_fraction
partial/central duration
apparent radii and separation
safety state
geometry uncertainty
```

For every supported Avalon site, `totality_safe_interval` must be `null`.

### Forecast evaluation interval

- Evaluate every candidate every five minutes over `[C1 - 60 min, C4 + 60 min]`.
- Rank primarily over exact candidate maximum ±30 minutes.
- Give additional emphasis to maximum ±10 minutes.
- Continue displaying the complete C1–C4 interval.
- Do not optimize a generic afternoon cloud average.

### Weather models

Primary HRDPS fields:

- `TCDC_Sfc`
- `CWAT_EAtm`
- `SKSTATE_Sfc`
- `VISLFG_AGL-2m`
- `VISIFG_AGL-2m`
- `RH_AGL-2m`
- `DEPR_AGL-2m`
- `DPT_AGL-2m`
- `TMP_AGL-2m`
- wind and gust fields
- precipitation rate/accumulation
- `RH`, `DEPR`, and `SPFH` at pressure levels from 1000 through 300 hPa where
  published.

Use the
[official HRDPS variable catalogue](https://eccc-msc.github.io/open-data/assets/csv/HRDPS_Variables-List_en.csv).
The current public product exposes total cloud rather than clean
low/middle/high cloud fractions. Derive pressure-layer saturation evidence and
label it derived.

Secondary/fallback:

- RDPS deterministic second opinion.
- REPS 20 perturbed members plus control.
- Previous four deterministic cycles for run-to-run displacement and timing
  uncertainty.

REPS outputs:

- `P(TCDC < 20%)`
- `P(TCDC < 40%)`
- `P(TCDC < 70%)`
- p10/median/p90 cloud
- clearing-time distribution
- candidate rank frequency
- sustained-clear-window frequency

Never use the ensemble mean as if it were a realizable sky.

### GOES-19 observation and nowcast

Use full-disk GOES-19 ABI because Newfoundland is outside the CONUS sector.

Required products:

- Clear Sky Mask / ACM
- Cloud Top Height
- Cloud Top Pressure
- Cloud Top Temperature
- Cloud Top Phase
- Cloud Optical Depth when valid
- Cloud Cover Layers when operational and validated
- Derived Motion Winds
- selected ABI CMI/L1b bands for documented fallback features

Retain scan start/end, platform, projection, DQF, algorithm version, and
parallax correction.

Nowcast:

- Maintain the latest several scans.
- Estimate cloud motion using official motion winds plus optical flow.
- Produce 20 perturbed 0–2-hour trajectories using observed motion residuals,
  edge uncertainty, and growth/decay.
- Blend from satellite-dominant now to NWP-dominant by two hours.
- Label this a statistical motion nowcast, not physical simulation.

### Surface and supporting evidence

- ECCC SWOB and METAR/SPECI:
  - visibility;
  - ceiling and reported cloud layers;
  - temperature/dew point/RH;
  - wind/gust;
  - precipitation and present weather;
  - amendments/corrections.
- ECCC radar:
  - precipitation and convection only;
  - absence of echoes never means clear sky.
- RAQDPS/RDAQA:
  - PM2.5/PM10;
  - wildfire/total column;
  - surface analysis.
- Aerosol is secondary for this eclipse; opaque cloud dominates.
- Light pollution is irrelevant to solar visibility and remains off by
  default.
- Astronomical seeing is not part of the V1 eclipse score. The requested
  “seeing” visualization is named `solar visibility` or `cloud opacity` to
  avoid confusing it with turbulence seeing.

### Spatial and temporal normalization

- Bilinear interpolation only for continuous NWP variables where all source
  cells pass QC and share land/water regime.
- Otherwise use nearest valid same-regime cell and flag the fallback.
- Nearest-neighbour for masks, phase, and categorical state.
- Linear hourly interpolation for continuous temperature, RH, and TCDC.
- Preserve precipitation interval semantics.
- Do not fabricate intermediate REPS members or information between three-hour
  steps.
- Do not lapse-rate-correct cloud or fog.
- Evaluate candidate-local buffers of 2–5 km plus 20–40 km upstream cloud
  sectors.
- Apply cloud-height parallax before intersecting the Sun ray.

### Cloud ray and opacity

For each cloud layer or retrieved cloud top, intersect the candidate-to-Sun
ray:

```text
horizontal_offset approximately equals
    (cloud_height - observer_height) / tan(Sun_altitude)
```

For valid GOES cloud optical depth `tau`:

```text
mu = sin(Sun_altitude)
direct_transmission = exp(-tau / mu)
effective_cloud_opacity = 1 - direct_transmission
```

Cap pathological values, respect DQF, and label this direct-beam approximation.
It is not full radiative transfer.

When COD is missing:

- combine total cloud fraction;
- column cloud water;
- pressure-layer saturation evidence;
- cloud phase;
- satellite mask;
- calibrated heuristic opacity mapping;
- widen uncertainty.

Ray-profile output contains distance from observer, ray altitude, inferred
cloud-layer height/thickness, opacity contribution, source, and uncertainty.

### Weather/scenario utility

Per five-minute sample:

```text
weather_utility =
    0.70 * direct_sun_transmission
  + 0.15 * fog_and_surface_visibility
  + 0.10 * transparency
  + 0.05 * precipitation_free
```

Apply hard gates separately.

Per scenario:

```text
critical_utility =
    0.60 * mean_utility(maximum ±10 min)
  + 0.40 * weighted_mean_utility(maximum ±30 min)
```

Weight the wider interval triangularly toward maximum.

Across scenarios:

```text
robust_utility =
    0.70 * p10(critical_utility)
  + 0.20 * median(critical_utility)
  + 0.10 * travel_utility
```

Access multiplier:

- verified public: `1.00`
- likely lawful: `0.85`
- access unknown: `0.65`
- known private/closed/unsafe: hard reject

Travel utility declines linearly from `1.0` at the current location to `0.0`
at 90 minutes. The current location is always evaluated.

`planning_score = round(100 * robust_utility * access_multiplier)`.

Show every component and missing input. Never call the score a probability.

### Hard rejection conditions

- Candidate lies outside the 90-minute Valhalla isochrone.
- Arrival cannot occur by maximum minus 20-minute setup margin.
- Sun is behind terrain/building with high-confidence evidence during maximum
  ±10 minutes.
- Site is known private, closed, unsafe, or has no lawful stopping location.
- Route is closed or requires a prohibited road.
- Required geometry or all critical cloud evidence is unavailable.
- Solar altitude is below the effective horizon.

### Freshness and degradation

Freshness policy:

- GOES scan end: ideal ≤12 minutes; stale after 20.
- Radar: stale after 15 minutes.
- SWOB/METAR: stale after 90 minutes.
- HRDPS/RDPS initialization: stale after 8 hours or incomplete required
  manifest.
- REPS initialization: stale after 10 hours.
- RAQDPS initialization: stale after 15 hours.

Degradation states:

1. Full: HRDPS + REPS + GOES + surface observation.
2. No HRDPS: RDPS + REPS; spatial confidence reduced.
3. No REPS: current/prior deterministic cycles; confidence capped.
4. No GOES: forecast-only; nowcast disabled.
5. No local observation: fog/ceiling marked unverified.
6. No COD/CTH: mask/spectral fallback; no quantitative transparency claim.
7. Conflicting local evidence: newest trustworthy observation dominates
   locally.
8. No reliable cloud evidence for all candidates: return
   `no_reliable_recommendation`.

## Candidate, routing, visualization, and delivery

### Candidate generation

1. Generate a Valhalla drive isochrone at 30, 60, and 90 minutes from the GPS
   origin and noon departure.
2. Always add the current location.
3. Add a manually reviewed seed catalogue of at least 12 Avalon sites:
   - official parks/day-use areas;
   - public parking/lookouts;
   - lawful beaches/harbours with safe setback;
   - established observing areas.
4. Add OSM `viewpoint`, `parking`, `park`, and `picnic_site` POIs as
   access-unknown unless verified.
5. Sample road-accessible open-land cells every approximately 5 km where
   useful.
6. Filter slope above 10°, unsafe shore/cliff cells, prohibited roads, and
   unreachable arrivals.
7. Deduplicate within 1 km while retaining distinct entrances where routing
   differs.
8. Cap preliminary candidates at 200 using geographic and weather diversity.
9. Perform full scenario/ray evaluation for the top 25 preliminary sites.
10. Return the top three, current location, and at least one geographically
    distinct fallback.

Access evidence is separate from ownership. Missing OSM access tags mean
unknown.

### Route policy

- Valhalla graph uses a pinned Newfoundland OSM extract.
- Avoid ferries by default.
- Return ETA, distance, geometry, road classes, surface, walking leg, graph
  date, and confidence.
- Route buffer is `max(10 minutes, 15% of ETA)`.
- Arrival deadline is:
  `critical_window_start - setup_minutes - route_buffer`.
- Overlay 511 NL closures/advisories where API access is configured.
- Navigation launches Apple/Google Maps only after warning that external
  routing can differ.

### Safe-cutoff rerouting

Before departure:

- Change recommendation only when another site is at least eight planning-score
  points better for two consecutive GOES refreshes.
- Immediate changes are allowed for closures or safety hazards.

After navigation begins:

- Require a 12-point advantage sustained for two refreshes.
- Require arrival at least 20 minutes before maximum.
- Never recommend cloud-chasing reroutes after 2:35 p.m. NDT.
- After cutoff, show route hazards and the safest fallback only.
- Current location remains available as the “stop chasing” option.

### Screen hierarchy

1. `Setup`
   - GPS/manual origin and accuracy.
   - Noon–7 p.m. availability.
   - 90-minute travel limit.
   - visual/camera mode.
   - accessibility and route avoids.
   - solar-safety acknowledgement.
   - “Find my best site.”

2. `Plan`
   - Decision headline: stay/go/move.
   - Top three cards and current location.
   - Map with selected route and isochrone.
   - Sticky forecast/GPS freshness.
   - Tabs: `Best`, `Timeline`, `Layers`, `Sources`.

3. `Site`
   - Planning score and confidence.
   - Eclipse contacts, maximum, obscuration, Sun altitude/azimuth.
   - Arrival/departure deadline.
   - Cloud-opacity timeline.
   - Sun-ray profile.
   - Horizon clearance.
   - Access, parking, walk, road, and safety evidence.
   - Route and fallback.

4. `Compare`
   - Candidate columns.
   - Geometry, opacity, uncertainty, access, travel, and provenance rows.
   - Model-by-model sensitivity.

5. `Monitor`
   - Large-text action.
   - Departure deadline.
   - Cloud trend.
   - Route hazard.
   - Next refresh.
   - No animated map while the device is moving.

### Map layers

Default:

- ranked candidate pins with uncertainty halo;
- selected route and 30/60/90-minute isochrones;
- Sun azimuth arrow and C1–maximum–C4 track;
- calculated magnitude/obscuration contours;
- effective cloud-opacity median;
- uncertainty stipple;
- observation/forecast timestamp badges.

Optional:

- HRDPS/RDPS selector;
- REPS clear-ray fraction and spread;
- GOES visible/IR/cloud/COD;
- radar precipitation;
- SWOB/METAR ceiling and visibility;
- terrain hillshade and directional horizon;
- building/canopy evidence;
- parks, parking, gates, trails, and washrooms;
- 511 incidents;
- raw aerosol evidence;
- light pollution off by default.

Every layer displays source, run/scan, valid time, retrieval age, resolution,
interpolation, and quality state.

### Synchronized timeline

One timeline spans noon–7 p.m. and controls all layers.

Tracks:

1. Deterministic obscuration curve.
2. Sun altitude versus terrain/building/canopy horizon.
3. Median direct transmission with p10–p90 band.
4. GOES scan and surface-observation markers.
5. Departure, arrival, C1, maximum, C4, fallback cutoff.

Scrubbing updates the map, Sun arrow, recommendation cards, and ray profile.

### Parallel implementation workstreams

Iteration 0 — contract freeze:

- API schemas and coordinate/time conventions.
- NASA event fixture and golden geometry outputs.
- Raw/normalized provenance format.
- UI wireframe and layer contract.
- Committed deterministic provider fixtures.

After contract freeze, delegate in parallel:

1. Geometry and safety agent:
   - Skyfield/DE440s engine;
   - contact/root calculations;
   - obscuration;
   - NASA/USNO validation;
   - safety state.

2. Weather ingestion agent:
   - HRDPS/RDPS/REPS manifests;
   - GRIB decoding;
   - interpolation;
   - immutable raw storage.

3. Observation/nowcast agent:
   - GOES/SWOB/METAR/radar/RAQDPS;
   - DQF;
   - cloud motion;
   - freshness/degradation.

4. Site/routing agent:
   - Valhalla;
   - Avalon OSM graph;
   - candidate generation;
   - access evidence;
   - horizon preprocessing.

5. Scoring agent:
   - ray intersection;
   - opacity;
   - scenarios;
   - ranking;
   - hysteresis.

6. Frontend agent:
   - PWA;
   - MapLibre/deck.gl;
   - timeline/ray profile;
   - setup/plan/site/compare/monitor screens.

7. Integration/verification agent:
   - fixture replay;
   - end-to-end provenance;
   - safety audit;
   - offline bundle;
   - live shadow runs.

Agents may not change shared contracts independently. Contract changes require
a version bump and integration review.

### Event-day delivery priority

Because the event is one day from the specification's review date, distinguish
the operational slice from the complete module.

Required event-day slice:

- pinned eclipse geometry;
- curated sites;
- Valhalla routes;
- HRDPS/RDPS/REPS extraction;
- latest GOES cloud mask;
- SWOB/METAR;
- planning score with explicit uncertainty;
- map, timeline, recommendation cards;
- solar-safety invariants;
- replayable source manifest.

May follow after the event if not already validated:

- perturbed optical-flow trajectories;
- full COD/CTH ray profile;
- building/canopy horizons for every generated site;
- complete offline PMTiles bundle;
- 511 integration;
- phone horizon scan;
- richer aerosol modelling.

Do not deploy an unvalidated sophisticated nowcast in place of a simpler,
traceable forecast comparison.

### Test and acceptance suite

Geometry:

- St. John's reference: partial, magnitude approximately `0.617`, obscuration
  approximately `0.531`.
- Approximate USNO UT1 controls:
  - C1 `16:58:43.7`;
  - maximum `18:04:54.9`;
  - C4 `19:06:55.0`.
- Bonavista and Halifax regression fixtures.
- No-eclipse and central-path classification tests.
- Contact tolerance ≤5 seconds across different documented ephemerides.
- Altitude/azimuth tolerance ≤0.1°.
- No C2/C3 or safe-totality interval for Avalon candidates.

Weather/providers:

- Exact GRIB field and unit tests.
- Land/water interpolation boundary tests.
- Missing member/run/file manifest tests.
- GOES DQF, parallax, day/night, and outage fixtures.
- Station corrections/amendments and deduplication.
- Radar-with-no-echo does not imply clear sky.
- REPS mean is never exposed as a physical scenario.
- Reanalysis cannot enter an issued-forecast evaluation.

Scoring:

- Opaque cloud hard-limits the recommendation.
- Thin cloud reduces photographic quality.
- Access unknown remains visible but penalized.
- Current location can win.
- Robust p10 ranking can beat a higher but fragile median.
- Travel penalty cannot make an obscured nearby site beat a reliably clear
  reachable site.
- Missing evidence lowers confidence deterministically.
- All-critical-data failure returns no reliable recommendation.

Routing/sites:

- 90-minute isochrone and arrival-deadline enforcement.
- Known private/closed candidates rejected.
- Unknown access never presented as verified.
- Synthetic terrain obstruction rejected.
- Route closure bypasses reroute hysteresis.
- No roadside shoulder candidate without explicit lawful/safe evidence.

Frontend:

- UTC/NDT conversion and DST tests.
- Timeline controls all layers consistently.
- Magnitude and obscuration are labelled separately.
- Forecast and observation palettes remain distinct.
- Stale data cannot look fresh.
- GPS denial, poor accuracy, and offline mode have manual fallbacks.
- Mobile-width usability.
- Safety acknowledgement is unavoidable.
- Export includes timestamps and provenance.

End-to-end acceptance:

- From the fixed origin, return current location plus at least three reachable
  candidates or explicit rejection reasons.
- Each candidate has independently calculated contacts and Sun direction.
- The recommendation includes arrival deadline, route, score components,
  uncertainty, primary risk, and fallback.
- Every result is reproducible from raw checksums, model runs, ephemeris
  version, routing graph, and algorithm versions.
- Live shadow runs complete successfully before event day.
- The system can honestly return “stay put” or “no reliable recommendation.”

## Assumptions

- The linked Astrospheric coordinates are the intended initial GPS origin.
- The user can depart at noon and return by 7 p.m. NDT.
- Maximum eclipse ±30 minutes is more important than preserving the entire
  partial phase.
- Access-unknown locations may appear but cannot receive an unpenalized
  recommendation.
- The application is local and unauthenticated for V1; GPS is stored locally by
  default.
- Probability calibration is out of scope.
- Astronomical seeing is not part of the eclipse score.
- Light pollution is irrelevant to daytime eclipse visibility.
- A manual review of the initial Avalon candidate catalogue is required before
  recommendations are considered safe.
- USNO is a validation service only; NASA/JPL-based local calculation is
  authoritative at runtime.
