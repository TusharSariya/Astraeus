## ADDED Requirements

### Requirement: Desktop absence is explicit and does not imply clearance
Desktop API responses SHALL represent native numeric zero, explicit checked
absence, unknown/unreadable evidence, unavailable acquisition, and unqueried
coverage as distinct states with a reason where applicable. An omitted value,
empty feature collection, unavailable source or unknown interval SHALL NOT be
converted to a favorable zero, all-clear, continuous coverage or current
reading.

#### Scenario: No astronomy value was served
- **WHEN** an astronomy value is absent from the applicable response
- **THEN** the response carries an explicit absence reason and does not use zero
  as a placeholder
