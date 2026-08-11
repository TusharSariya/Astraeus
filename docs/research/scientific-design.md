# Scientific and scoring design

Last reviewed: 2026-08-10

## Scientific stance

Astraeus is a decision and optimization layer, not a numerical weather model.

For the MVP, it produces an explainable **Observation Score**, not a calibrated
probability. Probability language must wait until historical predictions and
outcomes support empirical calibration.

The cross-system scientific, operational, safety, and product uncertainties are
tracked in [Risks and uncertainties](risks-and-uncertainties.md). Those risks
should be treated as delivery gates rather than buried inside score tuning.

The broader definition of observation success—including target/background
contrast, observer and equipment response, required duration, wind, dew, and
event-specific constraints—is defined in
[Observation variables and success criteria](observation-variables.md).

## Evaluation unit

The engine evaluates a state:

```text
(candidate location, valid timestamp, observation type)
```

Each state receives normalized inputs from independent providers. The optimizer
then aggregates good adjacent timestamps into observation windows and ranks
location/window pairs subject to travel constraints.

## Provider boundaries

```text
ObservationRequest
    +-- CandidateLocationProvider
    +-- AstronomyProvider
    +-- WeatherProvider
    +-- WeatherObservationProvider
    +-- AuroraProvider
    +-- TerrainProvider
    +-- LightPollutionProvider
    +-- RoutingProvider
    +-- ScoringEngine
    +-- WindowAggregator
    +-- Optimizer
    +-- RecommendationService
```

Raw vendor/model formats must stop at provider adapters. Scoring code should not
parse GRIB2, NetCDF, GeoTIFF, or vendor JSON directly.

The implementation libraries, official APIs, canonical repositories, and
community clients used behind these adapters are indexed in
[Repositories, documentation, APIs, and SDKs](integration-tooling-index.md).
An SDK or downloader is transport tooling; it does not change the scientific
semantics, freshness, uncertainty, or licence of the underlying product.

## Normalized provenance

Every time-varying state should carry:

```text
source
source_product
model_name
model_version_if_known
model_run_time_utc
valid_time_utc
retrieved_at_utc
age_seconds
quality_flags
normalization_version
```

This is necessary for freshness checks, replay, validation, incident diagnosis,
and later calibration.

## Hard constraints and soft quality

A flat weighted average can create nonsensical compensation, such as excellent
darkness offsetting complete overcast. Use gates and limiting factors before
soft quality adjustments.

Hard or near-hard constraints include:

- Sun too high;
- outside travel limit;
- inaccessible or unsafe candidate;
- aurora below the terrain horizon;
- missing critical astronomy, aurora, or weather data;
- near-total opaque cloud;
- usable window shorter than the required duration.

Conceptual structure:

```text
opportunity_score =
    aurora_potential
    * visibility_gate
    * darkness_gate
    * accessibility_gate
    * quality_adjustment
```

Where visibility is constrained by:

```text
visibility_gate =
    cloud_transmission
    * fog_visibility
    * terrain_visibility
```

And softer quality includes:

- Moon interference;
- atmospheric transparency;
- directional light pollution;
- forecast confidence.

This is a conceptual model, not the final formula. Initial functions and weights
must be explicit, versioned, tested at boundaries, and supported by worked
examples.

## Naked-eye versus camera modes

Use distinct parameter sets:

- camera mode can tolerate weaker aurora and somewhat more light pollution;
- naked-eye mode needs greater apparent brightness and contrast;
- Moon and high cloud penalties may differ;
- recommended exposure/equipment advice is outside the first scoring scope.

Do not merely add a constant bonus to camera mode. The component response
curves should differ.

## Cloud treatment

The detailed directional-cloud architecture is documented in
[Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md).
That document is authoritative for curved ray geometry, sub-grid overlap,
optical transmission, satellite conditioning, and cloud/fog validation.

Represent at minimum:

- total cloud fraction;
- low cloud fraction;
- middle cloud fraction;
- high cloud fraction;
- visibility/fog risk;
- precipitation obstruction;
- source/model agreement;
- current observation agreement.

Do not assume equal optical effects for all layers. Until optical-depth inputs
are available, document cloud-layer penalties as heuristics.

## Aurora treatment

Combine:

- spatial auroral intensity/oval data;
- observer geometry;
- recent solar-wind conditions and trends;
- geomagnetic context;
- observation type;
- darkness, Moon, terrain, and atmospheric obstruction.

Kp is context, not the final predictor.

## Viewing direction

Initial algorithm:

1. Identify relevant predicted auroral cells north of the observer.
2. Compute bearings from the observer to representative cells.
3. Estimate elevation using a documented nominal emission-altitude range.
4. Intersect the direction with the terrain horizon profile.
5. Return ranges, not false precision.

Example:

```json
{
  "cardinal": "NNW",
  "azimuth_range_deg": [325, 350],
  "elevation_range_deg": [8, 25],
  "confidence": "medium"
}
```

## Time-window aggregation

Evaluate candidate states every ten minutes initially.

Window aggregation should:

- group contiguous timestamps above a threshold;
- enforce a minimum useful duration;
- tolerate only explicitly defined short score dips;
- choose a representative peak time;
- retain score distribution and limiting-factor changes;
- avoid smoothing that invents a clear interval not present in the inputs.

## Uncertainty

Keep these concepts separate:

- `observation_score`: heuristic quality from 0–100;
- `forecast_confidence`: low/medium/high or a documented numerical index;
- `model_agreement`: ensemble/multi-model consistency;
- `data_completeness`: which scientific inputs are present;
- `data_freshness`: whether inputs are current enough for the requested mode.

Example explanation:

> Cape North has the best potential, but forecast confidence is low because
> only 7 of 20 ensemble members keep the northern horizon clear after midnight.

## Missing and stale data

Recommended initial policy:

- missing astronomy: fail evaluation;
- missing weather: fail evaluation;
- missing live aurora: fail a go-now recommendation, but allow clearly labelled
  forecast-only planning;
- missing terrain or light pollution: permit a degraded early-MVP result with
  explicit omissions;
- stale input: never silently substitute it as current data.

Provider errors should be typed and distinguish unavailable, stale, malformed,
out-of-domain, and unsupported conditions.

## Recommendation output

Return:

- location and coordinates;
- approximate travel distance/time;
- best contiguous observation window;
- leave-by time once routing exists;
- viewing azimuth/elevation range and cardinal direction;
- observation score and score version;
- component scores;
- confidence, agreement, completeness, and freshness;
- dominant limiting factor;
- plain-language explanation;
- diverse alternatives;
- source provenance.

## Validation and calibration

Archive every forecast used, including model initialization, lead time,
features, score version, and recommendation.

Compare against:

- GOES-observed cloud;
- surface visibility and ceiling;
- radar precipitation where relevant;
- optional structured user outcomes;
- later, vetted camera or all-sky observations.

Measure:

- Brier score for thresholded cloud events;
- clear/blocked classification precision and recall;
- clearing-time error;
- skill by model, lead time, season, region, and cloud layer;
- location-ranking regret;
- observation-score reliability once outcome data exists.

Potential structured outcomes:

- clearly visible naked eye;
- faint naked eye;
- camera only;
- not visible;
- user did not attempt;
- indeterminate report.

Only after enough representative outcomes should calibration methods such as
logistic calibration or isotonic regression turn model output into stated
probabilities.
