## MODIFIED Requirements

### Requirement: The window is exactly twenty-four hours back and fourteen days forward
The evidence window SHALL run from snapshot selection time minus 24 hours to
selection time plus 14 days inclusive, producing 361 hourly timeline items.
Those fixed boundaries SHALL bind `/timeline`, `/layers`, `/point`, the
selection-scoped ingestion window, manifest validation and retained evidence for
the snapshot's lifetime. A replacement snapshot computes new boundaries from
its own database-server selection time.

#### Scenario: Three reads cross wall-clock time
- **WHEN** timeline, layers and point are requested at different wall-clock instants through one snapshot
- **THEN** all use the snapshot's same fixed `now-24h .. now+14d` boundaries

#### Scenario: A selected instant is outside the window
- **WHEN** snapshot creation names an instant before its start or after its end
- **THEN** it is refused before acquisition or capacity reservation
