# Agent A handoff — fail-closed ingestion, storage integrity, registry categories

> **Tree state: source compiles and imports cleanly. Nothing is silently broken.**
> **18 API tests fail. Every failure is an existing test asserting the old
> behaviour I was asked to delete** (`complete is True`, `"status": "passed"`,
> `today/` discovery paths, ECMWF/DWD returning candidates). No production module
> is half-edited. The tests are the unfinished half of the work — see INCOMPLETE.

---

## 1. DONE — files actually on disk

### New files
| File | What it is |
|---|---|
| `ingest/manifest.py` | The fail-closed validator. `RequiredField`, `RunManifest`, `ValidationResult`, `validate_run(...)`, `required_leads(...)`. `ValidationResult` is frozen and its only mutator (`failing`) can lower a verdict and never raise one, so `complete=False` has no route back to publishable. Detects: missing non-optional field, all-NaN field, wrong normalized units (→ `qc_passed=False`), any `decode_errors` entry, missing `required_valid_times`, zero-size lat/lon axis, coverage below threshold. `as_quality()` / `as_coverage()` produce the provenance blocks. |
| `ingest/meteorology.py` | Worker-importable science: `relative_humidity_from_dewpoint`, `resolve_relative_humidity`, `HUMIDITY_DERIVATION(_VERSION)`, `fog_state`, `radar_echo_semantics`, `precipitation_interval_hours`, `interpolate_wind`, `haversine_km`. MetPy and the explicit `phase="liquid"` preserved verbatim. |
| `infra/postgres/init/002_run_publication.sql` | Additive migration (001 untouched). `weather_experiment.publish_run(uuid) RETURNS integer` — gates on the **parent `model_runs`** row, supersedes prior pointers, publishes every staged artifact of the run and upserts `current_artifacts` in one call; raises otherwise. `BEFORE UPDATE` trigger `artifact_revisions_immutable_metadata` rejecting changes to `object_key` / `sha256` / `byte_size` / `created_at`. Partial index + `weather_experiment.orphaned_objects` view for orphan detection. |

### Modified files
| File | Change |
|---|---|
| `api/weather_api/science.py` | Rewritten as re-export. Inserts `EXPERIMENT_ROOT` on `sys.path` (same pattern as `store.py`), then `from ingest.meteorology import (...)  # noqa: F401`. Keeps `ConsensusCandidate`, `ConsensusResult`, `build_consensus`, `select_fallback`, `to_newfoundland`, `validate_distinct_environmental_quantity`. **Public names are identical** — `tests/test_science.py` passes unchanged (15 passed, verified). |
| `ingest/grib.py` | `write_zarr` now writes to a temporary `zarr.storage.LocalStore` directory, then zips it deterministically (`ZIP_STORED`, sorted entries, fixed timestamps) and **round-trips it** (reopen via `ZipStore` + `open_zarr(consolidated=False)`, raise `GribError` if any data_var or coord was lost). Verified under `python -W error::UserWarning`: no `Duplicate name:` warnings, 9 zip entries, 9 unique. Also added `cap_open_range(...)` + `DEFAULT_TRAILING_MESSAGE_CAP` to bound a trailing open-ended `.idx` range so `bytes=N-` cannot pull a 521 MiB remainder into memory. |
| `ingest/adapters/awc.py` | `METAR_MANIFEST` / `TAF_MANIFEST`. Import fixed: `from ingest.meteorology import resolve_relative_humidity` (was `weather_api.science`, absent from the worker image). Temperature parse failures now collected into `decode_errors` instead of `except: pass`. All `complete=True` / `qc_passed=True` / `"status": "passed"` literals deleted; verdict comes from `validate_run`. |
| `ingest/adapters/eccc_datamart.py` | Rewritten. Discovery walks the **dated** path `https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/{model}/{HH}/{FFF}/` and **falls back to the previous UTC date** when today's directory is empty (the 00Z rollover). `provider_run_id` and `run_time` are parsed from the **filename's own `{YYYYMMDD}T{HH}Z` stamp** (`parse_run_stamp`); a cycle whose `000/` carries no stamp or mixes stamps is skipped rather than mislabelled. A per-file stamp mismatch during fetch becomes a decode error. **GDPS `15km` → `10km`.** Every missing/undecodable variable is now a `decode_errors` entry. |
| `ingest/adapters/noaa_s3.py` | `GFS_MANIFEST`; hard lead ceiling (`GFS_HOURLY_LEAD_LIMIT = 120`, ctor-overridable) — a window needing a lead beyond the product range raises `AdapterUnavailable`. `.idx` subsetting confirmed in use and now wrapped in `cap_open_range` for the final open-ended record. Silent `continue`s → `decode_errors`. `precipitation_accumulation` deliberately **not** declared (its normalized unit/interval is unverified). |
| `ingest/adapters/eccc_ogc.py` | `SWOB_MANIFEST` + `_coverage_floor(...)`. Provider QC flags containing `fail`/`reject` are passed in as decode errors. Coverage threshold is derived per run from the station/grid geometry, with the reasoning documented in the function (the `(time, lat, lon)` outer product can never be dense for scattered stations). Provider flags kept under `quality.provider_flags`. |
| `ingest/adapters/ecmwf_opendata.py` | Reduced to a registered, **non-publishing** adapter. `discover` and `fetch` both raise `AdapterUnavailable(UNRESOLVED_REASON)` naming the verified fact (`data.ecmwf.int/forecasts/` lists ~4 days; `20260830/` 404s). `parse_ecmwf_index` kept and still tested. No regrid, no guess. |
| `ingest/adapters/dwd_icon.py` | Same treatment. `UNRESOLVED_REASON` states the icosahedral-grid blocker explicitly. **No regrid invented.** |
| `ingest/store.py` | Added `publish_run(run_id) -> int` calling `SELECT weather_experiment.publish_run(%s)`. `stage_and_publish` is now `record_run` → stage all → **one** `publish_run` call (was one `publish()` per revision in separate transactions). `publish()` kept for compatibility. |
| `registry/source_data.py` | `_eccc_model` takes an explicit `category`. Corrected: HRDPS/RDPS/GDPS `deterministic_forecast`; REPS/GEPS `ensemble`; HRDPS-WEonG `postprocessed_forecast`; Integrated Nowcasting `nowcasting`; HRDPA/RDPA/HREPA/CaLDAS `analysis`; HRDLPS `land_surface_forecast`; CIOPS-East `ocean`; RDWPS/REWPS `wave`; GDSPS/RESPS `surge`. **No `status` changed; nothing became `active`.** `registry/schema.json` does *not* enum-constrain `category` (it is `$defs/nonempty`), so no schema edit was needed. |
| `ingest/registry.py` | `FORECAST_CATEGORIES` restated deliberately with the reasoning in a comment: added `postprocessed_forecast`, `nowcasting`, `land_surface_forecast`, `ocean`, `wave`, `surge`; **removed `hydrology`** (real-time station observations) and **`air_quality`** (mixes RAQDPS forecast with AQHI observations and wildfire hotspots). `analysis` and `aviation` stay excluded. Only genuine forecast products now get `lead_hours`. |

### Verified commands
```
cd registry && uv run --with-requirements requirements.txt --with pytest python -m pytest tests -q
  → 6 passed in 0.12s
cd registry && uv run ... python audit.py --summary-json
  → registry valid; categories now include analysis=4, ocean=1, wave=2, surge=2,
    nowcasting=1, postprocessed_forecast=1, land_surface_forecast=1
cd api && uv run pytest tests/test_science.py -q
  → 15 passed
zarr round-trip under `python -W error::UserWarning`
  → no warnings, 9/9 unique zip entries, values recovered
```

---

## 2. INCOMPLETE

**Nothing is half-edited in a production module.** Every file listed above is
complete, imports cleanly, and is internally consistent.

What is incomplete is the **test suite**, which I did not get to update before
being stopped. The 18 failures are all tests asserting behaviour I was
explicitly asked to remove:

- `tests/test_adapter_eccc_datamart.py` — mocks the old `today/model_hrdps/...`
  URL shape and asserts `provider_run_id == "2026082912"` derived from
  `window.now`; also asserts `result.complete is True`. Needs the dated
  `{YYYYMMDD}/WXO-DD/...` URL map and filename-derived run id.
- `tests/test_adapter_ecmwf.py`, `tests/test_adapter_dwd.py` — expect
  `discover()` to return candidates; both adapters now raise
  `AdapterUnavailable` by design. `test_dwd_fetch` also references names
  (`open_grib`, `crop_to_bbox`) that the module no longer imports.
- `tests/test_adapter_noaa_s3.py::test_noaa_gfs_fetch_subset_ranges` — asserts
  `complete is True`; the mocked dataset omits declared fields, which is now
  correctly a `missing_field` failure.
- `tests/test_adapter_eccc_ogc.py::test_swob_fetch_creates_zarr` — asserts
  `provenance["quality"]["flags"]` contains `air_temp-qa:passed`; provider flags
  moved to `quality.provider_flags` and `flags` now holds machine-readable
  validation reasons.
- `tests/test_ingest_store.py::test_publication_happens_only_after_every_artifact_is_staged`
  — asserts two `publish` statements; there is now one `publish_run`. It also
  hits `ValueError: invalid literal for int() with base 10: 'id-1'` because the
  test's `RecordingCursor.fetchone()` returns `('id-1',)` and `publish_run`
  coerces to `int`. **Fix the double (return an integer for `publish_run`), not
  the production code** — the SQL function genuinely returns `integer`.
  `_statement_kind` in that file also needs a `("publish_run", "publish_run")`
  marker ahead of the `publish_revision` one.

**No new tests were written.** The whole "TESTS (yours to write)" section of my
brief is untouched.

---

## 3. NOT STARTED

Of the assigned implementation tasks: **none**. All ten landed
(`manifest.py`, `meteorology.py`, adapter fail-closed rewrite, ECCC dated-path
discovery, GDPS 15km→10km, GFS lead ceiling, `grib.py write_zarr`,
`002_run_publication.sql`, `store.publish_run`, registry category fix).

Not started, from the test brief:
- Updating the 18 failing existing tests (above).
- New failure-case tests: missing required field, all-NaN field, bad units,
  missing lead/valid time, decode error passed in, empty bbox crop, coverage
  below threshold, GFS lead outside range, ECCC 00Z rollover fallback,
  filename-derived run id, Zarr round-trip under `-W error::UserWarning`,
  `publish_run` refusing a run whose parent is incomplete.
- `002_run_publication.sql` has **never been executed against a live
  PostgreSQL**. It is unverified SQL. It must be applied to a real instance
  before it is trusted.

---

## 4. TEST STATUS — verbatim, last observed

```
$ cd api && uv run pytest
18 failed, 143 passed in 1.44s
```

Named failures observed (a `-q` run listed 9; failure counts differ between runs
because ordering is randomised and some failures cascade — treat 18 as the
figure and re-run to enumerate):

```
FAILED tests/test_adapter_dwd.py::test_dwd_discover - ingest.contract.Adapter...
FAILED tests/test_adapter_dwd.py::test_dwd_fetch - AttributeError: 'module' o...
FAILED tests/test_adapter_eccc_datamart.py::test_hrdps_discover - ingest.cont...
FAILED tests/test_adapter_eccc_datamart.py::test_eccc_fetch_with_mocked_decode
FAILED tests/test_adapter_eccc_ogc.py::test_swob_fetch_creates_zarr - Asserti...
FAILED tests/test_adapter_ecmwf.py::test_ecmwf_discover - ingest.contract.Ada...
FAILED tests/test_adapter_ecmwf.py::test_ecmwf_fetch - AttributeError: 'modul...
FAILED tests/test_adapter_noaa_s3.py::test_noaa_gfs_fetch_subset_ranges - Ass...
FAILED tests/test_ingest_store.py::test_publication_happens_only_after_every_artifact_is_staged
```

Baseline before my changes was 135 passed. `tests/test_api.py` and
`tests/test_live_store.py` (not mine) were passing at last observation.

---

## 5. NEXT STEPS, in order

1. `cd api && uv run pytest -p no:randomly` to get the stable full failure list.
2. Fix `tests/test_ingest_store.py` first — it is the cheapest and it is a test
   double bug, not a code bug. Make `RecordingCursor.fetchone()` return an
   integer for the `publish_run` statement, add `("publish_run", "publish_run")`
   to `_statement_kind` **before** the `publish_revision` entry, and change
   `test_publication_happens_only_after_every_artifact_is_staged` to expect one
   `publish_run` after all `insert_revision`s.
3. Rewrite `tests/test_adapter_eccc_datamart.py` against the dated path
   (`https://dd.weather.gc.ca/20260829/WXO-DD/model_hrdps/continental/2.5km/12/000/`)
   with a filename carrying a `20260829T12Z` stamp, and add the 00Z-rollover
   case: today's date listing empty, yesterday's populated.
4. Rewrite `tests/test_adapter_ecmwf.py` / `test_adapter_dwd.py` to assert
   `pytest.raises(AdapterUnavailable)` from both `discover` and `fetch`, keeping
   the `parse_ecmwf_index` unit test as-is.
5. Extend the mocked datasets in `test_adapter_noaa_s3.py` and
   `test_adapter_eccc_ogc.py` so a *good* run really satisfies its manifest,
   then assert `result.complete is True` — and add the mirror-image cases where
   one declared field is dropped and the run must come back `complete=False`.
6. Write `api/tests/test_ingest_manifest.py` covering the full failure matrix in
   section 3.
7. Apply `infra/postgres/init/002_run_publication.sql` to a live PostgreSQL and
   prove: a run with `complete=false` makes `publish_run` raise and leaves
   `current_artifacts` byte-for-byte unchanged; an `UPDATE` touching `sha256`
   raises; `orphaned_objects` lists an abandoned staged revision.
8. Re-run `cd api && uv run pytest` and
   `uv run --with-requirements ../registry/requirements.txt --with pytest python -m pytest ../registry/tests`.

### Open uncertainties, stated rather than guessed
- **GDPS grid token.** The directory is `model_gdps/10km/` (verified), but I did
  not verify the `RLatLon…` token inside the filenames, so `grid_token` is set
  to the string `"10km"` rather than an asserted grid spacing.
- **RDPS path.** `model_rdps/10km` was inherited, not re-verified live.
- **SWOB coverage.** The `(time, lat, lon)` outer-product layout is structurally
  sparse for a scattered station network. `_coverage_floor` scales the threshold
  by the achievable occupancy and documents why; a `station`-dimension layout
  would be the real fix, but that changes the artifact contract
  `api/weather_api/store.py` reads, which is outside my file ownership.
- **METAR/TAF coverage thresholds** are set to 0.9 with the reasoning inline. A
  reviewer should confirm that judgement rather than inherit it.
- **No registry source was marked `active`.** No credentials were requested.
