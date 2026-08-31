## ADDED Requirements

### Requirement: The GFS subset covers the upper-air seeing ingredients exactly
The GFS byte-range selection SHALL include, in addition to the surface set,
exactly the messages `UGRD`/`VGRD` at `200 mb`, `UGRD`/`VGRD` at `300 mb` and
`PWAT` at `entire atmosphere (considered as a single layer)`, matched as
exact (parameter, level) pairs against the `.idx` sidecar and still filtered
to instantaneous forecasts (`anl` or `N hour fcst`) only. The isobaric
messages SHALL decode through a `typeOfLevel=isobaricInhPa` cfgrib filter and
be split by level into flat level-suffixed variables; nothing SHALL be
published on a pressure dimension from this path. A message the inventory
does not carry SHALL be treated as optional-field absence for that lead,
never synthesized. The merged byte span per lead SHALL stay under the
declared per-lead ceiling, and the ceiling SHALL only change together with a
measured span recorded beside it.

#### Scenario: The five messages are selected
- **WHEN** an `.idx` sidecar carrying the full GFS inventory is resolved
- **THEN** the selection contains the four isobaric wind messages and PWAT
  alongside the existing surface set, and no other isobaric message

#### Scenario: An averaged duplicate is refused
- **WHEN** the inventory carries both `7 hour fcst` and `6-7 hour ave fcst`
  variants of a selected message
- **THEN** only the instantaneous message is selected

#### Scenario: PWAT missing from one lead
- **WHEN** a lead's inventory carries no PWAT message
- **THEN** the lead is decoded without `precipitable_water`, the run reports
  the optional absence, and no value is invented

#### Scenario: The span exceeds the ceiling
- **WHEN** the gap-merged byte span for a lead exceeds the per-lead ceiling
- **THEN** the fetch for that lead fails closed rather than pulling the file
