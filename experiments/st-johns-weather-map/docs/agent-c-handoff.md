# Agent C handoff — API truth boundary

Scope owned: `api/weather_api/{app,models,fixtures,store,jobs,storage}.py`,
`api/tests/{test_api,test_live_store,conftest}.py`. Nothing committed.

## 1. DONE

All assigned tasks are implemented and green. Files actually modified on disk:

- `api/weather_api/models.py` — added `DataMode.UNAVAILABLE`; `Freshness.threshold_seconds`
  is now `int | None` (a registry record with no resolvable freshness promise must not
  borrow a default) and `Freshness.evaluate` accepts `None`; `SourceRecord` gained
  `category` and `schedulable`, `freshness_threshold_seconds` became optional, and the
  `fixture_status` / `live_smoke_status` Literals were widened to the registry's own
  vocabulary (`planned`, `blocked`, `not_applicable`); added `notices: list[str]` to
  `TimelineResponse`, `LayersResponse`, `PointResponse`, `ProfileResponse`,
  `SourceStatusResponse` so an outage or a dropped artifact is named in the response.
  `extra="forbid"`, the tz-aware validator and `operational: Literal[False]` untouched.

- `api/weather_api/store.py` —
  - `WEATHER_DATA_MODE` read once via `configured_mode()`, with `reset_data_mode()` as the
    test seam (`reset_live_store()` also resets it). Missing/blank/misspelt →
    `unavailable`, logged as an error. `WEATHER_FIXTURE_MODE` is gone; `live_store()`
    returns `None` outside live mode and logs the exception when the store is unreachable.
  - `_local_copy` now streams the download, computes size + SHA-256 and calls the new
    `_verify()` against `artifact.byte_size` and `artifact.provenance["sha256"]` before the
    file is cached. Mismatch, or a missing recorded digest, raises `ArtifactIntegrityError`
    and the `.part` file is removed. Cached copies are only ever written post-verification.
  - `SkippedArtifact` + `LiveStore.skipped` + `_record_skip()`: `sample_point`,
    `sample_profile` and `published_products` still skip a broken artifact (so one bad file
    cannot erase other evidence) but now log it and record it for the response `notices`.
  - New registry bridge: `registry_source_records()`, `registry_source_statuses()`,
    `schedulable_source_ids()`, `known_source_ids()` — all via `ingest.registry.ingest_configs()`
    and `registry.source_data.registry()`, following the existing `_registry_config` pattern.
    The registry `status` is a hard ceiling; nothing can emit `active`.
  - New unavailable-evidence builders: `unavailable_provenance()`, `unavailable_point_fields()`,
    `unavailable_profile_levels()` — value `None`, `data_mode=unavailable`,
    quality/coverage/freshness all `unknown`, `quality.flags` carrying `no_retrieval` plus a
    flag naming the outage.

- `api/weather_api/app.py` — rewritten. All seven `except Exception: → fixture` fallthroughs
  (old `:83`, `:103`, `:139`, `:204`, `:231`, `:267`, `:285`) are gone; every one now logs
  via `LOGGER.exception` and returns `data_mode=unavailable`. Mode is branched explicitly at
  the top of each handler.
  - `/catalog` derives from the registry in every mode (59 records, registry order).
  - `/timeline` in live mode is derived from `published_products()` only; an hour with
    nothing published lists nothing. No store / error / empty coverage → `unavailable`
    with the 28-hour shell and empty product lists.
  - `/layers` returns `unavailable` with `layers: []` instead of `fixtures.LAYERS`.
  - `/point` live: store error or empty artifact set → unavailable. Product selection maps
    to registry ids (`PRODUCT_SOURCE_IDS`) and filters live fields by
    `provenance.source_id`; a product with no published artifact returns unavailable naming
    that product, never another source's values. `fixtures.selected_forecast_fields` is
    reachable only in fixture mode.
  - `/profile` live: unavailable levels (null fields with provenance) rather than
    `profile_levels()`.
  - `/cross-section` still 501s, unchanged and unimplemented, as instructed.
  - `/sources/status` reports registry state; recorded retrieval only makes freshness
    measurable and sets that entry's `data_mode=live` — the state stays at the registry
    ceiling and `active` is never emitted.
  - `/refresh` rejects unknown ids and non-schedulable ids (`IngestConfig.ingestible`) with
    422; in live mode a down store is a 503, never a fixture job.
  - `/jobs/{id}` no longer falls back from the live store to the fixture job store.
  - `/ready` in live mode requires `live_store` **and** `evidence_boundary` (published
    artifacts covering `window_start..window_end`); fixture mode is ready and says
    `data_mode=fixture`; unavailable mode is `ready=false`.
  - `/health` reports the configured mode.

- `api/weather_api/fixtures.py` — module docstring stating it is synthetic and fixture-only;
  `provenance()` explicitly stamps `data_mode=DataMode.FIXTURE`; the bogus `cyyt-metar` id is
  now the real registry id `awc-metar-speci`; all six records carry `category` / `schedulable`;
  `source_statuses()` removed (the registry supplies it now). The `math.sin` generators are
  retained deliberately and are unreachable outside `WEATHER_DATA_MODE=fixture`.

- `api/tests/conftest.py` — the autouse fixture now sets `WEATHER_DATA_MODE=fixture`
  (replacing `WEATHER_FIXTURE_MODE=true`); added a `data_mode` fixture that flips the env var
  and resets the seam mid-test.

- `api/tests/test_api.py`, `api/tests/test_live_store.py` — see sections 4 and below.

`jobs.py` and `storage.py` needed no change.

## 2. INCOMPLETE

Nothing. No stubs or TODOs were left.

## 3. NOT STARTED

None of the assigned tasks. Two things outside my ownership that the change depends on:

- `compose.yaml:29,57` still set `WEATHER_FIXTURE_MODE: "true"`, which is now a dead
  variable. The api and worker services must be switched to `WEATHER_DATA_MODE` (plan Step 6,
  not my file). Until then a composed api falls closed to `unavailable` — which is the
  correct failure, but not the intended configuration.
- `web/` reads none of the new `data_mode: "unavailable"` value or the new `notices` arrays
  yet (Agent D's scope).

## 4. TESTS CHANGED

Three existing tests asserted behaviour this task deliberately removes:

- `test_catalog_is_explicitly_experimental_and_machine_readable` →
  `test_catalog_is_the_whole_registry_and_never_claims_an_active_source`. It asserted the
  catalogue was exactly six `implementing` records with `live_smoke_status == "not_run"`.
  The catalogue is now the 59-record registry, which legitimately contains
  `credential_required`, `licence_review`, `unavailable` and `retired` records. The new test
  asserts registry identity and order, the count of 59, that no source is `active`, and that
  `schedulable` matches `IngestConfig.ingestible`.
- `test_source_status_does_not_claim_live_activity_or_freshness` →
  `test_source_status_reports_registry_state_and_never_claims_live_activity`. Same reason:
  it asserted every status was `implementing`. It now asserts each reported state equals the
  registry's own `status`, that `active` never appears, and that freshness stays unknown
  without a recorded retrieval.
- `test_ready_reports_the_absent_live_store_without_blocking_readiness` →
  `test_a_fixture_deployment_is_ready_but_says_so`. Renamed only; its assertions are
  unchanged and still valid for fixture mode. The behaviour it described — ready while
  `live_store: false` — is now scoped to fixture mode and is contradicted for live mode by
  the new `test_live_readiness_requires_the_store_and_a_current_evidence_boundary`.

`test_refresh_job_is_fixture_only_and_validates_sources` was kept as-is (still passes) and a
new sibling added for non-schedulable ids.

Tests added (all new):
`test_the_fixture_catalogue_only_names_real_registry_ids`,
`test_refresh_rejects_a_source_the_scheduler_could_never_run` (parametrized over
`google-weathernext-2`, `raw-cwop-pws`, `nl-511`),
`test_a_live_failure_reports_unavailable_instead_of_a_fixture_number` (store-raises /
nothing-published), `test_a_live_failure_leaves_the_profile_unavailable_rather_than_synthetic`,
`test_a_missing_or_malformed_data_mode_fails_closed_to_unavailable` (6 cases including the
old `WEATHER_FIXTURE_MODE`-style `"true"`), `test_fixture_mode_stamps_every_single_field_as_fixture`,
`test_product_selection_never_claims_a_source_that_published_nothing`,
`test_the_timeline_lists_only_hours_that_actually_have_a_published_artifact`,
`test_layers_are_unavailable_rather_than_the_fixture_list_when_nothing_is_published`,
`test_live_readiness_requires_the_store_and_a_current_evidence_boundary`,
`test_a_live_source_status_never_promotes_a_source_to_active`,
`test_a_refresh_cannot_be_faked_into_a_fixture_job_when_the_live_store_is_down`;
and in `test_live_store.py`: `test_bytes_that_do_not_match_the_recorded_digest_are_refused`,
`test_an_artifact_with_no_recorded_digest_is_unverifiable_and_so_unavailable`,
`test_a_corrupt_artifact_is_dropped_with_a_flag_while_the_others_survive`.

## 5. TEST STATUS

Last run I actually observed, from `experiments/st-johns-weather-map`:

```
$ uv run --project api pytest api/tests/test_api.py api/tests/test_live_store.py \
      api/tests/test_science.py api/tests/test_storage.py -q
........................................................................ [ 80%]
..................                                                       [100%]
```

90 passed, 0 failed — the four suites that fall inside or adjacent to my ownership.

The full `cd api && uv run pytest` is currently RED, but not from my files. The first
failure is `tests/test_adapter_eccc_datamart.py::test_hrdps_discover` raising
`ingest.contract.AdapterUnavailable: eccc-hrdps: no populated run cycle under
https://dd.weather.gc.ca/{20260829,20260828}/WXO-DD/model_hrdps/continental/2.5km/` —
Agent B's in-flight discovery rework in `ingest/adapters/eccc_datamart.py`, which I do not own
and did not touch. I have not observed a clean full-suite run.

The coordinator's report of a `ValidationError` at `fixtures.py:54` for missing `category` /
`schedulable` was a snapshot of a partially-applied edit; all six `SOURCES` records supply
both fields on disk now and the autouse fixture imports cleanly.

Agent A's `science.py`: `select_fallback`, `build_consensus`, `ConsensusCandidate`,
`resolve_relative_humidity`, `fog_state`, `radar_echo_semantics`, `HUMIDITY_DERIVATION` all
still import fine from `weather_api.science`. Nothing anomalous seen.

## 6. NEXT STEPS

1. Re-run the full suite once Agent B's adapter work settles: `cd api && uv run pytest`.
   Expect the only remaining failures to be adapter/ingest ones.
2. Switch `compose.yaml` (api and worker) from `WEATHER_FIXTURE_MODE: "true"` to
   `WEATHER_DATA_MODE: live` (or `fixture` for a fixture stack) and give the api service
   read-only MinIO credentials. `WEATHER_FIXTURE_MODE` is now ignored entirely.
3. Have `web/src/api.ts` map `data_mode` to its `DataSource`: `"unavailable"` must render as
   unavailable, and `"fixture"` must never render as "Live API". Surface the new
   `notices[]` arrays and the per-field `provenance.data_mode`.
4. Optional follow-up, deliberately not done: `registry/source_data.py:97` still types
   CIOPS/RDWPS/GDSPS/HRDPA/RDPA/CaLDAS as `deterministic_forecast`, so
   `store._consensus_candidates` can still treat an ocean or analysis product as a
   deterministic forecast vote. That file is outside my ownership.
5. `/cross-section` remains a deliberate 501. Do not implement it before normalized spatial
   arrays and a sampling contract exist.
