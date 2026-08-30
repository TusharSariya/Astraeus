## Purpose
Define how the worker turns an upstream provider into a publishable artifact: one adapter per registry source, a declared manifest that a shared validator judges the assembled run against, and a one-way verdict in which anything partial, mis-united, out-of-window or undecodable is refused rather than published as evidence.

## Requirements

### Requirement: One adapter per source, discovery separate from retrieval
Every adapter SHALL implement the shared `Adapter` protocol for exactly one registry source id: `discover(window)` returns usable upstream runs newest-first without downloading bulk, and `fetch(candidate, window, workdir)` retrieves, subsets and normalizes one candidate into staged artifacts. The API SHALL NOT reach upstream for stored evidence; only the worker ingests.

#### Scenario: Upstream has nothing usable for the window
- **WHEN** upstream is reachable but carries nothing inside the evidence window
- **THEN** the adapter raises `AdapterUnavailable` rather than returning an empty result, so the scheduler records an explicit unavailable state instead of a silent gap

#### Scenario: Run identity comes from the provider
- **WHEN** an ECCC Datamart run is fetched from the dated directory layout
- **THEN** the run identity is taken from the provider's own filename stamp, never from the ingest clock, because deriving it from `now` mislabels every run fetched after 00Z from the previous day's directory

### Requirement: Completeness and QC are computed, never asserted
An adapter SHALL declare a `RunManifest` naming the required canonical fields with their normalized units and levels, the required valid times, a minimum coverage fraction and the bounds. `complete` and `qc_passed` SHALL be produced by `validate_run` from the assembled dataset and the adapter's own decode errors. An adapter SHALL NOT hard-code `complete=True`, `qc_passed=True` or a `quality.status = "passed"` provenance literal.

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

### Requirement: A crop that matched nothing is the wrong domain, not a thin run
Validation SHALL fail closed when the dataset has no latitude or longitude coordinate, or when either axis is empty after the bounding-box crop.

#### Scenario: An empty axis after cropping
- **WHEN** the latitude or longitude dimension is size zero
- **THEN** the verdict carries `empty_grid:<axis>` and the run is refused

#### Scenario: An unnormalized dataset
- **WHEN** the dataset carries no recognisable latitude or longitude coordinate name
- **THEN** the verdict carries `missing_axis:<axis>`, because the dataset was never normalized and must not be judged as if it had been

### Requirement: Every step must sit inside the evidence window
A run SHALL fail QC when any valid time falls outside the declared `now-3h .. now+24h` window, because the API samples the nearest step within an hour and an out-of-window step can surface as if it had answered the question asked, while consuming storage for evidence nothing may display. Reported out-of-window flags SHALL be capped so the flag list stays readable, with the remaining count stated.

#### Scenario: A step beyond the window end
- **WHEN** a run carries a valid time after `now+24h`
- **THEN** `qc_passed` is false with an `out_of_window:<iso>` flag, and the run is not publishable

#### Scenario: Many offending steps
- **WHEN** more than five steps fall outside the window
- **THEN** the first five are flagged individually and a further `out_of_window:+N_more` flag states how many remain

### Requirement: An unresolved provider stays non-publishing with a stated reason
An adapter whose endpoint contract, grid geometry or field assembly is unresolved SHALL raise `AdapterUnavailable` with that reason and SHALL NOT publish. Its registry record SHALL stay at its declared non-active status. No regridding, no guessed listing contract and no assumed cycle mapping SHALL be invented to make it publish.

#### Scenario: DWD ICON Global
- **WHEN** ICON Global ingestion is attempted
- **THEN** both entry points raise `AdapterUnavailable` stating that the native icosahedral mesh cannot be cropped to a bbox or sampled at a coordinate without a documented regrid, and nothing is published

#### Scenario: ECMWF Open Data IFS
- **WHEN** IFS discovery is attempted
- **THEN** `discover` raises `AdapterUnavailable` stating that the dated listing contract is unresolved, and `fetch` is unreachable — because publishing a partial or mislabelled IFS run is exactly the failure this experiment exists to rule out

### Requirement: Credentials live only in the environment and their absence is honest
Provider credentials SHALL be read from the environment through one lookup module and nowhere else, and SHALL never be written to an artifact, provenance block, log line, fixture, commit or browser bundle. A missing credential SHALL leave its source honestly non-active with a stated reason; it SHALL NOT crash the worker, disable an unrelated source, or fall through to a substituted value.

#### Scenario: A credential is not configured
- **WHEN** a credential-gated source is attempted with no key in the environment
- **THEN** `CredentialMissing` is raised for that source alone, and no evidence is reported for it

#### Scenario: A key that would appear in a URL
- **WHEN** an error or log message could carry a key supplied as a query parameter
- **THEN** the value is redacted before it is emitted

### Requirement: Upstream access is polite and bounded
All adapters SHALL fetch through one shared HTTP client that identifies the experiment, paces requests per host, retries a bounded number of times on retryable statuses with backoff, and abandons a response that grows past the caller's byte ceiling. Adapters SHALL NOT construct their own transport.

#### Scenario: A response exceeds its ceiling
- **WHEN** a body grows past the declared maximum
- **THEN** the download is abandoned with `MaxBytesExceeded` rather than being read into memory

#### Scenario: Retries are finite
- **WHEN** every permitted attempt fails with a retryable condition
- **THEN** `RetriesExhausted` is raised, and the failure is reported rather than retried indefinitely
