# Reuse-first source workflow

This is a non-normative working index. It points to maintained code and checks;
the source registry and accepted OpenSpec contracts remain authoritative.

## Start every source slice with the existing seam

1. Read `AGENTS.md`, the relevant issue and its comments, then the source row
   in `experiments/st-johns-weather-map/registry/source_data.py`.
2. Search current main before creating a client, parser or cache. From the repo
   root:

   ```sh
   git fetch origin main
   git ls-tree -r --name-only origin/main -- experiments/st-johns-weather-map/api/weather_api | grep -E 'query|source-name'
   git grep -n -E 'source-id|product-name' origin/main -- experiments/st-johns-weather-map
   gh issue list --state open --search 'source-name in:title' --limit 20
   gh pr list --state all --search 'source-name in:title' --limit 20
   ```

3. Reuse the narrowest existing source seam. Read its fixed-fixture tests before
   choosing a request, decoder, cache, receipt or public model shape. If the
   accepted source identity, time rule, unit, quality meaning or failure state
   is absent or conflicts, record the decision needed on the issue and stop
   before implementing it.
4. Write the claimed source, canonical endpoint, accepted contracts, owned
   files and reusable seam in the issue before code. Update that record when
   the actual request, test command, receipt location or browser runtime
   changes.

A hostname is not source identity. A response that can contain a partner or
third-party station needs a source-identity guard before its values are served.

## Existing seams

| Need | Reuse first | Notes |
| --- | --- | --- |
| ECCC GeoMet WMS/point semantics | `ingest/adapters/eccc_geomet.py` (`GeoMetClient`) | It owns WMS URL construction, capabilities, axis-order and service-exception handling. |
| ECCC Datamart selected native data | `ingest/adapters/eccc_datamart.py`, `api/weather_api/gdps_query.py` | Reuse run/lead identity and bounded native decoding. |
| AWC METAR and TAF | `api/weather_api/metar_query.py`, `api/weather_api/taf_query.py`, `ingest/adapters/awc.py` | Preserve report identity, valid time and existing parser semantics. |
| SWPC Kp, magnetometer and plasma | `api/weather_api/swpc_kp_query.py`, `api/weather_api/swpc_rtsw_query.py`, `api/weather_api/swpc_rtsw_worker.py`, `api/weather_api/swpc_plasma_query.py`, `api/weather_api/swpc_plasma_worker.py` | These model mutable-feed time selection and typed receipts. |
| AQHI station observations | `api/weather_api/aqhi_query.py`, `api/weather_api/aqhi_query_worker.py` | Reuse station identity, distance and native-observation handling only where its accepted rule fits. |
| GFS-Wave or OVATION | `api/weather_api/openmeteo_gfs_wave_query.py`, `api/weather_api/ovation_query.py`, `api/weather_api/ovation_query_worker.py` | Keep their declared evidence class and producer/run semantics. |
| Bounded decode | `ingest/isolation.py` (`run_bounded_process`, `ProcessAllocationLimits`) | Decode untrusted provider bodies in the bounded child process. |
| Fixed HTTP and API routes | `httpx.MockTransport`, FastAPI `TestClient`, and the closest `api/tests/test_<source>_query.py` | Reuse these deterministic test seams before creating a launcher or test-only client. |
| Transport and receive budget | `ingest/http.py` (`PoliteClient`), `ingest/resources.py` (`acquisition_budget`) | Source adapters share pacing/retries and byte caps. Demand readers need final-byte receipts and redirect policy; inspect an existing demand service before sharing transport behavior. |
| Public receipt/cache models | `api/weather_api/models.py` and the closest demand query test | Keep request identity, safe headers, final-byte time, byte count, digest, expiry and typed expired metadata bounded. |

The current demand readers intentionally contain source-local cache and receipt
logic. Do not replace one with `PoliteClient` without preserving the demand
contract's no-redirect, final-byte and public-receipt behavior. A shared
bounded demand transport helper is a future refactor only after a contract and
migration plan exist.

## Tight vertical-slice loop

Run commands from the stated directory and record the exact target test, not a
full suite by habit.

```sh
# repository root: specification and PR-traceability gate
uv run --project tools/specs python tools/specs/specctl.py validate

# experiment root: focused source/API tests
cd experiments/st-johns-weather-map
uv run --project api pytest -q api/tests/test_<source>_query.py

# client changes only
cd web
npm test -- src/api.test.ts src/App.test.tsx
npm run build
```

Use `httpx.MockTransport` for a fixed body, FastAPI `TestClient` for the public
route, and an injected clock for cache hit, coalescing, expiry, replacement
failure, advancing final-byte freshness and individual-null tests. A source query answers only the
accepted native time/selection rule. Expired values are withheld; bounded
identity/expiry metadata may remain when its contract allows it.

For a default bounded child, prove the real process seam in Linux with the
source's focused test and a fixed `httpx.MockTransport` body. First prepare an
exact-head test image or mounted environment with the locked dependencies while
network is available. Then run the proof with network disabled:

```sh
cd experiments/st-johns-weather-map
# Use the exact prepared image and test name recorded by the source slice.
docker run --rm --network none --memory <source-limit> \
  -v "$PWD:/work:ro" -w /work <exact-head-prepared-image> \
  pytest -q api/tests/test_<source>_query.py::<default-child-test>
```

A clean `uv` image with an empty environment cannot install dependencies under
`--network none`; the preparation is separate from the proof. The proof
records the image digest, fixture request count and zero provider requests. A
new low-limit worker should use exactly one `{output}` placeholder and prefer
an absolute leaf script: AQHI needed that to avoid importing the full API under
its memory limit. Existing workers may use a module launcher only when their
actual Linux child test proves it stays within its declared limit. macOS may
reject locked `RLIMIT_AS`, so Linux is the proof environment. The test proves a
fixed fixture with no provider network; it does not make a temporary launcher,
receipt or captured body a permanent tool or Git artifact.

For the one browser proof, the runtime owner launches an exact-head fixed-live
harness with provider transport blocked. Confirm which endpoint supplies each
card: `/point` often supplies the selected `valid_time`, while a source-specific
endpoint such as `/space-weather` may provide the card data. The browser waits
for `DOMContentLoaded`, then locates the specific rendered card rather than
waiting for network idle. Read the displayed value, source, native time, quality
and receipt disclosure. Record ports, head and whether any provider request
occurred in the issue or handoff. The Linux proof establishes the production
worker/cache seam; the browser proof establishes client rendering against its
fixed-live API. Other agents inspect only after the runtime owner hands it off.

## PR and handoff

Use the repository template. The governance parser requires all of these as
literal lines in the body:

```text
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004
Verification: exact command — result
```

Every referenced ID also needs a clickable link. Use a conventional lowercase
title such as `feat(source): add exact source query`; `docs(scope): ...` is the
same rule. Create PR bodies in a file and pass `--body-file` to `gh`.

Before merge, bind review, evidence and checks to the exact head. After a
squash merge, compare the reviewed head tree with `origin/main`, record the
merge SHA and remaining issue decision, then remove only the owned temporary
runtime and worktree. Add a short current note to `docs/handoffs/handoff.md`
when a completed slice leaves reusable workflow knowledge; keep historical
entries as history rather than copying them into this index.
