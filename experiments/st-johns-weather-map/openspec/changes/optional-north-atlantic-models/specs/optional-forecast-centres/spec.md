## ADDED Requirements

### Requirement: Optional forecast evidence passes explicit admission gates
An optional numerical-weather-prediction source SHALL contribute no value until
its official product identity, access path, licence, full evidence-box coverage,
field inventory, grid, units, temporal semantics, missing-value behavior,
cadence, latency, completeness and provenance are recorded. A successful point
request at St. John's SHALL NOT establish coverage. Coverage SHALL include all
four corners of `45.0..50.5 N, 58.0..46.0 W` and the declared upstream sector.
Availability alone SHALL NOT establish forecast skill.

#### Scenario: A product answers at St. John's but fails east of the Avalon
- **WHEN** a regional product returns a value at St. John's but fails a corner
  or upstream-sector probe
- **THEN** it remains conditional and contributes no optional evidence

#### Scenario: A full-box subset succeeds once
- **WHEN** a source returns a valid GRIB2 subset over the complete box for one
  run
- **THEN** coverage is recorded as observed for that run, while cadence,
  latency, boundary quality and skill remain unverified

### Requirement: Optional products do not multiply a forecast centre's vote
At most one deterministic product per forecast centre SHALL contribute to a
centre-level comparison at one valid instant. Other deterministic products from
that centre SHALL remain named scenarios. Ensemble members SHALL remain a
labelled within-family distribution and SHALL NOT become independent centre
votes. A product SHALL retain its producer-centre identity when delivered by an
intermediary.

#### Scenario: Four NOAA product families are present
- **WHEN** comparable GFS, RAP, NAM and GEFS evidence exists for an instant
- **THEN** the comparison contains at most one NOAA deterministic centre
  contribution, with the others exposed as named scenarios or an ensemble
  distribution

#### Scenario: A UKMO value arrives through Open-Meteo
- **WHEN** Open-Meteo delivers a UKMO Global value
- **THEN** its centre is UK Met Office, its intermediary and transformations are
  named, and it receives no extra vote for passing through Open-Meteo

### Requirement: Optional evidence preserves physical comparability
The system SHALL numerically combine forecast fields only when the field
catalogue declares their quantity, vertical support and temporal semantics
comparable. Non-comparable cloud fields MAY be displayed as labelled
disagreement but SHALL NOT be averaged, voted or silently normalized into one
quantity. Missing, stale, failed-QC, boundary-failed or unavailable evidence
SHALL remain absent and SHALL NOT be replaced by another optional model.

#### Scenario: Opacity-weighted and geometric cloud are both available
- **WHEN** HRDPS opacity-weighted total cloud and GFS geometric-overlap total
  cloud are displayed for the same instant
- **THEN** both retain their field keys and definitions and no numerical mean or
  consensus fraction is produced from them

#### Scenario: An optional endpoint fails
- **WHEN** an admitted optional source returns an error, invalid content or an
  all-null requested subset
- **THEN** its evidence is absent naming the source and failure, with no fixture,
  previous run or neighbouring model substituted as current evidence

### Requirement: Optional families have explicit eligibility tiers
Native official ECMWF IFS/ENS/AIFS and DWD ICON Global products MAY proceed
through optional-evidence verification. RAP and the NAM parent grid MAY proceed
as NOAA short-range candidates because full-box GRIB2 subsets were observed on
2026-09-03, but SHALL remain non-contributing until their remaining gates pass.
ARPEGE World and UKMO Global delivered through Open-Meteo SHALL remain research
comparisons, never display-primary and never derivation inputs, while their
native access or terms gates remain unresolved. RRFS SHALL remain conditional
until a stable official operational feed and full-box coverage are recorded.
HRRR and any regional model without documented full-box coverage SHALL NOT be
scheduled for this evidence box.

#### Scenario: RRFS appears in experimental graphics
- **WHEN** NOAA displays RRFS output but no stable operational distribution and
  complete box probe have been recorded
- **THEN** RRFS remains conditional and no adapter promises its data

#### Scenario: A geographically nearby centre publishes a regional model
- **WHEN** an Icelandic, Greenlandic, Nordic, British, French, Spanish,
  Portuguese or Russian regional model has no documented grid covering the box
- **THEN** national proximity or interest does not admit it and it contributes
  no value

### Requirement: Earth-2 inference remains generated and hardware claims are measured
Earth2Studio SHALL be treated as an inference framework and SHALL NOT be named
as an observation, forecast centre, or evidence source. A FourCastNet output
SHALL be `generated-here` and SHALL name the initialization source, exact model
and checkpoint digest, Earth2Studio/runtime version, precision, device,
seed/member, inputs and transformations. FourCastNet 1 and FourCastNet 3 SHALL
NOT satisfy critical cloud evidence because their declared outputs contain no
direct cloud, fog, ceiling or visibility field. Any cloud diagnostic built from
their moisture and thermodynamic fields SHALL be a separately registered and
verified construction.

GPU-memory catalogue badges SHALL be recorded as recommendations, not hard
minimums. CPU feasibility SHALL require a successful full-checkpoint inference
step with measured wall time and peak memory. A dummy-model test, checkpoint
load, `.to("cpu")`, or device-generic wrapper SHALL NOT be reported as successful
CPU inference. Until that measurement exists, FourCastNet 3 CPU inference SHALL
be labelled `unverified`, neither `unsupported` nor `viable`.

#### Scenario: FourCastNet 3 loads on CPU
- **WHEN** the complete checkpoint loads and moves to CPU but no full forecast
  step completes
- **THEN** CPU loading is recorded as successful and CPU inference remains
  unverified

#### Scenario: A FourCastNet forecast is displayed
- **WHEN** this deployment runs FourCastNet from a GFS initial condition
- **THEN** the value is labelled generated-here, names GFS and its run as the
  initializer, names the checkpoint and runtime, receives no NVIDIA forecast-
  centre vote, and supplies no direct-cloud claim

#### Scenario: A generic ForecastNet implementation is discovered
- **WHEN** an untrained or locally trained generic time-series ForecastNet is
  evaluated for admission
- **THEN** it is not registered as a weather provider; any trained output is a
  separate generated method requiring its own dataset, baseline and validation

### Requirement: WeatherNext 3 remains an optional restricted Google ensemble
WeatherNext 3 MAY proceed through optional-provider validation because its
published global product includes 64 members, hourly surface output and direct
total, high, medium and low cloud-cover fields at 0.1 degrees. It SHALL remain
credential-required, restricted and non-contributing until owner terms review,
allowlisted access, authenticated full-box reads, schema fixtures, measured
latency and cost, cloud-semantic comparability and Avalon skill validation pass.

Its 64 members SHALL constitute one Google family rather than 64 centre votes.
Provenance SHALL name initialization, publication and retrieval times, product
version, access surface, member or statistic identity, terms class and the
documented ECMWF HRES analysis input dependency. Hourly initialization SHALL
NOT be represented as one-hour availability. WeatherNext 3 SHALL NOT satisfy
fog, visibility, ceiling, cloud-base or cloud-top evidence unless a later
published product and accepted field contract explicitly provide it.

#### Scenario: Anonymous access is denied
- **WHEN** an unauthenticated WeatherNext bucket or object request returns `401`
  or `403`
- **THEN** the source remains credential-required and absent, and no cached,
  fixture or neighbouring-model value substitutes for live evidence

#### Scenario: An interim hourly forecast is published
- **WHEN** a WeatherNext 3 interim cycle becomes retrievable
- **THEN** its initialization, publication and retrieval times are distinct,
  its 48-hour scope is preserved, and its hourly cycle is not described as
  one-hour-fresh evidence

#### Scenario: Restricted real-time output is displayed
- **WHEN** WeatherNext data about the future or a time less than one hour ago is
  used in a value-added output
- **THEN** the applicable restricted terms, attribution and disclaimer are
  preserved, and recolouring, cropping or regridding alone does not relabel the
  underlying data as unrestricted

#### Scenario: Older WeatherNext evidence is retained
- **WHEN** WeatherNext data becomes at least one hour old and is handled under
  the published CC BY 4.0 class
- **THEN** its attribution and retrieval-time terms provenance remain attached
  and no broader right is inferred for the restricted real-time product
