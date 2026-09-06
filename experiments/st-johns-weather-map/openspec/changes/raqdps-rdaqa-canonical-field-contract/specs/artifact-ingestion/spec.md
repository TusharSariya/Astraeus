## ADDED Requirements

### Requirement: Product phase is part of RAQDPS and RDAQA run identity
Every selected artifact and manifest SHALL declare one approved `product_phase`: `forecast`, `forecast_statistic`, `preliminary`, `final`, or `firework_contribution`. RAQDPS SHALL retain provider reference and valid times. RDAQA SHALL retain its provider analysis valid time with `run_time: null` and no invented forecast lead. RDAQA immutable identity SHALL include source id, phase, valid time and ordered artifact digests.

#### Scenario: Preliminary and final share an analysis valid time
- **WHEN** complete preliminary and final products exist at the same valid time
- **THEN** they publish as distinct logical streams and neither overwrites or satisfies the other

#### Scenario: RDAQA carries no forecast reference time
- **WHEN** a PT0H analysis is assembled
- **THEN** its run time remains null and its analysis valid time is not relabelled as a forecast run

### Requirement: All fields and semantic attributes are manifest-validated per stream
The selected products SHALL be five atomic streams: RAQDPS hourly with 12 mandatory fields, RAQDPS statistics with 2, RDAQA preliminary with 6, RDAQA final with 6, and RDAQA FireWork contribution with 2. Every variable SHALL declare its approved `vertical_scope`; wildfire variables SHALL declare attribution. RAQDPS daily statistics SHALL declare a 24-hour window and `time: mean` or `time: maximum` as applicable. Shared validation SHALL compute completeness and QC. Because these WCS products expose no provider QC field, provenance SHALL state `provider_qc: unknown` separately.

#### Scenario: One mandatory phase field is missing
- **WHEN** one required field in a phase is absent or has mismatched units or attributes
- **THEN** that entire phase is refused without thinning and its previous revision remains current

#### Scenario: Daily maximum is presented as instantaneous
- **WHEN** the daily maximum lacks its 24-hour statistic window or `time: maximum` method
- **THEN** validation fails and no statistic artifact is published
