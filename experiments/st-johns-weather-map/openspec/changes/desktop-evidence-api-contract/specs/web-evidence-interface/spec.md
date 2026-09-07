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

### Requirement: Layer joins, forecast validity and freshness are explicit
A Layer SHALL expose explicit source-to-catalogue-field associations and their
mapping status or reason. A client SHALL NOT infer the relationship from a
layer title or product name. TAF evidence SHALL preserve its provider validity
start and end; it SHALL NOT infer an end from a neighboring forecast. Returned
run/freshness metadata SHALL use one authoritative run origin and state the
freshness assessment time. Missing origin, cadence, assessment time, mapping or
validity SHALL remain unknown with a reason.

#### Scenario: A mixed bundle layer has no inferred source mapping
- **WHEN** a layer contains readings from more than one source or field
- **THEN** the response lists each explicit source-to-field association rather
  than assigning one layer-wide inferred identity

#### Scenario: TAF has no provider end time
- **WHEN** a served TAF period lacks an end time from its provider
- **THEN** its end remains unknown and is not calculated from the next period

### Requirement: Focus coordinates and geographic refusal remain truthful
Desktop requests and links SHALL preserve full query coordinate precision;
rounding is display-only. A coordinate refused for geographic support SHALL
remain the Focus and return a typed outside-supported-area refusal with its
reason. It SHALL NOT substitute prior-point values, widen supported bounds, or
conflate that refusal with network or server failure.

#### Scenario: A point is outside the supported data area
- **WHEN** the reader selects a coordinate the API refuses for declared coverage
- **THEN** the coordinate remains selected with an outside-supported-area reason
  and no previous point reading is labelled as its evidence
