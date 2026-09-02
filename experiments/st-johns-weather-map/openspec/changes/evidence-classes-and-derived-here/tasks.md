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

- [ ] 1.1 Add `Provenance.evidence_class` as a required `Literal` of the six
  values with no default; add `derived` to the recognised `Quality.flags`;
  keep `Quality.status` at four values.
  Verify: `cd api && uv run pytest tests/test_models.py -k evidence_class`
  fails for a provenance without the field and for a status of `derived`.
- [ ] 1.2 Add `evidence_classes` to the artifact manifest model and to
  `ingest/manifest.py` validation: a manifest set that disagrees with its
  values fails with `evidence_class_mismatch`.
  Verify: `cd api && uv run pytest tests/test_manifest.py -k evidence_classes`.

## 2. Store admission and isolation (API owner)

- [ ] 2.1 Replace the logical-name match in `LiveStore.sample_point` with
  class-based exclusion of `generated_display` artifacts.
  Verify: `cd api && uv run pytest tests/test_store_live.py -k
  "generated and renamed"` shows a renamed generated artifact still excluded.
- [ ] 2.2 Isolate provenance modelling failures per artifact: the failing
  artifact yields `null` and a notice, the rest answer, `data_mode` reflects
  the rest.
  Verify: `cd api && uv run pytest tests/test_store_live.py -k
  provenance_isolation`.
- [ ] 2.3 Enforce the four derived-here conditions and the worst-input
  quality rule at serve time; refuse non-retrieved inputs with a notice.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  derived_here`.
- [ ] 2.4 Serve `reprocessed`, `intermediary_derived` and
  `uncalibrated_observation` values as non-primary only.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  non_primary`.

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
- [ ] 3.2 Register the five first entries (relative humidity, wind speed and
  direction, ensemble statistics, sector sampling, DE442 geometry) and wire
  the existing relative-humidity derivation to its entry.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  relative_humidity` shows the entry name and `derived_here` in provenance.
  Verify result: **half done, left unticked.** All five entries are registered
  (`ENTRIES`, in that order; ensemble statistics and sector sampling
  `enabled: false`, see design.md) and relative humidity is served through its
  entry by `resolve_registered_relative_humidity`, verified by `cd api && uv
  run pytest tests/test_derivation_registry.py -k relative_humidity` (2
  passed): the entry name, the version and `evidence_class: derived_here`. The
  named verify command's file `tests/test_point_evidence.py` does not exist yet
  and `api/weather_api/store.py` belongs to the API owner, so the remaining
  half is one line at `store.py:1230`, replacing `resolve_relative_humidity`
  with `ingest.derive.registry.resolve_registered_relative_humidity` (same
  three-tuple).
- [x] 3.3 Add the deployment-level refusal environment variable and the
  reader-level switch contract.
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py -k
  disabled`.
  Verify result: 4 passed. `WEATHER_DERIVED_HERE=off` (also `0`, `false`, `no`,
  any case) refuses every derived value with a notice naming the variable and
  leaves retrieved values untouched; `catalogue(reader_disabled=[...])` is the
  reader-level contract and refuses per reader only.

## 4. Registry (ingest owner)

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
