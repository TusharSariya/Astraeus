## ADDED Requirements

### Requirement: The SWPC sources schedule from parseable registry prose
The three SWPC registry entries SHALL carry cadence prose the scheduler
parses (10 minutes, 1 minute, 3 hours) and freshness prose that parses to
thresholds, so each source is polled within the clamped poll bounds and its
freshness verdicts are real. The `space_weather` category SHALL NOT be in the
forecast category list, so no member ever receives synthesized lead hours.

#### Scenario: Cadences parse
- **WHEN** the scheduler reads the three entries
- **THEN** each yields a parsed cadence and freshness threshold and is
  scheduled within the poll clamp

#### Scenario: No lead hours for space weather
- **WHEN** run metadata is built for a space-weather source
- **THEN** no lead-hours value is attached
