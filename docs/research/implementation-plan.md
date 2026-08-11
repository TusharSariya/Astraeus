# Detailed implementation plan

Last reviewed: 2026-08-10

## Outcome

Build a locally runnable application for Atlantic Canada that accepts:

- latitude and longitude;
- maximum search radius;
- start and end time;
- naked-eye or camera observation mode;

and returns ranked aurora-observation locations with score, best window,
viewing direction, cloud/darkness/aurora conditions, explanation, alternatives,
and source freshness.

The plan's major decision gates are summarized in
[Risks and uncertainties](risks-and-uncertainties.md). In particular, the
site-ranking feasibility experiment should precede large investments in
routing, interface polish, or generalized event support.

The scope boundary between aurora-MVP inputs and later event/equipment variables
is documented in
[Observation variables and success criteria](observation-variables.md#aurora-mvp-scope-recommendation).

## Delivery principles

- Build vertical slices before broad framework abstractions.
- Keep source adapters independent from scientific scoring.
- Use UTC internally and convert only at API/UI boundaries.
- Use `(latitude, longitude)` consistently and document it.
- Keep units explicit in names or typed values.
- Fail explicitly on missing or stale critical data.
- Prefer open/public primary data.
- Use realistic fixtures only when live integration would block a vertical
  slice, and label fixture provenance in responses.
- Remain a single application plus background ingestion jobs until scale proves
  a need for more services.

## Phase 0: repository and source feasibility

### Goals

Establish the project skeleton and eliminate major upstream-data uncertainty
before building application behavior.

### Work

1. Define Python version, dependency management, formatting, typing, and tests.
2. Create source-adapter and normalized-domain packages.
3. Download one HRDPS run and enumerate actual cloud, visibility, humidity,
   temperature, dew-point, wind, and precipitation fields.
4. Decode and interpolate several Atlantic Canada points.
5. Download one REPS run and inspect members and file sizes.
6. Fetch NOAA OVATION and real-time solar-wind products.
7. Retrieve one GOES cloud-mask product covering Atlantic Canada.
8. Confirm licences, attribution, usage limits, and redistribution rights.
9. Record source cadence, publication delay, failure behavior, size, and
   estimated storage/network cost.
10. Confirm whether Astrospheric's Pro API terms permit automated benchmark
    retrieval and forecast archival; if so, capture a small issued-forecast
    sample without making it a runtime dependency.

### Deliverable

A feasibility report plus small reproducible ingestion probes and normalized
sample records. Avoid building the user interface during this phase.

### Exit criteria

- Required V1 inputs are confirmed or explicitly replaced.
- A real HRDPS value can be retrieved for a known coordinate and valid time.
- NOAA products parse into versioned normalized structures.
- Source licensing risks are documented.
- The Astrospheric comparison path is either contractually confirmed or marked
  unavailable, with no silent scraping fallback.

## Phase 1: single-point scientific evaluator

### Input

```text
latitude
longitude
timestamp
observation_type
```

### Work

- Skyfield Sun, Moon, twilight, and darkness calculation.
- HRDPS point interpolation.
- Initial cloud and visibility normalization.
- Conservative fog-risk calculation.
- NOAA aurora and solar-wind normalization.
- Initial viewing-direction calculation.
- Versioned component and overall score.
- Provenance/freshness in every response.
- Live-provider contract tests plus stable fixtures.

### Deliverable

A CLI or API endpoint that evaluates one place and time end to end.

### Exit criteria

- All timestamps are timezone-aware and normalized to UTC.
- Expected astronomy values are verified against a trusted reference.
- Missing/stale sources produce explicit typed errors.
- Score explanations identify the dominant constraint.

## Phase 2: time optimization at one location

### Work

- Accept a start/end range.
- Sample every ten minutes.
- Interpolate weather fields in time without extrapolating beyond validity.
- Evaluate astronomy and aurora at each step.
- Aggregate contiguous usable timestamps.
- Enforce minimum useful duration.
- Select peak time and explain changing risks within the window.

### Deliverable

The best observation window at one location, plus alternatives if multiple
windows are materially different.

### Exit criteria

- Window aggregation passes gap, threshold, tie, and boundary tests.
- Returned windows do not extend outside source or user validity ranges.

## Phase 3: candidate-location optimization

### Work

- Build a curated Atlantic Canada candidate-site fixture/database.
- Always evaluate the user's current location.
- Filter by search radius.
- Initially use explicit great-circle distance.
- Evaluate every candidate across the requested window.
- Rank location/window pairs.
- Add geographic diversity so alternatives are not adjacent duplicates.
- Report unknown access confidence instead of inventing accessibility.

### Deliverable

The first complete local MVP response with ranked destinations and windows.

### Exit criteria

- Radius filtering and geodesic calculations are tested.
- Rankings are deterministic for fixed inputs and fixtures.
- Alternatives are geographically and scientifically meaningful.
- The current location may correctly win.

## Phase 4: terrain and directional light pollution

### Work

- Acquire and preprocess the chosen DEM.
- Precompute horizon profiles for curated sites.
- Intersect predicted aurora elevation with the relevant horizon sector.
- Acquire and preprocess a licensed VIIRS composite.
- Calculate local and directional light exposure.
- Add terrain and directional light components to explanations.

### Exit criteria

- Known open and obstructed horizons produce expected profiles.
- A city north of a site penalizes northward observing more than the same city
  behind the observer.
- Derived-data attribution is included.

## Phase 5: operational cloud nowcast

### Work

- Ingest current GOES cloud classification/probability.
- Compare observed cloud with HRDPS valid-time cloud.
- Derive a simple cloud trend or motion estimate.
- Add surface stations and METAR visibility/ceiling.
- Use radar only for precipitation obstruction.
- Rerank sites before departure and during an active recommendation.
- Add “improving,” “stable,” and “deteriorating” explanations.

### Product output

- `plan` mode for hours/days ahead.
- `go_now` mode for the next 0–3 hours.

### Exit criteria

- The system distinguishes forecast from observed conditions.
- Current observation age is visible.
- Forecast/observation disagreement reduces confidence.
- Nighttime low-cloud limitations are stated.

## Phase 6: road travel and accessibility

### Work

- Integrate [OSRM](https://project-osrm.org/docs/v5.24.0/api/) or
  [Valhalla](https://valhalla.github.io/valhalla/) behind `RoutingProvider`.
- Compute road travel time and distance.
- Cache common route matrices.
- Add leave-by time using route duration plus configurable setup buffer.
- Store candidate access, parking, hours, and safety metadata.
- Prevent recommendations that cannot be reached before the useful window.

### Exit criteria

- Route failure is explicit.
- Travel-time constraints affect optimization rather than display only.
- No destination is claimed publicly accessible without evidence.

## Phase 7: ensemble uncertainty

### Work

- Evaluate weather components for each REPS member.
- Compute score distributions rather than only score-at-mean-weather.
- Calculate location-ranking stability.
- Identify alternatives that win under plausible scenarios.
- Add concise confidence explanations.

### Example

> Cape North is best in 16 of 21 scenarios. Meat Cove is favored when the low
> cloud clears more slowly than the deterministic forecast.

### Exit criteria

- Ensemble member identity is preserved.
- Confidence is not labelled observation probability.
- A deterministic high score with weak ensemble support is visibly uncertain.

## Phase 8: validation foundation

### Work

- Archive normalized forecasts and observations used by every recommendation.
- Store model run, valid time, lead time, score version, and provider version.
- Match historical forecasts to GOES cloud and surface observations.
- Follow [Historical environmental-data retrieval](historical-data-retrieval.md)
  so verification preserves initialization time, forecast lead, member, model
  version, raw checksums, observation quality, and data semantics.
- Implement forecast skill reports by region, season, lead time, and cloud
  layer.
- Add optional structured user outcomes without treating “did not attempt” as
  failure.

### Exit criteria

- A recommendation can be replayed from archived inputs.
- Forecast errors can be attributed to source, normalization, scoring, or
  optimization.
- Calibration work has a documented minimum-data threshold before probability
  claims are enabled.

## Proposed application architecture

```text
ECCC / NOAA / GOES / DEM / VIIRS / routing
                    |
                    v
              Source adapters
                    |
                    v
        Versioned normalized snapshots
                    |
                    v
              Feature extraction
                    |
                    v
    (location, timestamp, observation type)
                    |
                    v
           Scoring and uncertainty
                    |
                    v
             Window aggregation
                    |
                    v
       Travel-constrained optimization
                    |
                    v
            Recommendation API/CLI
```

Recommended initial runtime:

- [Python](https://docs.python.org/3/) and
  [FastAPI](https://fastapi.tiangolo.com/);
- background ingestion within the same deployable application or a simple
  worker process;
- [SQLite](https://www.sqlite.org/docs.html) or
  [DuckDB](https://duckdb.org/docs/) for early metadata/cache needs;
- local/object storage for raw subsets and normalized artifacts;
- [PostgreSQL](https://www.postgresql.org/docs/) and
  [PostGIS](https://postgis.net/documentation/) only when spatial persistence
  or concurrency requires it.

Avoid Kubernetes, microservice decomposition, or a foundational ML model.

### Core implementation-library references

| Component | Documentation | Official repository |
| --- | --- | --- |
| FastAPI | [Documentation](https://fastapi.tiangolo.com/) | [fastapi/fastapi](https://github.com/fastapi/fastapi) |
| Pydantic | [Documentation](https://docs.pydantic.dev/) | [pydantic/pydantic](https://github.com/pydantic/pydantic) |
| xarray | [Documentation](https://docs.xarray.dev/) | [pydata/xarray](https://github.com/pydata/xarray) |
| cfgrib | [Documentation](https://github.com/ecmwf/cfgrib) | [ecmwf/cfgrib](https://github.com/ecmwf/cfgrib) |
| ecCodes | [Documentation](https://confluence.ecmwf.int/display/ECC) | [ecmwf/eccodes](https://github.com/ecmwf/eccodes) |
| Rasterio | [Documentation](https://rasterio.readthedocs.io/) | [rasterio/rasterio](https://github.com/rasterio/rasterio) |
| GDAL | [Documentation](https://gdal.org/) | [OSGeo/gdal](https://github.com/OSGeo/gdal) |
| pyproj | [Documentation](https://pyproj4.github.io/pyproj/) | [pyproj4/pyproj](https://github.com/pyproj4/pyproj) |
| Shapely | [Documentation](https://shapely.readthedocs.io/) | [shapely/shapely](https://github.com/shapely/shapely) |
| GeoPandas | [Documentation](https://geopandas.org/en/stable/) | [geopandas/geopandas](https://github.com/geopandas/geopandas) |
| Skyfield | [Documentation](https://rhodesmill.org/skyfield/) | [skyfielders/python-skyfield](https://github.com/skyfielders/python-skyfield) |
| DuckDB | [Documentation](https://duckdb.org/docs/) | [duckdb/duckdb](https://github.com/duckdb/duckdb) |
| PostgreSQL | [Documentation](https://www.postgresql.org/docs/) | [postgres/postgres mirror](https://github.com/postgres/postgres) |
| PostGIS | [Documentation](https://postgis.net/documentation/) | [postgis/postgis](https://github.com/postgis/postgis) |

These are implementation libraries, not forecast providers. Provider feeds,
APIs, CLIs, and community clients belong beside their source descriptions in
the other research documents; the cross-domain entry point is the
[repositories, documentation, APIs, and SDK index](integration-tooling-index.md).

## Core domain structures

- `ObservationRequest`
- `CandidateSite`
- `ForecastRun`
- `WeatherState`
- `WeatherEnsemble`
- `CloudObservation`
- `AuroraState`
- `AstronomyState`
- `HorizonProfile`
- `LightPollutionExposure`
- `RouteEstimate`
- `ScoredOpportunity`
- `ObservationWindow`
- `Recommendation`
- `SourceProvenance`

## Testing plan

### Astronomy

- Sun/Moon positions against trusted reference cases.
- Twilight transitions.
- timezone and UTC boundaries.
- high-latitude/no-transition cases.

### Provider normalization

- GRIB projection and coordinate interpolation.
- latitude/longitude ordering.
- unit conversion.
- run time versus valid time.
- missing variables and files.
- stale and malformed upstream data.

### Scoring

- monotonic behavior where scientifically intended.
- hard-gate boundaries.
- naked-eye versus camera differences.
- dominant limiting-factor selection.
- score-version snapshot cases.

### Geography and optimization

- great-circle distance.
- radius boundary behavior.
- current-location inclusion.
- route-time feasibility.
- alternative diversity.
- deterministic tie-breaking.

### Window aggregation

- isolated peaks.
- contiguous good periods.
- short dips.
- minimum duration.
- user-window boundaries.
- changing primary risk.

### Integration

- end-to-end fixed fixture recommendation.
- one opt-in live-source smoke test per provider.
- provenance/freshness propagation.
- partial-provider outage behavior.

## Operational requirements

- Cache immutable model runs by source/run/field/level.
- Never reinterpret one run as another after upstream updates.
- Record ingest completeness before publishing a run.
- Make source freshness observable through logs and metrics.
- Use bounded retries and retain the previous run only with explicit stale
  status.
- Validate coordinate reference systems at adapter boundaries.
- Subset large rasters to the Atlantic Canada domain where licensing permits.
- Keep secrets and proprietary credentials out of fixtures and logs.

## Decision gates before implementation expands

1. Which HRDPS cloud and visibility fields are consistently operational?
2. Can GOES cloud-probability data be retrieved reliably for the MVP backend?
3. Which VIIRS derivative has acceptable licensing and operational size?
4. Is OVATION adequate for direction/elevation estimates at Atlantic Canadian
   latitudes?
5. What source gives defensible public-access candidate sites?
6. Is road routing required before the first private demo or only before public
   recommendations?
7. What forecast inputs may be archived for validation?
8. What exact freshness limits apply to `plan` and `go_now` modes?

Resolve these with small, reproducible feasibility experiments. Record both the
hypothesis and result.

## First MVP response shape

```json
{
  "best": {
    "location": {
      "name": "Cape North",
      "latitude_deg": 0.0,
      "longitude_deg": 0.0
    },
    "travel": {
      "distance_km": 0.0,
      "duration_minutes": null,
      "method": "great_circle"
    },
    "window": {
      "start_utc": "...",
      "end_utc": "...",
      "peak_utc": "..."
    },
    "view": {
      "cardinal": "NNW",
      "azimuth_range_deg": [325, 350],
      "elevation_range_deg": [10, 30]
    },
    "observation_score": 87,
    "score_version": "aurora-v1",
    "forecast_confidence": "medium",
    "components": {
      "aurora": 94,
      "cloud": 91,
      "transparency": 82,
      "darkness": 100,
      "terrain": null,
      "light_pollution": null,
      "moon": 98
    },
    "primary_risk": "High cloud increasing after 00:30 UTC",
    "limitations": [
      "Terrain and directional light pollution are not evaluated in this version"
    ],
    "provenance": []
  },
  "alternatives": []
}
```

Actual example coordinates must replace placeholders before this becomes a
contract test.

## MVP acceptance criteria

The first concrete deliverable is complete when a local user can:

1. provide latitude, longitude, radius, start/end times, and observation type;
2. receive the current location plus ranked reachable candidates;
3. see the best contiguous observation window for each;
4. see viewing direction and elevation range;
5. see score, component scores, confidence, and dominant risk;
6. inspect source run, valid time, age, and limitations;
7. receive an explicit error or degraded result when data is missing/stale;
8. reproduce deterministic results from checked-in fixtures;
9. run documented tests locally.

## Post-MVP order

After the first functional slice:

1. terrain horizon;
2. directional light pollution;
3. road travel time and access confidence;
4. REPS uncertainty, if not pulled earlier;
5. GOES-driven operational nowcasting, if not pulled earlier;
6. smoke/aerosol transparency;
7. historical verification and calibrated probabilities;
8. generalized observation-event interface.

Operationally, GOES nowcasting may be more valuable than terrain or light
pollution and can be pulled earlier if source feasibility is strong.
