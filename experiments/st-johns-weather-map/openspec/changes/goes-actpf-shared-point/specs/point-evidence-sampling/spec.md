# Proposed ACTPF point requirements

Status: **draft; every SHALL below is proposed and has no authority until owner
acceptance**. This addition preserves the existing categorical meaning-string
requirement rather than replacing it.

## ADDED Requirements

### Requirement: ACTPF meaning strings retain typed native satellite provenance
A shared ACTPF `cloud_top_phase` field SHALL retain the native category code,
DQF, producer category table, granule identity, exact scan interval and typed
file-derived geostationary projection in `provenance.native_satellite` as
specified in this change's design. Existing sampled-cell coordinates, distance,
method, receipt, units and source identity SHALL remain attached. The public
value SHALL follow the existing CF meaning-string rule. Producer readability
SHALL NOT promote local quality from unknown or source operational status.

#### Scenario: A readable category is inspected
- **WHEN** a sampled ACTPF cell has DQF zero, a valid retained phase code and a
  matching producer CF meaning
- **THEN** the field value is that meaning, the integer and DQF remain in typed
  satellite provenance, and local quality remains explicitly unknown

#### Scenario: Quality or category is unavailable
- **WHEN** DQF is missing/nonzero, phase is masked, the category table has no
  matching meaning, or the existing spatial-distance ceiling is exceeded
- **THEN** the public field is null with the actual available native context
  and a reason, and no nearby good cell, numeric fallback or favorable cloud
  state replaces it

#### Scenario: A producer category table is malformed
- **WHEN** CF code/meaning cardinalities disagree or codes are duplicated
- **THEN** the reading is refused with an explicit category-metadata reason
  rather than resolved through a locally maintained lookup

### Requirement: ACTPF selected time equals the native scan start
A shared ACTPF point read SHALL match the selected instant exactly to native
scan start and SHALL preserve the actual scan end separately. No nearest-time,
latest-scan, contains-interval or inferred per-pixel-time substitution SHALL be
used. A source with no matching granule SHALL return unavailable.

#### Scenario: Selection differs from an available scan
- **WHEN** the selected instant is not exactly the available scan's native
  start, even when it is inside that scan interval or within one hour
- **THEN** that scan supplies no point value for the request

#### Scenario: Refresh cannot retrieve the selected scan
- **WHEN** revalidation/acquisition for the exact selected scan fails
- **THEN** the refresh reports unavailable and never substitutes another scan;
  existing unexpired-cache and fixed-expiry behavior remains unchanged
