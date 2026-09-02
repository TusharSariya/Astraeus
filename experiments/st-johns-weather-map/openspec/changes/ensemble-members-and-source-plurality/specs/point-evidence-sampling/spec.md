## REMOVED Requirements

### Requirement: Consensus requires ECCC regional, an independent centre and an ensemble
**Reason**: unsatisfiable by construction, and unwanted once examined. The
requirement needs an ensemble among the eligible candidates; eligibility is
read from the registry; and the registry audit refuses eligibility to any
record that is not `deterministic_forecast`, which every ensemble is not. The
branch has therefore never produced a value. Repairing it was rejected on the
merits: a mean over centres is a value no centre issued, it smooths away the
gradients a 2.5 km regional model exists to resolve, and the fields being
compared across centres are not the same quantity (hard-won facts 7 and 9).
Under the governing rule a blended value is a value that was not retrieved.

**Migration**: no consensus value, contributor list, centre range or reason is
emitted anywhere. Every source that published is shown side by side under the
new requirement below, so no evidence is lost by the removal; what disappears
is the single blended number and the vocabulary around it.

### Requirement: Display selection falls back explicitly and says which it used
**Reason**: its ladder starts at consensus, which no longer exists, and its
`Consensus unavailable but HRDPS fresh` scenario pins the badge wording that
is being retired. A MODIFIED block must keep every scenario the accepted spec
carries, so a requirement whose scenarios are the thing being removed cannot
be edited in place.

**Migration**: replaced by "Display selection names a declared primary and
says why" below, which keeps the HRDPS then RDPS then evidence-only order and
the requirement to state why an earlier option was not used, and drops only
the consensus rung and its badge.

### Requirement: A value is one published cell, unmodified
**Reason**: the rule forbade serving any value an intermediary had already
transformed, which rejected every foreign global model reachable at this
location. UKMO Global, JMA GSM, ARPEGE-world and CMA GRAPES are available here
only through an aggregator that selects a cell by its own policy, downscales
against a 90 m elevation model and interpolates the native step up to hourly.
The owner's decision on 2026-09-02 was to loosen the rule rather than lose the
sources: such a value is still retrieved rather than invented here, and the
honest answer is to declare what kind of source it came from.

**Migration**: replaced by "A value is one published cell unless its source is
declared reprocessed" below, which keeps all three original scenarios and the
unmodified-cell default unchanged, and admits a reprocessed source only under
declaration, dual attribution, exclusion from the display primary and
exclusion from every derivation.

## ADDED Requirements

### Requirement: A value is one published cell unless its source is declared reprocessed
Sampling SHALL select exactly one published grid cell per source and variable and SHALL report its value unmodified. No value SHALL be computed from more than one cell: there is no interpolation, no averaging and no regridding **performed here**. `sample_method` SHALL state how the cell was chosen — `rectilinear` by coordinate label, or `curvilinear_nearest_cell` by index on a 2-D coordinate grid.

A source MAY instead be declared `reprocessed`, meaning an intermediary between the originating producer and this deployment has already selected, downscaled, interpolated or otherwise transformed the producer's field before delivering it. Such a value is still retrieved rather than invented here, and it MAY be served, under all of these together: the registry declares the source as reprocessed and names the intermediary and the originating producer separately; provenance names both parties and states every transformation the intermediary documents, so a reader is never told a downscaled value is the producer's own cell; `sample_method` states the intermediary's own selection rule rather than `rectilinear` or `curvilinear_nearest_cell`, which describe a selection this deployment made and did not; the value SHALL NOT be the declared display primary, because a value transformed by a third party has no business outranking a producer's own published cell; and the value SHALL NOT be an input to any derivation, since a derivation over a reprocessed field would compound one intermediary's transformation with this stack's own.

Where the intermediary documents no transformation for a field, that SHALL be stated as undocumented rather than assumed to be none.

#### Scenario: A rotated grid is sampled by index
- **WHEN** an HRDPS or RDPS artifact on a rotated lat/lon grid is sampled
- **THEN** the nearest cell is chosen by index over the 2-D coordinate fields, because selection by latitude/longitude label is invalid there and previously caused every such artifact to answer with nothing

#### Scenario: Longitude distance is corrected for latitude
- **WHEN** nearest-cell distance is computed
- **THEN** the longitude difference is scaled by `cos(latitude)`, since a degree of longitude is about 0.68 of a degree of latitude at 47.5N and a raw degree distance would pick a cell too far east or west

#### Scenario: The reported coordinate is the cell's, not the request's
- **WHEN** a value is returned
- **THEN** provenance carries the sampled latitude and longitude of the cell actually read plus the distance in kilometres from the requested coordinate, because echoing the request back would claim a precision the reading does not have

#### Scenario: A reprocessed source is served
- **WHEN** a source declared reprocessed delivers a value that an intermediary downscaled and interpolated in time
- **THEN** the value is served with provenance naming the originating producer, the intermediary, and both transformations, and `sample_method` states the intermediary's own cell-selection rule rather than one this deployment applied

#### Scenario: A reprocessed source is not promoted
- **WHEN** a reprocessed source is the only source carrying a field, or would otherwise sort first
- **THEN** it is shown with its own provenance but is never named the declared primary, and no derivation reads it

#### Scenario: An undeclared source delivers a transformed value
- **WHEN** a source not declared reprocessed is found to be delivering values an intermediary transformed
- **THEN** it is a defect in the declaration and the source is refused, rather than its values being served as published cells

#### Scenario: The intermediary documents no transformation
- **WHEN** a reprocessed source's intermediary states nothing about how a particular field is produced
- **THEN** provenance records the transformation as undocumented, and it is not reported as unmodified


### Requirement: Display selection names a declared primary and says why
The displayed selection SHALL name one source chosen by a declared, ordered
preference over sources that actually published for the coordinate and time,
and SHALL state the ordering it applied. The order SHALL be HRDPS, then RDPS,
then evidence-only. No selection SHALL be computed from more than one source:
the selected value is that source's own retrieved value, unmodified. Each
state SHALL carry a badge and a reason naming why the earlier option was not
used, and evidence-only SHALL name no selected source or product. The
selection SHALL NOT suppress any other source's fields, which stand beside it
under their own provenance.

#### Scenario: HRDPS published
- **WHEN** `eccc-hrdps` has published evidence covering the request
- **THEN** the badge names HRDPS as the declared primary, the reason states
  that it is first in the declared order, and the value is HRDPS's own

#### Scenario: HRDPS absent, RDPS present
- **WHEN** HRDPS published nothing covering the request and RDPS did
- **THEN** the badge names RDPS with a reason stating that HRDPS published
  nothing for this coordinate and time, and no value is borrowed from HRDPS

#### Scenario: Neither model available
- **WHEN** neither HRDPS nor RDPS has published evidence
- **THEN** the mode is `evidence_only` with the badge `forecast unavailable`,
  both selected ids are null, and any observation evidence that was retrieved
  still stands on its own

#### Scenario: No consensus vocabulary survives
- **WHEN** any point response is produced
- **THEN** no field, badge, reason or notice mentions consensus, no blended
  value exists, and no response carries a list of contributing centres for a
  single number

### Requirement: Every source that published is shown, and none is merged into another
A field SHALL carry one entry per source that published a value for the
requested coordinate and time, each with its own provenance naming that
source, its run, the cell actually read and its units. No entry SHALL be
computed from more than one source, and no source's absence SHALL be filled
from another's value. Where a source published nothing for the request it
SHALL simply have no entry, which is distinct from an entry whose value is
null because the source published the field and the cell held no number.

#### Scenario: Several sources published the same field
- **WHEN** HRDPS, RDPS and GFS all published 2 m temperature covering the
  request
- **THEN** three entries are returned, one per source, each with its own value
  and provenance, and no fourth entry combines them

#### Scenario: One source published nothing
- **WHEN** GFS published nothing covering the request
- **THEN** no GFS entry appears for that field, no other source's value is
  labelled GFS, and the response does not report a lost artifact for a source
  that simply does not cover the request

#### Scenario: A published field with no number in the cell
- **WHEN** a source published the field but the nearest cell holds no value
- **THEN** that source's entry is present with a null value and full
  provenance naming why, which is distinct from having no entry at all

### Requirement: A sampled member is a value with an identity
Where an artifact carries individual ensemble members, a sampled value SHALL
name the member it came from in provenance, using the provider's own member
identifier, and SHALL distinguish a perturbed member from the control. A
value SHALL NOT be produced by reducing members at sample time except through
an enabled entry in the derivation method registry, served as `derived_here`
beside the raw members and never presented as a provider field (owner
decision 2026-09-02, wayfinder ticket 22, specified in
`ensemble-families-and-member-statistics`); a provider's own mean, median or
spread is served as retrieved only where the provider published it as a
field. A dataset carrying a member dimension that the request did not
address SHALL yield no value and SHALL be reported as read-but-unusable,
following the treatment of an unrequested pressure dimension, because
returning null there loses evidence silently and returning one arbitrary
member would claim an identity the request never chose.

#### Scenario: A member is sampled
- **WHEN** a member-bearing artifact is sampled for a named member
- **THEN** the value is that member's own, and provenance carries the
  provider's member identifier and whether it is the control

#### Scenario: A member dimension nobody addressed
- **WHEN** a dataset carries a member dimension and the request named no
  member
- **THEN** no value is taken from that artifact and a skip notice names the
  artifact and the unaddressed dimension, rather than a null value or a
  silently chosen member

#### Scenario: A reduction is asked for that the provider never published
- **WHEN** an ensemble mean is requested for a source that publishes only
  members
- **THEN** the field is unavailable with a reason stating that the provider
  published no such statistic, and no mean is computed here
