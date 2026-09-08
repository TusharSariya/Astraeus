# WeatherNext 3 surface point delivery

Classification: experiment. Owner authorization: on 2026-09-08 the owner requested
WeatherNext 3 historical and forecasting delivery, hiding WeatherNext 2, and
confirmed “yes do it all” for all 126 surface statistic fields.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

This amendment replaces the temperature-only consumer restriction for the
isolated local experiment. Production registration, scheduling, raw members and
pressure-level access remain excluded. No normative status transition is made.

## ADDED Requirements

### Requirement: All provider surface statistics
The local experiment SHALL expose all 21 native surface fields with mean, p10,
p25, p50, p75 and p90 as distinct selectable readings. Each request SHALL fetch
only its selected field/statistic through the existing bounded statistics reader.
Native units, grid, null mask, run, valid time and object receipts SHALL survive.
Temperature SHALL be represented in degC, cloud fraction in percent, pressure
in hPa and accumulated precipitation in mm. Hourly precipitation and solar
energy SHALL retain their one-hour accumulation semantics. Provider percentiles
SHALL never be reconstructed from members or marked computed here.

#### Scenario: Fields are selected
- **WHEN** a user selects a field and provider statistic
- **THEN** only that exact native array is acquired and its native identity is disclosed

#### Scenario: Native data is absent
- **WHEN** a land SST cell is masked or a request exceeds a resource bound
- **THEN** missingness is retained without a fabricated value or substituted source

### Requirement: Native timeline selection
Historical and local forecast paths SHALL retain distinct scopes and select the
first native hourly forecast valid time at or after the selected timeline instant
within the configured or discovered published run. The native coordinate reader SHALL verify
the selected lead exists. Exact legacy calls SHALL remain exact. A historical
forecast SHALL remain a forecast, and SHALL not be rejected merely because its
run is historical. No out-of-run time or unsupported member SHALL be substituted.

#### Scenario: Timeline is between native hours
- **WHEN** a selection falls between two hours in the configured run
- **THEN** the following native hour is returned with the original selection retained

### Requirement: Legacy source visibility
Both Google and Open-Meteo WeatherNext 2 entries SHALL be hidden from discovery
and selection while their source ledger records remain available for audit.
WeatherNext 3 SHALL retain its explicit provider identity.

#### Scenario: Sources are browsed
- **WHEN** the user browses or searches sources
- **THEN** WeatherNext 2 is absent and WeatherNext 3 surface readings are discoverable

### Requirement: Bounded published run discovery
The opted-in internal runtime SHALL discover the newest available main-cycle
root at or before the selected instant (with at least one hour lead) and real
clock, probing at most four six-hour cycles under 15 seconds and 64 KiB metadata.
Successful native metadata SHALL pin generation, ETag and size before science
access. Discovery SHALL retain at most 16 roots for five minutes. Only declared
2026 archive paths SHALL be requested; unavailable backfill remains a gap.
All-field selection SHALL remain individual bounded reads, with two frontend
requests at a time. No raw-ensemble billing project SHALL be supplied.

#### Scenario: A run has not yet been published
- **WHEN** the newest nominal cycle has no root metadata
- **THEN** the next earlier candidate is checked within the same finite budget

#### Scenario: Authentication or discovery fails
- **WHEN** no permitted published root can be resolved
- **THEN** point data remains unavailable and no alternative identity is used

### Requirement: Runtime source consistency
The local web proxy SHALL target its own Compose project's API container, so
a separately running workbench API on the same network cannot supply an older
catalogue or point implementation through a shared service alias.

#### Scenario: Two API experiments share a network
- **WHEN** both containers advertise the generic api service name
- **THEN** this application's proxy consistently selects its own project API
