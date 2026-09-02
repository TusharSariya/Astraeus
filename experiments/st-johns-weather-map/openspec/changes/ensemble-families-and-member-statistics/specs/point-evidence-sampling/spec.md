## ADDED Requirements

### Requirement: A member statistic is served as a labelled derived-here field beside its members
Where an ensemble statistic is requested for a family that publishes members,
the response SHALL carry it as a field of evidence class `derived_here`,
naming the derivation method entry, its version, the family, the run, the
statistic, the member set it covered and whether the control was included.
The response SHALL serve the per-member values for the same field, run and
instant beside it, and a statistic SHALL NOT be served where the members it
summarises cannot be served with it, because a statistic no reader can open is
the unnamed ensemble number this project refuses.

A statistic SHALL NOT replace, suppress or reorder any retrieved value: the
members, the family's provider reductions where it publishes any, and every
other source's own values stand beside it under their own provenance. Where
the statistic is unavailable, the per-member values SHALL still be served, and
where the members are unavailable, no statistic SHALL be served in their
place.

#### Scenario: A statistic is served
- **WHEN** an ensemble mean is requested for one field of one REPS run
- **THEN** it is returned as a `derived_here` field naming the method entry,
  the family, the run, the member set and the control treatment, with the 21
  member values returned beside it

#### Scenario: The statistic is disabled and the members are not
- **WHEN** the statistic entry is disabled for the deployment or the reader
- **THEN** the statistic reads null with the notice, and every per-member
  value is still served with its own member identity

#### Scenario: The members cannot be served
- **WHEN** the members for the field and instant cannot be served
- **THEN** no statistic is served for them either, and the field is
  unavailable with the reason, rather than a summary standing in for values
  nobody can inspect

#### Scenario: A request for a statistic from a reduction-only family
- **WHEN** a mean is requested from GEPS, which publishes no members
- **THEN** the provider's own published mean is served as a retrieved value
  labelled as the provider's, no statistic is computed here, and the response
  states that the family publishes no members to compute one from

### Requirement: A statistic request that crosses a family, a run or a reduction fails closed
Sampling SHALL refuse any statistic request whose resolved inputs are not the
members of exactly one family from exactly one run. A request naming two
families SHALL be refused naming both, and SHALL NOT be answered for whichever
family resolved. A request that would span two runs of one family SHALL be
refused naming both runs, and SHALL NOT be answered from the run with more
members. A request that would combine a provider reduction with a statistic
computed here SHALL be refused, and each SHALL instead be served separately
under its own class with its own member set named.

A refusal SHALL name the condition that failed and SHALL leave every retrieved
value in the response untouched, so that refusing a statistic never removes
evidence. A refusal SHALL NOT be reported as absent data, because the data is
present and the request is the thing that was not answerable.

#### Scenario: A request mixing two families
- **WHEN** one statistic is requested over GEFS and REPS members together
- **THEN** it is refused naming both families and the one-family rule, no
  value is computed for either, and both families' member values remain in the
  response

#### Scenario: A request spanning two runs
- **WHEN** the members resolved for a statistic come from two runs of one
  family
- **THEN** it is refused naming both runs, and no statistic is computed from
  the run that happens to have more members

#### Scenario: A reduction and a computed statistic together
- **WHEN** a response would carry the GEPS provider mean and a mean computed
  here over another family's members as one field
- **THEN** the combination is refused, and the two are served as separate
  fields, one `retrieved` and named as the provider's over its own members,
  one `derived_here` and named with its own member set

#### Scenario: A refusal is not an absence
- **WHEN** a statistic request is refused
- **THEN** the response says the request was refused and why, distinctly from
  a field that is null because nothing was retrieved

### Requirement: A statistic over a partial or stale ensemble says so on the value
Where the artifact backing a statistic reports the run partial, the served
statistic SHALL carry the members used, the members declared and the missing
members on the value, and SHALL be presented as covering that set rather than
the ensemble. Where the family's run is older than the staleness rule its
registry record declares, the statistic SHALL carry the run-stale flag and the
run's age, exactly as the members beside it do, and SHALL NOT be served
without it.

Where a statistic's quality is computed, it SHALL be no better than the worst
member that entered it, plus the derived flag, and a partial member set SHALL
lower the verdict rather than being rounded away. Where the run is stale
beyond what its record permits to be served at all, no statistic SHALL be
served, and the members SHALL be served under the same rule that governs any
other stale retrieved value.

#### Scenario: A statistic over a partial member set
- **WHEN** a statistic is served from a run the artifact published as partial
- **THEN** the value carries the members used, the members declared and the
  missing member identifiers, and no label calls it the ensemble's value

#### Scenario: A statistic from a stale run
- **WHEN** the backing run is older than twice its declared cadence
- **THEN** the statistic carries the run-stale flag and the run age beside the
  members, and nothing serves it as current

#### Scenario: A statistic whose members are stale beyond serving
- **WHEN** the run is too old to be served at all under its record's rule
- **THEN** no statistic is served, the reason names the run age, and no
  earlier run is substituted to keep a number on the field

#### Scenario: Quality follows the worst member
- **WHEN** one member that entered a statistic carries a suspect quality
  status
- **THEN** the statistic's quality is no better than suspect, carries the
  derived flag, and the shortfall is not rounded away

### Requirement: Every ensemble number served names its family, run, statistic and member set
No response SHALL carry an ensemble number that does not name, on the value
itself, the family and run it came from, which statistic it is, the member set
it covers, and whether it is a provider reduction or was computed here. A
value that cannot name all five SHALL NOT be served, because a number whose
construction a reader cannot recover is the failure the retired consensus
badge demonstrated.

A per-member value SHALL name its member identifier and whether it is the
control, and SHALL never be served as an unlabelled representative of the
family. Where a field name would otherwise read only as "ensemble", the
response SHALL use the family name and the statistic name instead, and no
field, badge or reason SHALL use the bare word ensemble as a value's identity.

#### Scenario: A statistic names its construction
- **WHEN** any computed ensemble statistic is returned
- **THEN** it names the family, the run, the statistic, the member set and
  that it was computed here

#### Scenario: A provider reduction names its construction
- **WHEN** a provider's own mean, spread, percentile or threshold probability
  is returned
- **THEN** it names the family, the run, the statistic, the provider's own
  member set and that the provider computed it

#### Scenario: A value that cannot name its member set
- **WHEN** an ensemble value's member set cannot be reconstructed from its
  provenance
- **THEN** it is not served, and the field is unavailable naming the missing
  provenance, rather than served as an unattributed number

#### Scenario: A single member is served
- **WHEN** one member's value is served
- **THEN** it names the member identifier and whether it is the control, and
  nothing presents it as the family's value
