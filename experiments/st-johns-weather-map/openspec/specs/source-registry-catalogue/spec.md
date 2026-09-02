## Purpose
Make `registry/source_data.py` the single catalogue of record for every meteorological source this experiment may retrieve, so that the API catalogue, source status, product controls, refresh scheduling and consensus eligibility all derive from one checked-in declaration whose status is a ceiling no live retrieval can raise.

## Requirements

### Requirement: The registry is the only catalogue
The API SHALL derive `/catalog`, `/sources/status`, refresh validation, product controls and scheduler eligibility from `registry/source_data.py`, in registry order, in every data mode. It SHALL NOT serve a separate fixture catalogue of sources. Publishing the registry is honest in every mode because the registry is a declaration of what may be retrieved, not a claim that anything has been.

#### Scenario: The catalogue is the whole registry
- **WHEN** `/catalog` is requested in any data mode
- **THEN** it returns one record per registry source (63 records), each carrying producer, product, state, status reason, role, consensus eligibility, exact variables, levels, coverage, cadence, horizon, authentication, licence, attribution, caching, archival, redistribution, schema version, documentation URL, access endpoint, integration, schedulability, fixture status and live-smoke status

#### Scenario: A source id the registry does not know
- **WHEN** `POST /refresh` names a source id absent from the registry
- **THEN** it is refused with 422 naming the unknown ids

### Requirement: Registry status is a ceiling, and `active` is never emitted
The API SHALL map each registry status through a ceiling table and SHALL NOT emit `active` for any source under any circumstance. Recording a live retrieval SHALL make a source's freshness measurable; it SHALL NOT promote its state. Promotion out of the declared state requires owner approval plus fixture test, live smoke, artifact validation, API readback and provenance checks, none of which the running system can grant itself.

#### Scenario: A source with recorded live retrieval
- **WHEN** the worker has published artifacts for `awc-metar-speci` and `/sources/status` is read
- **THEN** the row reports `state: "implementing"` with `data_mode: "live"`, a `last_retrieval` timestamp and an evaluated freshness — and never `state: "active"`

#### Scenario: No retrieval recorded
- **WHEN** a registry source has no recorded retrieval
- **THEN** its row reports `data_mode: "unavailable"`, `last_retrieval: null`, freshness `unknown`, and a detail restating the registry's own status reason

#### Scenario: An unrecognised registry status
- **WHEN** the registry carries a status the ceiling table does not know
- **THEN** the emitted state is `unavailable`, not a guess and not `active`

### Requirement: Only wired, catalogued, credential-free sources are schedulable
A source SHALL be schedulable only when its registry status is `implementing`, a freshness threshold can be resolved from its registry prose, and a successfully registered adapter claims its source id. A refresh naming an unwired source or a `credential_required`, `licence_review`, `retired`, `unavailable` or otherwise non-schedulable id SHALL be refused, because accepting it would promise work that cannot happen.

#### Scenario: A catalogued source has no adapter
- **WHEN** `POST /refresh` names an `implementing` source without a registered adapter
- **THEN** it is refused with 422 as not schedulable, and no job is created

#### Scenario: A credential-gated source is requested
- **WHEN** `POST /refresh` names a source such as `nl-511` or `purpleair`
- **THEN** the request is refused with 422 stating the ids are not schedulable, and no job is created

#### Scenario: An empty refresh request
- **WHEN** `POST /refresh` is sent with no source ids
- **THEN** it expands to the full schedulable set, and is refused with 422 if that set is empty

### Requirement: Freshness thresholds and cadences are derived, never defaulted into existence
Cadence and freshness SHALL be derived from the registry's own prose. A record that states no resolvable freshness promise SHALL report `threshold_seconds: null` and freshness `unknown`; a default threshold SHALL NOT be substituted, because that would assert a promise the provider never made. An unmeasurable age SHALL stay `unknown` rather than being called fresh.

#### Scenario: No measurable age
- **WHEN** a sample carries no retrieval time
- **THEN** freshness is `unknown` with `age_seconds: null`, never `fresh`

#### Scenario: No stated threshold
- **WHEN** the registry prose says "unknown", "not applicable" or "to be established"
- **THEN** the threshold is `null`, freshness is `unknown`, and the source is not schedulable

#### Scenario: A measurable age against a stated threshold
- **WHEN** an age and a threshold are both known
- **THEN** freshness is `fresh` at or below the threshold and `stale` above it

### Requirement: Consensus eligibility comes from the declared category
Consensus eligibility and family SHALL be read from each record's declared `category` and `consensus` block, not inferred from the product name. Categories that carry no forecast lead SHALL NOT be given lead hours.

#### Scenario: An ocean model does not vote on air temperature
- **WHEN** consensus candidates are assembled
- **THEN** only records whose declared category and consensus block make them eligible are admitted, so ocean, wave, surge, analysis and post-processed products cannot vote on a raw-model air temperature

#### Scenario: An observation family gets no lead hours
- **WHEN** ingest configuration is derived for `aviation`, `analysis`, `hydrology` or `air_quality` records
- **THEN** `lead_hours` is empty, because an analysis is valid at one time only and those groups mix observations with forecasts

### Requirement: An adapter may only claim a registered source id
Registering an adapter SHALL fail when its `source_id` is absent from the registry, and SHALL fail when a different adapter class already claims that id. An adapter module that exists and fails to import SHALL take the loader down; a module that does not exist yet SHALL be tolerated.

#### Scenario: A duplicate claim
- **WHEN** two different adapter classes register the same source id
- **THEN** registration raises, rather than one family silently replacing the other

#### Scenario: A broken adapter module
- **WHEN** an adapter module is present but raises on import
- **THEN** the loader fails loudly, because a silently skipped family would leave `/sources/status` reporting nothing wrong while an entire evidence family had vanished

#### Scenario: A family that has not landed
- **WHEN** an adapter module name is listed but no such module exists
- **THEN** the loader continues, since families land independently
