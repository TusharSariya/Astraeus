## REMOVED Requirements

### Requirement: Consensus eligibility comes from the declared category
**Reason**: there is no consensus for a record to be eligible for. The
requirement's real work was twofold, and only one half survives. It stopped
ocean, wave, surge, analysis and post-processed products being treated as
raw-model air temperature, which is still needed and is restated below as
display ordering. Its other half declared a right to vote in a blended value,
which no longer exists. Keeping an eligibility flag that nothing reads would
leave a declaration the audit still enforces and the code still ignores, which
is how the contradiction that removed consensus arose in the first place.

**Migration**: the `consensus` block and its audit rule are retired from every
record. The category keeps deciding what a record may be offered as, and gains
the ordering role, under the requirement below.

## ADDED Requirements

### Requirement: Display ordering comes from the declared category
Display ordering and forecast lead SHALL be read from each record's declared
`category`, not inferred from the product name. Categories that carry no
forecast lead SHALL NOT be given lead hours. No record SHALL declare a right
to contribute to a value computed across sources, and no code path SHALL read
such a declaration, because no such value exists. A record's category SHALL
still decide what it may be offered as, so that ocean, wave, surge, analysis
and post-processed products cannot be presented as a raw-model air
temperature.

#### Scenario: Ordering is assembled
- **WHEN** the display order for a field is resolved
- **THEN** it follows the declared order over records that actually published,
  and a record's category decides only what it may be offered as, never that
  its value is averaged with another's

#### Scenario: An observation family gets no lead hours
- **WHEN** ingest configuration is derived for `aviation`, `analysis`,
  `hydrology` or `air_quality` records
- **THEN** `lead_hours` is empty, because an analysis is valid at one time
  only and those groups mix observations with forecasts

#### Scenario: A non-comparable product is offered
- **WHEN** an ocean, wave, surge, analysis or post-processed record publishes
- **THEN** it is offered under its own category and never as a raw-model air
  temperature, as before

#### Scenario: A stale eligibility declaration
- **WHEN** a record still carries a consensus eligibility field
- **THEN** the audit rejects it as a declaration that nothing reads, rather
  than enforcing a rule with no consumer

### Requirement: An ensemble record declares whether members are published
A record whose category is `ensemble` SHALL declare which of two shapes its
provider publishes: individual members, or the provider's own reduction over
members. Where it declares members it SHALL declare the expected member count
and how the control member is identified. Where it declares a reduction it
SHALL name the statistics published, and SHALL NOT declare a member count,
because there are no members to count. An adapter SHALL NOT infer the shape,
and a record that declares neither SHALL NOT be schedulable, because an
ensemble whose shape is unknown cannot be validated for completeness.

#### Scenario: A member-publishing ensemble
- **WHEN** `noaa-gefs` is declared, publishing 31 members with the control
  identified by the provider's own marking
- **THEN** the record states the shape, the expected count and the control
  rule, and an adapter reading it knows to expect one artifact per member

#### Scenario: A reduction-publishing ensemble
- **WHEN** `eccc-geps` is declared, publishing mean, spread, percentiles and
  threshold probabilities and no members at all
- **THEN** the record names those statistics, declares no member count, and
  nothing downstream expects members from it

#### Scenario: An ensemble that declares neither shape
- **WHEN** a record's category is `ensemble` and no shape is declared
- **THEN** it is not schedulable and the audit names the missing declaration,
  because member completeness cannot be checked against an unknown expectation

### Requirement: Every source declares how its values reach this deployment
Every record SHALL declare its delivery kind: `published_cell`, meaning the
producer's own grid or observation is retrieved directly from the producer or
from a mirror that copies it byte for byte, or `reprocessed`, meaning an
intermediary transformed the producer's field before delivering it. A
`reprocessed` record SHALL additionally name the intermediary as distinct from
the originating producer, and SHALL state every transformation the
intermediary documents, so that provenance can carry them without a caller
guessing. A record that declares no delivery kind SHALL NOT be schedulable,
because a value whose provenance cannot say whether it is the producer's own
cell is not evidence anyone can weigh. A `reprocessed` record SHALL NOT be
eligible to be the display primary, and the audit SHALL enforce that rather
than leaving it to the display layer.

#### Scenario: A direct producer feed
- **WHEN** `eccc-hrdps` is declared, retrieved from ECCC's own distribution
- **THEN** its delivery kind is `published_cell`, it names no intermediary,
  and it may be the display primary

#### Scenario: An aggregator route to a foreign model
- **WHEN** a UK Met Office or JMA global model is declared, reachable at this
  location only through an aggregator that selects a cell by its own policy,
  downscales against an elevation model and interpolates to hourly
- **THEN** its delivery kind is `reprocessed`, the record names the Met Office
  or JMA as producer and the aggregator as intermediary, lists all three
  transformations, and the audit refuses it as a display primary

#### Scenario: A record declaring no delivery kind
- **WHEN** a record omits the declaration
- **THEN** it is not schedulable and the audit names the omission, because
  nothing downstream can describe where its values came from

#### Scenario: A mirror of a producer's own bytes
- **WHEN** a source is retrieved from a cloud mirror that republishes the
  producer's files unchanged
- **THEN** its delivery kind is `published_cell`, because copying bytes is not
  transforming a field, and the mirror is recorded as an access endpoint
  rather than as an intermediary
