Owned: `api/pyproject.toml` (skyfield dependency), `api/weather_api/ephemeris.py`
(new), `api/weather_api/astronomy.py` (new), `api/weather_api/app.py`
(`/astronomy` route only), `api/weather_api/models.py` (astronomy response
models only), `api/scripts/fetch_ephemeris.py` (new), `compose.yaml` (api
volume + env only), `.gitignore` (`data/ephemeris/`), `registry/source_data.py`
(`nasa-jpl-de442` entry only), `registry/catalogue_coverage.json` (one mapping), `api/tests/test_astronomy.py` (new),
`web/src/api.ts`, `web/src/types.ts`, `web/src/App.tsx`, `web/src/styles.css`,
`web/src/fixtures.ts`, `web/src/api.test.ts`, `web/src/App.test.tsx`.
Not touched: worker image/service, `ingest/` adapters, `/point`,
`api/weather_api/store.py`, `docs/specv1`.

## 1. Kernel plumbing (WP-A1)

- [x] 1.1 skyfield pinned in `api/pyproject.toml`; `ephemeris.py` recovered
      with `WEATHER_EPHEMERIS_PATH` override; `scripts/fetch_ephemeris.py`
      recovered; compose mounts `./data/ephemeris` read-only into api only;
      `.gitignore` covers the kernel dir.
      Verify: `cd api && uv sync && uv run python scripts/fetch_ephemeris.py --check`
- [x] 1.2 Registry entry `nasa-jpl-de442` with unparseable cadence and
      "not applicable" freshness; never scheduled by the worker.
      Verify: `make test-registry` and `cd api && uv run pytest tests/test_astronomy.py -q -k registry`

## 2. Computation and endpoint (WP-A2, WP-A3)

- [x] 2.1 `astronomy.py`: twilight bands, moon rise/set/phase/illumination,
      galactic-centre altitude and geometric core window; pure functions of
      (latitude, longitude, window).
- [x] 2.2 `GET /astronomy`: bands + moon + core window + one provenance
      block; 422 outside window or core bounds; missing/mismatched kernel ->
      unavailable with reason; `operational: false`.
      Verify: `cd api && uv run pytest tests/test_astronomy.py` (includes a
      known-answer check pinned against USNO for a fixed instant,
      checksum-mismatch and missing-kernel scenarios)

## 3. Web (WP-A5)

- [x] 3.1 Darkness and moon bands beside the timeline coverage rows with
      text alternatives; "Tonight" metric cards incl. the geometry-only core
      caption; unavailable astronomy renders as unavailable, never as an
      empty band.
      Verify: `cd web && npm test -- --run && npm run build`

## 4. Verification (WP-A6)

- [x] 4.1 Live smoke: HEAD the NAIF kernel URL, assert reachable and
      Content-Length equals the pinned byte size.
      Verify: `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q -k ephemeris`
- [ ] 4.2 `make test` fully green; `openspec validate
      night-sky-darkness-ephemeris --strict` and `openspec validate --all`;
      Docker: `/astronomy` answers with bands and provenance when the kernel
      is mounted, and unavailable-with-reason when it is not.
