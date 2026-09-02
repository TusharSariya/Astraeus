## MODIFIED Requirements

### Requirement: A control that cannot change the request is disabled and says why
A selector SHALL only offer options the API actually returned; an empty option list SHALL leave the control disabled with the reason stated. A field the API reports in provenance but has no request parameter for SHALL be presented read-only with an explanation, because a control that accepts a choice and then discards it misstates what was requested. Model and product controls SHALL be offered only for catalogue sources that `/point` accepts as a `product` value; registry `state` is a ceiling that never reads `active` and SHALL NOT gate them.

Member is no longer such a field. Where the selected source is an ensemble
family that publishes members, member SHALL be an operable selector whose
options are the members the response actually reported, each labelled with the
provider's own member identifier and with the control marked, and the choice
SHALL be sent as a request parameter. Where the selected source publishes no
members, or where the response reported none, the member selector SHALL be
disabled with that reason stated rather than offered empty. Run and level
SHALL remain read-only readouts, because the point request still has no
parameter for either.

#### Scenario: Run, member and level
- **WHEN** the expert controls are shown for a source that publishes members
- **THEN** member is an operable selector over the members the response
  reported, with the control marked, and run and level remain read-only
  readouts explaining that the point request has no parameter for them

#### Scenario: A catalogue that could not be read
- **WHEN** `/catalog` failed
- **THEN** the provider and product selectors are disabled with the catalogue error stated, rather than showing an empty but operable control

#### Scenario: A product whose source is not selectable
- **WHEN** a catalogue source maps to no `/point` `product` token
- **THEN** no model button or product option is rendered for it, rather than a control that no response could ever enable

#### Scenario: A model offered while no source is active
- **WHEN** the catalogue lists a source `/point` accepts as a product and its registry state is anything other than `active`
- **THEN** its model button is enabled and selecting it sends the endpoint's own product token, not the catalogue's prose product name

#### Scenario: A source with no members
- **WHEN** the selected source is deterministic, or is a reduction-only
  ensemble family, or reported no members for the instant
- **THEN** the member selector is disabled with that reason stated, and it is
  never shown as an empty but operable control

## ADDED Requirements

### Requirement: The map offers a member selector and statistic layers, both named
Where the selected source is an ensemble family that publishes members, the
interface SHALL offer a member selector over the members the response
reported and SHALL offer each available statistic as its own layer, distinct
from the member layers and from every other source's layer. A statistic layer
SHALL name the family, the run, the statistic and the member set it covers
wherever it is drawn, in its legend and in its disclosure, and SHALL be
distinguishable at a glance from a per-member layer.

A statistic layer SHALL NOT be drawn where the members it summarises are not
reachable in the same view, and selecting a statistic SHALL NOT remove the
member selector. Where the family publishes no members, no member selector and
no computed-statistic layer SHALL be offered, and any provider reduction SHALL
be offered as its own layer labelled as the provider's own. Where nothing was
retrieved for the family and instant, the layer SHALL decline with the reason
rather than drawing a neighbouring family's members.

#### Scenario: A member is selected
- **WHEN** a reader selects member 07 of a REPS run
- **THEN** that member's own values are drawn and read out, labelled with the
  provider's member identifier, and no statistic is substituted for it

#### Scenario: A statistic layer is drawn
- **WHEN** the ensemble spread layer is drawn for one run
- **THEN** its legend and disclosure name the family, run, statistic and
  member set, it is visibly distinct from the member layers, and the member
  selector stays available

#### Scenario: A reduction-only family is selected
- **WHEN** GEPS is selected
- **THEN** no member selector and no computed-statistic layer are offered, its
  published mean, spread, percentiles and threshold probabilities are offered
  as the provider's own layers, and the absence of members is stated

#### Scenario: Nothing was retrieved for the instant
- **WHEN** neither members nor statistics exist for the selected family and
  instant
- **THEN** the layer declines with the reason, and no other family's members
  and no earlier run are drawn in its place

### Requirement: No ensemble number is shown without its family, run, statistic and member set
Every ensemble number the interface shows SHALL be accompanied, wherever it
appears, by the family and run it came from, which statistic it is, the member
set it covers, and whether it is a provider reduction or was computed here.
The word ensemble SHALL NOT stand alone as a value's identity in any label,
legend, badge, tooltip or heading. A value the interface cannot label with all
five SHALL NOT be shown.

A statistic over a partial member set SHALL show the members used against the
members declared wherever the value is shown, and a statistic from a run
flagged run-stale SHALL show that flag and the run age beside it. The same
labels SHALL appear in the text alternative, in the same terms, so that
nothing about an ensemble number is available only visually. Where no ensemble
value is shown at all, none of these labels SHALL appear, so a label always
carries information.

#### Scenario: A computed statistic is labelled
- **WHEN** a mean computed here is shown on the map or in the point panel
- **THEN** the family, run, statistic and member set are shown with it, and it
  reads as computed here rather than as the model's output

#### Scenario: A provider reduction is labelled
- **WHEN** a provider's own percentile is shown
- **THEN** it reads as the provider's own statistic over the provider's own
  members, and it is not styled or grouped as though it were computed here

#### Scenario: A partial or stale set is visible
- **WHEN** a statistic covers 17 of 21 declared members, or comes from a
  run-stale run
- **THEN** the shortfall or the run age is shown beside the value, not only in
  an expandable detail

#### Scenario: The text alternative
- **WHEN** the map contents are read as text
- **THEN** every ensemble number is announced with its family, run, statistic
  and member set, and the bare word ensemble never stands for a value

### Requirement: A time-averaged member field is never drawn beside an instantaneous one
Where a member field is an average over a time window, the interface SHALL
name the window wherever the field is drawn or read out, and SHALL NOT place
it on the same colour ramp, the same axis or the same difference view as an
instantaneous field of the same quantity. GEFS six-hour-mean total cloud SHALL
be shown as a distinct field from any instantaneous cloud field, with the
comparability note its family carries.

Where a reader selects both an averaged and an instantaneous cloud field, the
interface SHALL draw them as separate layers with separate legends and state
why they are not comparable, rather than refusing silently or rendering one
scale for both. Where the averaged field is the only cloud field a family
publishes, the interface SHALL say so rather than presenting it as that
family's instantaneous cloud.

#### Scenario: Both fields are selected
- **WHEN** GEFS six-hour-mean cloud and an instantaneous cloud field are both
  shown
- **THEN** they are drawn as separate layers with separate legends and the
  comparability note is stated, and no single ramp or axis carries both

#### Scenario: The averaged field is read out
- **WHEN** the six-hour-mean cloud value is read out at a point
- **THEN** the averaging window is named with the value, in the text
  alternative as well, so it never reads as a value at the instant

#### Scenario: A family with no instantaneous cloud
- **WHEN** a reader looks for GEFS instantaneous cloud
- **THEN** the interface states that the family publishes only a time average
  of that quantity, and offers no instantaneous layer for it
