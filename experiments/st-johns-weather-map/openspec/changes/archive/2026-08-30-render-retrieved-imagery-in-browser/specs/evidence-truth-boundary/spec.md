## ADDED Requirements

### Requirement: Every client fetch SHALL apply the declared data mode

The client SHALL resolve `data_mode` on every fetch, including `/timeline`, by the same fail-closed rule. The fail-closed mode rule is applied to point, layers, catalogue and source
status, but not to the timeline, which is returned raw. A timeline served in
`unavailable` mode is currently indistinguishable from a live one, and it drives
which hours the reader is told carry evidence.

#### Scenario: The timeline declares a mode
- **WHEN** the client reads `/timeline`
- **THEN** it resolves the response's `data_mode` by the same rule as every other
  fetch
- **AND** an absent or unrecognised mode resolves to unavailable

#### Scenario: An unavailable timeline is not presented as coverage
- **WHEN** `/timeline` resolves to `unavailable`
- **THEN** the interface does not present its hours as published coverage
