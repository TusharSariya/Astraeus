## ADDED Requirements

### Requirement: HRDPS 00-24 hour acquisition is admitted as one complete operation

The experimental HRDPS adapter SHALL reserve its complete 00-24 hour receive,
temporary-filesystem, staged-store and measured allocation margin before the
first payload-bearing listing. Every listing and GRIB response SHALL have a
finite enforced byte ceiling. The Linux worker SHALL enforce a finite memory
cgroup and temporary filesystem ceiling. Unsupported enforcement SHALL refuse
before discovery. No missing or oversized response may be replaced or thinned.

#### Scenario: A continental crop retains a full-grid coordinate allocation

- **WHEN** a cropped field still shares memory with either full-grid coordinate
- **THEN** the adapter detaches the loaded crop before retaining it for the run

#### Scenario: A bound cannot fit

- **WHEN** the durable store reservation, temporary filesystem, memory cgroup, listing or payload ceiling cannot cover the complete operation
- **THEN** HRDPS is refused before publication and the previous revision remains readable

### Requirement: HRDPS uses the existing application evidence path

An explicit HRDPS refresh SHALL use the existing durable worker, immutable
artifact publication and live readers. The artifact SHALL retain every mapped
field that the producer supplies and SHALL record an explicit missing or
unsupported disposition for each optional field it does not supply. Existing
point and profile mappings MAY expose only their already contracted subset;
live-proxy rasters SHALL NOT substitute for artifact-backed evidence.

#### Scenario: The complete run publishes

- **WHEN** all mandatory fields and 00-24 valid times pass the existing manifest and QC checks
- **THEN** `/point`, `/timeline`, `/layers` and supported `/profile` fields read the immutable artifact and the current web client consumes those live responses

#### Scenario: The cache is partially populated

- **WHEN** some but not all selected HRDPS valid times are already present
- **THEN** the worker preserves the retained revision and refuses unsupported partial repair without fetching

#### Scenario: The same run already covers the selected window

- **WHEN** the published HRDPS artifact declares every selected valid time
- **THEN** an explicit refresh succeeds with zero bulk retrieval and retains the existing revision

#### Scenario: A display derivation has no complete-operation reservation

- **WHEN** the post-publication WEonG or cloud-motion pass has no separately admitted resource bound
- **THEN** the worker skips that derivation before creating a model run, staging bytes or changing a current pointer

#### Scenario: Readers report the retained run

- **WHEN** a retained HRDPS field covers the requested valid time
- **THEN** timeline, point and profile responses preserve its provider run time and each sampled field's catalogue vertical level
