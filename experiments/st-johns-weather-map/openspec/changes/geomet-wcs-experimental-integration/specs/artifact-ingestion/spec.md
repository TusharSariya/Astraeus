## ADDED Requirements

### Requirement: GeoMet WCS metadata gates numeric acquisition
The experimental GeoMet WCS client SHALL retrieve the matching WMS leaf
metadata before acquiring a coverage.  It SHALL select only an advertised
valid time and, when present, an advertised reference time.  An absent run
identity SHALL remain unknown and SHALL NOT be borrowed from another layer or
the latest model cycle.

#### Scenario: Requested time is absent
- **WHEN** a requested time is outside the WMS leaf's advertised time extent
- **THEN** acquisition fails before publication and no neighbouring or default field is substituted

#### Scenario: Published run identity is absent
- **WHEN** a coverage has no reference-time dimension
- **THEN** provenance records unknown run identity and does not infer one

### Requirement: WCS requests have explicit bounded geometry
Every numeric request SHALL carry `FORMAT=image/tiff`, longitude and latitude
`SUBSET`, and explicit `SCALESIZE`.  One operation SHALL select at most 64
fields, one coverage SHALL contain at most 200,000 pixels and at most 2 MiB,
and provider calls SHALL be sequential.

#### Scenario: GeoMet returns a full grid or default resampling
- **WHEN** the TIFF dimensions or georeferencing differ from the requested geometry
- **THEN** the artifact is rejected rather than cropped or relabelled locally

#### Scenario: HTTP success carries an exception
- **WHEN** GeoMet returns HTTP 200 with XML `NoMatch` or another exception instead of TIFF bytes
- **THEN** acquisition fails closed and removes the partial file

### Requirement: Numeric class products retain producer encoding
`RDPS_10km_SeeingIndex` and `RDPS_10km_SkyTransparencyIndex` SHALL be stored as
`seeing_class_eccc` and `transparency_class_eccc` with dimensionless class
units.  The client SHALL NOT convert either field to arcseconds, magnitudes,
percent, a favourable score, or a quality mask without a separately accepted
rule.

#### Scenario: A class zero is retrieved
- **WHEN** a valid GeoTIFF cell contains `0`
- **THEN** the artifact preserves `0` and provenance states that its class-versus-not-computed meaning is unresolved

### Requirement: Experimental WCS artifacts cannot activate production
The WCS module SHALL remain absent from the adapter registry and every artifact
SHALL carry `operational: false` while this change is unaccepted.

#### Scenario: Normal adapter discovery runs
- **WHEN** the production adapter loader imports its configured modules
- **THEN** the numeric WCS module is not imported, registered or scheduled and the existing Datamart model adapters remain owners
