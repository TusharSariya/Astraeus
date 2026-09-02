## ADDED Requirements

### Requirement: Six ensemble families are admitted in a declared order
The registry SHALL declare exactly six admitted ensemble families and the
order in which they are built: REPS, then AIFS-ENS, then IFS ENS, then GEFS,
then GEPS reductions, then ICON-EPS. The order SHALL be a declared field of
the registry rather than an implementation convention, so that a partial
build is a prefix of the list and a reader of the catalogue alone can tell
which families are expected to exist yet. Each record SHALL name the evidence
for its position, which is the measurement in
`docs/research/wayfinder/ensemble-access.md` for the first five and the
absence of any measurement for ICON-EPS.

A family SHALL NOT be admitted beyond its own measured evidence: where a
family's member count, access path or cadence is unverified, the record SHALL
declare it unverified and SHALL NOT be schedulable, because a member count
that was assumed cannot be used to check completeness. An ensemble family
absent from this list SHALL NOT be retrievable at all, and a request naming
one SHALL be refused with the six admitted names, rather than answered from
whatever happens to be in the store.

#### Scenario: The declared order is read
- **WHEN** the ensemble build order is resolved from the registry
- **THEN** it is REPS, AIFS-ENS, IFS ENS, GEFS, GEPS reductions, ICON-EPS, in
  that order, and no code path reorders it

#### Scenario: A family whose numbers were never measured
- **WHEN** ICON-EPS is declared with no measured member count, access path or
  cadence
- **THEN** the record declares those fields unverified, the family is not
  schedulable, and the catalogue says so rather than showing an empty family
  as though it were awaiting a run

#### Scenario: A family nobody admitted
- **WHEN** a request names an ensemble family that is not one of the six
- **THEN** it is refused naming the six admitted families, and nothing is
  served from any stored artifact for it

### Requirement: An ensemble record declares its storage scope from its subsettability
Every ensemble record SHALL declare whether its access path subsets server
side, and its storage scope SHALL follow from that declaration rather than
from a per-source judgement. A family retrieved over GeoMet, which subsets
server side, SHALL store every field it publishes. A family retrieved over a
path that cannot subset server side SHALL store only the fields the field
catalogue's families use, and SHALL catalogue every other published field as
`available-not-stored` so that a field is never hidden, only not fetched.

REPS and GEPS SHALL be declared subsettable. AIFS-ENS, IFS ENS, GEFS and
ICON-EPS SHALL be declared not subsettable. A record that declares no
subsettability SHALL NOT be schedulable, because a storage scope that was
inferred cannot be audited. Where a family publishes a field the catalogue
does not know, the field SHALL be catalogued as uncatalogued-upstream and
SHALL NOT be stored, rather than being stored under a guessed key.

#### Scenario: A server-side subsetting family
- **WHEN** REPS is ingested over GeoMet
- **THEN** every published member field is stored, and no published field is
  recorded as available-not-stored for it

#### Scenario: A family that cannot subset server side
- **WHEN** GEFS is ingested over S3 byte ranges
- **THEN** only the catalogue-family fields are fetched and stored, every
  other published record is catalogued available-not-stored with its name, and
  the catalogue shows the difference

#### Scenario: A record with no subsettability declaration
- **WHEN** an ensemble record omits the declaration
- **THEN** it is not schedulable and the audit names the omission, because the
  storage scope cannot be checked against an undeclared access shape

#### Scenario: A published field the catalogue does not know
- **WHEN** a family publishes a field with no catalogue key
- **THEN** it is catalogued as uncatalogued-upstream and not stored, and the
  absence is visible in the catalogue rather than silent

### Requirement: The control member is declared as a flagged member, never as a source
An ensemble record that publishes members SHALL declare how its control
member is identified, and the control SHALL be one member of the same member
axis carrying a `control` flag. No record SHALL declare a control as a
separate source, a separate product or a separate field, because a control
outside the member axis cannot be counted for completeness, cannot be
included or excluded from a statistic deliberately, and would be free to enter
the display-primary ordering as though it were a deterministic model.

Where a family publishes its control in a separate file or coverage from the
perturbed members, that SHALL be recorded as an access-shape detail of the one
record, not as a second record. Where a run's control is absent, the run SHALL
be reported partial with the control named as the missing member, never
complete with the perturbed members alone, and never with a perturbed member
promoted to stand in for it.

#### Scenario: A control identified inside the member files
- **WHEN** GEFS is declared, whose control is `gec00` beside `gep01` to
  `gep30`
- **THEN** the record states the control identification rule, the expected
  count of 31 includes it, and it is stored as a member carrying the control
  flag

#### Scenario: A control published in its own file
- **WHEN** AIFS-ENS is declared, whose 50 perturbed members arrive in a `pf`
  file and whose control arrives in a `cf` file
- **THEN** the record stays one record declaring 51 members, the two files are
  recorded as an access-shape detail, and the control lands on the same member
  axis with the flag set

#### Scenario: The control is missing from a run
- **WHEN** a run retrieves the perturbed members and no control
- **THEN** the run is partial with the control named as missing, and no
  perturbed member is presented as the control

#### Scenario: A reduction-only family has no control to declare
- **WHEN** GEPS is declared, publishing no members at all
- **THEN** it declares no control rule and no member count, and nothing
  downstream looks for a control in it

### Requirement: A field an ensemble family does not publish is declared as a gap
Where an admitted ensemble family does not publish a field that its sibling
families do, the record SHALL declare the gap explicitly, naming the field and
the reason it is absent. The gap SHALL NOT be filled by derivation, by another
family's value, or by the same family's provider reduction. REPS SHALL declare
that it publishes wind speed on its members and no `u` or `v` on any member,
so member wind direction is absent, is not derivable and SHALL stay null.

Where a declared gap is later found to be published after all, the record
SHALL be corrected before the field is served, so that a served value always
matches a declaration rather than appearing from an undeclared record.

#### Scenario: The REPS direction gap
- **WHEN** REPS member wind is catalogued
- **THEN** speed is declared published, direction is declared a gap with the
  reason that no member carries `u` or `v`, and nothing offers to derive it

#### Scenario: A gap is asked for anyway
- **WHEN** REPS member wind direction is requested
- **THEN** the field is null with the declared gap as its reason, no direction
  is computed, and no other family's or reduction's direction is substituted

#### Scenario: A gap that turns out not to be one
- **WHEN** a family is found to publish a field its record declares a gap
- **THEN** the record is corrected first, and the field is not served from an
  undeclared source in the meantime
