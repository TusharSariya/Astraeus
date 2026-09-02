## MODIFIED Requirements

### Requirement: A missing value is null with full provenance
An absent value SHALL surface with an explicit absence state and SHALL still
carry the same complete provenance shape as a present value. The absence
states SHALL be disjoint: `null` means not retrieved this cycle; `blocked`
means the field is known and refused for a stated reason of licence,
credential or partnership; `aged_out` means the value was retrieved once and
is now outside the retention window. NaN SHALL be read as absence rather than
as a reading. A response with nothing retrieved SHALL still enumerate every
expected field with its absence state, with `quality.flags` including
`no_retrieval` and a reason flag, so a caller can tell absence from a reading
without interpreting a status code. A field that cannot be served under
current terms SHALL NOT be reported as `null`.

Every served field, present or absent, SHALL carry the full output contract a
profile reads: the value; its evidence class; its quality; its freshness; its
source; its comparability within its family; and its absence state. A field
SHALL NOT be served with any element of that contract omitted.

#### Scenario: A NaN grid cell
- **WHEN** the selected cell holds NaN
- **THEN** the field value is `null` and the provenance still names the source, product, run time, valid time, level, units, quality, coverage, freshness, licence, attribution and adapter version

#### Scenario: An unavailable point response
- **WHEN** nothing could be retrieved
- **THEN** all twelve unavailable point fields (temperature, relative humidity, dew point, wind speed, wind gust, visibility, low/middle/high/total cloud, fog state and radar echo) are present with `null` values, `data_mode: "unavailable"` provenance and their declared units

#### Scenario: A licence-blocked field
- **WHEN** a field no admitted source may redistribute is requested
- **THEN** it is served with state `blocked`, its reason and the terms named, never as `null`, and never as a value

#### Scenario: A field outside the retention window
- **WHEN** a field is requested for an instant whose artifact has been purged
- **THEN** it is served with state `aged_out`, distinct from `null` and from `blocked`, naming the retention window

#### Scenario: An incomplete output contract
- **WHEN** a field would be served without its evidence class or its comparability
- **THEN** the field is served `null` with `contract_incomplete` naming the missing element, and the remaining fields still answer
