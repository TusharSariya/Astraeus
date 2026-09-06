# Design

## Recommended option A: structural manifest plus snapshot lookup

Add an optional `native_geojson` branch to `RunManifest`, mutually exclusive
with canonical `fields`. Existing field manifests and `validate_run` behavior
remain byte-for-byte compatible. The new branch contains only source-shape
claims:

- required logical artifacts and their exact upstream collection identifiers;
- required GeoJSON root members (`type: FeatureCollection`, `features: list`);
- each feature's required structural members (`type: Feature`, mapping
  `properties`, and mapping-or-null `geometry`);
- the provider schema's property paths, JSON types and nullability, recorded
  under their exact native names;
- allowed geometry types copied from provider schema, with no inferred hazard
  meaning, area, severity or category;
- the source's time policy: `feature_time` with named provider property paths,
  or `query_snapshot` with no producer run/valid instant;
- the complete required collection set and one acquisition receipt per
  collection.

`validate_run` dispatches to the existing canonical-field path or a new
`validate_native_geojson` path and returns the same frozen, one-way
`ValidationResult`. A source-schema mismatch, absent required collection,
missing receipt, digest mismatch, invalid geometry shape, malformed property,
or partial artifact set lowers completeness and prevents publication.
Additional provider properties are preserved and reported as uncontracted.
Advertised but absent nullable properties receive `missing-in-snapshot`; an
empty collection receives `observed-empty` for every advertised property.

### Completeness and quality vocabulary

The verdict separates what Astraeus checked from what the provider asserted:

- `format_valid` means bytes, hashes, GeoJSON structure, declared source
  schema, collection set and time policy passed local checks;
- `provider_qc` is `passed`, `failed` or `unknown`, and defaults to `unknown`
  unless an exact provider QC field and mapping are declared;
- the existing `qc_passed` publication gate is computed from structural checks
  and an explicit provider failure, never written as a literal by an adapter;
- provenance quality states `scope: structural_format` and
  `provider_qc: unknown`; it does not describe the meteorological guidance as
  scientifically correct.

For ECCC outlook and hurricane products the initial provider-QC value is
`unknown`. Their native properties and geometry may be served verbatim after
format validation, but no property becomes a canonical point, profile or
timeline value.

### Time and identity

For `feature_time`, only successfully parsed provider properties populate
`run_time` and `valid_times`. For `query_snapshot`, `run_time` is null and
`valid_times` is empty. Its immutable snapshot identity is the ordered set of
collection body digests plus source id and schema version. The exact requested
window and every HTTP completion timestamp remain provenance; neither is a
source frame.

### Receipts

Every required collection carries its full request URL and query, received
body bytes, body SHA-256, HTTP completion UTC, and selected identity/cache
headers. Fetch must carry the discovery receipt unchanged. The run retrieval
time is the latest completion among all required receipts. Replay never
reconstructs a timestamp or header.

### Publication, API lookup and retention

Validated artifacts stage and publish through the existing single run
transaction. A failed snapshot leaves the prior current revision usable.
The existing `/features?valid_time=` endpoint remains frame-exact and never
serves a query snapshot.

Add snapshot metadata to the layer index and a lookup by immutable snapshot
identity, for example
`GET /layers/{layer_id}/snapshots/{provider_run_id}/features`. A valid empty
snapshot returns HTTP 200 with `features: []`, `observed_empty: true`, its query
window, retrieval time, source schema version and receipts. An unknown or
superseded identity returns 404; an integrity or store failure returns
`data_mode: unavailable` and never falls back. A layer may expose snapshot
identities while its frame `times` remains empty.

Retention uses the already accepted latest-and-previous complete-run rule per
logical stream. Query snapshots do not enter valid-time window arithmetic and
are never retained because their requested window overlaps the evidence
window. Staged-debris cleanup, digest verification and row-before-object purge
ordering remain unchanged.

## Alternatives

### Option B: map native properties into canonical fields

This reuses current `RunManifest` and APIs, but requires scientific definitions
for every hazard property and geometry. It risks equating guidance labels with
measured or forecast scalar fields. Reject unless separate owner-approved
science and registry work defines those meanings.

### Option C: keep native snapshots permanently nonpublishable

This is the current safest behavior and needs no contract change. It preserves
acquisition evidence but cannot expose the provider's structured product to a
user. Choose it if native-document delivery is outside Astraeus's intended
evidence model.

### Option D: use retrieval time as a frame

This fits the current frame endpoint but falsely states when the provider's
guidance was valid. Reject: an HTTP completion time is provenance about our
request, not a producer observation.

## Owner decisions

1. Approve Option A, choose another option, or keep the current unresolved
   state.
2. Confirm that `qc_passed` may mean the computed publication-safety gate when
   provenance separately states `scope: structural_format` and
   `provider_qc: unknown`; otherwise approve a wider verdict-model rename.
3. Confirm snapshot lookup by immutable provider-run identity and the existing
   latest-and-previous retention rule for source-time-less snapshots.
