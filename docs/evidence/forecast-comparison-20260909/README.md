# Multiple-model forecast comparison, September 9

Classification: experiment. The September 9 owner request authorizes implementing
the supplied Series plan and amending the experimental contracts first. This
work changes no production/operational status. Pre-existing map and WeatherNext
working-tree changes were preserved; this evidence describes the comparison slice.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

Owning contracts:
- [Comparison decision and limits](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-api-contract/specs/desktop-evidence-api/comparison.md)
- [Desktop API](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-api-contract/specs/desktop-evidence-api/spec.md)
- [Desktop Series UX](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/specs/desktop-evidence-workbench/spec.md)
- [WeatherNext batching](../../../experiments/st-johns-weather-map/openspec/changes/weathernext3-surface-point/specs/source-delivery/spec.md)

## Result and reuse

`POST /point/comparison` is a typed additive interface; `/point/series` and its
clients remain intact. Comparison state pins advertised run/frame identities,
pages acquisition progressively, coalesces concurrent initial/cursor reads,
accepts cancellation, and retains a fixed 15-minute expiry. Both Series response
caches share an 8 MiB reservation budget. Comparison requests retain limits of
six sources, eight variable groups, 24 hours, 144 source/run/time positions,
12 positions per page, two concurrent acquisitions, 45 seconds per page, and
512 KiB per page. Smaller source batches rotate between models to show each
model early. Positions not attempted before a deadline remain on later pages.
Source readers, registered wind derivation, native decoders and their original
byte/process ceilings are reused.

The screen has stacked aligned charts, fixed start/end, shared cursor and model
visibility, source-specific native timestamps, separate cloud definitions,
precipitation interval bars, optional fields and published ensemble spread.
Native nulls and run boundaries break connecting lines. The client calculates
no model mean, forecast value, or uncertainty statistic. Viewing, hovering,
visibility and styling reuse the loaded comparison. Chart clicks update map time
without shifting its window. Expired charts remain explicitly expired; source
ledger values are withheld at expiry. Details contains native readings and full
provenance. Show available window requires explicit selection.

## Verification mapping

- `api/tests/test_forecast_comparison.py`: default four-model native day, sparse
  GFS timestamps, half-open end, pin identity, field coalescing, initial/cursor
  coalescing, fixed expiry, immutable pages, source-local credential/inventory
  failures, explicit available window, cancellation, deadline/concurrency,
  typed route/bounds, resource ceilings, HRDPS discovery, quantiles/intervals.
- `api/tests/test_weathernext_delivery.py`: selected-field/statistic batching,
  units, common receipt identity and partial-budget metadata receipts.
- `api/tests/test_weathernext_gcs_bridge.py`: actual Linux worker batches mean,
  P10 and P90 with each coordinate/chunk read once; a byte-capped batch retains
  completed fields and does not fetch the refused field's payload.
- `web/src/workbench/ForecastComparison.test.tsx`: default controls, cloud split,
  cursor, map time/window independence, visibility, progressive pages,
  cancellation/obsolete identity, StrictMode, expiry, available-window action,
  clipped precipitation intervals and a true zero bar baseline.
- Existing finite Series, App, API normalization, source delivery and native
  decoder tests protect compatibility.

API command (experiment directory):

```sh
uv run --project api pytest -q -o addopts= api/tests/test_forecast_comparison.py api/tests/test_desktop_series.py api/tests/test_hrdps_query.py api/tests/test_adapter_eccc_datamart.py api/tests/test_source_delivery.py api/tests/test_weathernext_delivery.py api/tests/test_weathernext_local_delivery.py api/tests/test_weathernext_shared_delivery.py api/tests/test_weathernext_gcs_bridge.py api/tests/test_weathernext_native.py
```

Result: 165 passed, eight platform-specific skips. The newly added default-worker
batch and byte-limit cases separately passed in Linux with networking disabled,
using the working tree mounted read-only and image
`astraeus-lightning-proof:c88ff83` at
`sha256:afbed8d5524a1c28a0bce3874118b6ab7d5e3f9d3ae9a54a8860494da55db3f6`.
These two worker proofs use fixed synthetic Zarr objects and zero provider calls.

Web command (web directory):

```sh
npm test -- src/workbench/ForecastComparison.test.tsx src/workbench/NativeSeries.test.tsx src/api.test.ts src/App.test.tsx
npm run build
node scripts/prove-forecast-comparison.mjs
```

Result: 213 frontend tests passed and production build passed. Vite reports its
existing large-bundle advisory. The fixed Chrome browser proof checks six charts,
shared interaction without extra science requests, stable boundaries, visibility,
expiry and layout at normal size and 200% CSS zoom. Temporary screenshots and
receipt are in `/tmp/astraeus-comparison-proof/`; they are constructed UI fixtures,
not live provider validation. CSS zoom is the recorded magnification method,
not a claim of a browser-menu zoom or screen-reader audit.

Generated OpenAPI/TypeScript checks, strict validation of all three changed
OpenSpec contracts, `git diff --check`, and root `specctl validate` pass.

## Live findings and remaining source limitations

The local Compose API and web services were rebuilt and restarted, preserving
other services. The existing selected Google identity was refreshed into the
API's private tmpfs using the repository script, without a new auth mechanism.

HRDPS discovery had coupled directory reads to decoder cgroup/tmpfs checks.
Inventory now reads bounded metadata without invoking those decode gates;
actual acquisition still enforces them. Run discovery can name a run using its
first advertised lead even when `000` is absent. Unreadable inventory remains
unknown rather than confirmed absence. Live HRDPS, RDPS and GFS returned native
temperature, humidity, cloud and registered wind-speed readings.

WeatherNext's native batch initially hit the bridge's single-field guard, then
its existing 64 MiB acquisition ceiling. The guard now admits bounded batches.
Completed fields survive a batch byte/operation limit, with explicit gaps for
unread fields and truthful metadata receipts. In the tested default batch,
temperature, cloud mean and one-hour precipitation were delivered; wind was a
budget gap. Relative humidity, wind-direction statistics, and gusts are not
inferred. Selecting fewer WeatherNext variables can leave room for additional
published statistics. HRDPS/RDPS/GFS precipitation and gusts remain unsupported
by their existing comparison delivery descriptors.

Native acquisition can be slow. A failed or timed-out attempted position remains
an explicit gap; later unattempted positions remain pageable. The fixed lifetime
never extends to finish a slow request. Early diagnostic live attempts and the
final comparison have separate receipts in `/tmp/astraeus-comparison-live*`.
Full native response bodies remain temporary local evidence, not committed data.

### Final common-window live result

The final live request used 47.5 N, 52.7 W and the half-open window
2026-09-09 03:00 UTC to September 10 03:00 UTC for all four default sources.
It delivered 46 pages and 92 of 94 planned positions: HRDPS 22, RDPS 24,
WeatherNext 24 and GFS 22. Each delivered HRDPS/RDPS/GFS position supplied
temperature, humidity, its labelled cloud definition and wind speed. Each
WeatherNext position supplied temperature, cloud and one-hour precipitation;
wind remained a source acquisition budget gap.

Successful page calls took 891.49 seconds in total. The final continuation
failed at the fixed lifetime boundary before the remaining two GFS positions
were delivered. The diagnostic driver recorded `HTTPError` without its status,
so this is evidence of incomplete live delivery, not a verified HTTP 410
receipt. Fixed-expiry rejection is covered separately by automated tests.
The largest returned page was 101,463 bytes, below 512 KiB. No lifetime or
acquisition ceiling was raised to complete this run.

[Sanitized live counts](live-summary.json) preserve the window, delivery counts,
page sizes and final failure without native weather response bodies. The final
runtime rebuild also includes subsequent presentation corrections for interval
bars, coordinate labels and incomplete quantile explanations; the full live
24-hour acquisition was not repeated for those changes.

## Follow-up: one timeline and native pages rendering

The owner's September 9 screenshot reported the duplicate cursor slider and
missing curves. Classification remains experiment. Spec-Refs: GOV-SPEC-001,
GOV-SPEC-004, GOV-SPEC-006. The owning comparison/workbench contracts now specify
one bottom timeline spanning the fixed Series window. It drives the chart and
map time; hover temporarily inspects samples and leaving restores the selected
instant. Playback retains loaded charts and does not renew the comparison.

The rendering defect was selection validation using `JSON.stringify` on source
objects. The client sent `source_id, run, product_id`; Pydantic returned
`source_id, product_id, run`. Identical identities were rejected because of
property order. Validation now compares source/product/run values explicitly,
retaining rejection of actual identity changes. The old browser fixture echoed
the request and therefore missed the production serialization difference. It
now uses API property order and asserts actual points and connecting paths.
Empty initial charts also say loading while their request is pending.

Verification: 102 tests passed across ForecastComparison and App; nine finite
Series compatibility tests passed. Production build passed (existing large
bundle advisory). Strict validation of both changed OpenSpec contracts and
`specctl validate` passed. Browser checks verify a single bottom slider spanning
24 hours, chart cursor updates, preserved points during playback, fixed window,
no extra comparison calls from transport/hover/visibility, and normal/200% CSS
zoom. `LIVE_COMPARISON=1 node web/scripts/prove-forecast-comparison.mjs` passes
real comparison HTTP responses through to the browser while stubbing unrelated
map APIs. Its screenshots and receipts are separate under
`/tmp/astraeus-comparison-live-browser/`; it tests initial native rendering,
not completion of the whole 24-hour comparison. Proof-owned comparisons are
cancelled after inspection. The existing Google token was refreshed through the
repository script, and only the local web service was rebuilt/restarted.
