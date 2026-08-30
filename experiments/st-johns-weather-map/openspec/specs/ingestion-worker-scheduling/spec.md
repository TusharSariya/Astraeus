## Purpose
Define the single ingestion worker: how it schedules registry-derived sources, how a refresh job reaches a terminal state that reflects what actually happened, and how its liveness signal distinguishes a running process from advancing ingestion.

## Requirements

### Requirement: A source outcome names what actually happened
`run_source` SHALL never raise and SHALL classify each attempt as `succeeded`, `cancelled` or `failed`. `cancelled` SHALL mean upstream had nothing usable for the window; `failed` SHALL mean the attempt broke. A staged but incomplete or QC-failed run SHALL be reported `failed` with the previous revision left visible, never `succeeded`.

#### Scenario: Upstream has nothing usable
- **WHEN** the adapter raises `AdapterUnavailable` during discovery or fetch, or discovery returns no candidate
- **THEN** the outcome is `cancelled` with the stated reason, not a silent gap and not a success

#### Scenario: A run that failed validation
- **WHEN** the fetched run is not both complete and QC-passed
- **THEN** the outcome is `failed` stating that the run was staged but incomplete or QC-failed and the previous revision stays visible, and zero artifacts are counted as published

#### Scenario: The quota or store blocks publication
- **WHEN** the storage cap is reached or the store is unavailable
- **THEN** the outcome is `failed` naming that condition

#### Scenario: A non-success survives the process
- **WHEN** an outcome is anything other than `succeeded`
- **THEN** it is recorded as a durable terminal job row, because success is already recorded in the run table and the other states would otherwise vanish

### Requirement: Scheduling is derived from the registry and never spins
The scheduler SHALL run only registered adapters whose registry record permits live ingestion, at the poll interval derived from that record's cadence and freshness. A source SHALL be rescheduled on its cadence regardless of outcome, so a failing source neither spins nor drops out of the rotation.

#### Scenario: A failing source
- **WHEN** a source fails a cycle
- **THEN** it is rescheduled at its normal cadence rather than retried immediately or removed

#### Scenario: A non-schedulable source
- **WHEN** a registered adapter's registry record is not ingestible
- **THEN** the scheduler does not run it

### Requirement: A refresh job reports the truth about what it ran
Draining a job SHALL run only the requested sources that have a registered schedulable adapter. A job that matched no such adapter SHALL finish `failed` naming the unmatched ids. Otherwise the job state SHALL be `failed` if any source failed, `succeeded` if any succeeded, and `cancelled` when every source was cancelled, with a detail listing each source's own state.

#### Scenario: Zero matched sources
- **WHEN** a job names sources that no registered schedulable adapter serves
- **THEN** it finishes `failed` naming them, because reporting it as succeeded is exactly the dishonesty this experiment forbids

#### Scenario: A mixed job
- **WHEN** one source fails and another succeeds
- **THEN** the job is `failed`, and its detail names each source's outcome individually

#### Scenario: Job failures do not stop the loop
- **WHEN** claiming or finishing a job raises
- **THEN** the failure is logged and the worker continues

### Requirement: Liveness distinguishes a live process from advancing ingestion
The heartbeat document SHALL carry both a timestamp and per-source ingestion progress, written atomically, and SHALL be beaten before each source rather than only between cycles, so a long serial cycle does not outlive the healthcheck window. The healthcheck SHALL report unhealthy for a missing, unparseable or stale heartbeat, and also when ingestion has stalled.

#### Scenario: A long cycle
- **WHEN** a cycle walks many sources serially over minutes
- **THEN** the heartbeat is refreshed before each source and during a fetch, so the container is not killed mid-download leaving staging to clean up

#### Scenario: A source that used to work and stopped
- **WHEN** a source with a recorded past success has gone more than three nominal cadences without another
- **THEN** the healthcheck reports unhealthy naming the stalled sources, because a live process is not the same claim as advancing ingestion

#### Scenario: A source that never worked
- **WHEN** a source has never succeeded — a 404 endpoint, or a product this stack cannot yet decode
- **THEN** it is not counted as a stall; that is an ingestion fact to report through source status, not a reason to restart-loop the container

#### Scenario: A missing or unparseable heartbeat
- **WHEN** the heartbeat file is absent, malformed, or its timestamp is stale or in the future
- **THEN** the healthcheck reports unhealthy
