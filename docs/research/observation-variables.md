# Observation variables and success criteria

Last reviewed: 2026-08-10

## Purpose

This document records important observation variables that sit outside basic
event geometry, weather, terrain, and routing. It defines what `successful
observation` means for different observers, equipment, and celestial events.

The central relationship is:

```text
successful observation
    = event is physically present
    + target is geometrically visible
    + atmosphere transmits sufficient signal
    + target contrasts with the background sky
    + observer or equipment can detect it
    + conditions remain usable for the required duration
    + the site and journey are operationally feasible
```

For the aurora MVP, most of this architecture should remain deferred. Four
variables deserve early inclusion:

1. Minimum continuous observation duration.
2. Wind and gust limits.
3. Dew and frost risk.
4. A more explicit naked-eye-versus-camera contrast model.

## The missing core: define success

`Visible` is not a universal outcome. The same event can be:

- obvious to a dark-adapted naked-eye observer;
- faintly detectable with averted vision;
- detectable only with binoculars;
- camera-visible in one exposure;
- detectable only after stacking or image processing;
- geometrically present but indistinguishable from sky background;
- observable scientifically but not visually impressive.

Every event module should define versioned success classes. An initial common
taxonomy is:

```text
clear_naked_eye
faint_naked_eye
optical_aid_visible
camera_single_exposure
camera_stacked_detection
instrumental_detection
not_detected_clear_attempt
unobservable
unknown
```

`Unobservable` means that clouds, obstruction, daylight, equipment failure, or
another condition prevented a valid attempt. It must not be used as a negative
event label.

## 1. Target-to-background contrast

Detection depends on target signal relative to background rather than target
brightness alone:

```text
detectability approximately scales with
target apparent signal / sky-background signal
```

Relevant variables include:

- apparent surface brightness;
- integrated brightness;
- angular size and spatial structure;
- emission or reflected-light spectrum;
- atmospheric transmission by wavelength;
- Moon altitude, phase, separation, and scattering;
- twilight and airglow;
- directional artificial skyglow;
- cloud and aerosol scattering;
- observer dark adaptation;
- equipment sensitivity and spectral response.

An object with high total brightness but low surface brightness can be harder to
see than a compact source. Therefore an event module should not represent all
targets using apparent magnitude alone.

### Background-sky state

Suggested normalized fields:

```text
sky_luminance_estimate
sky_brightness_band
moon_scattering_penalty
twilight_background
directional_light_dome_penalty
cloud_backscatter_penalty
aerosol_scattering_penalty
airglow_or_unknown_background
```

Until locally calibrated, these should be reported as model-derived quality
components rather than physical photometric truth.

## 2. Observer and equipment response

The original naked-eye/camera distinction is necessary but too broad for later
events.

### Naked-eye profile

Potential variables:

- corrected or uncorrected visual acuity;
- dark-adaptation duration;
- experience level;
- colour perception;
- willingness to use averted vision;
- age-sensitive contrast response, if voluntarily provided;
- minimum acceptable visual quality.

Astraeus should avoid collecting medical or demographic data that do not
materially improve recommendations. Defaults and optional experience settings
are preferable.

### Optical-aid profile

For binoculars or telescopes:

- aperture;
- focal length and focal ratio;
- magnification;
- true field of view;
- mount type;
- tracking capability;
- minimum and maximum target altitude;
- filter transmission;
- wind and vibration tolerance.

### Camera profile

Potential variables:

- sensor and spectral response;
- lens or telescope aperture;
- focal length and focal ratio;
- field of view;
- exposure duration;
- ISO or gain;
- read noise and dark current where material;
- filter bandpass;
- tripod or mount type;
- tracking accuracy;
- stacking policy;
- acceptable motion blur;
- desired output: evidence, snapshot, timelapse, or high-quality image.

The MVP does not need a complete camera simulator. It does need separate
response curves for naked-eye and ordinary-camera observation rather than a
constant camera bonus.

## 3. Observation duration and continuity

A high score at one instant does not establish a usable opportunity.

Each event should define:

```text
minimum_continuous_usable_minutes
preferred_continuous_usable_minutes
minimum_total_usable_minutes
allowed_interruption_minutes
setup_minutes
teardown_minutes
critical_subwindows
```

Examples:

- A bright meteor or aurora photograph may need seconds.
- A useful aurora outing may require a stable 30–60-minute window.
- Totality has a short, non-negotiable critical interval.
- A meteor shower benefits from long continuous exposure.
- Deep-sky imaging may tolerate cloud interruptions but requires substantial
  accumulated integration time.

Window aggregation must consider continuity, not merely average score.

## 4. Wind and mechanical stability

Wind affects:

- tripod vibration;
- telescope tracking and guiding;
- long-exposure sharpness;
- equipment tipping risk;
- wind-borne salt spray, dust, or snow;
- thermal comfort and wind chill;
- whether an exposed coastal site is safe.

Relevant variables:

```text
sustained_wind_m_s
gust_m_s
gust_frequency
wind_direction
terrain_exposure
crosswind_relative_to_equipment
user_or_equipment_wind_limit
salt_spray_risk
```

Wind should act as an equipment- and site-specific operational gate rather than
a universal astronomical penalty.

## 5. Dew, frost, condensation, and icing

An optically clear sky can still become unusable when lenses, mirrors, filters,
or electronics collect condensation or frost.

Potential predictors:

- air temperature;
- dew point and frost point;
- relative humidity;
- surface and sky-facing radiative cooling;
- wind speed;
- prior fog or precipitation;
- rapid temperature transitions;
- sea-spray exposure;
- expected observation duration.

Output should distinguish:

```text
atmospheric_fog_risk
optical_surface_dew_risk
frost_or_icing_risk
```

Possible recommendation:

> Sky conditions are favourable, but lens-dew risk becomes high after 00:40.
> A dew heater or frequent lens checks are recommended.

For V1, a conservative temperature/dew-point-spread heuristic is sufficient if
its limitations are explicit.

## 6. Astronomical seeing

Seeing describes image degradation from atmospheric turbulence. It is
important for:

- planetary and lunar imaging;
- double stars;
- high-resolution solar or eclipse imaging;
- long-focal-length astrophotography.

It is usually not a limiting variable for wide-field aurora or naked-eye meteor
observation.

Potential inputs include:

- boundary-layer stability;
- vertical temperature gradients;
- wind shear;
- jet-stream wind;
- model-derived turbulence or `Cn²` profiles;
- seeing-monitor or star-image observations.

Seeing belongs in applicable event modules and should not enter the aurora MVP
score merely because the field is available.

## 7. Wavelength-dependent transmission

Cloud, aerosol, molecular scattering, skyglow, sensors, and filters are
wavelength-dependent.

Examples:

- auroral green emission near 557.7 nm;
- auroral red emission near 630.0 nm;
- hydrogen-alpha emission near 656.3 nm;
- broadband stellar and galaxy imaging;
- blue-rich twilight scattering;
- infrared-sensitive equipment.

The long-term atmospheric interface should therefore support:

```text
transmission(wavelength or bandpass)
background_radiance(wavelength or bandpass)
target_signal(wavelength or bandpass)
equipment_response(wavelength or bandpass)
```

The MVP can use broadband proxies while preserving a data model that does not
assume one scalar transparency value is universally valid.

## 8. Ground and local site conditions

Legal access is not sufficient for operational use. A site may be unusable
because of:

- snow depth or absent plowing;
- ice, mud, or flooding;
- storm surge, waves, or unsafe cliffs;
- wildfire restrictions;
- unstable or uneven tripod ground;
- active construction;
- insects or wildlife;
- wind exposure;
- salt spray;
- insufficient setup area;
- traffic, crowds, or headlights.

For the Atlantic Canadian aurora MVP, prioritize:

```text
road and parking condition
snow and ice risk
coastal wave/surge exposure
safe setup area
closure status
```

These operational variables should constrain a recommendation separately from
the scientific observation score.

## 9. Observer mobility and comfort constraints

Potential optional request fields:

```text
maximum_walking_distance_m
maximum_slope
wheelchair_or_step_free_access_required
parking_required
maximum_cold_or_wind_exposure
shelter_required
maximum_time_away
travelling_alone
```

These are constraints on candidate suitability, not celestial quality. Avoid
collecting unnecessary sensitive information; request functional constraints
instead of diagnoses.

## 10. Communications and emergency resilience

Remote dark sites may lack:

- cellular coverage;
- live rerouting;
- reliable online navigation;
- emergency access;
- fuel or vehicle charging;
- safe turnaround space;
- weather alerts after departure.

A travel recommendation should be exportable as an offline package containing:

- coordinates and route summary;
- offline map or compatible navigation handoff;
- observation window and viewing direction;
- last forecast retrieval time;
- source freshness and uncertainty;
- access and safety notes;
- fallback destination;
- conditions that should cause the user to abandon the attempt.

## 11. Event-direction evolution

Target direction is a function of time:

```text
azimuth(t)
elevation(t)
horizon_clearance(t)
cloud_ray_intersection(t)
moon_separation(t)
light_dome_intersection(t)
```

A site that is excellent at the beginning can become obstructed or illuminated
later. The optimizer must evaluate the changing direction throughout the
window, including eclipse contacts and other critical phases, rather than use a
single peak-time direction.

## Aurora-specific variables

An aurora is a three-dimensional luminous volume, not a target fixed to the
celestial sphere.

Important variables include:

- corrected geomagnetic latitude;
- magnetic local time;
- auroral emission altitude and vertical distribution;
- line-of-sight length through the emitting volume;
- visibility equatorward of the precipitation footprint;
- diffuse aurora versus discrete arcs;
- substorm phase and motion;
- optical radiance or an emission proxy;
- green/red emission balance;
- camera and naked-eye spectral response;
- foreground haze and cloud backscatter;
- directional artificial-light contrast.

The aurora score should eventually distinguish physical activity, geometric
opportunity, atmospheric transmission, and observer/equipment detectability.

## Eclipse-specific variables

Solar and lunar eclipse modules should add:

- visibility at each contact rather than only maximum eclipse;
- critical-contact duration;
- Sun or Moon altitude and azimuth throughout the event;
- directional horizon clearance throughout the path;
- path-centre and path-edge distance;
- Delta T and path uncertainty where relevant;
- lunar-limb corrections for precise solar contact timing;
- setup time and equipment readiness;
- traffic, crowds, parking capacity, and road closures;
- visual, photographic, or scientific-timing objective;
- solar eye-safety and filter requirements.

For a major eclipse, event traffic and capacity can dominate ordinary routing
assumptions.

## Deep-sky-specific variables

Deep-sky optimization should eventually include:

- target surface brightness and angular size;
- altitude, azimuth, and airmass over time;
- meridian transit and mount limits;
- Moon separation and spectral sky background;
- seeing and transparency;
- field rotation;
- obstruction over the complete imaging sequence;
- camera, telescope, and filter response;
- expected usable integration minutes;
- guiding and wind limitations.

A useful objective is expected usable integration time, not peak instantaneous
quality.

## Meteor-shower and comet-specific variables

Meteor showers require:

- radiant altitude over time;
- expected activity profile and uncertainty;
- Moon interference;
- unobstructed sky fraction rather than only one direction;
- continuous observation duration;
- limiting stellar magnitude;
- whether the goal is visual counts, photography, or radio detection.

Comets require:

- uncertain observed brightness, coma, and tail morphology;
- altitude and airmass;
- elongation and twilight;
- tail orientation and field of view;
- naked-eye, binocular, telescope, or camera objective;
- orbit-solution and brightness-model freshness.

## Sunset and sunrise-specific variables

A colourful sunset or sunrise is not determined by geometric horizon crossing
alone. Future modelling would require:

- whether sunlight reaches candidate cloud volumes;
- whether the observer can see those illuminated volumes;
- cloud height, thickness, and optical depth;
- aerosol type and vertical distribution;
- humidity and multiple scattering;
- terrain and Earth-curvature occlusion;
- colour, spatial structure, and duration success criteria.

This remains outside the aurora MVP.

## Value of moving

The decision objective should not be the highest destination score. It should
approximate:

```text
expected observation improvement after arrival
    × probability the improvement persists
    × usable duration after setup
    - travel cost
    - recommendation-instability cost
    - access and safety risk
```

This allows the correct output to be:

> The coastal site is slightly better, but the improvement is too uncertain to
> justify a 45-minute drive. Remain at your current location.

The minimum improvement required to recommend travel should increase with
travel duration, weather uncertainty, access uncertainty, and event
irreversibility.

## Proposed domain model

### ObservationEvent

```text
event_type
physical_state_or_forecast
direction_over_time
brightness_or_signal_model
success_classes
required_duration
critical_subwindows
event_specific_constraints
```

### ObservationProfile

```text
observation_mode
equipment_profile
detectability_threshold
setup_and_teardown_duration
wind_and_dew_limits
mobility_and_comfort_constraints
minimum_desired_quality
```

### CandidateSiteState

```text
directional_horizon
access_and_parking
ground_and_road_conditions
wind_exposure
connectivity_and_safety
usable_setup_area
site_capacity
source_freshness
```

### ScoredOpportunity

```text
physical_event_potential
geometric_visibility
atmospheric_transmission
target_background_contrast
observer_equipment_detectability
usable_duration
operational_feasibility
travel_adjusted_utility
uncertainty_and_provenance
```

The structures should remain compositional. Event modules should only require
variables material to their success criteria.

## Aurora MVP scope recommendation

### Add now

1. `minimum_continuous_usable_minutes` in the request or observation profile.
2. Sustained-wind and gust fields with conservative camera/tripod limits.
3. A dew/frost-risk component using temperature, dew point, humidity, wind, and
   observation duration.
4. Separate naked-eye and camera response curves based on target/background
   contrast assumptions.

### Preserve in the architecture but defer

- detailed camera sensor simulation;
- astronomical seeing;
- wavelength-resolved radiative transfer;
- personalized human-vision modelling;
- live cellular-coverage scoring;
- crowd and parking-capacity prediction;
- generalized telescope/mount modelling;
- sunset colour prediction.

### Do not add as one universal score

- seeing for aurora;
- telescope tracking quality for naked-eye observation;
- ground comfort as a substitute for physical visibility;
- event-specific variables that do not affect the selected event;
- speculative high-precision variables without validation data.

## Validation implications

Historical and prospective observation records should include the observation
profile. Otherwise the same physical conditions can produce contradictory
labels with no way to explain the difference.

At minimum, collect:

```text
event and success class
naked-eye versus camera
basic equipment class
attempt start/end
setup completion time
clear, obstructed, or unobservable state
wind/dew equipment impacts
directional sky condition
user-reported outcome quality
```

Equipment-specific calibration must use held-out observations and avoid
converting camera-only outcomes into naked-eye positives.

## Relationship to other research

- [Scientific and scoring design](scientific-design.md) defines gates,
  components, provenance, and calibration.
- [Risks and uncertainties](risks-and-uncertainties.md) tracks forecastability,
  label quality, false precision, access, and product risks.
- [Cloud and fog line-of-sight forecasting](cloud-fog-line-of-sight.md) defines
  directional atmospheric transmission.
- [Observation-site obstructions and public access](site-obstructions-and-access.md)
  defines horizon, access, and safety evidence.
- [Historical celestial events](historical-celestial-events.md) defines event
  reconstruction and outcome semantics.
- [Implementation plan](implementation-plan.md) controls delivery sequence and
  MVP scope.
