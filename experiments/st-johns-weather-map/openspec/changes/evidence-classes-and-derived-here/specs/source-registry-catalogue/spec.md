## ADDED Requirements

### Requirement: A record may declare intermediary-derived delivery
Beside `published_cell` and `reprocessed`, a registry record MAY declare the
delivery kind `intermediary_derived` for a product whose values an
intermediary computed from a producer's retrieved fields by the intermediary's
own method. Such a record SHALL name the producer, the intermediary and the
intermediary's method where documented, and SHALL declare which of its fields
carry that kind, because one intermediary may deliver reprocessed and
intermediary-derived fields for the same producer. Values from such fields
SHALL carry `evidence_class: intermediary_derived`. A record that declares the
kind without naming producer and intermediary SHALL fail the registry audit.

#### Scenario: Open-Meteo WeatherNext 2 cloud
- **WHEN** the registry declares Open-Meteo's WeatherNext 2 record with total, low, mid and high cloud as `intermediary_derived` and temperature as `reprocessed`
- **THEN** the audit passes, cloud values carry `intermediary_derived`, temperature values carry `reprocessed`, and both name Google WeatherNext 2 as producer and Open-Meteo as intermediary

#### Scenario: A record names no intermediary
- **WHEN** a record declares `intermediary_derived` and omits the intermediary
- **THEN** the audit fails naming the record, and the adapter is not schedulable
