## ADDED Requirements

### Requirement: HRDPS 00-24 hour acquisition is admitted as one complete operation

The experimental HRDPS adapter SHALL reserve its complete 00-24 hour receive,
temporary-filesystem, staged-store and measured allocation margin before the
first payload-bearing listing. Every listing and GRIB response SHALL have a
finite enforced byte ceiling. The Linux worker SHALL enforce a finite memory
cgroup and temporary filesystem ceiling. Unsupported enforcement SHALL refuse
before discovery. No missing or oversized response may be replaced or thinned.

For this measured slice the complete-operation ceilings are 12,673,089,536
received bytes, 2,952,790,016 temporary-filesystem bytes, 536,870,912 staged
store bytes and a 134,217,728-byte filesystem margin. Each directory listing is
limited to 2,097,152 bytes, each GRIB response to 10,485,760 bytes, discovery to
four cycles on each of two dates, and the selected run to 25 lead times and 48
mapped fields. The worker cgroup SHALL have the measured 4,294,967,296-byte
ceiling; its `/tmp` filesystem SHALL have a capacity no larger than 3 GiB and
enough available bytes for the
temporary-filesystem reservation plus margin.

#### Scenario: A continental crop retains a full-grid coordinate allocation

- **WHEN** a cropped field still shares memory with either full-grid coordinate
- **THEN** the adapter detaches the loaded crop before retaining it for the run

#### Scenario: A bound cannot fit

- **WHEN** the durable store reservation, temporary filesystem, memory cgroup, listing or payload ceiling cannot cover the complete operation
- **THEN** HRDPS is refused before publication and the previous revision remains readable

#### Scenario: A listing advertises an unbounded shape

- **WHEN** either dated directory advertises more than four cycles, or a listing or selected GRIB exceeds its byte ceiling
- **THEN** the adapter refuses the operation without thinning cycles, fields or lead times

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

#### Scenario: Publication metadata closes after retrieval

- **WHEN** the last selected HRDPS message has been received and decoded
- **THEN** the artifact records all 25 exact valid times and the provider run time, and retrieval time is captured after that final decode

#### Scenario: A retained legacy revision lacks exact frame metadata

- **WHEN** a retained HRDPS revision predates exact `run_time` and `valid_times` provenance
- **THEN** readers recover its exact frame coordinates from the integrity-checked immutable Zarr and derive its run time from the PT000 frame, without interpolating database span edges or modifying the revision

### Requirement: Preserved experiment volumes accept the current source-state vocabulary

The local migration path SHALL replace the historical source-state check with
the closed vocabulary used by the current registry while retaining accepted
legacy values needed by existing rows. It SHALL preserve those rows and SHALL
NOT promote any source to `operational`.

#### Scenario: The migration is applied again

- **WHEN** the source-state migration runs on an already upgraded preserved volume
- **THEN** its constraint is recreated successfully, legacy rows remain unchanged and `implemented-unverified` publication metadata is accepted
