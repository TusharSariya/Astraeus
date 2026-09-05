Owned: `ingest/space_weather.py` (new), `ingest/http.py`
(`download_with_headers`), `ingest/adapters/swpc.py`, `ingest/adapters/swpc_products.py`
(new), `ingest/adapters/gfz.py` (new), `ingest/adapters/__init__.py`
(`_MODULES`), `ingest/registry.py` (`VARIABLE_OVERRIDES`),
`registry/source_data.py` (space-weather records), `registry/tests/test_reach.py`,
`api/weather_api/store.py` (`read_series`), `api/weather_api/app.py`
(space-weather section), `api/weather_api/models.py` (space-weather models),
`api/tests/test_space_weather_series.py`, `test_adapter_swpc.py`,
`test_adapter_swpc_products.py`, `test_adapter_gfz.py`, `test_space_weather.py`,
`test_space_weather_registry.py`, `test_space_weather_products.py`,
`api/tests/fixtures/space_weather/*.json`, `scripts/space_weather_capture.py`,
`docs/research/wayfinder/space-weather-receipts/*.json`,
`docs/research/wayfinder/space-weather-integration-evidence.md`.
Not touched: `docs/specv1`, web, OVATION/Kp adapters' behaviour, the
`unavailable`, `partnership-only` and `link-only` space-weather states.

## 1. Seam

- [x] 1.1 `ingest/space_weather.py`: bounded receipted retrieval, feed-own
      instants, 1-D and platform-axis datasets, provenance with scope and
      mandatory intermediary for `reprocessed`; `read_series` platform axis
      and text values.
      Verify: `cd api && uv run pytest tests/test_space_weather_series.py -q`

## 2. Adapters

- [x] 2.1 RTSW v2 and plasma on `valid_time x spacecraft` with every flag.
      Verify: `cd api && uv run pytest tests/test_adapter_swpc.py -q`
- [x] 2.2 Propagated wind, Kp 1m, alerts, scales, GOES magnetometer, GOES
      X-ray, Kyoto Dst (reprocessed).
      Verify: `cd api && uv run pytest tests/test_adapter_swpc_products.py -q`
- [x] 2.3 GFZ Hp30 over a bounded 24 h selection with the licence checked.
      Verify: `cd api && uv run pytest tests/test_adapter_gfz.py -q`

## 3. Registry and scheduling

- [x] 3.1 Ten records schedulable (reach, native cadence, freshness,
      variables, RTSW condition satisfied, plasma endpoint corrected);
      tombstones unchanged in state.
      Verify: `make test-registry && cd api && uv run pytest tests/test_ingest_admission.py tests/test_ingest_registry_reach.py tests/test_space_weather_registry.py -q`

## 4. API readback

- [x] 4.1 `/space-weather` serves the active spacecraft's Bz by name;
      `/space-weather/products` reads every published series back; fixture
      mode fails closed.
      Verify: `cd api && uv run pytest tests/test_space_weather.py tests/test_space_weather_products.py -q`

## 5. Evidence

- [x] 5.1 One bounded live capture per feed with a receipt; hand-trimmed
      fixtures under 20 KB; no payload in Git.
      Verify: `git rev-list --objects origin/execution/free-source-contracts..HEAD | git cat-file --batch-check='%(objectsize) %(rest)' | sort -n | tail`
- [x] 5.2 `make test-api test-registry`, `specctl validate`, `openspec validate free-space-weather-products --strict`.
- [x] 5.3 Remaining dispositions recorded: STEREO-A keeps its settled
      `unavailable` tombstone, and live GFZ Kp/Hp60 are routed to native map-70
      child issue 150, which blocks issue 89. No state is promoted. The
      evidence-backed plasma endpoint correction and the non-operational
      products readback are completed experimental seams authorized by issue
      75.
