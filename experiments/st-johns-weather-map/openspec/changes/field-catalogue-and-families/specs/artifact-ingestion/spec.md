## ADDED Requirements

### Requirement: Every published field of a subsettable source is stored
For a source retrieved through a service that subsets server side to the
evidence box (GeoMet WCS), the adapter SHALL retrieve and store every field
the producer publishes for that product, each under its catalogue key, subset
to the evidence box. A field the catalogue lacks SHALL block publication
until the catalogue is extended, never be silently skipped.

#### Scenario: A new coverage appears upstream
- **WHEN** GeoMet advertises an HRDPS coverage the catalogue does not know
- **THEN** the run publishes the known fields, reports the unknown coverage by name as `uncatalogued_upstream_field`, and the registry audit lists it until the catalogue is extended

#### Scenario: A known field is missing upstream
- **WHEN** a catalogued HRDPS field is absent from a run
- **THEN** the run publishes as partial with the field named, as completeness rules already require

### Requirement: A non-subsettable feed stores family fields and catalogues the rest
For a feed with no server-side subsetting (GFS, GEFS, ECMWF, ICON), the
adapter SHALL retrieve and store the fields the catalogue's families use, by
byte range where an index exists, and SHALL record every other record the
producer publishes as `available-not-stored` in the source's field mapping.
An `available-not-stored` field SHALL be visible in the catalogue and in the
source's status, and SHALL never be served as `null` without that reason.

#### Scenario: A GFS record outside the families
- **WHEN** a reader asks for a GFS field the catalogue marks `available-not-stored`
- **THEN** the response says the field is published upstream and not stored here, distinct from "not retrieved" and from "blocked"

#### Scenario: A family field is added
- **WHEN** the catalogue adds a field to a family that a non-subsettable feed publishes
- **THEN** the feed's stored set grows on the next run and the field leaves `available-not-stored`
