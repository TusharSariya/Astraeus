Owned by this change: `openspec/changes/field-catalogue-and-families/**`,
`registry/fields.py` (new), `registry/fields.schema.json` (new),
`registry/audit.py` (catalogue checks), `ingest/manifest.py` (key
validation), every adapter's `RequiredField` list under `ingest/adapters/`
(re-keying only), `api/weather_api/models.py` (family, comparability, phase
on field responses), `web/src/` (family grouping and comparability
disclosure), and the tests named below. Not touched: adapter retrieval
logic, `openspec/config.yaml`, registry status.

Owners: registry and ingest (one owner); API (one owner); web (one owner).
Re-keying adapters and editing `models.py` must not happen concurrently with
the `evidence-classes-and-derived-here` change's owners on the same files;
apply that change first.

## 1. Catalogue (registry owner)

- [x] 1.1 Write `registry/fields.schema.json` and `registry/fields.py` with
  every key adapters declare today plus the families and comparability notes
  in `design.md`; split `total_cloud` into opacity-weighted, geometric and
  six-hour-mean keys; add the five-layer GOES fraction, transparency and
  seeing encodings, the 40/80/120 m fields, the astronomy geometry fields,
  the space-weather and marine families.
  Verify: `python3 registry/audit.py` reports the catalogue valid and every
  adapter key resolved.
  Verify result: pass — "catalogue valid: 135 fields in 20 families, version
  1.0.0, as of 2026-09-02" and "adapter keys: 43/43 resolved", exit 0.
- [x] 1.2 Add the per-source field mapping with `available-not-stored`
  entries for GFS, GEFS, ECMWF and ICON records outside the families.
  Verify: `python3 -m unittest discover -s registry/tests -v` includes a test
  that an uncatalogued manifest key fails.
  Verify result: pass — 54 tests OK, including
  `test_fields.AdapterManifestTests.test_an_uncatalogued_manifest_key_fails`
  (a `RequiredField("total_cloud", ...)` raises `uncatalogued_field:total_cloud`)
  and `SourceMappingTests.test_available_not_stored_is_distinct_from_a_gap_the_producer_leaves`.
  44 `available-not-stored` and 15 `not-published` entries across 28 sources.

## 2. Manifests and adapters (ingest owner)

- [x] 2.1 Validate manifest keys and units against the catalogue in
  `ingest/manifest.py`; report `uncatalogued_upstream_field` for unknown
  GeoMet coverages.
  Verify: `cd api && uv run pytest tests/test_manifest.py -k catalogue`.
  Verify result: pass — 7 passed, 11 deselected. Covers the refusal of an
  uncatalogued key and of a wrong unit at declaration, the level-expanded
  variable resolving to its profile key, and
  `uncatalogued_upstream_field` being reported as a notice that does not
  lower the verdict. Limit recorded in `design.md`: the notice covers the
  coverages a run asked for, not everything GeoMet advertises, because the
  unfiltered capabilities document is 39 MB and the adapter never fetches it.
- [x] 2.2 Re-key every adapter's `RequiredField` list; require the phase
  attribute on humidity fields.
  Verify: `cd api && uv run pytest tests/ -k "adapter and manifest"` passes
  with no `total_cloud` key remaining (`grep -r '"total_cloud"' ingest/`
  returns nothing).
  Verify result: pass — 9 passed, 6 skipped, 724 deselected; `grep -r
  '"total_cloud"' ingest/` returns nothing (exit 1). Every ECCC GEM path is
  `total_cloud_opacity`, GFS/ECMWF/ICON `total_cloud_geometric`, GEFS
  `total_cloud_mean_6h`, METAR/TAF `total_cloud_okta`; the GeoMet pressure
  profile is `relative_humidity_pressure`. The phase attribute is now required
  and stamped by every adapter that publishes humidity, including the three
  that did not before (GeoMet surface and profile, SWOB, METAR).

### The seam sections 3 and 4 code against

`registry/fields.py` is the single source of truth. Import it as
`from registry import fields as catalogue` (it ships beside `ingest/` and
`api/` in both images and pulls in nothing heavier than `re`). Use only these:

- `catalogue.field(key) -> Field` — raises `UnknownFieldKey`; never returns a
  placeholder. `Field` carries `key, quantity, units, family, level,
  level_coordinate, standard_name, comparability_group, evidence_classes,
  phase_attribute, range, description`.
- `catalogue.resolve(name) -> Resolved(field, level)` — accepts a plain key or
  a level-expanded artifact variable (`relative_humidity_850hPa`), returning
  the one profile key plus `"850 hPa"`. This is what `/point` should call on an
  artifact variable name.
- `catalogue.has_field(name) -> bool`, `catalogue.keys() -> tuple[str, ...]`.
- `catalogue.family_of(key) -> str`, `catalogue.family(name) -> Family`
  (`name, title, note, groups`), `catalogue.families()`,
  `catalogue.members(family_name) -> tuple[str, ...]`.
- `catalogue.units_for(key)`, `catalogue.requires_phase(key)`.
- `catalogue.comparability(a, b, *, phase_a=None, phase_b=None,
  temperature_k=None) -> Comparability(comparable, reason, detail)` with
  `.as_dict()`. Reasons are `family`, `definition`, `phase_missing`, `phase`.
  Pass the phases and the air temperature for a humidity pair or it answers
  `phase_missing`.
- `catalogue.phase_from_convention(rh_phase_convention) -> "liquid" | "mixed" |
  None`, and `catalogue.PHASE_ATTRIBUTE` for the attribute's name on a value.
- `catalogue.source_mapping(source_id) -> tuple[SourceField, ...]`
  (`source_id, key, upstream, storage, note, phase`),
  `catalogue.storage_of(source_id, key)`, `catalogue.phase_of(source_id, key)`,
  `catalogue.available_not_stored(source_id=None)`,
  `catalogue.not_published(source_id=None)`,
  `catalogue.source_scope(source_id) -> SourceScope`,
  `catalogue.key_for_upstream(source_id, producer_name)`.

`storage` is one of `stored`, `available-not-stored`, `not-published`, and the
three are different answers a response must keep apart. Nothing outside
`registry/fields.py` should reach into its tables.

## 3. Responses (API owner)

- [ ] 3.0 Re-key the API's own variable tables. Sections 1 and 2 left them
  untouched on purpose - they are the API owner's files - so the API still
  looks for a `total_cloud` no adapter writes any more, and live cloud will
  not reach `/point` or the raster layers until this lands. The places, all
  found by `grep -rn 'total_cloud' api/weather_api/` after excluding
  `total_cloud_weong`: `store.py` `FIELD_BY_VARIABLE` and the
  `("total_cloud", "percent")` entry near line 1968; the two
  `eccc-*-surface-total-cloud` specs in `grids.py`; the
  `geomet-live-hrdps-nt` spec in `wms.py`; `OBSERVATION_FIELDS` in `app.py`;
  and the fixture field in `fixtures.py`. ECCC GEM paths take
  `total_cloud_opacity`, GFS/ECMWF/ICON `total_cloud_geometric`, GEFS
  `total_cloud_mean_6h`, METAR/TAF `total_cloud_okta`. Prefer
  `catalogue.resolve()` over a hand-written table where the code is mapping an
  artifact variable name.
  Verify: `cd api && uv run pytest` stays green and a `/point` against a live
  HRDPS artifact returns a cloud value.
- [ ] 3.1 Add `family`, `comparability` and `phase` to field responses and
  compute pairwise comparability from the catalogue, including the
  below-freezing humidity rule.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  "family or comparab or phase"`.
- [ ] 3.2 Refuse to serve a variable with no catalogue key, with a notice.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  uncatalogued`.

## 4. Web (web owner)

- [x] 4.1 Group by family, change legends on member switch, refuse
  non-comparable difference views, show `available-not-stored`.
  Verify: `cd web && npm test -- --run family`.
  Verify result: pass — 27 tests in 2 files
  (`src/field-family.test.tsx`, `src/field-family-catalogue.test.ts`), and the
  whole suite stays green at 318 tests in 14 files with `npm run build`
  succeeding. New `web/src/fieldFamily.ts` (family, storage, absence and
  comparability logic), `FieldFamilyPanel.tsx` (family groups, difference view,
  per-source field catalogue), `MapFamilyLegend.tsx` (legend definitions and
  the not-one-ramp statement), and the generated `web/src/fieldFamilies.ts`
  written by `web/scripts/generate-field-families.mjs` — 20 families, 135
  fields, catalogue 1.0.0 — with a staleness test that re-runs the generator
  against `registry/fields.py` and `registry/fields.schema.json`. Every new
  response field is optional on the client, so the page renders against the
  API as it stands today; an absent `family` groups under `ungrouped` and is
  never inferred from a key's spelling. Recorded in `design.md` under "How the
  web says what a member measures".

## 5. Gate

- [ ] 5.1 `make test`, `openspec validate field-catalogue-and-families
  --strict`, `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
