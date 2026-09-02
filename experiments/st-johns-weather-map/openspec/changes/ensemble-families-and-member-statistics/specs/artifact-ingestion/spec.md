## ADDED Requirements

### Requirement: The control lands on the member axis with its flag set
An ensemble artifact SHALL carry its control on the same member axis as its
perturbed members, with a `control` flag on that member and the provider's own
member identifier preserved. Where the control arrives in a separate file or
coverage, the artifact SHALL still publish one member axis, and the separate
retrieval SHALL be recorded in provenance rather than in the member identity.

An artifact SHALL NOT publish a control as a field beside the members, as a
second artifact, or as an unflagged member. Where the control was not
retrieved, the artifact SHALL publish partial with the control named as the
missing member, and SHALL NOT set the flag on any other member. Where a family
publishes no control at all, the artifact SHALL carry no control flag rather
than defaulting one onto the lowest member number.

#### Scenario: The control arrives with the members
- **WHEN** a run retrieves the control and every perturbed member
- **THEN** the artifact publishes one member axis, the control carries the
  flag and its own provider identifier, and completeness counts it

#### Scenario: The control arrives separately
- **WHEN** the perturbed members and the control are retrieved from two
  different files
- **THEN** one member axis is published, provenance records both retrievals,
  and no second artifact exists for the control

#### Scenario: The control is absent
- **WHEN** the control is not retrieved for a run
- **THEN** the artifact publishes partial naming the control as missing, and
  no perturbed member carries the control flag

#### Scenario: A family with no control
- **WHEN** a family publishes perturbed members only
- **THEN** no member carries the control flag, and nothing downstream reads a
  control from that family

### Requirement: Storage scope is applied per family at ingest, and the difference is recorded
Ingest SHALL apply the storage scope the registry declares for the family: for
a server-side subsetting family, every published field; for a family that
cannot subset server side, only the fields the field catalogue's families use.
The artifact's manifest SHALL record which scope was applied and SHALL list
every published field that was not stored, as `available-not-stored`, so that
a field is never silently missing from the artifact.

A run that stored fewer fields than the applied scope requires SHALL publish
as incomplete against the scope, naming the fields that were not retrieved,
which is distinct from a field that the scope deliberately excluded. Where the
declared scope cannot be applied because the family's subsettability
declaration is absent, nothing SHALL be retrieved for that family.

#### Scenario: Every field from a subsettable family
- **WHEN** a REPS run is ingested
- **THEN** every published member field is stored, the manifest records the
  every-field scope, and the available-not-stored list is empty

#### Scenario: Family fields only from a non-subsettable family
- **WHEN** a GEFS run is ingested
- **THEN** only the catalogue-family fields are stored, the manifest records
  the family-fields scope and lists every other published record as
  available-not-stored

#### Scenario: A field inside the scope that did not arrive
- **WHEN** a field the applied scope requires is not retrieved
- **THEN** the run publishes incomplete naming that field, distinctly from the
  fields the scope excluded on purpose

#### Scenario: No scope could be applied
- **WHEN** a family's subsettability is undeclared at ingest time
- **THEN** nothing is retrieved for it and the reason names the missing
  declaration, rather than defaulting to either scope

### Requirement: A time-averaged member field is stored under its own key with its window
Where an ensemble family publishes a field as an average over a time window
rather than at an instant, it SHALL be stored under the catalogue key for that
averaged quantity, never under the instantaneous key, and its averaging window
SHALL be recorded on the field as retrieved from the producer's own record
rather than assumed from the lead time. GEFS total cloud SHALL be stored as
the six-hour-mean total cloud field, whose window is three hours at the first
step of each six-hour block and six hours thereafter.

A stored averaged field SHALL NOT be presented as, converted to, or used in
place of the instantaneous field of the same family, and no instantaneous
value SHALL be inferred from it. Where the producer's record does not state
the window, the field SHALL NOT be stored, because a mean whose window is
unknown is not a quantity anyone can weigh.

#### Scenario: The GEFS averaged cloud column is ingested
- **WHEN** GEFS total cloud is retrieved for a lead
- **THEN** it is stored under the six-hour-mean cloud key with the window read
  from the producer's record, and nothing stores it as instantaneous cloud

#### Scenario: The instantaneous field is asked for and does not exist
- **WHEN** an instantaneous total cloud column is requested from GEFS
- **THEN** it is absent with a reason stating that the family publishes only a
  time average of that quantity, and no instantaneous value is inferred from
  the average

#### Scenario: An averaging window the record does not state
- **WHEN** an averaged field's window cannot be read from the producer's own
  record
- **THEN** the field is not stored and the run reports the field as
  unstorable, rather than storing a mean with an assumed window
