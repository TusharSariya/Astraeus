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
