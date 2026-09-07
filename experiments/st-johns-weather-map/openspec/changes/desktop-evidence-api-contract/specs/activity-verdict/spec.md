## Purpose

Formalize the already-selected server behavior in Wayfinder #38 issues
[#48](https://github.com/TusharSariya/Astraeus/issues/48),
[#49](https://github.com/TusharSariya/Astraeus/issues/49) and
[#64](https://github.com/TusharSariya/Astraeus/issues/64), under the existing
[owner authorization](../../../desktop-evidence-workbench/acceptance.md).
The September 7 timestamp-demand/finite-cache direction supersedes the older
Postgres persistence, ingest-poller and warm-up dependencies. This is the
experimental Activity contract, not an operational safety certification.

## ADDED Requirements

### Requirement: One registered evaluator reads versioned profile files
The API SHALL evaluate the four registered profiles through one
`activity_verdict` version 1 method. The method SHALL cite the activity-profile
contract and ADR 0002, declare a single `profile` input from the activity-profile
registry, output `verdict_score` with units `1` and range 0 to 100, and refuse
out-of-range output. The body SHALL enumerate the actual driving fields on its
rows; the single profile input SHALL NOT hide their provenance. The method
SHALL be reader-switchable; a method refusal SHALL return its refusal code and
no manufactured verdict body. Profiles SHALL remain declarative, validated
registry files with version increments for changes to criteria, anchors,
weights, hard stops or windows. A malformed profile SHALL be individually
unavailable without substitution.

#### Scenario: Scoring is disabled
- **WHEN** the registered method refuses evaluation
- **THEN** the response names the refusal and contains no substituted score or verdict

### Requirement: Verdicts retain the selected state precedence and evidence
`GET /verdicts` SHALL return the four profiles in fixed order: running,
astronomy, aurora, landscape photography, at one exact point/site and instant.
The existing pressure-level `/profile` route SHALL keep its meaning. Every
verdict SHALL carry profile id/version, method/version, Focus, tier, resolution,
evaluation time, computation time/cache state, hard stops, criteria, geometric
window, threshold-override provenance, quality/freshness and built-in stack.

State SHALL use first-match precedence `unresolved`, `stopped`, `unchecked`,
`unscorable`, `outside_window`, `scored`. Lower conditions SHALL remain flags.
Unresolved geometry SHALL name the absent field. A fired hard stop SHALL prevent
all grading and produce an empty criteria list with that reason. An unknown
hard stop SHALL be as explicit as a fired stop; grades MAY be evaluated but
score SHALL be withheld. Score SHALL exist only in `scored` or `outside_window`.
Coverage below the profile's floor SHALL withhold the score. Nothing SHALL rank
profiles, recommend a site, or claim clearance from missing evidence.

#### Scenario: A hard stop fires outside the geometric window
- **WHEN** precipitation meets the profile's hard-stop threshold outside its window
- **THEN** state is stopped, outside-window remains a flag, score is absent and no graded criterion is evaluated

#### Scenario: An unknown hard stop has otherwise usable grades
- **WHEN** a hard-stop value is absent but graded fields are usable
- **THEN** state is unchecked, grades and coverage remain inspectable, and score is withheld

### Requirement: One eligible source supplies a criterion at its native time
The evaluator SHALL use deployment-wide source precedence by tier: HRDPS,
RDPS, then supported global products in core; supported global products in
planning. Each field SHALL have one chosen source, never an average. Selection
SHALL use existing frame-exact point semantics and the source's own staleness
tolerance. Falling to the next source SHALL name skipped sources and mark
`fell_to_next_source`. Source and field mappings SHALL be explicit. A source
registry declaration alone SHALL NOT establish a working field path.

Failed quality SHALL leave the numeric evidence inspectable with
`quality_failed` but contribute no evaluated weight. Suspect and unknown
quality SHALL remain evaluated and propagate by existing `QUALITY_SEVERITY`.
Verdict quality SHALL be no better than its worst evaluated input and carry a
derived flag; freshness SHALL be the oldest evaluated input's freshness.
Freshness SHALL NOT add a new gate inside the source's staleness tolerance.
Generated-display and otherwise inadmissible derivation inputs SHALL NOT score.

#### Scenario: A primary source has no exact frame
- **WHEN** the next eligible source has the exact requested field/time
- **THEN** one value from that source is selected and the skipped primary is disclosed

#### Scenario: Quality failed but a numeric value exists
- **WHEN** a criterion's returned quality is failed
- **THEN** its value remains evidence, its evaluated weight is zero and its reason is quality_failed

### Requirement: Grading curves and overrides follow the recorded mechanics
The registered v1 curve set SHALL be step, linear, exponential and band.
Each criterion SHALL name a curve and named threshold anchors; anchors SHALL
resolve to that field's units. Step SHALL use the declared comparison. Linear
SHALL progress from zero loss at start to full loss at full, clamped to [0,1],
with direction from the comparison. Exponential SHALL use
`1 - exp(-((value - start)/scale)^k)` beyond start in the declared direction,
with positive scale and k (default 2), and zero loss before start. Band SHALL
have an inclusive zero-loss comfort interval and linear ramps to its outer
anchors; `low_cap` SHALL cap only its low-side loss. Invalid anchor order,
units, curve, comparison or parameter SHALL fail validation, not be repaired.

Every field-unit anchor SHALL be a named existing threshold parameter and
record defaults/overrides through the existing override mechanism. Dimensionless
shape parameters SHALL use units `1` and be non-overridable in v1. Repeated
`override=<threshold>:<value>` query parameters SHALL be validated; unknown,
non-finite or invalid overrides SHALL return 422. Provenance SHALL explicitly
say `no_override_in_force` when appropriate. Client storage/sharing of overrides
SHALL follow #48; URLs SHALL include them only through explicit share-with-overrides.

Score SHALL be `round(100 * (1 - sum(weight * loss) / evaluated_weight))`.
Limiting criterion SHALL be largest `weight * loss`, ties by profile file order.
Active positive declared weights SHALL sum to 1.0; zero-weight context SHALL NOT
be graded. Coverage SHALL expose declared, reachable (declared minus blocked),
evaluated weight and floor 0.60. Hard stops SHALL be outside coverage. Null and
aged-out inputs SHALL reduce evaluated weight; blocked inputs SHALL reduce
reachable weight. Applicability SHALL be explicit and based only on returned
geometry/tier evidence; missing applicability inputs SHALL not imply applicability
or favorable loss. The body SHALL disclose applicability and its evidence.

#### Scenario: A band has a low-side cap
- **WHEN** landscape cloud is below its low outer anchor with low_cap 0.5
- **THEN** its loss is 0.5, while the high-side outer anchor still has loss 1

#### Scenario: The Moon is below the horizon
- **WHEN** returned Moon altitude is at or below zero
- **THEN** the Moon-brightness criterion is explicitly not applicable and no missing altitude is inferred from illumination alone

### Requirement: Profile anchors and active budgets follow the adopted staged design
The following are the owner-selected active designs from #64, in native units.
Only an admitted, verified field path SHALL enter an active weight budget.
Missing producers, mappings, geometry or methods SHALL be recorded as named
admission/implementation residuals with intended curve and replacement role;
they SHALL NOT silently enter weights or be represented as verified by a fixture.
Replacing a proxy SHALL require the recorded replacement path and a new profile
version; correlated proxy and replacement SHALL NOT be graded simultaneously.

The active-weight normalization explicitly selected in #64 SHALL preserve the
relative weights in the intended design: divide each admitted positive intended
weight by the sum of admitted positive intended weights. The profile/version
SHALL record both intended and effective active weights, excluded field paths
and the reason for each exclusion. No eligible weight budget SHALL mean no
score. A null, failed-QC, blocked or aged-out reading from an already admitted
path SHALL NOT remove that path from the active budget or trigger normalization
at request time; its coverage effect follows the existing rules above. Admission
or replacement changes SHALL increment the profile version. This staged budget
SHALL NOT be described as complete intended field coverage.


| Profile / field | Curve and anchors | Weight |
| --- | --- | --- |
| Running temperature_2m | band outer -27 / 30, comfort 0 / 20 degC | 0.25 |
| Running dew_point_2m | linear ge 15 to 24 degC | 0.25 |
| Running downward_shortwave_flux | linear ge 300 to 900 W m-2 | 0.10 |
| Running pm2_5_surface | linear ge 3e-8 to 1e-7 kg m-3 | 0.15 |
| Running wind_speed_10m | linear ge 5.5 to 10.8 m s-1 | 0.10 |
| Running wind_gust_10m | linear ge 10.8 to 17.2 m s-1 | 0.05 |
| Running visibility | linear le 5000 to 1000 m | 0.10 |
| Astronomy cloud_high | linear ge 10 to 90 percent | 0.20 |
| Astronomy cloud_middle | linear ge 10 to 70 percent | 0.10 |
| Astronomy cloud_low | linear ge 10 to 50 percent | 0.15 |
| Astronomy precipitable_water | linear ge 10 to 30 kg m-2 | 0.05 |
| Astronomy moon_illuminated_fraction | linear ge 0.20 to 1; moon_altitude > 0 | 0.20 |
| Astronomy wind_speed_10m | linear ge 5.4 to 15 m s-1 | 0.15 |
| Astronomy relative_humidity_2m | linear ge 70 to 90 percent, interim proxy | 0.15 |
| Aurora kp_index | linear le 5 to 1 | 0.35 |
| Aurora hp30_index | linear le 5 to 1 | 0.15 |
| Aurora moon_illuminated_fraction | linear ge 0.20 to 1; moon_altitude > 0 | 0.15 |
| Aurora north-sector cloud_high | linear ge 10 to 90 percent | 0.35 |
| Landscape Sun-sector total_cloud_opacity | band outer 0 / 100, comfort 20 / 70 percent, low_cap 0.5 | 0.60 |
| Landscape wind_speed_10m | linear ge 5.7 to 14.4 m s-1 | 0.20 |
| Landscape sun_altitude | band outer -12 / 12, comfort -6 / 6 degrees | 0.20 |

Running SHALL remove relative humidity from grading. Aurora's Kp/Hp30 losses
SHALL decrease as activity rises; solar wind and Bz SHALL remain context.
Landscape's cloud bearing SHALL follow returned sun_azimuth, never fixed 90 degrees.
The existing lightning-density, generic active-alert and 2.5 mm h-1 rain stops
for running, 90 percent total-cloud and 1000 m visibility stops for astronomy,
and 2.5 mm h-1 rain stop for landscape SHALL retain their temporary meanings.
Typed CAP splits, 16 km lightning extent, 30-minute holds, optics precipitation,
coastal wave/surge danger and categorical curves SHALL NOT activate without
their separately verified contracts. Road state, light pollution and local
magnetometer gaps SHALL remain explicit. The replacement targets, variants and
context/admission classifications in #64 SHALL remain residual tasks; they SHALL
NOT silently be treated as active implementations by this contract.

#### Scenario: The intended design includes a path not yet admitted
- **WHEN** a profile has intended weights 0.25 and 0.75 but only the first field
  has an admitted verified path
- **THEN** its effective active weight is 1.0, the intended weights and excluded
  path remain disclosed, and a later missing reading still reduces coverage
  instead of being removed from the active budget

#### Scenario: A replacement source is only catalogued
- **WHEN** humidex has a registry entry without its verified data path
- **THEN** its intended replacement is recorded, and the current thermal proxy is not silently replaced

### Requirement: Geometric windows and strips share the Bench instant
The evaluator SHALL reuse the registered DE442 window rules and provenance.
Current/next intervals SHALL be geometric opportunities, never a next-good-weather
recommendation. Unresolved geometry SHALL name absent fields and supply no guessed
window. An arbitrary point SHALL return no_site for horizon/sector inputs and
SHALL NOT borrow the nearest site's horizon or sector values.

`GET /verdicts/series` SHALL return all four profiles within explicit finite
window, sample, duration, byte and concurrent-acquisition bounds. Core strip
resolution SHALL be hourly; planning SHALL use the coarsest driving source's
native resolution, disclosed per verdict. Cells SHALL be drawn only for issued
driving-source times at the applicable step, retaining gaps and unqueried spans.
An off-step instant verdict MAY have less coverage; the client SHALL NOT invent
a full-coverage cell or interpolate a score. Clicking a cell SHALL move the
shared Focus. Planning scores SHALL render as bands, not precise numbers.

#### Scenario: A planning source has no issued cell
- **WHEN** no driving source issued evidence at a candidate strip instant
- **THEN** no scored cell is invented there and the unqueried/absence state remains explicit

### Requirement: Verdict acquisition is bounded request-time work with finite caching
Verdicts SHALL compute on demand from existing selected-time source queries.
Cache keys SHALL include exact Focus/time, profile and method versions, overrides
and relevant input identities. A cache hit SHALL not imply fresh provider
revalidation. Fixed expiry, concurrent misses, failures and failed replacement
SHALL be verified. Expired results SHALL not be relabelled current. Numeric
bounds and cache implementation are routine delegated choices requiring tests.
No Postgres cache table, artifact archive, scheduled site precomputation, ingest
poller or boot warm-up SHALL be required. No raw provider payload SHALL enter Git.

#### Scenario: An expired verdict cannot be recomputed
- **WHEN** a new selected-time read fails after cache expiry
- **THEN** the response states unavailable and does not silently serve the expired score

### Requirement: Built-in profile stacks preserve unavailable entries
Each profile SHALL declare coverage_floor and an ordered saved_stack with layer
ids/opacities. The audit SHALL validate ids against declared layer catalogue,
not currently served layers. Unknown ids SHALL fail validation. The selected
#48 stacks SHALL be used, with RAQDPS PM2.5 as the running smoke entry. A
catalogued but unserved entry SHALL remain visibly not served and draw nothing.
Stack loading SHALL replace the Map stack through its existing controls.
Top-first selections SHALL be:

- Running: lightning, radar, CAP alerts, RAQDPS PM2.5, HRDPS precipitation
  accumulation, HRDPS wind speed, HRDPS temperature, AQHI.
- Astronomy: HRDPS total cloud opacity, GFS high/middle/low cloud, HRDPS WEonG
  liquid fog visibility, GOES night IR.
- Aurora: GFS high cloud, HRDPS total cloud opacity, HRDPS WEonG liquid fog
  visibility, GOES night microphysics.
- Landscape: HRDPS total cloud opacity, HRDPS WEonG liquid fog visibility,
  HRDPS precipitation accumulation, HRDPS wind speed, GOES natural colour.

Wave height, seeing, transparency and Kp SHALL remain off these stacks.

#### Scenario: A built-in stack includes an unserved layer
- **WHEN** the reader loads that profile stack
- **THEN** the missing layer remains listed with its reason and no substitute is drawn
