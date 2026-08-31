## Why

When the scrubbed instant has no frame within a layer's staleness tolerance,
the client today renders nothing for that layer. The tolerance is half the
cadence, so a satellite composite goes dark five minutes past its last frame
and a forecast field disappears between its hourly valid times. The only
explanation lives in the layer drawer and the coverage ribbon — both off the
map, and the ribbon below the fold. The owner has directed (2026-08-31,
recorded in `design.md`) that a layer fall back to a neighbouring published
frame instead — previous-only for observed evidence, nearest for forecasts —
with a visible per-layer note on the map disclosing exactly which frame is
shown and how far it sits from the selected time. Nothing is hidden silently
and nothing is misdated silently: the fallback trades "invisible absence" for
"disclosed neighbouring evidence", which the owner judges more honest in use.

Two companion decisions ride with it. First, an opt-in, default-off
"interpolation" setting: when on, a forecast layer's imagery is display-
composited between its previous and next frames by fractional opacity. This
touches the governing "never interpolate into a gap" convention, so the owner
has approved amending that convention's wording to carve out exactly this
disclosed, display-only case; every description of it says "display
compositing", never that intermediate values exist. Second, when interpolation
is off the timeline scrubber snaps to the closest instant in the union of the
active layers' published frame times, so the selected time is always a real
frame instant of at least one drawn layer.

The layout changes with it: the map fills the viewport, the conditions panel
becomes a scrollable right strip, the scrubber docks along the bottom so map
and timeline are visible together (today the timeline sits ~900 px down the
page), and the weather story and coverage ribbon move into a panel that
expands from that dock.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **`web/src/api.ts`**: a `resolveLayerFrame` resolver over the kept
  `resolveFrame`/`nearestFrame` primitives, returning
  `exact | snapped | blend | none` with the direction and disclosure sentence;
  `previousFrame`/`nextFrame`; `unionFrameInstants` and `snapInstant` for the
  scrubber. All pure and unit-tested.
- **`web/src/MapPanel.tsx`**: consumes resolutions; slot-based raster state so
  a blend is two real retrieved images at fractional opacities committed
  atomically; a `.map-frame-notes` corner block (one note per snapped, blended
  or undrawable active layer) mirrored into the text alternative and drawer
  rows; per-frame image reuse keyed by layer + frame + extent.
- **`web/src/App.tsx`** plus new `web/src/TimelineDock.tsx` and
  `web/src/StoryFlyout.tsx`: exact-instant scrub state, snapping, the
  interpolation toggle, and the full-viewport shell (map stage, right
  conditions strip, bottom timeline dock, expandable story panel). Expert mode
  keeps its current scrolling layout.
- **`web/src/styles.css`**: the app-shell grid, dock, strip and flyout rules;
  existing scrubber/ribbon/story rules survive inside the new containers.
- **`openspec/config.yaml`**: the governing-rule sentence and the
  staleness-tolerance hard-won fact are amended to carry the owner-approved
  fallback-with-disclosure and opt-in display-compositing carve-outs.
- **Specs**: `map-layers` staleness requirement is modified (render nothing →
  fall back with mandatory disclosure); `web-evidence-interface` layer-answer
  and scrubber requirements are modified and interpolation + viewport-layout
  requirements added; `web-raster-rendering` gains the display-compositing
  requirement. `/features` exact-frame and server-side 422 rules are unchanged.

No API or server change: the client only ever requests instants taken verbatim
from `layer.times`, which the server's nearest-within-tolerance matching hits
exactly.

## Impact

- Affected specs: `map-layers`, `web-evidence-interface`,
  `web-raster-rendering`, plus the `openspec/config.yaml` convention text.
- Affected code: `web/src/` only (api.ts, MapPanel.tsx, App.tsx, two new
  components, styles.css, tests). `api/`, `ingest/`, `registry/`, Compose and
  `docs/specv1` untouched.
- Risk: display compositing doubles raster requests for blended layers —
  bounded by default-off, forecast-only scope, per-frame image reuse and
  debounced scrub fetches against the documented 16/240 upstream budget.
