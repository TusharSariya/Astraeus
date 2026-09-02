## ADDED Requirements

### Requirement: A horizon tier is a valid-time range and names no sources
The deployment SHALL define exactly two horizon tiers as valid-time ranges: the
core tier from 24 h back to 24 h ahead, and the planning tier from 24 h ahead
to 14 d ahead. A tier SHALL NOT name, include or exclude any source. No source
SHALL be assigned to a tier, and no source SHALL be withheld from an instant
because of the tier that instant falls in. The bounds of the storage window
these ranges sit in are defined by `storage-window-and-restart-cache` and SHALL
NOT be restated here. An instant with no tier SHALL be refused rather than
served from the nearer tier.

#### Scenario: A source that spans the boundary
- **WHEN** GFS is hourly to f120 and reaches 384 h
- **THEN** it covers instants in both tiers, and neither tier excludes it

#### Scenario: A near-in planning-reach source
- **WHEN** an instant three hours ahead is requested
- **THEN** every source reaching it is offered, the global models included, because the tier is a range and not a source list

#### Scenario: An instant in neither tier
- **WHEN** a valid time falls outside both tier ranges
- **THEN** it is refused naming the two ranges, and no evidence from the nearest covered instant is substituted

### Requirement: Coverage at an instant is computed from declared reach
For every instant it serves, `/timeline` SHALL list each source whose declared
reach, for a run actually retrieved, contains that instant, together with that
run's run time and its staleness flags. A source SHALL be listed only when a
retrieved run covers the instant; a declared reach alone SHALL never put a
source on the timeline. An instant no retrieved run covers SHALL carry an empty
source list with a notice naming that nothing covers it, never the nearest
covering instant's list.

#### Scenario: An instant covered by three runs
- **WHEN** an instant twelve hours ahead is covered by retrieved HRDPS, GFS and IFS runs
- **THEN** all three are listed with their own run times, none is presented as the primary and no value is combined across them

#### Scenario: A declared reach with no retrieved run
- **WHEN** a source declares reach over an instant but no run of it has been retrieved
- **THEN** it is absent from that instant's coverage and the reason is available, rather than being listed as covering

#### Scenario: An uncovered instant
- **WHEN** no retrieved run covers an instant
- **THEN** its source list is empty with a notice saying nothing covers it, and neighbouring instants' coverage is not borrowed

#### Scenario: Coverage cannot be resolved
- **WHEN** the live store is unreachable while resolving coverage
- **THEN** the timeline is `unavailable` with a notice naming the failure and no instant is said to be covered

### Requirement: A run older than twice its cadence is flagged run_stale
Every frame SHALL carry the run time of the run that produced it and a
`run_stale` flag. `run_stale` SHALL be true when the frame's run time is older
than twice that source's declared producer run cadence, on every frame that run
feeds, whatever the frame's own valid time. `run_stale` SHALL NOT cause a frame
to be withheld, because a stale run that is the only evidence is still the only
evidence. A source whose run cadence is not resolvable SHALL report `run_stale:
null` with the reason, never false.

#### Scenario: A run two cycles behind
- **WHEN** a six-hourly source's newest retrieved run is thirteen hours old
- **THEN** every frame it feeds carries `run_stale: true` with the run time and the cadence it was measured against

#### Scenario: A stale run is still served
- **WHEN** the only run covering an instant is `run_stale`
- **THEN** its frames are still served and drawn, flagged, and nothing is substituted for them

#### Scenario: An unresolvable cadence
- **WHEN** a source declares no resolvable run cadence
- **THEN** its frames carry `run_stale: null` with the reason, and are not reported as current
