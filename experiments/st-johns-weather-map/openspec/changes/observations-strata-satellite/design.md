## Context

- **Product filter.** `app._live_point` (`app.py:504-524`) filters
  `fields` to `provenance.source_id == source_id` when `product=` is given.
  Every observation is dropped in live mode. The fixture path keeps them. The
  registry (`registry/source_data.py`) already carries a `category` per record
  (`surface_observation`, `marine_observation`, `optional_observation`, `radar`,
  `satellite`, `deterministic_forecast`, `ensemble`, ...) and
  `store._registry_config(source_id)` (`store.py:918-924`) already reads it.
- **Cloud layers.** `cloud_layer_{n}_cover` (percent) and `cloud_layer_{n}_base`
  (metres, original feet) are already sampled into `/point` (`store.py:56-60`)
  and listed as reported in the web point panel. `store.py:51-55` prohibits
  deriving `cloud_low/middle/high`; that is owner gate 2 in
  `cloud-and-fog-evidence`, still open.
- **Satellite.** GeoMet's four GOES-East layers advertise
  `<now-48h>/<now-~15min>/PT10M`. `TimeExtent.steps()` (`eccc_geomet.py:231-243`)
  materialises the range; `_proxied_forecast_layers` (`app.py:313-386`)
  intersects it with the -3 h / +24 h window and derives cadence 600 s,
  tolerance `max(60, 300)` = 300 s. The scrubber steps 5 min, so every scrub
  position resolves to a 10-min frame or to "no frame here". Titles end in
  `[1 km]` / `[2 km]`; `parse_title_units` (`eccc_geomet.py:159`) is anchored
  to the last bracket and would publish `units: "1 km"`.
- **Budget.** `MAX_UPSTREAM_CALLS_PER_REQUEST = 16` (`wms.py:57`), 13 proxies
  today, `test_wms_proxy.py:493` pins `13 <= budget`. On a cold cache 17
  capability fetches would exhaust 16 and `app.py:333-334` would then return
  no proxies at all, a total loss rather than a partial one.
- **Grouping.** `Layer.group` is a Literal (`models.py:225`); the web
  `layerGroup()` is private to `MapPanel.tsx:242`. Coverage rows
  (`App.tsx:695-722`) are flat in API order; the model row (`App.tsx:464-503`)
  is flat with a `source.producer` badge; the station `Select` helper
  (`App.tsx:103-106`) emits flat `<option>`s.

## Goals / Non-Goals

**Goals:**
- Under a selected model, keep every retrieved observation visible with its own
  source tag, so nothing is borrowed and nothing disappears.
- Let the reader narrow the as-reported cloud layers by band without the system
  computing, classifying or returning anything it did not retrieve.
- Offer GOES-East imagery as observed, past-only evidence with semantics that
  say so, without regressing any existing proxied layer.
- Group the three flat menus with one shared grouping function.

**Non-Goals:**
- Any derived `cloud_low`, `cloud_middle` or `cloud_high` value (gate 2 open).
- Any registry change; `noaa-goes-east` is named as the closest record, not
  promoted or edited.
- Sampling satellite imagery into `/point`, or counting it in `/timeline`.
- Changing the fixture product path, the selection badge or the reason text.
- Changing `ingest/adapters/awc.py` or `ingest/meteorology.py`.

## Decisions

**Observations are retained by registry category, not by name.** The live
product path returns `product_fields + observation_fields`, where an observation
field is one whose source is not the product's and whose registry `category` is
in `OBSERVATION_CATEGORIES = {surface_observation, marine_observation,
optional_observation, radar, satellite}`. A model source such as `eccc-rdps`
(`deterministic_forecast`) stays excluded, so the product header still means
"this model's numbers". Each field already carries its own `source_id`, so a
METAR visibility under an HRDPS header is labelled `awc-metar-speci` and the
reader is never shown a borrowed value. A notice lists the observation sources
shown alongside. Alternative considered: a hard-coded allowlist of source ids.
Rejected because the registry already states the category and a list would
drift. The "nothing published for this product" branch is deliberately left
unchanged: the reader asked about the product, and answering with observations
alone would misstate what was found.

**The band filter is a view filter and says so.** Low / Middle / High are three
client-side toggles over the already-returned `cloud_layer_{n}_base` in metres,
using 1,981.2 m and 6,096 m as boundaries (6,500 ft and 20,000 ft, FAA AC 00-6B
/ NAV CANADA convention). It hides layers; it never counts, sums, buckets or
labels them, and the API is untouched. A layer with no base in metres cannot be
placed in a band, so it is never hidden and is labelled "base Unknown — not
filterable". The metric detail states "N of M reported layers shown · view
filter, not a classification" whenever a band is off. "Cloud L / M / H" stays
Unknown. This is the owner's chosen answer to gate 2, which remains open: a
filter over reported values is not a derivation.

**Satellite layers reuse `ForecastLayerSpec` and declare what they are.** A new
tuple `SATELLITE_LAYERS` is iterated wherever `FORECAST_LAYERS` is
(`_FORECAST_BY_ID`, `forecast_spec`, `_proxied_forecast_layers`,
`_resolve_imagery`, legend). `ForecastLayerSpec` gains `group: str | None =
None` and `legend: bool = True`; both defaults keep the 13 existing specs
byte-identical. `Layer.group` gains `"satellite"`. `SATELLITE_SEMANTICS` states:
observed imagery relayed by ECCC GeoMet from NOAA GOES-East; frames exist only
for the past; it is never forecast; display evidence only; not sampled by
`/point`; closest registry record `noaa-goes-east`. `X-Weather-Time-Semantics`
on `/raster` for these specs reads "observed at the instant in
X-Weather-Valid-Time". Alternative considered: a separate observation-layer
mechanism. Rejected because the existing one already does time-extent snapping,
tolerance, budget and caching correctly for a past-only extent; only the words
need to change.

**A resolution bracket is not a unit.** A trailing bracket matching
`^\d+(\.\d+)?\s*(km|m)$` after the unit position is a pixel resolution.
`parse_title_units` returns `(None, None, False)` for it and a new
`parse_title_resolution(title) -> str | None` exposes it. Units must come from
the provider, and the provider declared none, so `forecast_coverage` publishes
`units="unknown"` and the resolution goes into a notice
`"{layer_id}: ECCC advertises {resolution} pixel resolution"`. Publishing
`units="image"` was considered and rejected: it is a label the adapter would be
inventing. Existing `[m]` behaviour is tested unchanged.

**Legend availability reflects a probe.** Satellite layers may answer
`GetLegendGraphic` with 4xx or a non-image. `legend_available` is set from the
spec's `legend` flag, which Agent A sets from one polite probe per layer, rather
than the unconditional `True` at `app.py:~370`. A legend link that 502s is a
control that appears to do something and does not.

**The budget is raised by one batch.** `MAX_UPSTREAM_CALLS_PER_REQUEST` goes
from 16 to 32. 17 proxies on a cold cache fit with headroom for roughly one
more batch; capabilities are cached 300 s so only cold requests pay. The
alternative, leaving 16 and dropping a WEonG layer, was rejected as an
unrequested regression. `test_wms_proxy.py` pins `17 <= budget`.

**One grouping function, shared.** `layerGroup()` moves from `MapPanel.tsx` to
`api.ts` with `LAYER_GROUP_ORDER` and `LAYER_GROUP_LABELS`. Order: satellite,
observation, alert, forecast_proxy, published_model, observed evidence first
because it is the part that cannot be forecast. The drawer and the coverage rows
use it; nothing else new does. A layer with no `group` falls back as today. The
model row groups by `source.producer` with BLEND first and ungrouped; the
station select uses `<optgroup>` for "Live ingested source" / "No ingested
source (place to query)" from `stationCoverage(...).state`. Disabled and empty
states are unchanged.

## Risks / Trade-offs

**A grouped satellite row at a forward hour reads "no frame here".** That is
correct, every frame is in the past, and the group heading line "observed
imagery: frames exist only for the past" says why. The drawer already offers a
jump to the nearest (past) frame.

**A cold request now makes up to 17 upstream calls.** Mitigated by the 300 s
capability cache and the per-process rolling budget, which is unchanged.

**`cloud-and-fog-evidence` still says sixteen.** Its delta scenarios "Capabilities
cannot be read for a WEonG layer" and "The budget is nearly full" state the
ceiling as 16 and thirteen proxies. Those were true when written and are not
edited here; this change's modified budget requirement supersedes the number
once both are archived. That change's `tasks.md` gate 4.2 is not ticked.

**The band boundaries are a convention, not a measurement.** They are printed
on the buttons so the reader sees exactly which reported bases are hidden, and
all-on is the full list.
