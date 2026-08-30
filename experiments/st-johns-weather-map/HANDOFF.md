# Claude handoff: St. John's weather evidence map

## Mission

Continue the isolated experiment in this directory until it satisfies the prior St. John’s 24-hour meteorological evidence-map plan. Keep all work under `experiments/st-johns-weather-map/`. Do not modify V1 contracts, production specs, `.repowise/`, or invent a celestial module ID.

Classification: **Experiment, Spec-Impact: none**. Keep `operational: false` on every response. Do not mark a source active or verified without fixture, live-smoke, artifact, and API-readback evidence.

The original plan is the source of intent: evidence from `now - 3h` through `now + 24h`, source-specific layers, field-wise consensus only where comparable evidence exists, explicit HRDPS then RDPS fallback, full provenance, and visible unknown/unavailable states.

## Current truth

This is a foundation and partial live-adapter spike, not a completed POC.

- Registry: 59 sources; 46 `implementing`, 7 `credential_required`, 3 `licence_review`, 2 `unavailable`, 1 `retired`, 0 `active`.
- Registered adapters: `awc-metar-speci`, `awc-taf`, `dwd-icon-global`, `eccc-gdps`, `eccc-hrdps`, `eccc-rdps`, `eccc-swob`, `ecmwf-ifs`, `noaa-gfs`.
- Published artifacts observed: TAF, SWOB, and IFS. IFS is not trustworthy: logs show skipped fields/leads while it was marked complete and QC-passed.
- Compose forces the API into fixture mode. `/ready` can report ready while `live_store=false`.
- Live failures observed: METAR imports an API-only package absent from the worker image; ECCC model roots return 404; DWD cannot handle the native grid; GFS exceeds its range ceiling; ECMWF has missing indexes/fields.
- Worker health can go unhealthy during long serial cycles because heartbeat updates only between cycles.
- `make test` has passed 135 API, 7 web, and 6 registry tests, but these are mainly mocked/fixture tests. Zarr tests emit duplicate-entry warnings. There is no real Compose/live-smoke/browser E2E gate.

Treat older README and handoff claims as stale. Re-check endpoints and current code before relying on old notes.

## Release blockers

1. **Truth boundary:** the browser ignores API `data_mode` and treats every HTTP 200 as live. The API can fall through from live errors to synthetic fixture values. Fixtures are allowed only under an explicit fixture mode and must be visibly watermarked.
2. **No invented evidence:** remove procedural map weather, fabricated forecast stories, fake marine defaults, and synthetic product selection. Missing data must be null/unknown/unavailable with provenance.
3. **Fail-closed ingestion:** adapters need measurable manifests for required variables, valid times, spatial coverage, units, CRS, and QC. Partial fields, leads, decode errors, suspect QC, or incomplete coverage must prevent publication.
4. **Consensus correctness:** consensus must be keyed by field, time, level, and quantity. It requires real ECCC regional evidence, one independent deterministic centre, and one applicable ensemble family. Freshness and QC come from provenance; ensembles remain distributions.
5. **Storage integrity:** publish complete runs atomically; enforce parent-run QC/completeness in SQL; protect immutable metadata; verify object size/SHA on read; account for orphaned objects.
6. **Canonical source truth:** derive API catalog, status, refresh validation, product controls, and scheduler eligibility from `registry/source_data.py`, not the six-record fixture catalog.
7. **Operational honesty:** live readiness must require the live store and current evidence boundary. Worker health must detect stalled ingestion. Bind host ports to localhost and use least-privilege MinIO credentials.

## Execution order

Use GPT-5.6 Terra low agents with disjoint ownership. The root agent orchestrates, integrates interfaces, runs gates, and does not make speculative provider or science decisions.

### Gate 0: baseline and ledger

- Read `docs/specv1/README.md`, `docs/specv1/GOVERNANCE.md`, and this file.
- Run `make test`, `docker compose config`, registry audit, and `specctl validate`.
- Build a ledger mapping all 59 registry records to adapter, artifact type, fields, UI consumer, smoke command, and status.
- Do not change registry status merely because an adapter exists.

### Gate 1: API and UI truth boundary

API owner: `api/weather_api/{app.py,models.py,store.py}` plus registry-to-API conversion and API tests. UI owner: `web/src/{api.ts,App.tsx,MapPanel.tsx,fixtures.ts}` plus web tests. Do not edit these areas concurrently.

- Make fixture/live/unavailable mode explicit end to end. A malformed or missing mode fails closed.
- In live mode, never return fixture values after store errors or empty artifacts.
- Make catalog, status, refresh, timeline, layers, point, and profile use canonical registry and stored artifacts.
- Reject non-schedulable refresh IDs and make zero-matched/cancelled jobs fail truthfully.
- Remove synthetic story, marine defaults, procedural weather rasters, and static model claims. Render only response-backed fields; retain a clearly labelled development fixture mode.
- Keep cross-section unavailable until normalized spatial arrays and a sampling contract exist.

Acceptance: fixture responses show a watermark; live responses show only stored values; live outage returns unknown/unavailable; catalog IDs match the registry; product selection cannot claim a different source.

### Gate 2: ingestion and storage integrity

Owner: `ingest/`, worker runtime, SQL, Compose credentials/bindings, and adapter tests. Do not edit API/UI files concurrently.

- Create a worker-importable shared meteorology module so METAR does not import an API-only package.
- Add per-adapter manifests and derive `complete`/`qc_passed` from a shared validator, never literals.
- Fix ECCC discovery, bounded GFS ranges, ICON grid handling, and ECMWF field/lead assembly; unresolved endpoints stay non-active.
- Make Zarr warning-free and round-trip validated. Add Parquet for observations, GeoJSON for alerts, and COG only for validated map rasters.
- Publish all artifacts for a run in one transaction after parent-run validation. Add immutable revision guards and readback digest/size checks.
- Add least-privilege MinIO credentials, localhost bindings, API read credentials, and truthful worker/job liveness.

Acceptance: partial or failed-QC runs cannot publish; interrupted staging preserves the prior pointer; object bytes/SHA match metadata; live readiness fails when storage is unavailable.

### Gate 3: live source spine

Implement and smoke in this order, activating each registry record only after fixture test, live smoke, artifact validation, API readback, and provenance checks pass:

1. AWC CYYT METAR/SPECI and TAF.
2. ECCC SWOB and HRDPS.
3. NOAA GFS and ECMWF IFS.
4. RDPS, GDPS, REPS, GEPS, GEFS, ENS, and ICON as endpoint/grid validation permits.

For every source, prove discovery, bounded download, exact fields/units/levels/CRS, QC and licence metadata, atomic publication, and API point/profile/timeline readback. If endpoint, licence, cadence, or field meaning is unresolved, retain a documented non-active status.

### Gate 4: consensus and vertical capabilities

- Replace scalar temperature consensus with field/time/level consensus on an approximately 10 km grid.
- Report centre range, ensemble quantiles, threshold fractions, disagreement class, and contributors.
- Keep source layers and observations separate. Do not bias-correct or weight models without owner-approved experimental rules.
- Add pressure profiles, MetPy-backed Skew-T, and drawn cross-sections only after numeric arrays and sampling semantics are real.

### Gate 5: remaining evidence families

Implement and smoke in cohorts: ECCC radar/lightning/CAP/analyses/nowcasting; GOES cloud/moisture/fog; AQHI/RAQDPS/RDAQA/CAMS/aerosols; SmartAtlantic and official marine observations; CIOPS, waves, surge, IWLS, hydrology, and NL 511 transport.

Credential-gated work stops when the adapter is ready for its live test. Ask only for that provider’s official key using the required secrets workflow. Never put credentials in fixtures, logs, commits, or browser bundles.

### Gate 6: UI, verification, and documentation

- Wire simple/expert controls to canonical catalog/layer/timeline capabilities.
- Add textual map alternatives, keyboard/focus/reduced-motion behavior, and accessible errors/statuses.
- Code-split MapLibre/deck.gl and remove procedural canvas generation from production paths. Record and enforce a bundle budget.
- Rewrite README and this handoff only after behavior and smoke evidence are current.

## Required verification

Every adapter needs mocked fixture tests plus an opt-in live smoke test. Add failure cases for missing fields, stale data, partial runs, throttling, schema drift, bad units, invalid CRS, and unavailable endpoints.

Required science/data tests include RH liquid/ice behavior, dew-point/specific-humidity separation, wind-vector interpolation, precipitation intervals, fog unknown-state handling, radar no-echo semantics, ensemble-family independence, AQHI/PM/AOD/extinction separation, tide/surge/water-level separation, and numeric probe versus normalized-array parity.

Required integration tests include disposable Postgres/MinIO publication, parent-run gating, immutable revisions, digest verification, restart recovery, quota enforcement, worker job outcomes, API readback, and browser tests against the real MapPanel/API.

Run before handoff:

```sh
cd experiments/st-johns-weather-map
make test
docker compose config --quiet
uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate
docker compose up --build --wait
docker compose ps
curl -fsS http://localhost:8000/api/experiments/weather/v0/ready
curl -fsS 'http://localhost:8000/api/experiments/weather/v0/point?latitude=47.5615&longitude=-52.7126'
curl -fsS http://localhost:8000/api/experiments/weather/v0/timeline
curl -fsS http://localhost:8001/healthz
```

Completion requires at least one active source in every applicable category: deterministic forecast, ensemble, independent centre, surface observation, aviation, satellite, radar, lightning, local buoy, humidity profile, air quality, marine, tide/water level, hazard, and transport. Every remaining candidate needs an honest non-active status and reason.

## Coordination and authority

- Agents edit only assigned paths and report exact files, tests, and uncertainty.
- Never edit `registry/source_data.py`, API models/store, `science.py`, Compose, or docs concurrently with another agent.
- Run an adversarial read-only review after each gate.
- Never mark a source active from mocked tests alone.
- Stage only explicit experiment paths. Do not add `.repowise/` or unrelated files.
- Use conventional commits with `Spec-Impact: none` and exact `Verification` commands if commits are requested. Do not push unless explicitly requested.
- Stop for owner approval on bias correction, consensus weights, new scientific interpretations, unresolved licence/cadence/endpoint facts, credentials, or any V1 promotion.

## First Claude task

Start with Gate 1. Run the baseline first, inspect the current files, then assign Terra-low agents for API truth, ingestion/storage integrity, and UI truth. Have an adversarial reviewer inspect the combined diff before Gate 2. Report blockers instead of manufacturing values or changing registry status.

