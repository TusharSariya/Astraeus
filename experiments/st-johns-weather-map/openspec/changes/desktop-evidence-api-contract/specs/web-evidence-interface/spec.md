## ADDED Requirements

### Requirement: Existing desktop responses expose reading identity without inference
The API representations used by the desktop SHALL expose the source, catalogue
field, actual valid or report time, evidence class, quality, native unit,
provenance and applicable station/report or run identity for every served
reading. A client SHALL NOT infer these from a layer title, product name,
delivery kind, source-wide coverage, or an empty result. Existing response
models SHALL be extended rather than replaced with a parallel untyped evidence
format.

#### Scenario: A station report has a separate report identity
- **WHEN** a reading has both station and report identity
- **THEN** both are exposed distinctly and neither is relabelled from the other

### Requirement: Read-only registered location metadata remains distinct from evidence
The desktop API SHALL expose only registered site, horizon and camera metadata
through read-only, versioned records after their serving schema is accepted. An
arbitrary point SHALL NOT gain a nearby registered horizon, a reference record
SHALL NOT become an observation, and a metadata response SHALL NOT authorize
camera imagery or registry writes.

#### Scenario: An arbitrary coordinate has no registered horizon
- **WHEN** a request names a coordinate without a selected matching registered site
- **THEN** the response explicitly reports no registered horizon rather than
  borrowing a nearby site's geometry
