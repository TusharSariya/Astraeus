Owned by this change: `openspec/changes/evidence-classes-and-derived-here/**`,
`api/weather_api/models.py` (Provenance, Quality, manifest models),
`api/weather_api/store.py` (class-based admission and per-artifact
isolation), `ingest/derive/registry.py` (new), `ingest/manifest.py`
(evidence_classes), `registry/schema.json` and `registry/source_data.py`
(delivery kind `intermediary_derived`, the Open-Meteo WeatherNext 2 record),
`web/src/` (badge and legend), and the tests named below. Not touched: any
adapter's retrieval logic, `openspec/config.yaml` carve-outs, any registry
status promotion.

Work is parallelisable across three owners: API and store; ingest and
registry; web. Do not edit `models.py` and `store.py` from two owners at once.

## 1. Models and validation (API owner)

- [x] 1.1 Add `Provenance.evidence_class` as a required `Literal` of the six
  values with no default; add `derived` to the recognised `Quality.flags`;
  keep `Quality.status` at four values.
  Verify: `cd api && uv run pytest tests/test_models.py -k evidence_class`
  fails for a provenance without the field and for a status of `derived`.
  Verify result: 9 passed - a provenance without the field and an unknown
  class are both refused, `Quality(status="derived")` is refused, and
  `derived` stands as a flag beside the four statuses.
- [x] 1.2 Add `evidence_classes` to the artifact manifest model and to
  `ingest/manifest.py` validation: a manifest set that disagrees with its
  values fails with `evidence_class_mismatch`.
  Verify: `cd api && uv run pytest tests/test_manifest.py -k evidence_classes`.
  Verify result: 7 passed - a manifest declaring only `retrieved` beside a
  `derived_here` field fails QC with `evidence_class_mismatch:derived_here`,
  and a value stamped with a class its field did not declare fails too.

## 2. Store admission and isolation (API owner)

- [x] 2.1 Replace the logical-name match in `LiveStore.sample_point` with
  class-based exclusion of `generated_display` artifacts.
  Verify: `cd api && uv run pytest tests/test_store_live.py -k
  "generated and renamed"` shows a renamed generated artifact still excluded.
  Verify result: 1 passed - a generated artifact published under a logical
  name the sampler has never seen is excluded by its declared class, and the
  point stays frame-exact. `_is_display_only` now reads the manifest classes;
  the `derived`/`generated` provenance flags are no longer consulted.
- [x] 2.2 Isolate provenance modelling failures per artifact: the failing
  artifact yields `null` and a notice, the rest answer, `data_mode` reflects
  the rest.
  Verify: `cd api && uv run pytest tests/test_store_live.py -k
  provenance_isolation`.
  Verify result: 4 passed - an artifact declaring no classes, an unknown
  class, or a class it never stated for a value answers `null` with a notice
  naming its source and revision, while every other artifact answers; with
  every artifact unmodelled the point path returns no fields, so the caller
  reports `unavailable` rather than a fixture value.
- [x] 2.3 Enforce the four derived-here conditions and the worst-input
  quality rule at serve time; refuse non-retrieved inputs with a notice.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  derived_here`.
  Verify result: 7 passed - a derived value carries `derived_here`, its
  inputs with their own provenance, the entry's version and citation, and the
  worst input's quality with a `derived` flag; a non-retrieved input, an
  unregistered or disabled method, and a result outside the declared physical
  range each yield `null` with a notice naming the failed condition.
- [x] 2.4 Serve `reprocessed`, `intermediary_derived` and
  `uncalibrated_observation` values as non-primary only.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  non_primary`.
  Verify result: 6 passed - each of the three is served beside the others
  with `display_primary_eligible` false, an `intermediary_derived` value
  names its intermediary and that intermediary's method, and none of the
  three is ever read as a derivation input.

## 3. Derivation method registry (ingest owner)

- [x] 3.1 Create `ingest/derive/registry.py` with entries carrying name,
  version, citation, inputs, output, physical range and range rule, `enabled`,
  and an approval record; refuse blending entries and unapproved entries at
  load.
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py`.
  Verify result: 18 passed. An entry with no approval record and each of the
  three blending shapes (same field from two sources, two members of one field
  family from two sources, a provider reduction with another member set) raise
  `RegistryError` at construction, so importing the module with one refuses to
  load.
- [x] 3.2 Register the first entries (relative humidity, wind speed and
  direction, fog state from the present-weather group, ensemble statistics,
  sector sampling, DE442 geometry) and wire the existing derivations to their
  entries. One interface: the API gates on `registry.resolve`, constructs
  through `derive_relative_humidity`, `derive_wind` and `derive_fog_state`,
  and names entries by the registry's own names; see design.md.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  relative_humidity` shows the entry name and `derived_here` in provenance.
  Verify result: 2 passed - a derived relative humidity carries
  `evidence_class: derived_here`, `derivation:
  relative_humidity_from_dewpoint_liquid`, the entry's version and its
  citation, and a published relative humidity is still never replaced by one.
  The seam reconciliation that made this true (merge 2026-09-02): the API's
  `get_entry` seam is gone, the entry names are the registry's, the range
  rules are the registry's four, `fog_state_from_present_weather` was added to
  `ENTRIES` because `/point` already served that derivation, and
  `tests/test_point_evidence.py` pins the API's three method names against the
  registry's constants so they cannot drift. Also verified: `cd api && uv run
  pytest tests/test_derivation_registry.py` (18 passed).
- [x] 3.3 Add the deployment-level refusal environment variable and the
  reader-level switch contract.
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py -k
  disabled`.
  Verify result: 4 passed. `WEATHER_DERIVED_HERE=off` (also `0`, `false`, `no`,
  any case) refuses every derived value with a notice naming the variable and
  leaves retrieved values untouched; `catalogue(reader_disabled=[...])` is the
  reader-level contract and refuses per reader only.
- [x] 3.4 Publish the class declaration on every artifact: each staged
  artifact's provenance carries `evidence_classes`, and
  `evidence_class_by_variable` wherever an artifact holds more than one class,
  written from `RunManifest.as_manifest_block`. Until an artifact declares
  them the API isolates it and answers `null` with a notice, because a class
  is never inferred from a name or a flag. (Added during implementation of
  section 2: the store now admits on the declaration, and no task published
  it.)
  Verify: `cd api && uv run pytest tests/test_ingest_store.py
  tests/test_manifest.py`.
  Verify result: 28 passed. Every artifact-producing path declares: the four
  manifest-backed adapters (AWC METAR and TAF, ECCC SWOB, ECCC Datamart, NOAA
  GFS - both its surface and upper_air artifacts) splat
  `RunManifest.as_manifest_block()`; GeoMet declares once in
  `_base_provenance`, which every one of its eight artifacts is built on;
  SWPC's three and GOES-19's one declare `retrieved` through
  `ingest.manifest.declared_classes`; cloud motion and the WEonG low-cloud
  repair declare `generated_display`. `ArtifactStore.stage` now refuses an
  artifact that declares nothing, declares a class outside the six, or whose
  per-variable classes are not in its declared set
  (`UndeclaredEvidenceClasses`), with nothing uploaded or recorded - staging
  is the one gate every artifact passes, and a declaration missed there would
  publish and be isolated at read time instead. The adapter tests assert the
  declaration on the artifacts they build. No Open-Meteo adapter exists yet,
  so its `intermediary_derived` cloud fields have no artifact to declare;
  registry record and API provenance carry the kind (4.0/4.1).

## 4. Registry (ingest owner)

- [x] 4.0 Add the delivery-kind field itself (`published_cell` | `reprocessed`) to
  `registry/schema.json` and to every record in `registry/source_data.py`,
  the audit rule that refuses a reprocessed record as a display primary, the
  provenance fields, and the interface label. Deferred here from
  `ensemble-members-and-source-plurality` task 2b.5, which specified the
  field without implementing it; 4.1 extends the same field.
  Verify: `python3 registry/audit.py` and `python3 -m unittest discover -s
  registry/tests -v`.
  Verify result: **registry half done, left unticked for the rest.** Audit
  clean ("registry valid: 64 sources"); 25 tests ran, OK. `delivery_kind` and
  `display_primary` are required on every record; all 64 declare a kind
  (60 `published_cell`, 3 `reprocessed`, 1 `intermediary_derived`); the audit
  refuses a record with no kind, a `reprocessed` record that names no
  intermediary distinct from its producer or documents no transformation, and
  any record whose `display_primary` is true while its kind is not
  `published_cell`.
  **Naming deviation:** the task text above writes the producer-direct kind as
  `retrieved`, but both spec deltas name it `published_cell`
  (`ensemble-members-and-source-plurality/specs/source-registry-catalogue`
  "Every source declares how its values reach this deployment", and this
  change's own "A record may declare intermediary-derived delivery", which
  reads "Beside `published_cell` and `reprocessed`"). `retrieved` is an
  evidence class, not a delivery kind, and the two axes are deliberately
  separate: an `intermediary_derived` value is still retrieved by this
  deployment. The accepted spec text is implemented; renaming the kind would
  need a spec delta, not a code edit.
  **API half, done 2026-09-02 (second wave):** `Provenance` carries
  `delivery_kind`, `intermediary`, `intermediary_method` and
  `source_display_primary`; `display_primary_eligible` is computed from all
  three refusals - the evidence class, the delivery kind, and the record's own
  `display_primary` - so it can never disagree with what it is computed from.
  `SourceRecord` (the `/catalog` model) gains `delivery_kind`, `intermediary`
  and `display_primary`, copied from the record in `registry_source_records`.
  `IngestConfig` carries the four registry fields so `live_provenance` can
  name them on every value without reopening the registry per field; an
  artifact may override the intermediary for itself, and where it does not the
  record's stands. Verified: `cd api && uv run pytest tests/test_point_evidence.py`
  (23 passed, including the WeatherNext 2 record serving
  `delivery_kind: intermediary_derived`, intermediary Open-Meteo and
  `display_primary_eligible: false`, and a `display_primary: false` record
  refusing the primary while its class and kind would allow it); `python3
  registry/audit.py` (registry valid: 64 sources); `python3 -m unittest
  discover -s registry/tests` (25 tests, OK).
  **Web half, done 2026-09-02 (second wave, see 5.4):** the interface label
  beside the class badge ("producer's own cell", "reprocessed by
  <intermediary>", "computed by <intermediary>") read from
  `provenance.delivery_kind` and `provenance.intermediary`, and a value whose
  `provenance.display_primary_eligible` is false, or whose catalogue record
  has `display_primary: false`, is never rendered as a field's primary.
  All three halves are done; ticked at merge.
- [x] 4.1 Add delivery kind `intermediary_derived` with producer, intermediary
  and method fields and per-field kind declaration to `registry/schema.json`;
  fail the audit for a record naming no intermediary.
  Verify: `python3 registry/audit.py` and `python3 -m unittest discover -s
  registry/tests -v`.
  Verify result: audit clean ("registry valid: 64 sources"); 17 tests ran, OK
  (6 existing, 11 new in `registry/tests/test_delivery_kind.py`). A record that
  declares the kind and drops its intermediary, names the producer as the
  intermediary, names no field carrying the kind, or names a field it does not
  publish, each fails the audit naming the record. `delivery_kind` is optional
  at record level until `ensemble-members-and-source-plurality` makes it
  required (design.md).
- [x] 4.2 Add the Open-Meteo WeatherNext 2 record with cloud fields
  `intermediary_derived` and the rest `reprocessed`, status
  `credential_required`.
  Verify: `python3 registry/audit.py --summary-json` lists the record with
  no audit failure.
  Verify result: exit 0, `"intermediary_derived_sources":
  ["open-meteo-weathernext-2"]` and `"delivery_kind_counts":
  {"intermediary_derived": 1, "undeclared": 63}`. Total, low, middle and high
  cloud carry `intermediary_derived`; the other nine fields `reprocessed`;
  producer Google DeepMind, intermediary Open-Meteo with its documented
  humidity-profile method and all six of its transformations; status
  `credential_required`, fixture and live smoke `blocked`. No status is
  promoted.

## 5. Web (web owner)

- [x] 5.1 Render the class badge on every value and layer, add the legend,
  and render an unknown class as unavailable with the reason.
  Verify: `cd web && npm test -- --run evidence-class`.
  Verify result: 12 passed (1 file). Badge on every attributed value, on the
  hero reading, on every drawer layer row and in the provenance table; legend
  names all six plus the unrecognised state; an unrecognised OR absent class
  shows "Unavailable" with the reason and no number. Layer-drawer badge
  rendering is additionally asserted in `MapPanel.test.tsx` (3 new cases),
  which owns the MapLibre fake.
- [x] 5.2 Show a derived value's inputs and method on demand.
  Verify: `cd web && npm test -- --run derived-inputs`.
  Verify result: 6 passed (1 file). A `derived_here` value discloses its
  method name, version and citation, its quality with the `derived` flag, and
  each input with source, valid time, quality and its own class badge; the
  panel is closed until asked; no such panel exists for any other class.
- [x] 5.3 Gate the web slice: whole suite and production build.
  Verify: `cd web && npm test -- --run` and `cd web && npm run build`.
  Verify result: 258 passed across 10 files (unit + gl projects); `tsc -b`
  and `vite build` clean. The pre-existing App/MapPanel fixtures were stamped
  `evidence_class: retrieved` through one helper, because the required field
  with no default means a value without one no longer renders as a number.

- [x] 5.4 The web half of task 4.0, plus the flat provenance contract: the
  delivery-kind label beside the class badge and in the source catalogue; a
  value that may not be a display primary rendered only as an alternative
  reading; a refused derivation and an unmodelled artifact rendered as
  unavailable with the response's own notice.
  Verify: `cd web && npm test -- --run delivery-kind`.
  Verify result: 20 passed (1 file). The label reads "producer's own cell",
  "reprocessed by <intermediary>" and "computed by <intermediary>", names an
  unnamed intermediary rather than reading as the producer's own, and renders
  NOTHING when the record declared no kind (the kind is a registry attribute;
  its absence is not an evidence failure). `pickField` now refuses a value
  that is not display-primary even when the response selected its source and
  even when it is the field's only value; refusal comes from
  `provenance.display_primary_eligible` OR the catalogue's
  `display_primary: false`, and the refused value is rendered under
  "Retrieved, but never the reading" with its badge, its label and, where the
  intermediary documents nothing, the statement that the transformation is
  undocumented rather than absent. `derivation_refused` and
  `provenance_unmodelled` render "Unavailable" with the matching response
  notice, and say the response gave no reason when it carried none.
  Contract: the web reads the API's FLAT provenance (`derivation`,
  `derivation_version`, `derivation_citation`, `derivation_inputs[]` with
  `field, source_id, product, valid_time, run_time, units, evidence_class,
  quality`, plus `intermediary`, `intermediary_method`); `derivation_method`
  as an object is still accepted first because it costs three lines. design.md
  "Web contract" describes the real shape.
  Whole suite after it: 291 passed across 12 files; `npm run build` clean.

## 6. Gate

- [x] 6.1 Run the full suite and the spec validators.
  Verify: `make test`, `openspec validate evidence-classes-and-derived-here
  --strict`, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.

  Verify result (2026-09-02, merged tree `execution/evidence-classes`):
  `make test` green - API 839 passed, 25 skipped; web 291 passed in 12
  files; registry 25 passed; SQL publish tests all PASS; specctl 0 errors,
  0 warnings. `openspec validate evidence-classes-and-derived-here --strict`
  valid.