## ADDED Requirements

### Requirement: CYYT TAF preserves native forecast-group identity

The experimental `awc-taf` artifact SHALL retain the raw TAF, issue time,
overall validity, and every forecast group that intersects the requested window
in provider order, including duplicate start stamps. Each group SHALL preserve
its end time, becoming time, change-group label and probability, plus wind,
gust, visibility, present-weather text and up to six ordered cloud layers with
existing canonical conversions. Missing values remain missing. Unsupported or
invalid rows SHALL refuse the whole report rather than disappear. Intersection
uses the native half-open interval `[timeFrom, timeTo)`; the stored native start
MUST NOT be clamped to the request window.

Structural completeness SHALL be evaluated by group type, not by the generic
timestamp-grid coverage ratio. The initial prevailing group and every `FM`
group are self-contained and SHALL contain decoded wind speed and direction,
visibility, and a sky declaration. `CAVOK` satisfies visibility, weather and
sky together when AWC preserves it as such. A null or empty `wxString` in a
self-contained group is an explicit decoded absence of significant weather,
not a missing field. Gust is optional. A BECMG, TEMPO or PROB group MAY omit
unchanged fields. AWC sometimes expands such fields into decoded JSON: a
populated decoded field SHALL be marked `decoded_value`, an explicit null SHALL
be `decoded_absence`, and only a missing decoded key SHALL be
`not_stated_in_change_group`. The adapter MUST NOT infer from decoded repetition
whether the raw coded group repeated or inherited a value.

#### Scenario: Overlapping change groups keep provider order
- **WHEN** FM, TEMPO, BECMG or probability groups share a start time
- **THEN** their artifact order and native group metadata match the response

#### Scenario: Prevailing group overlaps the request start
- **WHEN** a self-contained group begins before the request but its native end
  falls after the request start
- **THEN** it is retained with its original interval and is not rejected merely
  because its native start precedes the request

#### Scenario: AWC expands a BECMG field
- **WHEN** the raw BECMG changes only wind but AWC's decoded group also carries
  visibility, weather or cloud values
- **THEN** those populated values are preserved as `decoded_value` and are not
  mislabeled as absent or proven raw repetition

#### Scenario: Gust is absent
- **WHEN** a group carries no `wgst`
- **THEN** `wind_gust_10m` is missing for that group and is not inferred from sustained wind

### Requirement: TAF groups are disclosed without composing a prevailing forecast

The API SHALL expose `/aviation/taf?station=CYYT&at=<instant>` from the selected
immutable `awc-taf` revision. The response SHALL contain report issue/validity,
raw TAF, source/revision/QC provenance and every native group whose half-open
interval contains `at`, in provider order. Each group SHALL carry its native
interval, change label, probability, sparse decoded fields and per-field
presence state. It SHALL NOT merge overlapping groups, carry prior fields
forward, or select one conditional group as authoritative.

The existing Workbench SHALL render ordered group cards and their labels,
intervals, sparse values, missing/not-stated states, raw report and source
provenance. Brief SHALL continue to use its existing forecast inputs and SHALL
NOT present these uncomposed conditional groups as a single forecast.

#### Scenario: TEMPO overlaps the prevailing group
- **WHEN** both groups contain the selected instant
- **THEN** the response and Workbench show both ordered groups separately and
  no combined wind, visibility, weather or cloud value is manufactured
