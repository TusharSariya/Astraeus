# Design

## Recommended decision: structural manifest plus snapshot lookup

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

### Measured storage consequence and admission boundary

The retained five-collection ECCC capture measured 4,556 received bytes in
total (892, 911, 901, 926 and 926 bytes). Two immutable revisions of bodies at
that observed size consume 9,112 bytes; staging a replacement beside them
raises the body-only peak to 13,668 bytes, about 0.00002% of the accepted 64
GiB hot-store ceiling. The populated alert sample was 13,801 bytes, showing
that seasonal empty snapshots are not a sizing proxy for active events.

The recommendation therefore does not turn those samples into capacity
limits. Each source must declare and enforce received, stored, filesystem and
margin bounds before activation. The current experimental five-collection
HTTP ceiling is 5 x 8 MiB = 40 MiB received per operation; it is a refusal
ceiling, not proof of serialized-artifact or filesystem peak. Activation stays
blocked until measurements bound those additional copies and the admission
calculation proves that the complete staged operation plus two retained
revisions fits the 64 GiB quota. This keeps the contract decision independent
from an unsupported capacity promise.

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

The recommended API eligibility ceiling is 24 hours from the latest HTTP
completion in the required receipt set. This is a proposed acquisition-age
safety limit, not a provider cadence, source valid time or claim that the
guidance remains meteorologically fresh for 24 hours. At age greater than
86,400 seconds the current snapshot route returns unavailable with an expired
reason and no fallback, even if no refresh succeeded. An absent or unmeasurable
receipt completion time is immediately unavailable.

Retention uses the already accepted latest-and-previous complete-run rule per
logical stream. Only the current, unexpired identity is route-eligible. The
previous complete revision is retained solely for integrity audit and atomic
failure recovery; direct lookup returns 404 because it is superseded. Query
snapshots do not enter valid-time window arithmetic. Staged-debris cleanup,
digest verification and row-before-object purge ordering remain unchanged.

This recommendation is one indivisible contract choice. Approval means that
`qc_passed` remains the shared validator's computed publication-safety gate,
while provenance separately and explicitly reports `format_valid`,
`scope: structural_format`, and `provider_qc: unknown`. It also means that a
source-time-less document is addressed only by immutable snapshot identity and
uses the 24-hour receipt-age refusal above with the existing latest-and-previous
retention rule. Retrieval time remains receipt provenance and is never eligible
as a frame time.

## Valid alternatives

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

## Owner decision

Approve the recommended contract above as one package, or leave native
GeoJSON nonpublishable under Option C. Option B remains available only after a
separate science and registry contract. Retrieval time is excluded as a valid
alternative because it contradicts the source-time rule rather than expressing
a viable design tradeoff.
