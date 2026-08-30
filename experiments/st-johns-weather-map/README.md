# St. John's weather evidence map experiment

This directory is an isolated, fixture-first proof of concept for a 24-hour
meteorological evidence workbench over the Avalon Peninsula and upstream
Atlantic. It is experimental, makes no operational or safety claim, and does
not alter Astraeus V1 production behavior or contracts.

## Run locally

Requirements: Docker with Compose, `uv`, Node.js 22, and Python 3.13. The
selected container images publish both `linux/amd64` and `linux/arm64`
manifests.

```sh
cd experiments/st-johns-weather-map
cp .env.example .env                 # optional local port/value overrides
make config
make up
```

Open the web app at <http://localhost:5173>. The fixture API is at
<http://localhost:8000/api/experiments/weather/v0/health>, TiTiler is at
<http://localhost:8001/healthz>, and the MinIO console is at
<http://localhost:9001>. Values in `.env.example` are local-only service
credentials, not weather-provider credentials. `.env` is ignored.

Stop without deleting data:

```sh
make down
```

To intentionally reset all experiment data, review the target from this
directory and run `docker compose down --volumes`. This deletes both named
volumes and reruns the database bootstrap on the next start.

## Verify

```sh
make test
```

Individual commands are `make test-api`, `make test-web`,
`make test-registry`, `make spec-validate`, and `docker compose config`. The
registry target creates an ephemeral `uv` environment from its pinned
requirements; it does not modify the system Python installation.
Container health can be inspected with `docker compose ps`; logs are available
through `make logs`.

## Architecture

Compose runs exactly six services on one private bridge network:

- `web`: React/Vite and MapLibre/deck.gl UI, with `/api` proxied to `api`.
- `api`: FastAPI under `/api/experiments/weather/v0`.
- `worker`: the single ingestion-process seam and MinIO quota initializer.
- `postgres`: PostgreSQL 17/PostGIS 3.5 metadata, jobs, geometry, and revisions.
- `minio`: immutable source/normalized artifact storage.
- `titiler`: COG raster delivery backed by the internal MinIO endpoint.

PostgreSQL and MinIO use named volumes. All services have health checks, and
dependencies wait for health rather than merely container startup. There is no
Redis or distributed task system. See [infra/STORAGE.md](infra/STORAGE.md) for
the enforced 25 GiB artifact quota and atomic publication boundary.

## Current truth and limitations

**Updated 2026-08-30.** The paragraph that stood here said everything was a
deterministic fixture and the worker was idle. That has not been true for some
time, and leaving it would have understated what the stack does.

The deployment runs in **live** mode. The worker schedules and runs adapters, and
artifacts are published atomically: METAR/SPECI, radar, lightning, AQHI, CAP
alerts, SWOB and TAF have all completed live retrievals. `/layers` serves 15
layers and 308 frames, 216 of them forecast frames.

Fixtures still exist, but only behind an explicit escape hatch:
`WEATHER_DATA_MODE=fixture` for the API and
`import.meta.env.DEV && VITE_WEATHER_FIXTURES === 'true'` for the web client.
When engaged they watermark the screen and stamp every field.

Two honest limits remain. **Forecast imagery is live-proxied** from ECCC GeoMet
at request time, carrying full provenance but bypassing the ingest/QC/atomic
publication spine, so it is display evidence rather than audited evidence and is
labelled `evidence_basis: "live_proxy"`. And **TiTiler still has no COG**, since
no adapter publishes one.

The source registry is a catalogue and implementation-state audit, not proof
that remote endpoints are currently healthy. No live or credential-gated
adapter is started, no provider key is requested, and no credential is exposed
to the browser. The SQL schema is ready for persistent jobs and revision
pointers, but the fixture API deliberately continues to use its in-memory
store.

## Specification classification

**Experiment. Spec-Impact: none.** Everything is contained under
`experiments/st-johns-weather-map/`; it does not enter a production path,
claim conformance, modify accepted requirements, or create a V1 module ID.
Only the specification owner can authorize promotion out of this experiment.
