# Dedicated WeatherNext workspace evidence

Classification: experiment. The September 9 user-supplied implementation plan
explicitly authorizes the workspace and experimental contract amendment. No V1
production behavior or normative status is changed.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
References: [authority](../../specv1/GOVERNANCE.md#gov-spec-001--specifications-are-authoritative),
[traceability](../../specv1/GOVERNANCE.md#gov-spec-004--behavior-changes-are-spec-traceable),
[verification](../../specv1/GOVERNANCE.md#gov-spec-006--verification-is-part-of-the-requirement).

## Delivered behavior

WeatherNext is a navigable and dockable view, sharing location, range and the
bottom timeline. It preserves section/product/threshold choices across view
changes. Metadata from the pinned run contributes native timeline markers.
Clouds has four charts; the other five sections expose the plan's explicit
quantities and product choices. Charts separate amount, percentile bands and
approximate probability; missing statistics are named. Keyboard time buttons
and the shared timeline inspect retained results without new science requests.

The API serves one quantity at one native time per bounded page, using the existing batch
reader, native sampling, two-acquisition bound and comparison executor. Initial
requests coalesce through the existing comparison machinery. Retained pages
share the existing 8 MiB response budget. Failed later pages preserve completed
pages. The September 9 live-loading correction gives workspace summaries and
selection metadata a fixed one-hour retention deadline. Other consumers keep
their 60-second default. Every quantity retains its own acquisition receipt. There is no automatic refresh or
silent run stitching. Long ranges remain visible even where no run covers them.

Threshold estimates read retained summaries only. They use strict neighboring
quantiles, skip ties, retain open tails and withhold non-monotonic/unusable sets.
The estimate's selection id, quantity/unit, sample timestamp and run identify
its source summary and shared acquisition receipt. No raw members, fitted
probability distributions, combined events or requester billing are introduced.

The four native cloud means use the existing grid route and rendering, with
field-specific identity in both caches and native provenance validation.

## Design and browser proof

[Desktop mockup](desktop.svg) and [narrow mockup](narrow.svg) were created before
implementation. All mockup and browser data is synthetic, not a forecast.

The maintained replay script is
`experiments/st-johns-weather-map/web/scripts/prove-weathernext-workspace.mjs`.
It runs the actual App and WeatherNext view through Vite at port 5391, intercepts
all API routes and blocks external origins. Provider requests: **zero**.
The mock WeatherNext API uses the same quantity/time page ordering as the backend;
backend tests independently verify six fields per page and fixed expiry.

[Browser receipt](browser/result.json) records:

- Four aligned charts, a single shared timeline, keyboard inspection and cursor movement.
- Mean/threshold/detail interactions without new WeatherNext acquisition calls.
- Cached section reuse; precipitation with repeated zeros; pending and expired pages.
- Light/dark/night themes, 1440- and 390-pixel layouts, and actual Chrome 200% zoom.

Screenshots include [desktop](browser/light-1440.png),
[narrow](browser/dark-390.png), [200% zoom](browser/zoom-200.png),
[upper tail](browser/cloud-1.png), [broad uncertainty](browser/cloud-2.png),
[missing percentile](browser/cloud-3.png), [precipitation ties](browser/precipitation-ties.png),
[pending pages](browser/pending.png) and [expired evidence](browser/expired.png).
Visual inspection confirmed readable charts and controls at desktop/narrow/zoom.

## Verification

Commands run from the repository root unless noted:

```sh
uv run --project experiments/st-johns-weather-map/api pytest -ra -q \
  experiments/st-johns-weather-map/api/tests/test_weathernext_workspace.py \
  experiments/st-johns-weather-map/api/tests/test_source_grid.py \
  experiments/st-johns-weather-map/api/tests/test_weathernext_native.py \
  experiments/st-johns-weather-map/api/tests/test_weathernext_surface.py \
  experiments/st-johns-weather-map/api/tests/test_weathernext_shared_delivery.py
```

Passed. The two platform-specific native-worker tests skip on macOS and pass
in the network-disabled Linux proof below. After the final changes, the affected
workspace and grid tests were rerun locally and in Linux.

```sh
npm --prefix experiments/st-johns-weather-map/web test -- \
  src/workbench/WeatherNext.test.tsx src/workbench/DesktopApp.test.tsx \
  src/workbench/sourceGrid.test.ts src/workbench/sourceTimes.test.ts \
  src/workbench/pointRequests.test.ts src/workbench/WorkbenchShell.test.tsx \
  src/workbench/focusUrl.test.ts
npm --prefix experiments/st-johns-weather-map/web run build
uv run --project experiments/st-johns-weather-map/api python \
  experiments/st-johns-weather-map/scripts/generate_source_contract.py --check
npm --prefix experiments/st-johns-weather-map/web run check:source-types
uv run --project tools/specs python tools/specs/specctl.py validate
```

Passed; the final affected WeatherNext/grid client tests were rerun after adding
field-identity validation. Build retains the existing large-bundle warning.
`specctl`: zero errors, zero warnings.

From `experiments/st-johns-weather-map`:
`openspec validate weathernext3-surface-point --strict` passed.

Linux proof uses the existing prepared Python 3.13 proof image and mounts this
workspace read-only, so imports and the default worker use the changed source:

```sh
docker run --rm --network none --memory 2g \
  -v /Users/tusharsariya/Projects/Astraeus/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work astraeus-cloud-proof:20260908 \
  pytest -p no:cacheprovider -ra -q \
  api/tests/test_source_grid.py api/tests/test_weathernext_workspace.py
```

Image: `sha256:b757d6a49ff20646c78cd123585d58733507f46ce9e6975c424101bfe545f0bd`.
All 43 tests passed, including both default bounded worker proofs. No provider
network is available in this container. The original image dependencies were
reused; no new environment or dependency claim is made.

## Handoff

No live-provider smoke test or deployment was performed. Real availability still
depends on the existing opted-in runtime, credentials and published roots. The
short source TTL can cause early pages of a slow, long selection to expire while
later pages load; those values are visibly withheld, without extending freshness.
Browser and fixture tests prove behavior, not current provider availability.
Rollback is removal of the isolated workspace routes/view and the four-mean grid
amendment. Existing Map/Series URLs and saved point selections remain compatible.

Verification: focused API/client tests, network-disabled Linux native-worker proof,
browser replay, build, generated-contract checks, strict OpenSpec, specctl and
git diff --check passed. The proof runtime is stopped after verification.

## Follow-up: owner-requested 1 GiB download ceiling

The owner subsequently requested increasing WeatherNext downloads to 1 GB. The
experimental amendment implements **1 GiB (1,073,741,824 bytes) per acquisition**
across delivery, accounted transport, bridge, Linux worker and receipt validation.
This supersedes the original aggregate-byte restriction above. Standalone bridge
calls still default to 16 MiB. Individual compressed chunks remain capped at
64 MiB, decoded chunks at 128 MiB, with existing deadlines, memory, concurrency
and evidence-expiry limits unchanged.

The fixed 30-operation ceiling also prevented complete 24-statistic cloud reads.
Point batches now receive a field-count-based allowance capped at the existing
native maximum of 270. Grid/inventory budgets remain 30/10. The bridge accepts
up to 36 fields to cover the workspace's six native wind quantities.

Verification: 78 tests passed in the same network-disabled Linux image using
`api/tests/test_weathernext_gcs_bridge.py`, `test_weathernext_delivery.py`,
`test_weathernext_local_delivery.py` and `test_source_grid.py`. The real bounded
worker completed all 24 synthetic cloud statistics with a configured 1 GiB cap.
A separate accounting test crosses the former aggregate ceiling using a seeded
counter, refuses totals above 1 GiB and refuses an oversized individual object
before transport. It does not download or allocate 1 GiB of fixture data.
Generated-contract checks, strict OpenSpec, specctl and diff whitespace checks
passed. The local API was rebuilt with the new policy; runtime credentials were
refreshed after recreation. No claim is made that a full live batch fits within
the unchanged deadlines or that the 60-second freshness issue is resolved.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

## Live-loading correction

The first 1 GiB deployment still failed: the workspace abandoned each 24-field
page at 45 seconds, before its 90-second native child could finish. A direct
six-field Total-cloud acquisition succeeded in 33.5 seconds. The correction
uses six-field pages, loads consecutive times for each quantity, waits up to
95 seconds for page acquisition, and merges quantities by time without replacing
previous results. A fixed one-hour selection/receipt deadline prevents earlier
points expiring during the progressive load. No byte, object, decoder, process
concurrency, billing or native worker time limit was increased in this fix.

Verification after correction: 61 API tests passed in the network-disabled Linux
proof image with current source mounted read-only; five frontend tests passed;
TypeScript/Vite build passed (existing bundle-size warning). Generated contracts,
strict experimental validation and specctl passed. The maintained browser proof
was updated to quantity/time pages and passed all themes, narrow, actual 200%
zoom, keyboard, cached section reuse, no display-triggered science calls, ties,
pending and expiry checks. Live API evidence is recorded separately from these
synthetic checks.

Live API verification after rebuilding API/web and refreshing the authorized
runtime token: all eight pages (four cloud quantities × two adjacent native
hours) returned all 48 values. Pages took 32.8–41.8 seconds, and the first page
remained available after the final page completed. Retained threshold requests
returned 90–100% approximate chance above 80% total cloud at both times.
[Live API receipt](live-api-result.json) retains values, run and per-quantity
provenance. First acquisition remains bandwidth-heavy because native compressed
spatial chunks must still be read; this fix does not claim server-side subsetting
or a cross-selection raw-chunk cache.

[Live-data browser replay](browser/live-api-replay.png) uses the eight actual API
responses, with other times explicitly marked not loaded. Browser assertions
confirm four connected median paths, both percentile bands on all four charts,
eight probability intervals, and no page requests from mean/threshold/cursor
interactions. Its [receipt](browser/live-api-replay.json) distinguishes this replay
from the real provider/API acquisition above and the synthetic visual suite.
