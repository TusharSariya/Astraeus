## ADDED Requirements

### Requirement: CIOOS buoy demand values preserve literal native schema and unknown quality

After owner acceptance, the CIOOS buoy reader SHALL validate literal metadata
identifiers, standard names and units for its declared ten variables before
admitting a row. It SHALL preserve native values and units, zeroes and
individual nulls. Its local quality SHALL be `unknown` because the canonical
metadata exposes no quality variable; it SHALL NOT infer pass/fail, convert
units, derive a field, or reinterpret wind/wave `from` directions.

#### Scenario: A declared variable changes unit or standard name

- **WHEN** metadata for a requested buoy variable differs from its accepted
  identifier, standard name or literal unit
- **THEN** the source is unavailable and no mismatched value is relabelled or
  converted


### Requirement: CIOOS buoy current-context selection is bounded by native time and metadata coverage

After owner acceptance, the CIOOS buoy reader SHALL select the newest native
record at or before the aware selected instant only when its age is strictly
less than one hour. Before serving that record for a current-context request,
it SHALL parse the bounded metadata `time_coverage_end` and require it to be no more than two hours before the metadata acquisition
final-byte completion. A
future record, an exactly one-hour-old record, a missing/invalid coverage end,
a coverage end more than two hours old, or duplicate newest native report
identity SHALL produce unavailable evidence. It SHALL NOT interpolate, choose a
future or older report, substitute another station, or infer a cadence.

#### Scenario: The newest native report is exactly one hour old

- **WHEN** the newest native report at or before the selected instant is exactly
  one hour old
- **THEN** no buoy value is served

#### Scenario: A future native record exists

- **WHEN** a row is later than the selected instant
- **THEN** it is not eligible for selection and is not used to fill the request

#### Scenario: Duplicate newest native report identity is returned

- **WHEN** two rows have the same newest eligible report identity
- **THEN** current-context buoy evidence is unavailable because the reader does
  not choose between duplicate native reports

#### Scenario: Metadata coverage exceeds its ceiling

- **WHEN** `time_coverage_end` is more than two hours before metadata final-byte
  completion
- **THEN** current-context buoy evidence is unavailable and no cached or
  historical report substitutes

### Requirement: CIOOS buoy demand cache expires without stale report fallback

After owner acceptance, a CIOOS buoy cache key SHALL identify the canonical
metadata/data request, dataset id, fixed station identity, selected timestamp,
selection rule and sorted field set. Identical misses SHALL coalesce and a
fresh hit SHALL make zero provider payload requests. The cache SHALL preserve
native report time, station identity, units, missingness, bounded safe transport
receipt and final-byte completion. After expiry a failed refresh SHALL withhold
all values and may expose only bounded typed expiry metadata; it SHALL NOT
return stale rows, raw bodies, retained artifacts, a scheduled retrieval or a
neighbouring source.

#### Scenario: Refresh fails after expiry

- **WHEN** the canonical cache entry has expired and metadata or data refresh
  fails
- **THEN** the response reports unavailable with `values_withheld: true` and
  no buoy reading
