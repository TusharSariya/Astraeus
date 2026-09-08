# Map-first desktop correction evidence

Owner direction: “Restore the original look with a map-first layout”, September
8, 2026. This revision replaces the old vertical rail, permanent status banner,
Hyperlegible tokens and permanent stack with the accepted map-first contract.
Issue #38 was reopened. Implementation and browser verification are complete;
owner visual acceptance remains open. Retired issues and phone work are unchanged.

The before captures run merged main `85ba422` from a separate temporary archive.
The after captures run `fix/map-first-workbench`. Both use the same constructed
weather fixtures and fixed clock (`2026-09-07T12:00:00Z`). OpenFreeMap reference
tiles are allowed; weather-provider traffic is blocked. These captures verify
layout and evidence interactions, not live source coverage or operational use.

## Measured layout

| Application viewport | Toolbar | Collapsed timeline | Map pane | Viewport share |
|---|---:|---:|---:|---:|
| 1280×800 | 56px | 72px | 1280×672 | 84.0% |
| 1440×900 | 56px | 72px | 1440×772 | 85.8% |
| 1920×1080 | 56px | 72px | 1920×952 | 88.1% |

All measurements pass in dark, light and red night. Opening Layers or timeline
details preserves map dimensions. The final browser run also checks native Chrome
200% page zoom at all three sizes: `innerWidth` halves and `devicePixelRatio` is
2. It checks page overflow and hit-tests the toolbar, timeline, map navigation and
overlay close controls. Scrollable view bodies and overlay contents remain local;
the application page does not scroll. At 200%, the toolbar wraps to keep controls
reachable; the 56px desktop target applies at normal zoom and widths ≥1280px.

## Verification mapped to the accepted contract

Owning contract: [desktop-evidence-workbench](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/specs/desktop-evidence-workbench/spec.md).
Authorization: [September 8 owner-selected revision](../../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-workbench/acceptance.md).

| Requirement | Verification |
|---|---|
| Original ocean design system; map-first shell and visible state | Browser captures at all three sizes, all themes, normal and native 200% zoom; map fraction/toolbar/timeline measurements; five-view theme captures |
| Ordered evidence stack | Browse search, addition, opacity, visibility, raise, removal and saved-stack restoration in the browser; MapStack unit tests retain run and legend distinctions |
| Linkable Focus and stack | Browser reload preserves exact URL selections and reopens with overlays closed; existing Focus URL and DesktopApp tests |
| Camera and local view state | Pan before all five view switches, verify the same canvas and scale, and verify the same map pixel selects identical coordinates; lazy-mount/state-retention unit test |
| Shared overlay and keyboard context | Layer and point provenance, Escape return to the actual opener, overlay return to Layers/Evidence button, search preservation when replacing provenance; WorkbenchShell and DesktopApp tests |
| Timeline details and weather story | Both expand over the stage without changing map dimensions; existing scrubber/playback tests retained |
| Honest loading, absence and errors | Held point request, failed point/layer requests, unavailable default stack entries and long labels; existing data/evidence tests |

Commands and results:

- `npm test -- --reporter=dot` in `web`: **556 passed**, including eight GPU tests.
- `npm run build` in `web`: **passed**. Existing large-bundle warning remains.
- `node scripts/prove-map-first.mjs` in `web`: **passed** in installed Chrome.
- `openspec validate desktop-evidence-workbench --strict` in the experiment: **passed**.
- `uv run --project tools/specs python tools/specs/specctl.py validate`: **0 errors, 0 warnings**.
- `git diff --check`: **passed**.

The final main-agent review corrected hidden-view acquisition, retained camera
resizing, inspector replacement, fullscreen focus fallback, disclosure/control
obstruction and night attribution styling. No backend/API, source identities,
native timestamps, scientific rules or provider acquisition contracts changed.

## Screenshots

Representative before/after pairs and panel/theme/zoom captures are versioned
alongside this file. Full captures remain at `/tmp/astraeus-map-first-proof/` and
are reproducible with the checked-in browser procedure. JSON receipts record the
complete size/theme measurement matrix and intercepted application requests.

| Viewport | Before (original shell) | After (closed) | After (Layers open) |
|---|---|---|---|
| 1280×800 | [Before](before-1280x800-dark-closed.png) | [After](after-1280x800-dark-closed.png) | [Layers](after-1280x800-dark-open.png) |
| 1440×900 | [Before](before-1440x900-dark-closed.png) | [After](after-1440x900-dark-closed.png) | [Layers](after-1440x900-dark-open.png) |
| 1920×1080 | [Before](before-1920x1080-dark-closed.png) | [After](after-1920x1080-dark-closed.png) | [Layers](after-1920x1080-dark-open.png) |

Additional captures: [light](after-1440x900-light-open.png),
[red night](after-1920x1080-Red-night-open.png),
[native 200%](zoom200-1280x800-dark-open.png),
[Browse search](browse-search.png), [Evidence](evidence-open.png),
[provenance](provenance-open.png), [timeline](timeline-open.png),
[weather story](weather-story-open.png), [loading](loading-point.png),
[failed layers](failed-layers.png), [failed point](failed-request.png).

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-006; accepted
experimental desktop workbench and web evidence interface requirements.
Classification: spec-compatible-change, owner-selected desktop revision.
