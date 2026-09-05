# WeatherNext 3 statistics experimental delta

Status: draft. This specification authorizes no production behavior.

## ADDED Requirements

### Requirement: Exact source identity

An experimental WeatherNext adapter SHALL accept only product 3.0.0 on the GCS
statistics surface and SHALL preserve variable, statistic, run, lead, valid
time, native unit, mask, provenance and object identity without member
fabrication.

#### Scenario: A bounded manifest is normalized

- **WHEN** all 126 fields have explicit dispositions and retrieved samples pass
  identity, time and range checks
- **THEN** an immutable artifact exposes only the retrieved fields and carries
  every selected, deferred, missing and unsupported disposition

#### Scenario: Input is ambiguous or invalid

- **WHEN** product/surface/member identity, inventory, statistic, time, value,
  object identity or a resource gate is invalid
- **THEN** acquisition fails explicitly and publishes nothing

### Requirement: Experimental isolation

The WeatherNext 3 adapter SHALL remain absent from production registration and
scheduling until owner acceptance resolves access, terms and API semantics.

#### Scenario: Draft code is loaded

- **WHEN** the experiment package imports its normal adapter registry
- **THEN** no WeatherNext 3 adapter is registered or schedulable
