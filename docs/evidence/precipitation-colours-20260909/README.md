# Experimental precipitation display verification

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006

Owner intent: implement the supplied temperature-colouring plan as an experiment.
No normative status transition, precipitation-type derivation, API change or new
provider acquisition was introduced. The owning experimental rendering contract
is `experiments/st-johns-weather-map/openspec/specs/web-raster-rendering/spec.md`.

## Implemented behaviour

Numeric point readings, stored numeric precipitation features and compatible
native IFS precipitation cells use intensity-dependent colour. Temperature is
read from already returned point data or loaded native IFS grids, with exact
location/native-time and same-source product/run/variant checks. HRDPS is the
fallback; an HRDPS layer cannot fall back to its own wrong run. Expired and
failed temperatures are withheld. Hidden temperature data can contribute.
Temperature-based colours and Same source → HRDPS are disclosed, including
native temperature, source, timestamp and run in inspection. Missing cells,
zero and no-echo flags retain distinct treatment; no rate is inferred from echo.
Native rate, interval amount and snowfall-depth units are preserved. WMS images
retain their provider styles and legends. IFS spread/probability statistics are
not treated as precipitation intensity.

There is no automatic temperature acquisition. Point samples can colour only
their matching location; they do not become a temperature field across the map.
Native grids use exact existing centres and never interpolate temperature.
Visibility, opacity and display-style changes reuse the current IFS selection.

## Verification

- `npm test -- src/workbench/precipitationColours.test.tsx src/workbench/PointDataPanel.test.tsx src/workbench/IFSLayers.test.tsx src/MapPanel.test.tsx src/workbench/MapEvidenceDetails.test.tsx src/workbench/pointRequests.test.ts`: 119 passed.
- After the final HRDPS same-source run guard and display-identity adjustment:
  `npm test -- src/workbench/precipitationColours.test.tsx src/workbench/IFSLayers.test.tsx`: 21 passed.
- `npm run build`: passed (existing bundle-size advisory).
- `uv run --project api pytest -q api/tests/test_layer_coverage.py api/tests/test_layer_frame_contract.py api/tests/test_rendered_grids.py api/tests/test_source_grid.py`: passed, two skips.
- `uv run --project api python scripts/generate_source_contract.py --check`: passed for OpenAPI and fixtures.
- `openspec validate web-raster-rendering --type spec --strict`: passed.
- `uv run --project tools/specs python tools/specs/specctl.py validate`: zero errors and warnings.
- `node experiments/st-johns-weather-map/web/scripts/prove-precipitation-colours.mjs`:
  passed using the owned Vite server on `127.0.0.1:5269`, all weather responses
  intercepted and all external providers blocked. Three explicitly selected
  grids (precipitation, hidden temperature, cloud) were loaded. Hiding cloud and
  adjusting precipitation opacity created no new science selections or grids.

The broad `src/App.test.tsx` gate is not green in this workspace: 88 failures
reach the existing untracked `ForecastComparison.tsx:195` and call `.filter` on
an absent IFS catalogue field list. The combined run reported 125 passes and
88 failures. That independent in-progress implementation was preserved.

## Browser evidence and limits

`01-overlapping-cloud.png` shows the constructed opaque cloud overlay;
`02-isolated-precipitation.png` shows the same precipitation cells after hiding
it. This demonstrates an overlap mechanism, not the cause of the user's original
live white-layer report. Numeric cells include above-zero, exactly-zero and
below-zero temperatures, missing temperature, missing precipitation and zero.
`03-inspection.png` discloses 1.9°C, IFS source, native time and run for a cell.

`04-200-percent-equivalent.png` uses a 720×450 CSS viewport for a nominal
1440×900 desktop. Native Chrome settings navigation terminated the installed
headless browser, so this is a effective-viewport emulation, not a verified native
browser zoom operation. The test confirms no horizontal document overflow and
no legend/Point data overlap. The two panels scroll independently.

Screenshots are fixed synthetic data, not current weather. The basemap is absent
because provider traffic is blocked. `receipt.json` records requests and checks.

The final layer/legend integration check passed `MapStack.test.tsx` and
`MapEvidenceDetails.test.tsx`. Expanding that check to `discovery.test.tsx`
found two existing ambiguous `getByRole('searchbox')` selectors because the
in-progress IFS browser adds another search input. These are retained alongside
the App catalogue-mock failures; the overall workspace suite is not green.

Final browser rerun also asserts that visibility/opacity changes create no
additional point requests. Final MapStack and MapEvidenceDetails run: 21 passed.
The owned Vite proof server on port 5269 was stopped after verification.
