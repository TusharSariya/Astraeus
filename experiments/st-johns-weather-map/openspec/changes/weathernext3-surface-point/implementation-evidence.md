# WeatherNext 3 surface delivery evidence

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Owner requested WeatherNext 3 historical and forecast integration, hiding WN2,
and explicitly confirmed all 126 surface statistics on 2026-09-08.

## Contract mapping

- All provider fields: `registry/weathernext.py`, registry field catalogue,
  `weathernext_delivery.py`; 126 parametrized value/unit/statistic/null tests.
- Native time and identity: opt-in `field` point selector, the existing bounded
  native coordinate decoder, `weathernext_runs.py`, and next-hour/refusal tests.
- Legacy visibility: discovery hides the exact two WN2 IDs, preserving ledger
  records; discovery and request-identity tests cover the distinction.
- Resource limits: existing single-array receive/worker bounds retained;
  run discovery is four metadata probes, 15 seconds, 64 KiB, 16 cached roots,
  five-minute root TTL. Existing bounded service caches and two-request frontend
  queue remain in use. No billing project or raw ensemble path is introduced.

## Verification

Commands run from the weather-map experiment unless specified otherwise.

- `uv run --project api pytest -o addopts='' -q api/tests/test_weathernext_surface.py api/tests/test_weathernext_local_delivery.py api/tests/test_weathernext_delivery.py api/tests/test_weathernext_shared_delivery.py api/tests/test_weathernext_local_shared.py`: 189 passed.
- `uv run --project api pytest -o addopts='' -q registry/tests`: 237 passed.
- `uv run --project api pytest -o addopts='' -q api/tests/test_weathernext_native.py api/tests/test_weathernext_gcs.py api/tests/test_weathernext_gcs_bridge.py api/tests/test_weathernext_query.py api/tests/test_point_directional.py`: 135 passed, 2 Linux-only tests skipped on macOS.
- `npm --prefix web test`: 629 passed. After concise WN3 labels and percentage rounding, affected PointDataPanel/discovery/pointRequests suite: 30 passed.
- `npm --prefix web run build`: passed, existing large-bundle warning.
- Source OpenAPI/fixture generation check, generated TypeScript check, and field catalogue generation: passed.
- `npx --yes @fission-ai/openspec validate weathernext3-surface-point --strict`: passed.
- Root `uv run --project tools/specs python tools/specs/specctl.py validate`: 0 errors, 0 warnings.

The exact mounted source ran in the prepared `astraeus-point-merge-check` Linux
image (manifest `sha256:a8f0787cc15fb21d21695f47e17aaf2e64ab2f46c172ba13e681899716034e38`):

```sh
docker run --rm --network none --memory 3g -v "$PWD:/work:ro" -w /work \
  -e PYTHONPATH=/work/api:/work -e OPENBLAS_NUM_THREADS=1 \
  --entrypoint /app/api/.venv/bin/python astraeus-point-merge-check \
  -m pytest -o addopts='' -q -p no:cacheprovider \
  api/tests/test_weathernext_gcs_bridge.py api/tests/test_weathernext_native.py \
  api/tests/test_weathernext_surface.py
```

176 passed before the final additional HTTP refusal test; this exercised the
actual default bounded worker with zero provider network. Later changes were
frontend labels, metadata copy and a configuration-status declaration.

## Actual provider versus browser evidence

Two separately bounded authenticated API requests against mounted current code
on temporary localhost:8323 returned actual native data: a future total-cloud
mean (19.6 seconds) and a historical experimental hourly precipitation p90
(16.8 seconds). Successful root discovery selected September 8 12Z and August 1
00Z respectively, with returned native valid times September 9 00Z and August 1
06Z. These are two live samples, not a claim of live validation of every field.
The earlier all-field acquisition evidence remains in the original experiment.

Private raw receipts, forecast values, screenshots and logs remain outside Git
at `/private/tmp/astraeus-wn3-surface-proof/`. Browser verification replays those
responses against current catalogue declarations on temporary localhost:5323,
blocks provider weather endpoints, and asserts selected field queries, 252
historical/forecast capability paths, hidden WN2 entries, percentage and
historical percentile rendering, and provenance. Real Chrome 100/200 percent
zoom is used; four captures and `browser/result.json` record the result.
`node web/scripts/prove-weathernext-surface.mjs` reproduces this private replay.

## Limits and rollback

Only the published statistics surface is connected. Raw members, pressure
levels, scheduled ingestion, full-map rasters, public redistribution and
primary-source admission remain excluded. Missing/oversized arrays fail closed.
The current archive namespace is 2026; 2024/2025 backfill is not fabricated.
The legacy historical reader still uses its conservative 48-hour valid-time
gate; the separately authorized internal local path covers recent past/future.
Disabling `WEATHER_WEATHERNEXT_AUTO_RUNS` restores pinned-run behavior. Reverting
this change and rebuilding restores temperature-only WN3 and WN2 discovery.
No stored weather records or database schema are changed.

## Running local application verification

Rebuilt and recreated only the local web/API services, then refreshed their
private runtime token through the existing script. The independent map-first
API also advertised `api` on the shared Docker network, causing the web proxy
to alternate between old and new catalogues. Compose now targets its own
project-qualified API container name, using documented `COMPOSE_PROJECT_NAME`
interpolation. Other running experiments were left intact.

After the correction, four consecutive requests through localhost:5173 returned
all 252 WeatherNext 3 paths, and a real cloud-mean request through that same web
proxy returned native evidence in 17.1 seconds. The final browser replay was
also rerun against localhost:5173, with provider weather requests intercepted.
The production app remains on web5173/API8000. Temporary proof API8323 and
Vite5323 are stopped after verification; their private receipts remain outside Git.

Compose config validation and the final spec validator passed. The proxy fix
is covered by the repeated actual runtime catalogue check with both API
containers present; no duplicate container or provider integration was added.
