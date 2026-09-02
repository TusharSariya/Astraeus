## ADDED Requirements

### Requirement: The five ensemble statistics are registered entries
The derivation method registry SHALL carry one entry per admitted ensemble
statistic: ensemble mean, ensemble spread, ensemble quantile, ensemble
threshold probability and ensemble member count. Each entry SHALL declare, as
every entry does, its inputs as one catalogue field over a member axis, its
output catalogue field, its physical range and its out-of-range rule, and
SHALL additionally declare whether the control member is included in the
computation. No ensemble statistic SHALL be produced by any code path that is
not one of these entries.

An entry SHALL declare its own conventions where more than one exists: the
quantile entry SHALL declare its quantile convention and interpolation rule,
because two conventions differ visibly over 21 members, and the threshold
probability entry SHALL declare that the threshold, its unit and its
comparison sense are carried on every value it produces. The member count
entry SHALL report members used and members declared as two numbers, never one
number standing for both. Where an entry is disabled at any of the three
levels the registry defines, the statistic SHALL be null with a notice naming
the level, and the raw members SHALL be unaffected.

#### Scenario: A mean is produced
- **WHEN** an ensemble mean is computed for one field of one run
- **THEN** its provenance names the mean entry, its version, its citation, the
  member set it covered and whether the control was included

#### Scenario: A statistic with no entry
- **WHEN** code attempts to publish an ensemble median with no registered
  entry for it
- **THEN** publication fails with `unregistered_method` and nothing is served,
  rather than the value being served as an unnamed statistic

#### Scenario: A quantile whose convention is unstated
- **WHEN** the quantile entry declares no convention or interpolation rule
- **THEN** the registry fails validation and the deployment refuses to start
  with it

#### Scenario: The statistics are switched off
- **WHEN** the deployment or the reader disables the ensemble statistic
  entries
- **THEN** every statistic reads null with a notice naming the level that
  disabled it, and the per-member values are still served

### Requirement: An ensemble statistic entry is refused unless it stays inside one family and one run
An ensemble statistic entry SHALL declare that its inputs are the members of
one family, from one run, of one catalogue field, and registration SHALL be
refused otherwise. Registration SHALL refuse an entry whose inputs span two
families, whose inputs span two runs of the same family, whose inputs mix an
instantaneous field with a time-averaged field of the same quantity, or that
takes a provider reduction as an input alongside members.

At derive time the same conditions SHALL be checked against the inputs
actually resolved, not only at registration, because the resolved artifacts
are what carry the family and run. A derivation whose resolved inputs fail any
condition SHALL produce no value and SHALL report the condition it failed,
rather than computing over the subset that passes.

#### Scenario: An entry spanning two families
- **WHEN** an entry declares inputs from GEFS members and REPS members with
  one output
- **THEN** registration is refused naming the one-family rule

#### Scenario: An entry mixing a provider reduction with members
- **WHEN** an entry declares the GEPS provider mean and REPS members as inputs
- **THEN** registration is refused, because a provider's statistic is
  retrieved evidence over its own member set and is never an input to a
  statistic over a different one

#### Scenario: An entry mixing averaged and instantaneous cloud
- **WHEN** an entry declares GEFS six-hour-mean total cloud and an
  instantaneous total cloud field as inputs to one statistic
- **THEN** registration is refused, because the inputs are two quantities and
  the output would have no meaningful window

#### Scenario: Resolved inputs that violate a condition the entry satisfies
- **WHEN** a registered entry's inputs resolve at derive time to two different
  runs of one family
- **THEN** no value is produced, the failed condition is reported, and nothing
  is computed over whichever run has more members

### Requirement: A statistic over an incomplete member set carries the set it covered
Every value an ensemble statistic entry produces SHALL carry, on the value
itself, the family, the run, the statistic, the members used and the members
the registry declares, so that a reader can weigh it without consulting
another response. Where the artifact reports the run partial, the statistic
MAY still be produced, and it SHALL be labelled as covering a partial member
set with the missing members named; it SHALL NOT be labelled or presented as a
statistic over the whole ensemble.

Where an entry declares an owner-approved minimum member count and the
resolved set is below it, no value SHALL be produced and the shortfall SHALL
be reported. Where an entry declares no minimum, none SHALL be invented at
derive time, and the shortfall SHALL be carried on the value instead. Where no
member resolved at all, the statistic SHALL be null with that reason, and
SHALL NOT be reported as zero, as an empty set or as a spread of zero.

#### Scenario: A complete member set
- **WHEN** every declared member resolved
- **THEN** the value names the family, run, statistic and a member set equal
  to the declared count, and it is not labelled partial

#### Scenario: A partial member set
- **WHEN** 17 of 21 declared REPS members resolved and the artifact reports
  partial
- **THEN** the statistic is labelled as covering 17 of 21 with the four
  missing members named, and nothing presents it as the ensemble's mean

#### Scenario: A set below a declared minimum
- **WHEN** an entry declares a minimum member count and fewer members resolved
- **THEN** no value is produced and the shortfall is reported naming the
  minimum, rather than a statistic being served with a caveat

#### Scenario: No member resolved
- **WHEN** no member of the family resolved for the run
- **THEN** the statistic is null with that reason, and it is not reported as a
  spread of zero or a count of zero standing for agreement
