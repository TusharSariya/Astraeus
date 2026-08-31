# Design: frame fallback, display interpolation, viewport layout

## Owner decisions (approved 2026-08-31 with the implementation plan)

1. **Observed groups snap previous-only.** `satellite`, `observation`, `alert`
   and any undeclared group fall back only to an earlier frame: snapping an
   observation forward would show weather that had not yet happened, and an
   alert issued after the scrubbed instant did not exist then. `forecast_proxy`,
   `published_model` and `rendered_grid` snap to the nearest frame in either
   direction. Snap distance is unlimited within the −3h..+24h window; the
   disclosure always names the real frame time and offset.
2. **Observed layers at future instants.** The tolerance check keeps its
   published meaning and runs first: a frame within tolerance is effectively
   the same instant and is drawn quietly exactly as today, even a hair past the
   session reference. The future prohibition governs only the fallback path:
   beyond tolerance, observed groups fall back previous-only and only for
   scrubbed instants at or before the session reference; further into the
   future the note says observed imagery has no frames for future instants. An
   hours-old radar sweep under a +18 h timestamp is exactly the misdating the
   governing rule forbids.
3. **Tolerance is the exact/fallback boundary.** Within tolerance: drawn
   quietly, signed offset in the drawer and ribbon as today. Beyond tolerance:
   drawn from the fallback frame with a prominent on-map note. Nothing is
   hidden silently in either case.
4. **Interpolation is opt-in, default off, display-only.** It applies to
   forecast imagery only — never to observed groups and never to stored
   features. What it does is composite two real retrieved frames at fractional
   opacities on the GPU. Stacked translucent layers compose as
   `1−(1−a)(1−b)`, which is not a linear crossfade, and alpha compositing
   produces derived display pixels — so every description of the feature says
   "display compositing of two retrieved frames", and none claims that no
   pixel is synthesized or that intermediate field values exist. The
   `openspec/config.yaml` governing-rule sentence is amended to carve out
   exactly this disclosed, opt-in display case and nothing more: `/point`,
   `/features`, stories, readings and every data path remain interpolation-free.
5. **Scrubber snapping.** With interpolation off and at least one active
   visible layer holding frames in the window, the selected instant snaps to
   the closest member of the union of active layers' frame instants (ties go
   earlier). Otherwise the scrub is free at five-minute steps. Toggling a
   layer never force-resnaps the current position — only a user scrub action
   snaps — so the timeline cannot jump under the reader.
6. **Exact instants.** The selected time is an exact epoch-instant, not a
   whole-minute offset: the session reference is an unrounded `new Date()`,
   so minute offsets could never land exactly on published frame timestamps.
   Snapping and frame jumps set the exact frame instant; the slider maps its
   minute-granular track onto instants.

## Blend atomicity and budget

A blend is keyed by layer + extent + both frame times. Both images are fetched
together and committed only when both arrive with valid provenance and the key
is still current; if either fails, the layer falls back to the nearer single
frame at its full intended opacity with the snapped-frame disclosure — never a
lone half-opacity slot, which would present a partial retrieval as a blend.
Retrieved images are reused across slots by layer + frame time + extent (small
LRU), so a frame moving from "next" to "previous" during a scrub is not
refetched, and scrub-driven fetches are debounced against the documented
upstream budget.

## Layout

Simple mode becomes a `100dvh` shell with explicit grid rows for every child
(status banner, masthead, workspace), so the conditional banner cannot steal
the `1fr` row. The workspace is map stage + right conditions strip
(scrollable) over a bottom timeline dock; the story/coverage panel expands
from the dock over the map. Expert mode keeps its existing scrolling layout
and still gains fallback, notes and snapping through the shared MapPanel. The
page footer's disclaimer moves into the strip in simple mode. Below 900 px the
shell reverts to document flow with a sticky dock.
