Owned by this change: `openspec/changes/ensemble-families-and-member-statistics/**`
only. Nothing under `registry/`, `ingest/`, `api/`, `web/` or
`openspec/config.yaml` is touched here, and no registry status is promoted.
The implementation files named per task are the files the implementation pass
will own; they are recorded so that the parallel owners below do not collide,
and are explicitly NOT edited by this change.

Owners: specs owner (tasks 1 and 5); registry owner (task 2, implementation
pass); ingest owner (task 3, implementation pass); API owner (task 4.1 to 4.3,
implementation pass); web owner (task 4.4, implementation pass). Tasks 2 to 4
must not start before `ensemble-members-and-source-plurality`,
`evidence-classes-and-derived-here` and `field-catalogue-and-families` are
applied, because they own `registry/source_data.py`, the derivation registry
and `registry/fields.py` respectively.

Decision reference: wayfinder ticket
[#22](https://github.com/TusharSariya/Astraeus/issues/22), owner resolution
2026-09-02. Measurements:
`docs/research/wayfinder/ensemble-access.md` on branch
`research/ensemble-access`.

## 1. Specification (specs owner, this change)

- [x] 1.1 Declare the six families, their build order, their subsettability
  and storage scope, the control-as-flagged-member rule and the REPS direction
  gap in `specs/source-registry-catalogue/spec.md`.
  Owned file: `openspec/changes/ensemble-families-and-member-statistics/specs/source-registry-catalogue/spec.md`.
  Verify: `openspec validate ensemble-families-and-member-statistics --strict`.

- [x] 1.2 Specify the control landing on the member axis, the per-family
  storage scope at ingest, and the time-averaged field key and window in
  `specs/artifact-ingestion/spec.md`.
  Owned file: `openspec/changes/ensemble-families-and-member-statistics/specs/artifact-ingestion/spec.md`.
  Verify: `openspec validate ensemble-families-and-member-statistics --strict`.

- [x] 1.3 Register the five statistics and their refusals in
  `specs/derivation-method-registry/spec.md`.
  Owned file: `openspec/changes/ensemble-families-and-member-statistics/specs/derivation-method-registry/spec.md`.
  Verify: `grep -c '^#### Scenario' openspec/changes/ensemble-families-and-member-statistics/specs/derivation-method-registry/spec.md` reports 12, four per requirement, with an absence case in each.

- [x] 1.4 Specify serving statistics beside members, the three fail-closed
  refusals and the naming rule in `specs/point-evidence-sampling/spec.md`.
  Owned file: `openspec/changes/ensemble-families-and-member-statistics/specs/point-evidence-sampling/spec.md`.
  Verify: `openspec validate ensemble-families-and-member-statistics --strict`.

- [x] 1.5 Modify the expert-control requirement so member becomes a request
  parameter, and add the member selector, the naming rule and the
  averaged-cloud fence in `specs/web-evidence-interface/spec.md`.
  Owned file: `openspec/changes/ensemble-families-and-member-statistics/specs/web-evidence-interface/spec.md`.
  Verify: `diff <(grep '^#### Scenario' openspec/specs/web-evidence-interface/spec.md | sed -n '/Run, member and level/,+3p') <(grep '^#### Scenario' openspec/changes/ensemble-families-and-member-statistics/specs/web-evidence-interface/spec.md | head -4)` shows the four original scenario titles carried over in order.

- [x] 1.6 Cross-check every ADDED heading against `openspec/specs/` and
  against every open change, which `openspec validate` does not do.
  Verify: `grep -rh '^### Requirement' openspec/changes/ensemble-families-and-member-statistics/specs/ | sort | uniq -d` is empty, and each heading is grepped against `openspec/specs/` and `openspec/changes/*/specs/` with only the one intended MODIFIED collision.

## 2. Registry (registry owner, implementation pass, NOT in this change)

- [ ] 2.1 Add the six family declarations to `registry/source_data.py`:
  build order, subsettability, storage scope, expected member count, control
  identification rule, declared gaps. ICON-EPS is declared unverified and not
  schedulable.
  Owned files: `registry/source_data.py`, `registry/schema.json`,
  `registry/catalogue_coverage.json`, `ingest/registry.py` (the `ensemble`
  block on `IngestConfig` and the `ingestible` gate, Seam A),
  `api/tests/test_ingest_ensemble_declaration.py`.
  Verify: `python3 registry/audit.py && cd api && uv run pytest tests/test_ingest_ensemble_declaration.py`.

- [ ] 2.2 Add the audit rules: an ensemble record with no subsettability, no
  control rule where it declares members, or a declared gap that is also
  declared published, is refused.
  Owned file: `registry/audit.py`.
  Verify: `python3 -m unittest discover -s registry/tests`.

- [x] 2.3 Record the REPS direction gap and the GEFS six-hour-mean cloud key
  in `registry/fields.py`, against the catalogue that
  `field-catalogue-and-families` creates.
  Owned file: `registry/fields.py`.
  Verify: `python3 registry/audit.py` reports the catalogue valid with the
  averaged-cloud key present and no REPS direction key.
  Verify result: `python3 registry/audit.py` -> `catalogue valid: 135 fields
  in 20 families, version 1.0.0, as of 2026-09-02`; `grep -n '"noaa-gefs",
  "total_cloud_mean_6h"' registry/fields.py` -> present (upstream
  `TCDC:entire atmosphere (n-n+6 hour ave fcst)`, matching
  docs/research/wayfinder/ensemble-access.md); `grep -n '"eccc-reps".*wind_'
  registry/fields.py` -> only `wind_direction_10m` marked `not-published`,
  no stored or derived REPS direction key. `api && uv run pytest` -> 968
  passed, 36 skipped. `python3 -m unittest discover -s registry/tests` ->
  88 passed.

## 3. Ingest (ingest owner, implementation pass, NOT in this change)

- [ ] 3.1 One adapter per access shape, built in the declared order: GeoMet
  WCS per-member coverages (REPS), ECMWF byte ranges with a separate control
  file (AIFS-ENS), ECMWF byte ranges with the control in the member file
  (IFS ENS), S3 byte ranges per member file (GEFS).
  Owned files: `ingest/adapters/eccc_geomet_ensemble.py`,
  `ingest/adapters/ecmwf_opendata.py`, `ingest/adapters/noaa_s3.py`,
  `ingest/adapters/__init__.py`, `api/tests/test_adapter_ensemble.py`.
  Verify: `cd api && uv run pytest tests/ -k "ensemble and adapter"`.

- [ ] 3.2 Apply the per-family storage scope and write the
  `available-not-stored` list into the manifest.
  Owned files: `ingest/manifest.py`, `api/tests/test_manifest.py`.
  Verify: `cd api && uv run pytest tests/test_manifest.py -k "scope or available_not_stored"`.

- [x] 3.3 Set the control flag on the member axis, including the two-file
  AIFS-ENS case, and store the averaging window on a time-averaged field.
  Owned files: `ingest/grib.py`, `ingest/manifest.py`,
  `api/tests/test_ingest_grib.py`, `api/tests/test_ingest_manifest.py`.
  Verify: `cd api && uv run pytest tests/test_ingest_grib.py tests/test_ingest_manifest.py -k "control or averaging_window or member"`.
  Verify result: `cd api && uv run pytest tests/test_ingest_grib.py tests/test_ingest_manifest.py -k "control or averaging_window or member"` -> 40 passed, 56 deselected. Full `cd api && uv run pytest` -> 1009 passed, 36 skipped.
  Live smoke remains: no member feed is scheduled (every family's `schedulable`
  is false until 2.1 lands and owner gate 6.1 is decided), so nothing has yet
  stacked a real REPS coverage set or a real AIFS-ENS `cf` plus `pf` pair, and
  no real GEFS `.idx` `N-M hour ave fcst` label has been read end to end. The
  fixture tests are the whole of the evidence here; the first scheduled member
  run is the smoke.

## 4. Serving and reading (API owner 4.1 to 4.3, web owner 4.4, implementation pass, NOT in this change)

- [x] 4.1 Add the five derivation registry entries with inputs, ranges,
  conventions, control treatment and the registration-time refusals.
  Owned files: `ingest/derive/registry.py`, `api/tests/test_derivation_registry.py`
  (the change's plan named `api/weather_api/derivations.py`, which does not
  exist; the registry is `ingest/derive/registry.py`).
  Verify: `cd api && uv run pytest tests/test_derivation_registry.py -k ensemble`.
  Verify result: `cd api && uv run pytest tests/test_derivation_registry.py -k ensemble` -> 21 passed, 18 deselected.

- [ ] 4.2 Serve statistics beside members with the family, run, statistic and
  member set on every value, and refuse a cross-family, cross-run or
  reduction-mixing request at derive time.
  Owned files: `api/weather_api/store.py`, `api/weather_api/science.py`,
  `api/weather_api/app.py` (passing the Seam D request parameters through),
  `api/tests/test_point_evidence.py`.
  Verify: `cd api && uv run pytest tests/test_point_evidence.py -k "ensemble and (refus or member_set)"`.

- [x] 4.3 Add the member request parameter and the statistic, member set,
  partial and run-stale fields to the response models.
  Owned files: `api/weather_api/models.py`, `api/weather_api/fixtures.py`,
  `api/tests/test_api.py`, `api/tests/test_models.py`.
  Verify: `cd api && uv run pytest tests/test_api.py tests/test_models.py -k member`.
  Verify result: `cd api && uv run pytest tests/test_api.py tests/test_models.py
  -k member` -> 43 passed, 81 deselected. Full `cd api && uv run pytest` ->
  1073 passed, 36 skipped.
  Run staleness reuses `Provenance.run_stale` and `Provenance.run_stale_reason`
  from the horizon-tiers change: `EnsembleProvenance` hangs off that same
  `Provenance`, so the existing field is reachable and no second one was added.
  `EnsembleMemberSet` deliberately carries no `run_stale`, and a test asserts
  the absence so it is not added later by accident.
  Ownership note (lead, 2026-09-02): 4.3 also edited `api/weather_api/app.py`
  for exactly two things, because 4.2 starts from this merged result - the five
  Seam D `Query` parameters on `get_point` (with `statistic` checked against
  `ENSEMBLE_STATISTIC_ENTRIES` and `comparison` against `ge|gt|le|lt`, both 422
  on a bad value) and the fixture-mode answer. `_live_point` and
  `api/weather_api/store.py` were not touched; 4.2 wires live mode.

- [ ] 4.4 Add the member selector, the statistic layers, the labelling rule in
  the text alternative and the averaged-versus-instantaneous fence.
  Owned files: `web/src/App.tsx`, `web/src/api.ts`, `web/src/types.ts`,
  `web/src/ensemble.test.tsx` and any new `web/src/Ensemble*.tsx` component
  (`web/src/components/` does not exist; components sit flat under `web/src/`).
  Verify: `cd web && npm test -- --run ensemble`.

## 5. Gate (specs owner)

- [ ] 5.1 `make test`, then
  `openspec validate ensemble-families-and-member-statistics --strict`, then
  `uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate`.

## 6. Owner gates (owner decisions; agents do not tick these)

- [ ] 6.1 Accept the upstream cost of the non-subsettable families: about
  7.7 MB per field per lead across 31 GEFS members, about 29 MB per lead for
  one IFS ENS field across 51 members and about 72 MB for the same AIFS-ENS
  field, all to store a few KB each. REPS at 40 224 bytes per member field per
  lead needs no such acceptance.
- [ ] 6.2 Accept that `ensemble-members-and-source-plurality` forbids computing
  any statistic at sample time, which ticket 22 reverses. That sentence must
  be corrected in that change before either is archived; only the owner
  decides which change carries the correction.
- [ ] 6.3 Decide whether ICON-EPS is measured before or after the other five
  are built, since nothing about it has been verified and it cannot be
  scheduled until it is.
- [ ] 6.4 Decide the owner-approved minimum member count, if any, for each
  statistic entry, since none is invented at derive time.
