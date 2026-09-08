# Unified source discovery — September 8, 2026

The owner approved the unified discovery plan and requested implementation.
WeatherNext 3 was already in `/catalog`, but Browse consumed only `/layers`.
The point-product selector also changed the map catalogue. The corrected browser
uses all registry declarations plus map capabilities independently of that selector.

All 125 registry sources have discovery metadata. Subject tags use explicit
canonical families, declared variable labels and reviewed product associations;
they do not assert implemented fields or scientific comparability. Provider,
product, kind, method, ensemble form and interface are separate dimensions.
Unknown metadata and information-only products remain visible. WeatherNext has
separate local/historical point actions, with no invented map image or Series.
GOES cloud imagery belongs to Clouds and Satellite imagery; the snow/fog product
also belongs to Snow/ice and Visibility/fog. Solar imagery stays in Space weather.

The existing GFS selected-time raster routes remain listed with empty native
axes and unknown imagery when their finite cache is empty. Only selecting a map
layer requests its existing raster route. Catalogue reads do not acquire values.

## Verification

- Full frontend suite: 590 tests pass (42 files, including GPU tests).
- Final focused discovery/stack/Sources/focus check: 22 tests pass.
- Affected backend suite: 168 tests pass, including empty-cache catalogue paths,
  WeatherNext capabilities, explicit GOES identity, variable-based discovery and
  synthetic fixture clock stability.
- Production build passes; the existing large-bundle warning remains.
- Generated OpenAPI/fixtures and source TypeScript drift checks pass. Synthetic
  fixture values now use the fixture clock instead of the current hour.
- Strict desktop OpenSpec and specctl validation pass.
- Chrome discovery proof uses the real catalogue with deliberately unavailable
  weather responses: 125 sources, point and Series navigation, multi-subject
  grouping, combined filters, focus/URL/camera preservation, and no data requests
  from browsing or inspecting WeatherNext. Weather requests after explicit actions
  are intercepted and fail visibly; no live forecast retrieval is claimed.
- Chrome map-first regression passes, including saved stacks, URL restoration,
  view switching, camera, focus, all themes and native 200% zoom.

The earlier complete backend suite had baseline-confirmed unrelated failures;
this change does not claim to repair those or claim a green complete backend run.
A time-sensitive NativeSeries expiry test failed once while browser checks ran
concurrently; the later complete frontend run passed without competing browser
work. The discovery proof waits for the existing asynchronous focus restoration.

## Browser evidence

The `browser/` directory contains the actual three-size, three-theme, 100% and
native 200% zoom captures, with panels open and closed, plus capability/filter
and Series captures. The receipt records requests and viewport measurements.
Weather responses are explicitly unavailable constructed responses. Reference
map tiles are OpenFreeMap. No operational or scientific verification is asserted.

Before: [map-only Browse](../map-first-20260908/browse-search.png).
After: [WeatherNext paths](browser/weathernext-paths.png),
[combined filters](browser/combined-filters.png),
[Series navigation](browser/series-navigation.png).

## Runtime and handoff

Frontend: http://localhost:5197. Isolated API: http://localhost:8197.
Use the [workbench startup instructions](../../../experiments/st-johns-weather-map/docs/workbench-runtime.md).
The original dirty checkout is untouched. No credentials, provider acquisition
rules, admission states, saved-stack schema or production deployment changed.
Optional catalogue fields are backwards-compatible; old/malformed discovery
metadata falls back to declared fields and explicit Unknown groups.

PR #306 carries the correction. #38 stays open for owner visual acceptance.
Rollback is the implementation/spec revision and rebuilding the isolated API.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-006;
`desktop-evidence-workbench/web-evidence-interface` unified discovery,
`source-registry-catalogue`, separate imagery availability and existing
`api-first-source-delivery` capability semantics.
