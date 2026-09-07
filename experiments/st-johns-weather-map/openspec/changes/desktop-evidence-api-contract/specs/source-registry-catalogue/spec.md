## ADDED Requirements

### Requirement: Served registry metadata is versioned and read-only
When registered site, horizon or camera metadata is exposed to the desktop, the
response SHALL name the registry version and preserve each record's declared
identity, geometry basis, eligibility and absence information. The endpoint
SHALL NOT provide registry writes, implicit source admission, camera-image
delivery or unreviewed private configuration.

#### Scenario: A camera is registered but ineligible
- **WHEN** a registered camera record declares that it is not eligible for a
  requested use
- **THEN** the read-only response preserves that declared ineligibility and does
  not present an image or inferred alternative
