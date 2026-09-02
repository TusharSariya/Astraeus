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

- [ ] 3.1 Create `ingest/derive/registry.py` with entries carrying name,
  version, citation, inputs, output, physical range and range rule, `enabled`,
  and an approval record; refuse blending entries and unapproved entries at
  load.
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py`.
- [ ] 3.2 Register the first entries (relative humidity, wind speed and
  direction, fog state from the present-weather group, ensemble statistics,
  sector sampling, DE442 geometry) and wire the existing relative-humidity
  derivation to its entry. The API reads the registry through
  `ingest.derive.registry.get_entry(name)` and names three of them
  `relative_humidity_from_dew_point`,
  `wind_speed_and_direction_from_components` and
  `fog_state_from_present_weather`; see design.md for the entry shape.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  relative_humidity` shows the entry name and `derived_here` in provenance.
- [ ] 3.3 Add the deployment-level refusal environment variable and the
  reader-level switch contract.
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py -k
  disabled`.
- [ ] 3.4 Publish the class declaration on every artifact: each staged
  artifact's provenance carries `evidence_classes`, and
  `evidence_class_by_variable` wherever an artifact holds more than one class,
  written from `RunManifest.as_manifest_block`. Until an artifact declares
  them the API isolates it and answers `null` with a notice, because a class
  is never inferred from a name or a flag. (Added during implementation of
  section 2: the store now admits on the declaration, and no task published
  it.)
  Verify: `cd api && uv run pytest tests/test_ingest_store.py
  tests/test_manifest.py`.

## 4. Registry (ingest owner)

- [ ] 4.1 Add delivery kind `intermediary_derived` with producer, intermediary
  and method fields and per-field kind declaration to `registry/schema.json`;
  fail the audit for a record naming no intermediary.
  Verify: `python3 registry/audit.py` and `python3 -m unittest discover -s
  registry/tests -v`.
- [ ] 4.2 Add the Open-Meteo WeatherNext 2 record with cloud fields
  `intermediary_derived` and the rest `reprocessed`, status
  `credential_required`.
  Verify: `python3 registry/audit.py --summary-json` lists the record with
  no audit failure.

## 5. Web (web owner)

- [ ] 5.1 Render the class badge on every value and layer, add the legend,
  and render an unknown class as unavailable with the reason.
  Verify: `cd web && npm test -- --run evidence-class`.
- [ ] 5.2 Show a derived value's inputs and method on demand.
  Verify: `cd web && npm test -- --run derived-inputs`.

## 6. Gate

- [ ] 6.1 Run the full suite and the spec validators.
  Verify: `make test`, `openspec validate evidence-classes-and-derived-here
  --strict`, and `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
