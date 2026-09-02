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

- [ ] 1.1 Write `registry/fields.schema.json` and `registry/fields.py` with
  every key adapters declare today plus the families and comparability notes
  in `design.md`; split `total_cloud` into opacity-weighted, geometric and
  six-hour-mean keys; add the five-layer GOES fraction, transparency and
  seeing encodings, the 40/80/120 m fields, the astronomy geometry fields,
  the space-weather and marine families.
  Verify: `python3 registry/audit.py` reports the catalogue valid and every
  adapter key resolved.
- [ ] 1.2 Add the per-source field mapping with `available-not-stored`
  entries for GFS, GEFS, ECMWF and ICON records outside the families.
  Verify: `python3 -m unittest discover -s registry/tests -v` includes a test
  that an uncatalogued manifest key fails.

## 2. Manifests and adapters (ingest owner)

- [ ] 2.1 Validate manifest keys and units against the catalogue in
  `ingest/manifest.py`; report `uncatalogued_upstream_field` for unknown
  GeoMet coverages.
  Verify: `cd api && uv run pytest tests/test_manifest.py -k catalogue`.
- [ ] 2.2 Re-key every adapter's `RequiredField` list; require the phase
  attribute on humidity fields.
  Verify: `cd api && uv run pytest tests/ -k "adapter and manifest"` passes
  with no `total_cloud` key remaining (`grep -r '"total_cloud"' ingest/`
  returns nothing).

## 3. Responses (API owner)

- [ ] 3.1 Add `family`, `comparability` and `phase` to field responses and
  compute pairwise comparability from the catalogue, including the
  below-freezing humidity rule.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  "family or comparab or phase"`.
- [ ] 3.2 Refuse to serve a variable with no catalogue key, with a notice.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k
  uncatalogued`.

## 4. Web (web owner)

- [ ] 4.1 Group by family, change legends on member switch, refuse
  non-comparable difference views, show `available-not-stored`.
  Verify: `cd web && npm test -- --run family`.

## 5. Gate

- [ ] 5.1 `make test`, `openspec validate field-catalogue-and-families
  --strict`, `uv run --project ../../tools/specs python
  ../../tools/specs/specctl.py validate`.
