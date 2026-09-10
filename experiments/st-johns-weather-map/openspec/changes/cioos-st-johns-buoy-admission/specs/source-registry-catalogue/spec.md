## ADDED Requirements

### Requirement: CIOOS Atlantic St. John's buoy admission remains draft until current identity and coverage are proven

The proposed `cioos-atlantic-sma-st-johns` record SHALL identify CIOOS Atlantic
ERDDAP as distributor, Marine Institute as the metadata-named producer/operator,
dataset `SMA_st_johns` and UUID `92fdac9b-91b7-48f0-8afd-5d9d1b24db90`. It SHALL
cite the canonical CIOOS metadata and CC BY 4.0 catalogue URLs with read date.
It SHALL remain catalogued and unschedulable until an accepted implementation
validates current metadata, named-station identity, literal schema and coverage.
It SHALL NOT replace, merge with, promote, or relax the existing
`smartatlantic-st-johns` stale/licence-pending record.

#### Scenario: The canonical metadata remains stale

- **WHEN** metadata `time_coverage_end` fails the accepted current-context
  coverage ceiling
- **THEN** the CIOOS candidate returns unavailable with its own provenance and
  stale-coverage reason, and no SmartAtlantic, fixture, cache or historical row
  substitutes for it
