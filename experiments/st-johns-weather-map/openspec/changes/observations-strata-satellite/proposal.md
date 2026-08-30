## Why

Selecting HRDPS in the point panel makes every METAR observation vanish. The
live product path (`api/weather_api/app.py:512`) keeps only fields whose
`provenance.source_id` equals the product's source, so cloud layers, fog and
visibility, which come from `awc-metar-speci`, are dropped the moment a model is
chosen; the fixture path (`app.py:551,560`) keeps observations alongside the
product, so the two modes disagree. The owner then asked, and clarified by
question on 2026-08-30, for three things:

1. Keep the as-reported cloud layers under a selected model and let the reader
   narrow them by band, Low / Middle / High, as a **view filter** over reported
   base height. No derived percentage, nothing new from the API. Owner gate 2 in
   `cloud-and-fog-evidence` (deriving `cloud_low/middle/high`) stays open and the
   `store.py:51-55` prohibition stays.
2. Group three flat menus: the 21 timeline coverage rows, the forecast-model
   row, and the station/buoy select. The layer drawer already groups.
3. Offer GOES-East satellite imagery as layers, relayed by ECCC GeoMet. The
   owner is explicit that it is **now/past only and cannot be forecast**. Four
   products: Day Visible / Night IR (1 km), Snow-Fog / Night Microphysics
   (1 km), Natural Color (1 km), Night IR (2 km).

Evidence verified live on 2026-08-30 (not re-derived here): GeoMet advertises
`GOES-East_1km_DayVis-NightIR`, `GOES-East_1km_SnowFog-NightMicrophysics`,
`GOES-East_1km_NaturalColor` and `GOES-East_2km_NightIR` with a time dimension
of `<now-48h>/<now-~15min>/PT10M`; their titles end in `[1 km]` / `[2 km]`,
which `parse_title_units` would read as a unit. `TimeExtent.steps()`
materialises 289 instants (under the 4096 cap) and the window intersection
leaves roughly 19 past frames at 600 s cadence with a 300 s tolerance. The
per-request upstream budget is 16 with 13 proxies today; a 17th proxied layer on
a cold cache would exhaust it and `_proxied_forecast_layers` would return no
proxies at all.

What remains unverified: whether every one of the four layers answers `GetMap`
with a non-trivial image at the latest advertised instant and at `now-2h`, and
whether `GetLegendGraphic` answers for satellite layers at all. Both are probed
once, politely, in tasks A3 and the results recorded rather than assumed.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **A1 (observations survive a product selection):** in the live product path,
  return the product's own fields plus every field whose source's registry
  `category` is one of `surface_observation`, `marine_observation`,
  `optional_observation`, `radar`, `satellite`. Each field keeps its own
  source; a METAR visibility under an HRDPS header is tagged `awc-metar-speci`.
  The header, badge, reason and the "nothing published for this product" branch
  are unchanged. A notice names the observation sources shown alongside.
- **A2 (removed by owner decision):** no cloud derivation. `store.py:51-55` and
  the `UNAVAILABLE_POINT_FIELDS` note stay as they are; `cloud_low`,
  `cloud_middle`, `cloud_high` remain unavailable.
- **A3 (satellite proxies):** four `SATELLITE_LAYERS` specs on the existing
  `ForecastLayerSpec` mechanism, `product="GOES-East"`, new layer group
  `satellite`, `evidence_basis: live_proxy`, semantics stating observed imagery
  relayed by ECCC GeoMet from NOAA GOES-East, frames exist only for the past, it
  is never forecast, not sampled by `/point`, closest registry record
  `noaa-goes-east`. A `[N km]` resolution bracket is a resolution, not a unit:
  units publish as `unknown` and the resolution goes into a notice.
  `legend_available` reflects a real probe rather than an unconditional `True`.
  Per-request upstream ceiling raised from 16 to 32 with the 13 existing specs
  byte-identical.
- **B1–B4 (grouping):** one shared `layerGroup()` plus group order and labels in
  `web/src/api.ts`; coverage rows grouped under headings with counts, satellite
  first with the line "observed imagery: frames exist only for the past"; the
  model row grouped by `source.producer` with BLEND first and ungrouped; the
  station select grouped by live / no-source `<optgroup>`.
- **B5 (cloud band filter):** three `aria-pressed` toggles Low / Middle / High
  above the Cloud layers metric, each printing its band (low: base < 6,500 ft
  / 1,981 m; middle: 6,500–20,000 ft / 1,981–6,096 m; high: >= 20,000 ft /
  6,096 m, the FAA AC 00-6B / NAV CANADA aviation convention). All on by default
  equals the full as-reported list. A layer with no base in metres is never
  hidden and is labelled "base Unknown — not filterable". The detail states
  "N of M reported layers shown · view filter, not a classification". Nothing is
  computed per band; "Cloud L / M / H" stays Unknown.
- **B6–B7 (verification):** no web change is expected for observations under a
  selected model; it is asserted, along with every item above, in the web tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `point-evidence-sampling`: a product selection returns the product's own
  fields plus observations retained by registry category, each with its own
  source; the product's own "nothing published" branch is unchanged; low,
  middle and high cloud remain unavailable.
- `geomet-wms-access`: GOES-East satellite proxies are observed, past-only,
  never forecast, not sampled by `/point`; a `[N km]` resolution bracket is not
  a unit; legend availability reflects a probe; the per-request budget is 32
  with the 13 original proxies unchanged.
- `web-evidence-interface`: coverage rows, the model row and the station select
  are grouped; the cloud band filter is a view filter that never hides an
  unfilterable layer and never computes a value; "Cloud L / M / H" stays
  unavailable.

## Impact

Ownership is disjoint so the three agents run in parallel:

- Agent A (API): `api/weather_api/{app.py,store.py,wms.py,models.py}`,
  `ingest/adapters/eccc_geomet.py` (title parser only), `api/tests/*`,
  `docs/geomet-layers.md`.
- Agent B (web): `web/src/{App.tsx,api.ts,MapPanel.tsx,types.ts,styles.css,
  fixtures.ts,*.test.ts*}`.
- Spec agent: `openspec/` only.

Nobody touches `registry/`, `ingest/adapters/awc.py`, `ingest/meteorology.py`.
`cloud-and-fog-evidence/tasks.md` is not edited; its gate 4.2 stays unticked.

Risk: proxied layer count goes from 13 to 17 against a raised ceiling of 32.
Capabilities are cached for 300 s so only cold requests pay 17 upstream calls;
the ceiling is a politeness limit against a free public service and is raised by
exactly one batch of headroom, not removed. `Layer.group` gains a Literal member,
which is a schema addition, not a change to any existing value.
