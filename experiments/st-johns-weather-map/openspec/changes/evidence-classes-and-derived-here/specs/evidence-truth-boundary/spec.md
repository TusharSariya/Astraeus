## ADDED Requirements

### Requirement: Every value declares exactly one evidence class
Every provenance record SHALL carry `evidence_class`, one of `retrieved`,
`reprocessed`, `derived_here`, `intermediary_derived`, `generated_display`
or `uncalibrated_observation`, with no default. The class SHALL NOT be
inferred from a derivation name, an `evidence_basis`, a generated flag or a
logical name. Every published artifact manifest SHALL record the set of
classes its values carry. A provenance without a class, or an artifact whose
manifest set disagrees with its values, SHALL fail validation and SHALL NOT
publish.

#### Scenario: A provenance without a class is refused
- **WHEN** an artifact is staged whose provenance omits `evidence_class`
- **THEN** validation fails naming the field, nothing publishes, and the previous revision stays visible

#### Scenario: A manifest that understates its classes is refused
- **WHEN** an artifact manifest declares only `retrieved` and one of its values carries `derived_here`
- **THEN** validation fails with `evidence_class_mismatch` and nothing publishes

#### Scenario: A retrieved value is labelled retrieved
- **WHEN** an adapter publishes a value exactly as the producer issued it
- **THEN** its provenance carries `evidence_class: retrieved` and the class is visible on every data path that serves it

### Requirement: A derived-here value is admitted on data paths only under four conditions together
A value of class `derived_here` MAY be served on `/point`, `/profile`,
`/timeline`, `/features` and the map only when all of the following hold:
every input is a value of class `retrieved`, from any number of sources, and
every input is listed in the value's provenance with its own provenance; the
method is an enabled entry in the derivation method registry, named with its
version and citation; the result is bounded to the method's declared physical
range; and the result's quality is no better than the worst input's. A value
failing any condition SHALL NOT be served and SHALL be reported as `null` with
a notice naming the failed condition.

#### Scenario: All four conditions hold
- **WHEN** air-sea temperature difference is computed from retrieved CIOPS-East sea-surface temperature and retrieved HRDPS 2 m dew point by an enabled registered method
- **THEN** the value is served with `evidence_class: derived_here`, both inputs listed with their provenance, the method name, version and citation, and a quality equal to the worse of the two inputs

#### Scenario: An input is not retrieved
- **WHEN** a method's input is a value of class `reprocessed`, `intermediary_derived` or `uncalibrated_observation`
- **THEN** no derived value is produced, the field is `null`, and the notice names the disqualifying input and its class

#### Scenario: The method is disabled
- **WHEN** the registry entry for the method is `enabled: false`, or the deployment refuses derivations by environment variable
- **THEN** the value is `null` with a notice naming the method as disabled, and no fallback construction is substituted

#### Scenario: The result leaves the physical range
- **WHEN** a method produces a relative humidity of 104 percent
- **THEN** the value is not served as 104, the method's range rule decides whether it is clamped with a `range_clamped` flag or refused, and the choice is recorded in provenance

### Requirement: Combining the same field across centres remains forbidden
No value SHALL be produced by combining the same field from two or more
centres, whether by mean, weighting or selection presented as one value. No
value SHALL combine a provider's own ensemble reduction with a statistic over
a different member set. A derivation registry entry that declares such a
combination SHALL be refused at registration.

#### Scenario: A mean of two centres' cloud is refused
- **WHEN** a method is proposed whose inputs are HRDPS total cloud and GFS total cloud and whose output is one cloud value
- **THEN** registration is refused as blending, and no such value can exist

#### Scenario: Different fields combine by a physical relation
- **WHEN** a method reads temperature and dew point from one source and outputs relative humidity
- **THEN** that is derivation, not blending, and registration proceeds

### Requirement: A published field is never replaced by a derivation for that source
Where a source published a field, that field SHALL be served as retrieved and
no derived value of the same field SHALL be produced for that source. A
derived value of the same field from other inputs MAY be served beside it,
labelled, and SHALL NOT be presented as the source's own.

#### Scenario: The source published the field
- **WHEN** HRDPS publishes 2 m relative humidity
- **THEN** the HRDPS relative humidity served is the published value, and no derived relative humidity is attributed to HRDPS

#### Scenario: The source did not publish the field
- **WHEN** a source publishes temperature and dew point and no relative humidity
- **THEN** relative humidity MAY be derived by the registered method and is served as `derived_here` with both inputs named

### Requirement: Reprocessed, intermediary-derived and uncalibrated values are never primary and never inputs
A value of class `reprocessed`, `intermediary_derived` or
`uncalibrated_observation` MAY be served side by side with other sources,
labelled, and SHALL NOT be the display primary for any field, SHALL NOT be an
input to any derivation, and SHALL NOT be used for verification. An
`intermediary_derived` value SHALL name the producer whose fields the
intermediary read, the intermediary, and the intermediary's method where it
is documented.

#### Scenario: Open-Meteo cloud for WeatherNext 2
- **WHEN** Open-Meteo's total cloud for Google WeatherNext 2 is retrieved
- **THEN** it is served with `evidence_class: intermediary_derived`, producer Google WeatherNext 2, intermediary Open-Meteo, method "humidity-profile cloud closure" as documented by Open-Meteo, and it is never the primary and never read by a derivation

#### Scenario: A reprocessed value is offered as primary
- **WHEN** the only value for a field at an instant is `reprocessed`
- **THEN** the field's primary is reported as absent with the reprocessed value shown beside it as non-primary, rather than promoting it

### Requirement: A derived value's quality is the worst of its inputs plus a derived flag
The `Quality.status` of a `derived_here` value SHALL be the worst status among
its inputs, and its flags SHALL include `derived`. A method MAY downgrade the
status further and SHALL NOT raise it. `Quality.status` SHALL keep exactly
its four values; `derived` is a flag, never a status.

#### Scenario: One suspect input
- **WHEN** a method reads one `passed` input and one `suspect` input
- **THEN** the derived value is `suspect` with flags including `derived`

#### Scenario: A method sees an absent ingredient
- **WHEN** a fog closure finds no valid cloud-top height for a cell
- **THEN** it reports `unknown` for that cell regardless of its other inputs' statuses

#### Scenario: A derived status is not a fifth status
- **WHEN** an artifact records a QC status of `derived`
- **THEN** validation fails, because the status set is `passed`, `suspect`, `failed`, `unknown`

### Requirement: A provenance that cannot be modelled fails only its own artifact
When an artifact's provenance cannot be modelled (an unknown class, a status
outside the contract, a missing required field), the store SHALL record the
failure with the artifact's source id, revision id and reason, SHALL report
that artifact's fields as `null` with a notice, and SHALL continue to answer
from every other artifact. One artifact's provenance failure SHALL NOT change
the response's `data_mode` or fail the response.

#### Scenario: One artifact carries an unmodelled status
- **WHEN** `/point` reads five artifacts and one carries a provenance the model refuses
- **THEN** four sources answer normally, the fifth's fields are `null` with a notice naming the artifact and reason, and `data_mode` reflects the four

#### Scenario: Every artifact fails
- **WHEN** no artifact's provenance can be modelled
- **THEN** every field is `null`, each with its notice, and `data_mode` is `unavailable`, never a fixture value

### Requirement: Generated-display values never reach a data path
Values of class `generated_display` SHALL be produced and served only for the
web map's display construction under the carve-outs recorded in
`openspec/config.yaml`, SHALL carry the on-map disclosure those carve-outs
require, and SHALL NOT appear on `/point`, `/profile`, `/timeline`,
`/features`, stories or readings. Admission SHALL be by class, never by
logical-name match.

#### Scenario: A generated artifact is sampled for a point
- **WHEN** `/point` encounters an artifact whose manifest classes include `generated_display`
- **THEN** that artifact is excluded from the sample by its class, with no name matching involved, and the point stays frame-exact

#### Scenario: A renamed generated artifact
- **WHEN** a generated artifact's logical name changes
- **THEN** it is still excluded, because exclusion reads the class
