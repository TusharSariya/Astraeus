# Native-frame timeline correction — September 8, 2026

Status: implementation and automated/browser verification complete; owner visual
acceptance remains pending on #38. No operational or verified status promotion.

The former compact timeline hid markers and transport controls. The corrected
80px dock exposes step/playback intervals, previous/next native frames, exact
selected date/time, three range presets and the native frame rail. Tracks expand
over the unchanged map canvas, with per-layer cadence, native/run identity,
retrieval status, timestamp search and exact-time cluster selection.

## Evidence scope

These are actual Chrome screenshots of the implemented app, not mockups.
Weather responses are explicitly constructed fixtures: 6-minute radar history,
10-minute satellite history, hourly forecasts, six-hourly long-range forecasts,
missing imagery, and request failures. OpenFreeMap supplies reference map tiles.
This verifies interface behavior; it does not certify provider history completeness,
live acquisition, screen-reader compatibility or weather accuracy.

## Verification

- `npm test`: **565 passed**, 41 files, including eight GPU tests.
- `npm run build`: **passed**; existing large JavaScript chunk warning remains.
- `openspec validate desktop-evidence-workbench --strict`: **passed**.
- `uv run --project tools/specs python tools/specs/specctl.py validate`: **0 errors, 0 warnings**.
- `node scripts/prove-timeline.mjs`: **passed**, 38 captures, no page errors.
- `BENCH_PROOF_DIR=/tmp/astraeus-timeline-regression node scripts/prove-map-first.mjs`: **passed**. Search, add/remove, opacity/order, saved stacks, URL restoration, all five views/themes, optional docking, exact repeated map-coordinate camera check, 200% zoom, loading and failed requests.

Timeline browser checks exercise every 1/2/4/8/15/30-minute step and playback
interval, reverse, manual interruption, pointer scrubbing, exact cluster picks,
focus return, timestamp search, offscreen selection recovery, range preservation,
URL restoration, an empty stack and failed timeline requests. Unit tests also
exercise background/resume without catch-up, irregular native-frame navigation,
range/API-bound intersections and dense clustering without timestamp loss.

Mapped requirements: “The compact timeline exposes transport and native frames”,
“Display ranges and layer tracks preserve exact shared time”, and “Every returned
frame timestamp remains reachable” in the [accepted desktop contract](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/specs/desktop-evidence-workbench/spec.md).
Owner direction is recorded in [acceptance](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/acceptance.md).
Tests: `timelineModel.test.ts`, `playback.test.ts`, `workbench/DesktopApp.test.tsx`,
existing frame/Map tests, and both browser scripts.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-006.

## Measured layout

| Viewport | Closed map viewport share | Toolbar | Timeline | Page scrolling |
|---|---:|---:|---:|---|
| 1280×800 | 83.0% | 56px | 80px | None |
| 1440×900 | 84.9% | 56px | 80px | None |
| 1920×1080 | 87.4% | 56px | 80px | None |

Each measurement passed in dark, light and red-night themes. Expanding Tracks
preserves map width/height. At native Chrome 200% zoom, controls reflow taller,
the expansion stays inside the remaining stage, and page scrolling remains absent.
The expansion itself scrolls so every row and detail remains reachable.

[Timeline run receipt](results.json) · [Broader regression receipt](regression-after-receipt.json)

## Before and after

The linked before captures show the previously delivered slim timeline with its
controls hidden. They use the earlier single-layer fixture; the after captures
use the mixed-cadence fixture described above.

| Viewport | Before timeline revision | After, closed | After, tracks |
|---|---|---|---|
| 1280x800 | [Before](../map-first-20260908/after-1280x800-dark-closed.png) | [After](after-1280x800-dark-closed.png) | [Tracks](after-1280x800-dark-tracks.png) |
| 1440x900 | [Before](../map-first-20260908/after-1440x900-dark-closed.png) | [After](after-1440x900-dark-closed.png) | [Tracks](after-1440x900-dark-tracks.png) |
| 1920x1080 | [Before](../map-first-20260908/after-1920x1080-dark-closed.png) | [After](after-1920x1080-dark-closed.png) | [Tracks](after-1920x1080-dark-tracks.png) |

## Desktop capture matrix

| Viewport | Dark | Light | Red night |
|---|---|---|---|
| 1280x800 | [Closed](after-1280x800-dark-closed.png) / [Tracks](after-1280x800-dark-tracks.png) | [Closed](after-1280x800-light-closed.png) / [Tracks](after-1280x800-light-tracks.png) | [Closed](after-1280x800-Red-night-closed.png) / [Tracks](after-1280x800-Red-night-tracks.png) |
| 1440x900 | [Closed](after-1440x900-dark-closed.png) / [Tracks](after-1440x900-dark-tracks.png) | [Closed](after-1440x900-light-closed.png) / [Tracks](after-1440x900-light-tracks.png) | [Closed](after-1440x900-Red-night-closed.png) / [Tracks](after-1440x900-Red-night-tracks.png) |
| 1920x1080 | [Closed](after-1920x1080-dark-closed.png) / [Tracks](after-1920x1080-dark-tracks.png) | [Closed](after-1920x1080-light-closed.png) / [Tracks](after-1920x1080-light-tracks.png) | [Closed](after-1920x1080-Red-night-closed.png) / [Tracks](after-1920x1080-Red-night-tracks.png) |

## Native Chrome 200% zoom matrix

| Viewport | Dark | Light | Red night |
|---|---|---|---|
| 1280x800 | [Closed](zoom200-1280x800-dark-closed.png) / [Tracks](zoom200-1280x800-dark-tracks.png) | [Closed](zoom200-1280x800-light-closed.png) / [Tracks](zoom200-1280x800-light-tracks.png) | [Closed](zoom200-1280x800-Red-night-closed.png) / [Tracks](zoom200-1280x800-Red-night-tracks.png) |
| 1440x900 | [Closed](zoom200-1440x900-dark-closed.png) / [Tracks](zoom200-1440x900-dark-tracks.png) | [Closed](zoom200-1440x900-light-closed.png) / [Tracks](zoom200-1440x900-light-tracks.png) | [Closed](zoom200-1440x900-Red-night-closed.png) / [Tracks](zoom200-1440x900-Red-night-tracks.png) |
| 1920x1080 | [Closed](zoom200-1920x1080-dark-closed.png) / [Tracks](zoom200-1920x1080-dark-tracks.png) | [Closed](zoom200-1920x1080-light-closed.png) / [Tracks](zoom200-1920x1080-light-tracks.png) | [Closed](zoom200-1920x1080-Red-night-closed.png) / [Tracks](zoom200-1920x1080-Red-night-tracks.png) |

## Interaction and failure captures

- [Exact native timestamp chooser](outlook-frame-chooser.png)
- [Failed timeline request](timeline-request-failed.png)
- [Loading point evidence](regression-loading-point.png)
- [Failed layer index](regression-failed-layers.png)
- [Failed point request](regression-failed-request.png)
- [Weather story expansion](regression-weather-story-open.png)

## Review findings resolved

Browser review found a global minimum input height overriding the slim slider,
and the zoomed expansion could extend beneath the toolbar. The corrected CSS
bounds the dock and uses the measured stage height. Review also preserved exact
older Focus selections outside the timeline window, separated requested/native
frame labels from actual draw receipts, and restored focus when Weather story
replaces Tracks. Right overlays and native-frame choosers dismiss competing
panels without changing selections, camera or acquisition policy.
