## MODIFIED Requirements

### Requirement: Registry status is a ceiling, and `active` is never emitted
The API SHALL map each registry state through a ceiling table and SHALL NOT emit `active` or `operational` for any source under any circumstance. The declared state SHALL be one of the ten registry states: `operational`, `implemented-unverified`, `catalogued`, `credential-required`, `licence-blocked`, `link-only`, `partnership-only`, `unavailable`, `rejected`, `superseded`. Recording a live retrieval SHALL make a source's freshness measurable; it SHALL NOT promote its state, and a retrieval failure under an admitted record SHALL NOT demote it either, because the state is the owner's declaration and only the owner moves it. Promotion out of the declared state requires owner approval plus fixture test, live smoke, artifact validation, API readback and provenance checks, none of which the running system can grant itself. Where a source is absent for any reason, the row SHALL report its declared state, `data_mode: "unavailable"` and the record's own status reason, and SHALL NOT report a value, a substituted source or a changed state.

#### Scenario: A source with recorded live retrieval
- **WHEN** the worker has published artifacts for `awc-metar-speci` and `/sources/status` is read
- **THEN** the row reports `state: "implemented-unverified"` with `data_mode: "live"`, a `last_retrieval` timestamp and an evaluated freshness, and never `state: "active"` or `state: "operational"`

#### Scenario: No retrieval recorded
- **WHEN** a registry source has no recorded retrieval
- **THEN** its row reports `data_mode: "unavailable"`, `last_retrieval: null`, freshness `unknown`, and a detail restating the registry's own status reason

#### Scenario: An unrecognised registry status
- **WHEN** the registry carries a state the ceiling table does not know
- **THEN** the emitted state is `unavailable`, not a guess, not `active` and not `operational`

The ceiling table SHALL recognise `partnership-only`: a source whose terms grant no redistribution and for which no written permission is recorded (wayfinder ticket 21, cameras). A `partnership-only` source SHALL be catalogued with its terms evidence quoted from the operator, SHALL NOT be scheduled or retrieved, and SHALL have every field it would supply served with the absence state `blocked` and reason `partnership`. Written permission or a licence SHALL be recorded against the source record before its state may change, and unresolved terms SHALL NOT be read as permission.

#### Scenario: A partnership-only camera source
- **WHEN** a camera source whose terms grant no redistribution is read from the registry
- **THEN** its row reports `partnership-only` with the operator's own terms quoted, it is not schedulable, and its fields are `blocked` with reason `partnership`

#### Scenario: Unresolved terms
- **WHEN** a source's terms page could not be retrieved at probe time
- **THEN** the record states the terms are unresolved, the state stays `partnership-only`, and the source is not promoted on the absence of a prohibition

### Requirement: Only wired, catalogued, credential-free sources are schedulable
A source SHALL be schedulable only when its registry state is `implemented-unverified`, no declared admission condition is outstanding, a freshness threshold can be resolved from its registry prose, and a successfully registered adapter claims its source id. A refresh naming an unwired source, or a source in any of the states `catalogued`, `credential-required`, `licence-blocked`, `link-only`, `partnership-only`, `unavailable`, `rejected`, `superseded` or `operational`, SHALL be refused, because accepting it would promise work that cannot happen. A refusal SHALL name the ids and their states and SHALL NOT create a job, fetch, prepare a request, or fall back to another source.

#### Scenario: A catalogued source has no adapter
- **WHEN** `POST /refresh` names an `implemented-unverified` source without a registered adapter
- **THEN** it is refused with 422 as not schedulable, and no job is created

#### Scenario: A credential-gated source is requested
- **WHEN** `POST /refresh` names a source such as `nl-511`, `purpleair` or `nav-canada-weather-cameras`
- **THEN** the request is refused with 422 stating the ids are not schedulable, and no job is created

#### Scenario: An empty refresh request
- **WHEN** `POST /refresh` is sent with no source ids
- **THEN** it expands to the full schedulable set, and is refused with 422 if that set is empty

#### Scenario: A conditional admission whose condition is outstanding
- **WHEN** `POST /refresh` names `eccc-rdwps` or `eccc-gdwps` while the Atlantic-domain check over the evidence box is unrecorded
- **THEN** the request is refused with 422 naming the outstanding condition, because an admission subject to a check is not an admission until the check is recorded

## ADDED Requirements

### Requirement: Registry state is one of ten values, and the mapping from the old enum is exact
Every registry record SHALL declare exactly one state from `operational`, `implemented-unverified`, `catalogued`, `credential-required`, `licence-blocked`, `link-only`, `partnership-only`, `unavailable`, `rejected`, `superseded`, matching the vocabulary in `CONTEXT.md`. The migration from the previous `status` enum SHALL follow one stated rule per value and SHALL NOT be decided per record: `active` becomes `operational`; `implementing` becomes `implemented-unverified` when a registered adapter claims the id, `integration.kind` is not `link_only` and `fixture_status` is `passing`, and `catalogued` in every other case; `credential_required` becomes `credential-required`, which is the state the glossary calls credential-blocked; `licence_review` becomes `licence-blocked`; `unavailable` and `rejected` are unchanged; `retired` becomes `superseded` when the record names its successor and `unavailable` when it does not; `duplicate_evidence` becomes `superseded` and SHALL name the superseding source; `unsupported_field` becomes `unavailable` with the unreachable field named in the status reason. No record SHALL declare `operational`, and the audit SHALL reject the value, so that the state remains unreachable rather than merely unemitted. A record whose state the schema does not know SHALL fail the audit and SHALL NOT be schedulable; it SHALL NOT be treated as catalogued by default.

#### Scenario: A declared but unwired source migrates to catalogued
- **WHEN** `eccc-integrated-nowcasting` is migrated, having no registered adapter
- **THEN** its state is `catalogued`, not `implemented-unverified`, and `/sources/status` reports it as catalogued with its own status reason

#### Scenario: A record declaring operational
- **WHEN** any record declares state `operational`
- **THEN** the audit fails naming the record, because no source may claim a state the promotion gates have not granted

#### Scenario: A superseded record names no successor
- **WHEN** a record migrating from `retired` or `duplicate_evidence` declares `superseded` without naming the superseding source
- **THEN** the audit fails, because "superseded" without a successor is an unavailable source wearing a better word

#### Scenario: An unknown state
- **WHEN** a record carries a state outside the ten
- **THEN** the audit fails and the API emits `unavailable` for it, never a guess

### Requirement: A credential-gated source is admitted credential-required and fails closed
A source whose access needs a credential SHALL be admitted in state `credential-required`, SHALL name the credential and the registration page, SHALL carry no credential value, and SHALL NOT be schedulable. With no credential resolved at runtime, no adapter SHALL fetch for it, no request SHALL be prepared, no prepared URL or key placeholder SHALL be logged, no fixture SHALL stand in for it on a live path, and no other source's value SHALL be served in its place; `/point`, `/timeline` and `/features` SHALL report the field absent with the record's own reason naming the missing credential. Supplying the credential later SHALL make the source schedulable and SHALL NOT change its state. Removing or invalidating the credential SHALL return the source to the same stated absence rather than to a cached or substituted value.

#### Scenario: A credential-required source with no key in the environment
- **WHEN** `copernicus-cams` is requested at a point and no credential is configured
- **THEN** the field is absent with provenance naming `copernicus-cams`, its state `credential-required` and the missing credential, no request was prepared, nothing was logged that contains a key or a key placeholder, and no other aerosol source was substituted

#### Scenario: A credential arrives
- **WHEN** the owner supplies the NC-SPACES credential for `nav-canada-weather-cameras`
- **THEN** the source becomes schedulable, its state stays `credential-required`, and promotion still requires the owner's gates

#### Scenario: A credential is withdrawn mid-window
- **WHEN** a previously resolving credential stops resolving
- **THEN** subsequent instants report the stated absence, already published artifacts stay valid and labelled with their own retrieval times, and no stale value is presented as current

### Requirement: A restricted-terms source is admitted for research use only, with terms recorded
A record MAY declare restricted terms; it SHALL then carry the terms text and the URL it was read from, SHALL set `redistribution: false`, and its values SHALL be served only to this deployment's own reader. Such values SHALL NOT be exported, republished, included in a public catalogue payload, or written to any artifact that leaves this deployment. A record that declares restricted terms without terms text or without the source URL SHALL fail the audit, because unrecorded terms are terms nobody can honour. Where the terms are read and found to forbid the use this experiment makes, the record SHALL move to `licence-blocked` and its fields SHALL report the licence as the reason for their absence, never a value.

#### Scenario: A share-alike foreign model
- **WHEN** `openmeteo-ukmo-global` is declared with its CC BY-SA terms recorded
- **THEN** the audit passes, its values are served to the owner's reader with attribution, and any export path refuses them naming the share-alike clause

#### Scenario: A non-commercial atlas
- **WHEN** `falchi-night-sky-atlas` is declared with CC BY-NC 4.0 recorded
- **THEN** the record carries the clause as a standing constraint on any commercial path, and the audit fails any later record that reuses the atlas without it

#### Scenario: Restricted terms declared with no text
- **WHEN** a record sets `redistribution: false` and carries no terms text
- **THEN** the audit fails naming the record, and the source is not schedulable

#### Scenario: Terms that forbid the use
- **WHEN** the CWOP licence text is read and found to forbid this use
- **THEN** `raw-cwop-pws` moves to `licence-blocked`, its fields report the licence as the reason, and no value is served from it

### Requirement: Every source the owner resolved carries a state, an access path and a reason
The registry SHALL carry one record for every source named in the owner resolutions of 2026-09-02 (tickets 24, 25, 26 and 28), and each SHALL declare its decided state, the access path it was decided on (or explicitly none), and the reason for the decision, in the record itself rather than in a ticket. A record in a state with no access path SHALL declare none rather than an endpoint a caller could try. Reprocessed and intermediary-derived records SHALL additionally declare their delivery kind, producer and intermediary under `openspec/changes/ensemble-members-and-source-plurality/` as extended by `openspec/changes/evidence-classes-and-derived-here/`; this requirement adds no delivery kind of its own. A resolved source with no record, or a record with no reason, SHALL fail the audit. Where a source is absent, blocked or refused, its record SHALL still answer the catalogue with its state and reason, because a catalogue that omits what was refused invites the refusal to be re-litigated as an oversight.

#### Scenario: A rejected source stays in the catalogue
- **WHEN** `/catalog` is read after `eccc-rewps` is rejected
- **THEN** the record is listed with state `rejected`, no access path, and the reason that the domain is Great Lakes only as verified on GeoMet on 2026-09-02

#### Scenario: A reprocessed aggregator record
- **WHEN** `openmeteo-cams-aod` is declared
- **THEN** it carries state `implemented-unverified`, delivery kind `reprocessed`, CAMS as producer and Open-Meteo as intermediary, every documented transformation including the 0.1 degree upsampling of a 0.4 degree producer grid, and it is refused as a display primary

#### Scenario: An intermediary-derived record
- **WHEN** `openmeteo-weathernext-2-cloud` is declared
- **THEN** it carries delivery kind `intermediary_derived`, names Google WeatherNext 2 as producer and Open-Meteo as intermediary, and its values are never the display primary and never a derivation input

#### Scenario: A resolved source with no record
- **WHEN** the audit compares the resolutions' source list against the registry and a named source is missing
- **THEN** the audit fails naming the missing id, because an undeclared source is one nobody decided

#### Scenario: An admitted source whose endpoint dies
- **WHEN** an admitted `implemented-unverified` source returns 404, an empty directory, or a body that fails validation
- **THEN** the retrieval fails with the failure recorded, the field is absent with provenance naming the source and the failure, the record's state is unchanged, and no neighbouring source, fixture or previous run is presented as the current value

### Requirement: Link-only and partnership-only records are declarations, never data paths
A record in state `link-only` SHALL carry a citation for the reader and no access endpoint any adapter could fetch, and SHALL NOT be schedulable. A record in state `partnership-only` SHALL declare that written permission is required, SHALL name what has been requested and from whom where a request has been made, SHALL carry no access endpoint, and SHALL NOT be schedulable. Neither state SHALL contribute a value to any data path, and neither SHALL be presented to the reader as pending data; each SHALL be presented as what it is, a source this deployment does not retrieve. Granting a permission SHALL be an owner action that changes the record; nothing in the running system SHALL move a record out of `partnership-only`.

#### Scenario: A link-only benchmark
- **WHEN** `7timer` is listed in the catalogue
- **THEN** it appears with state `link-only`, a documentation URL, no access endpoint, and it is refused by `POST /refresh`

#### Scenario: A partnership-only instrument
- **WHEN** `nrcan-stj-magnetometer` is requested at a point
- **THEN** the field is absent with the reason that redistribution needs written permission that this deployment does not hold, and no FDSN request is made

#### Scenario: A partnership-only camera in the camera list
- **WHEN** the camera list is assembled
- **THEN** the Coast Guard, City of St. John's and NTV cameras appear as partnership-only with no frames, and no frame is fetched or stored for them

### Requirement: Recorded licence text matches the publisher's own catalogue
Each record's licence text SHALL be the text the publisher's own catalogue states, with the URL it was read from and the date it was read. Where a previously recorded licence disagrees with the publisher's catalogue, the record SHALL be corrected to the publisher's text rather than kept, and the correction SHALL be visible in the record's history. A record whose licence cannot be read SHALL declare `licence-blocked` rather than a guessed licence, and its fields SHALL be absent with the licence named as the reason.

#### Scenario: The CAMS licence is corrected
- **WHEN** the `copernicus-cams` record is audited against the ADS catalogue
- **THEN** its licence text reads CC BY 4.0 as the ADS catalogue states, with the catalogue URL and read date, replacing the text the registry carried before

#### Scenario: A licence that cannot be read
- **WHEN** a source publishes no readable licence
- **THEN** the record declares `licence-blocked`, no value is served from it, and the absence names the unreadable licence
