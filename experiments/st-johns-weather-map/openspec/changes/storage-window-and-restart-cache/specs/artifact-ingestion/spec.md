## ADDED Requirements

### Requirement: Ingestion is idempotent by provider run id and frame time
A frame SHALL be identified by `(source_id, provider_run_id, valid_time)`,
with the provider run id taken from the provider's own stamp and the valid
time compared as integer nanoseconds. Before fetching, the worker SHALL ask
the store which of the frames the window wants are already published under
that key, and SHALL fetch only the answers that are no. Re-running a source
whose window is already satisfied SHALL make no bulk upstream request and
SHALL publish nothing new. An already-published frame SHALL NOT be
overwritten by a second fetch of the same key; a byte-different fetch of an
existing key SHALL be refused as `run_identity_conflict` rather than silently
replacing published evidence. Where the store cannot be asked, the worker
SHALL fail the source rather than assume the window is empty, because
refetching everything on an unreadable store is how a restart becomes an
outage on the constraint that binds.

#### Scenario: A restart with a satisfied window
- **WHEN** the stack is stopped and restarted with every frame of a source's window already published
- **THEN** discovery runs, no bulk fetch is issued, the outcome is `succeeded` with zero artifacts published, and the reason states the window was already satisfied

#### Scenario: A restart with a partly filled window
- **WHEN** the stack restarts with some frames of a run missing
- **THEN** only the missing `(provider_run_id, valid_time)` frames are fetched, and the frames already published are neither re-fetched nor re-uploaded

#### Scenario: A frame missing upstream on the second pass
- **WHEN** a frame the window wants is no longer published upstream
- **THEN** the run reports `missing_valid_time:<iso>` as it already does and is not publishable, and no earlier value is substituted for the gap

#### Scenario: The same key with different bytes
- **WHEN** an upstream fetch produces different bytes for a `(source_id, provider_run_id, valid_time)` already published
- **THEN** the attempt is refused with `run_identity_conflict` naming both digests, and the published artifact stays visible

#### Scenario: The store cannot be asked what is present
- **WHEN** the metadata or object store is unreachable at the idempotency check
- **THEN** the source fails naming that condition, and no fetch is attempted, because an unknown cache state is not an empty one

### Requirement: Derived artifacts are recomputed on restart, never re-fetched
A derived-here or display-derived artifact absent after a restart SHALL be
rebuilt from the retained retrieved inputs already inside the window, and
SHALL NOT cause those inputs to be fetched again. A derived artifact whose
inputs are all present SHALL be recomputed before the next publication that
depends on it. A derived artifact whose inputs are not all present SHALL be
absent and SHALL report the absence state of its worst input, `aged out` when
an input was purged and `null` when an input was never retrieved. Recomputing
SHALL NOT lower an input's evidence class, and SHALL NOT reach for a
substitute input from another source.

#### Scenario: A derived artifact is missing after a restart
- **WHEN** the worker restarts with the retrieved inputs present and the derived artifact absent
- **THEN** the derived artifact is recomputed from those inputs and no upstream request is made for them

#### Scenario: An input has aged out
- **WHEN** a derived artifact's input frame was purged for leaving the window
- **THEN** the derived artifact is absent and reports `aged out at <last valid time>` naming the input, rather than being computed from a shorter input set

#### Scenario: An input was never retrieved
- **WHEN** a derived artifact's input was never published here
- **THEN** the derived artifact is absent and reports `null` naming the input

## MODIFIED Requirements

### Requirement: Every step must sit inside the evidence window
A run SHALL fail QC when any valid time falls outside the declared `now-24h .. now+14d` sliding window, because the API samples the nearest step within an hour and an out-of-window step can surface as if it had answered the question asked, while consuming storage for evidence nothing may display and nothing may retain. The bounds SHALL be read from the single window definition in `evidence-window-timeline`, never restated as literals in an adapter. A step inside the window that the store will purge before it can be served SHALL still be published; ageing out is retention's decision, not a QC verdict. Reported out-of-window flags SHALL be capped so the flag list stays readable, with the remaining count stated. A run carrying no valid time inside the window at all SHALL be refused rather than published empty, and the source SHALL report that reason rather than a silent gap.

#### Scenario: A step beyond the window end
- **WHEN** a run carries a valid time after `now+14d`
- **THEN** `qc_passed` is false with an `out_of_window:<iso>` flag, and the run is not publishable

#### Scenario: Many offending steps
- **WHEN** more than five steps fall outside the window
- **THEN** the first five are flagged individually and a further `out_of_window:+N_more` flag states how many remain
