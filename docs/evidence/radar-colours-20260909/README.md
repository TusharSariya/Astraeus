# Radar RGB regression and temperature source controls

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006

User report: radar alone was white and temperature source was not selectable.
This supersedes the overlap hypothesis recorded in the earlier precipitation
colour proof for this particular live report.

## Cause and correction

`isLocallyRendered` classified every raster with `published_artifact` evidence
as a local scalar cloud render. Radar's stored sample metadata has that basis,
while its image is a `live_proxy` WMS image. With interpolation enabled, even a
single radar frame entered FlowBlendLayer, whose alpha-based cloud shader emits
white. The captured provider PNG is blue/green before client rendering.

The client now confines that path to rendered-grid and satellite groups;
observation-group radar retains provider RGB and never requests cloud flow.
The cloud-mask rendering regression tests still pass.

Active precipitation rows now contain a Temperature source selector: Auto,
Same source only, HRDPS, and catalogue-declared temperature sources. Choices
persist through saved stacks and URLs and affect only already-loaded numeric
evidence. Explicit choices never silently fall back. The radar row has a shorter
readable title, Provider colours status, and an explanation that its image uses
the provider palette while temperature selection applies to numeric samples.
Source choice and opacity no longer retrigger the stored-feature effect merely
because the display selection object changed.

## Verification

- Five focused frontend files: 130 tests passed (MapPanel, precipitationColours,
  MapStack, pointSelections, PointDataPanel).
- `npm run build`: passed, existing bundle-size advisory.
- `openspec validate web-raster-rendering --type spec --strict`: passed.
- `uv run --project tools/specs python tools/specs/specctl.py validate`: passed.
- Browser proof: `node experiments/st-johns-weather-map/web/scripts/prove-radar-colours.mjs`.
  Captured provider PNG replay verifies visible RGB, directly accessible picker,
  persisted HRDPS choice, zero additional science requests from changing source,
  and no JavaScript errors. External/provider traffic is blocked in the replay.
  The PNG is stretched across the requested bounds solely to test colour
  preservation; the replay screenshot is not evidence of current geography.
- `provider-radar.headers` records the actual local API response and upstream
  request for the captured PNG at 2026-09-09T15:48Z. No temperature was fetched.

Only the local web service was rebuilt/recreated with `docker compose build web`
and `docker compose up -d --no-deps web`. It serves port 5173. The API and worker
were not restarted. Existing unrelated workspace test failures are described in
`../precipitation-colours-20260909/README.md`.

Experimental rendering contract amended; no normative status changed.
