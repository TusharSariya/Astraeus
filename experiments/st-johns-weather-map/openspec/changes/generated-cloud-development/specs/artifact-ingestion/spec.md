## MODIFIED Requirements

### Requirement: Completeness and QC are computed, never asserted
An adapter SHALL declare a `RunManifest` naming the required canonical fields with their normalized units and levels, the required valid times, a minimum coverage fraction and the bounds. `complete` and `qc_passed` SHALL be produced by `validate_run` from the assembled dataset and the adapter's own decode errors. An adapter SHALL NOT hard-code `complete=True`, `qc_passed=True` or a `quality.status = "passed"` provenance literal. An adapter MAY additionally declare OPTIONAL variables - the steering winds, vertical velocity, and the low-level profile of relative humidity, temperature and geopotential height at 1015, 1000, 985, 970, 950, 925, 900, 875 and 850 hPa with the surface height - whose absence SHALL NOT lower the verdict; an optional variable that was fetched but will not decode SHALL still be a decode error. Every optional humidity variable SHALL carry its measured saturation-phase convention. Optional variables are display-derivation input only and SHALL never reach a reading.

#### Scenario: A declared field is absent
- **WHEN** a mandatory manifest field is missing from the assembled dataset
- **THEN** the verdict is `complete=False` with a `missing_field:<name>` flag, and the run is not publishable

#### Scenario: A field is present but entirely fill values
- **WHEN** a mandatory field carries no finite values
- **THEN** the verdict carries `empty_field:<name>` and the run is not publishable

#### Scenario: Units are not the normalized ones
- **WHEN** a field arrives carrying units other than the manifest's normalized unit
- **THEN** the verdict fails QC specifically (`bad_units:...`, `qc_passed=False`), because the data arrived but does not mean what the rest of the stack assumes

#### Scenario: A silently skipped variable
- **WHEN** the adapter could not decode one variable or URL and reports it as a decode error
- **THEN** the verdict carries `decode_error:<item>` and the run is refused, rather than publishing a thinner run as complete

#### Scenario: A required lead is missing
- **WHEN** a run does not carry a valid time the manifest declared as required
- **THEN** the verdict carries `missing_valid_time:<iso>` and the run is not publishable; times are compared as integer nanoseconds so a resolution difference cannot read as a missing lead

#### Scenario: Coverage below the declared minimum
- **WHEN** the mean finite-cell fraction across mandatory fields is below `min_coverage_fraction`
- **THEN** the verdict carries `coverage_below_threshold:<got><min>` and the run is not publishable

#### Scenario: The verdict cannot be raised back
- **WHEN** a validation result has been lowered
- **THEN** it is frozen, its only mutator can lower and never raise a verdict, and `quality.status` reports `failed` when QC failed, `suspect` when only completeness failed, and `passed` only when both hold

#### Scenario: A profile level the provider did not publish
- **WHEN** a run carries no relative humidity, temperature or height at one of the optional low-level pressure surfaces
- **THEN** the surface artifact still publishes as complete, the level is simply absent, and any derivation that needs the profile declines by name rather than substituting a neighbouring level

#### Scenario: A profile level fetched but undecodable
- **WHEN** an optional level's message downloads but will not decode
- **THEN** the verdict carries `decode_error:<item>` and the run is refused, exactly as for a mandatory field

#### Scenario: The phase convention travels with the humidity
- **WHEN** an optional humidity level is published
- **THEN** it carries `rh_phase_convention` and `rh_phase_basis` in its attributes, so a threshold calibrated on one model cannot be applied to the other unnoticed
