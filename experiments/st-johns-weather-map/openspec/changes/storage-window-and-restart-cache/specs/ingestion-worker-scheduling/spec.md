## ADDED Requirements

### Requirement: A restart resumes the window rather than refilling it
On start the worker SHALL reconcile the retained window before scheduling any
fetch: it SHALL sweep abandoned staging, purge frames outside `now-24h ..
now+14d`, and then, per source, fetch only the frames the window is missing.
It SHALL NOT clear the store on start, and it SHALL NOT re-fetch a frame it
already holds. A restart that cannot read the store SHALL report unhealthy
and SHALL NOT fetch, because a worker that cannot see the cache would refetch
everything. Where a reconciliation leaves a source with no frame inside the
window, its fields SHALL report `aged out at <last valid time>` when frames
were once held and `null` when none ever were, never an empty success.

#### Scenario: A restart mid-publication
- **WHEN** the worker is killed after staging some artifacts of a run but before `publish_run` committed
- **THEN** the staged rows and objects are discarded on the next start, the previously visible run is still current and answers, the interrupted run is re-attempted from its own provider run id, and no partially published run is ever visible

#### Scenario: A restart with a full window
- **WHEN** the worker starts with every source's window already satisfied
- **THEN** it purges nothing that is inside the window, issues no bulk fetch, and reports each source `succeeded` with zero artifacts published and the reason stated

#### Scenario: A restart after a long outage
- **WHEN** the worker starts after the stack was down long enough for every retained frame to leave the window
- **THEN** the purge empties the store, each source reports `aged out at <last valid time>` until its next run publishes, and no attempt is made to fetch past frames to refill the 24 hours of history

#### Scenario: A restart with an unreadable store
- **WHEN** the store cannot be read at reconciliation
- **THEN** the worker reports unhealthy, schedules no fetch, and the API reports `unavailable`

### Requirement: A run that never completes never publishes and never holds bytes
A run that does not reach `complete` and `qc_passed` SHALL never be published,
SHALL be reported `failed` with the reason stated, and its staged bytes SHALL
be discarded by the abandoned-staging sweep so an incomplete run cannot
consume quota indefinitely. A source whose runs never complete SHALL keep
being rescheduled at its cadence and SHALL NOT be promoted, retried
immediately, or counted as a stall on the ingestion healthcheck if it has
never succeeded. Its fields SHALL report the absence honestly: `null` where
nothing was ever held, `aged out at <last valid time>` where an earlier
complete run has since left the window, never a value from the incomplete
run.

#### Scenario: A run that never completes
- **WHEN** a source's runs are staged and refused on every cycle
- **THEN** each cycle reports `failed` with the verdict flags, no artifact is published, and the staged bytes are discarded before the next cycle stages more

#### Scenario: An incomplete run does not accumulate quota
- **WHEN** the same source stages and fails over many cycles
- **THEN** projected usage does not grow across cycles, because abandoned staging is swept before the next attempt reserves room

#### Scenario: The last complete run ages out while the source keeps failing
- **WHEN** a source's only complete run leaves the window and every later run fails
- **THEN** its fields report `aged out at <last valid time>`, distinct from the `failed` outcome recorded for the source, so the reader is told both that evidence was held and that ingestion is broken

## MODIFIED Requirements

### Requirement: A source outcome names what actually happened
`run_source` SHALL never raise and SHALL classify each attempt as `succeeded`, `cancelled` or `failed`. `cancelled` SHALL mean upstream had nothing usable for the window; `failed` SHALL mean the attempt broke. A staged but incomplete or QC-failed run SHALL be reported `failed` with the previous revision left visible, never `succeeded`. An attempt that fetched nothing because the retained window already held every frame for the source's current provider run id SHALL be reported `succeeded` with zero artifacts published and a reason naming the satisfied window, so an idempotent no-op is never mistaken for an upstream failure. An outcome SHALL NOT be inferred from how many artifacts were published.

#### Scenario: Upstream has nothing usable
- **WHEN** the adapter raises `AdapterUnavailable` during discovery or fetch, or discovery returns no candidate
- **THEN** the outcome is `cancelled` with the stated reason, not a silent gap and not a success

#### Scenario: A run that failed validation
- **WHEN** the fetched run is not both complete and QC-passed
- **THEN** the outcome is `failed` stating that the run was staged but incomplete or QC-failed and the previous revision stays visible, and zero artifacts are counted as published

#### Scenario: The quota or store blocks publication
- **WHEN** the 64 GiB hot quota is reached or the store is unavailable
- **THEN** the outcome is `failed` naming that condition, the cap and the projected size, and no visible revision is evicted to make room

#### Scenario: A non-success survives the process
- **WHEN** an outcome is anything other than `succeeded`
- **THEN** it is recorded as a durable terminal job row, because success is already recorded in the run table and the other states would otherwise vanish
