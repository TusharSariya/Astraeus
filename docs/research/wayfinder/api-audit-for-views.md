Non-normative research, 2026-09-03. Not a spec, not a design.

# Live API audit against the five views

Answers wayfinder ticket
[#43](https://github.com/TusharSariya/Astraeus/issues/43) (child of the
wayfinder map [#38](https://github.com/TusharSariya/Astraeus/issues/38)):
what each route of the live experiment API returns, at one instant or as a
series, how it names and groups layers, what provenance travels, and which
gaps the five views (Map, Series, Sky, Activity, Sources) would hit.

Every shape below is a real response from
`http://localhost:8000/api/experiments/weather/v0` on 2026-09-03 between
15:00 and 15:25 UTC, trimmed. The running stack's `openapi.json` was used as
the route list; the code under
`experiments/st-johns-weather-map/api/weather_api/app.py` was read only to
name the query parameters and the selection modes. Where the live response
and the worktree code disagree, the response wins. Terms follow
`CONTEXT.md` (Source, Field, Field family, Frame, Evidence class, Horizon
tier, Site) and the map's own vocabulary (Focus: the shared point and instant
every view reads; View: one of the five; Layer stack: the ordered set of
layers drawn on Map; Verdict: a scored activity read from the decision
layer).

---

## 1. Summary

| Route | Instant or series | Names and groups | Provenance carried |
| --- | --- | --- | --- |
| `GET /catalog` | neither; registry snapshot | 118 sources, 30 `category` values, per-source `fields[]` with `family` (28 sources have them) | licence, attribution, `delivery_kind`, `intermediary`, `display_primary`, `state` |
| `GET /timeline` | series: 361 hourly items, 15 days | per item `available_products[]` (source ids) and `coverage[]` (source runs) | `run_time`, `run_age_seconds`, `run_stale`, `run_stale_reason` per coverage entry |
| `GET /layers` | catalogue of 35 layers, each with a `times[]` and `frames[]` series | `id`, `title`, `kind`, `group`, `field`, `product`, `evidence_basis` | `run_*` per layer and per frame (all null today), `upstream_wms_layer`, `semantics` |
| `GET /layers/{id}/features` | one instant | GeoJSON, per-feature `properties` keyed by field key | `layer_id`, `source_id`, `product`, `valid_time`, `run_time`, `<key>_units` |
| `GET /layers/{id}/raster` | one instant, PNG | n/a | 18 to 24 `X-Weather-*` response headers |
| `GET /layers/{id}/flow` | one frame pair, PNG | n/a | `X-Weather-*` headers incl. method, derivation, version |
| `GET /layers/{id}/legend` | not time-indexed, PNG | n/a | `X-Weather-*` headers incl. legend basis |
| `GET /point` | one instant, one point | 54 fields, each with `key`, `family`, `absence_state`, `blocked` | full 42-key provenance object per field, plus `comparability[]` |
| `GET /astronomy` | one instant for altitudes, 15-day series for bands and windows | fixed keys | one provenance object for the whole response |
| `GET /space-weather` | series (Kp readings) plus one latest solar-wind sample | fixed keys | `source_id`, `product`, `freshness` per block |
| `GET /profile` | one instant, one point, five pressure levels | fixed keys | same 42-key provenance per field |
| `GET /sources/status` | now | 118 statuses by `source_id` | `state`, `data_mode`, `last_retrieval`, `freshness`, `detail` |
| `GET /methods` | now | 6 interpolation methods with per-layer `scores[]` | `derivation_version`, `applied`, `reduced_to_default` |
| `POST /cross-section` | n/a | requires `path[]` of objects; 501 once the body validates | n/a |

Routes probed and absent (404): `/cameras`, `/sites`, `/profiles`,
`/verdict`, `/verdicts`, `/activities`, `/scores`. There is no scoring
route, no site or camera route, and no route that returns a time series of
values at a point.

---

## 2. Response shapes, route by route

Every JSON envelope carries `data_mode` (`live`, `unavailable` or `mixed`)
and `operational: false`. Most carry a `notices: string[]`.

### 2.1 `GET /catalog`

Registry snapshot: `{experimental, data_mode, operational, generated_at,
sources: [118]}`. One source, trimmed:

```json
{"id": "eccc-hrdps", "category": "deterministic_forecast",
 "producer": "Environment and Climate Change Canada", "product": "HRDPS raw",
 "state": "implemented-unverified", "status_reason": "...", "role": "...",
 "delivery_kind": "published_cell", "intermediary": null,
 "display_primary": true, "may_enter_consensus": true,
 "fields": [{"key": "total_cloud_opacity", "family": "cloud_cover",
             "storage": "stored", "upstream": "HRDPS.CONTINENTAL_NT",
             "note": "Title verified 'Total cloud cover [%]'. ..."}],
 "exact_variables": ["air_temperature", "..."], "levels": ["surface", "..."],
 "cadence": "4 runs/day; product-dependent hourly output",
 "forecast_horizon": "approximately 48 h; use only +24 h in this POC",
 "licence": "MSC Open Data licence", "attribution": "...",
 "freshness_threshold_seconds": 43200, "documentation_url": "...",
 "access_endpoint": "...", "schedulable": true,
 "fixture_status": "passing", "live_smoke_status": "planned"}
```

Facts: 118 sources; `state` counts are catalogued 62, implemented-unverified
20, credential-required 10, rejected 9, unavailable 9, partnership-only 4,
link-only 3, superseded 1. `delivery_kind` is `published_cell` 92,
`reprocessed` 25, `intermediary_derived` 1. 28 sources declare `fields[]`;
their `family` values are cloud_cover, humidity, wind, temperature, marine,
pressure, space_weather, precipitation, astronomy_geometry, air_quality,
cloud_geometry, boundary_layer, radiation, lightning, terrain, seeing,
transparency, hazard, vertical_motion. `category` has 30 distinct values
(space_weather 17, deterministic_forecast 15, air_quality 13, analysis 8,
ensemble 6, astronomy 6, camera 4, ...). The six ensemble sources are
eccc-reps, eccc-geps, ecmwf-ens, ecmwf-aifs-ens, noaa-gefs, dwd-icon-eps;
none has a live retrieval (section 2.12).

### 2.2 `GET /timeline`

Series. `{data_mode, operational, start, end, boundary, tiers: [2],
items: [361], notices}`. Tiers: `core` 2026-09-02T15:00Z to
2026-09-04T15:00Z, `planning` to 2026-09-17T15:00Z. One hourly item:

```json
{"valid_time_utc": "2026-09-03T02:00:00Z",
 "valid_time_newfoundland": "2026-09-02T23:30:00-02:30",
 "available_products": ["awc-metar-speci", "eccc-cap-alerts", "eccc-hrdps",
                        "eccc-lightning", "eccc-radar", "eccc-rdps",
                        "noaa-gfs", "noaa-swpc-rtsw"],
 "aged_out_sources": {}, "tier": "core",
 "coverage": [{"source_id": "eccc-aqhi",
               "provider_run_id": "eccc-aqhi-20260903T010000Z",
               "run_time": "2026-09-03T01:00:00Z", "run_cadence_seconds": null,
               "run_age_seconds": 50400, "run_stale": null,
               "run_stale_reason": "the source declares no run cadence, ..."}],
 "coverage_notice": null}
```

Facts: `available_products` holds source ids, not product or layer ids, and
names a source at an instant it has a frame for. `coverage[]` is populated on
2 of 361 items (01:00Z and 02:00Z on 2026-09-03, for eccc-aqhi and
eccc-lightning only); the other 359 carry `coverage_notice: "nothing covers
this instant"` even where `available_products` lists eight sources. The two
arrays therefore disagree about what "covers" means and neither is per layer.
`aged_out_sources` is `{}` on every item.

### 2.3 `GET /layers`

Catalogue with an embedded series per layer. `{data_mode, operational,
layers: [35], notices: [17], aged_out_sources: {}}`. Layer keys, all 35 the
same: `id, title, kind, field, product, units, semantics, times[],
cadence_seconds, staleness_tolerance_seconds, default_opacity, z_index,
evidence_basis, group, raster_available, legend_available,
upstream_wms_layer, upstream_endpoint, run_time, run_stale,
run_stale_reason, run_cadence_seconds, frames[], runs[]`. A frame is
`{valid_time, run_time, provider_run_id, run_stale}`; today every frame has
`run_time: null`, `provider_run_id: null`, and every `runs[]` is empty, on all
35 layers including the published-artifact grids.

How layers are named and grouped (live):

| `group` | `kind` | `evidence_basis` | Count | Example `id` / `title` |
| --- | --- | --- | --- | --- |
| satellite | raster | live_proxy | 4 | `geomet-live-goes-east-nightir-2km` / "GOES-East night IR (2 km, live proxy)" |
| forecast_proxy | raster | live_proxy | 13 | `geomet-live-hrdps-nt` / "HRDPS total cloud (live proxy)" |
| published_model | raster | published_artifact | 5 | `eccc-hrdps-surface` / "ECCC-HRDPS surface (published grid)" |
| rendered_grid | raster | published_artifact | 7 | `eccc-hrdps-surface-total-cloud` / "ECCC-HRDPS total cloud cover (opacity-weighted) (rendered grid)" |
| alert | alert | published_artifact | 1 | `eccc-cap-alerts-alerts_features` |
| alert | point | published_artifact | 1 | `eccc-cap-alerts-alerts` |
| observation | point | published_artifact | 5 | `awc-metar-speci-surface` / "CYYT METAR/SPECI surface (sampled points)" |

`group` is a delivery-mechanism grouping (how the image is made), not a
field-family grouping. `field` is a single string per layer and is a field
key for rendered grids and live proxies (`total_cloud_opacity`,
`relative_humidity`, `visibility_through_liquid_fog`), but a bundle name for
published-model and point layers (`surface`, `upper_air`, `aqhi`, `radar`,
`alerts`). No layer carries a `family`. `title` is a sentence; the longest
(the two WEonG low-cloud layers) runs to 280 characters and repeats the
product name twice, and `product` on those two layers is the full sentence
"ECCC-HRDPS low cloud, WEonG repair (derived, generated, display only)"
rather than a product name. Two of the 13 forecast proxies carry a leading
"[experimental]" in the title. `units` is `"unknown"` on every live proxy.

`times[]` length: 144 to 145 on satellite proxies (10-minute cadence over
24 h), 48 to 84 on forecast proxies, 20 on HRDPS and RDPS artifacts, 27 on
GFS, 1 to 30 on point and alert layers. `raster_available` and
`legend_available` are true on the 24 raster layers and false on the 11
point, alert and published-model layers.

Notices (17) are strings such as "noaa-goes19-cloud-mask: the newest stored
scan is 47406 s old, beyond the 600 s staleness tolerance; the layer is
unavailable" and "noaa-swpc-kp-kp_observed (application/zarr+zip) has no map
representation this API can vouch for". They are not attached to a layer id
in a structured way.

### 2.4 `GET /layers/{id}/features?valid_time=`

One instant, GeoJSON. `{type: "FeatureCollection", data_mode, operational,
features[], notices[]}`. `valid_time` defaults to the focus instant of the
service (15:00Z at call time), and a point layer with no frame there
returns `features: []`, `data_mode: "unavailable"` and the notice
"`<layer>` publishes no stored value at `<instant>`; nothing has been
substituted". At a declared time, METAR:

```json
{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-52.7519, 47.6186]},
 "properties": {"temperature_2m": 7.0, "temperature_2m_units": "degC",
   "relative_humidity_2m": 81.2, "relative_humidity_2m_units": "percent",
   "visibility": 24140.16, "visibility_units": "m",
   "total_cloud_okta": 0.0, "total_cloud_okta_units": "percent",
   "wind_u_10m": 1.18, "wind_v_10m": -0.99, "dew_point_2m": 4.0,
   "mean_sea_level_pressure": 1025.1,
   "layer_id": "awc-metar-speci-surface", "source_id": "awc-metar-speci",
   "valid_time": "2026-09-03T02:00:00+00:00", "product": "CYYT METAR/SPECI",
   "run_time": "2026-09-03T02:00:00+00:00"}}
```

Radar and lightning layers return one feature at the default focus point
with `radar_echo: null` / `lightning_observed: null` and units `"flag"`. The
CAP alert layer returned `features: []` even at its own declared time. A
`valid_time` outside the 15-day window is a 422 with a sentence explaining
the two tiers. No evidence class, quality, freshness or licence travels on
a feature; only `source_id`, `product`, `valid_time`, `run_time`.

### 2.5 `GET /layers/{id}/raster`

One instant, `image/png`, `cache-control: public, max-age=60`. Provenance
is entirely in response headers. Rendered grid (trimmed):

```
x-weather-layer-id: eccc-hrdps-surface-total-cloud
x-weather-evidence-basis: published_artifact
x-weather-image-basis: rendered_grid
x-weather-retrieval-status: retrieved
x-weather-render-semantics: each pixel is the stored value of the nearest published cell centre ... a transparent pixel means no stored cell or no stored value there, or a stored cover of 0 percent
x-weather-sample-method: curvilinear_nearest_cell
x-weather-colormap: cloud cover percent -> white ... colormap-version grid-cloud-alpha-v1
x-weather-derivation-version: rendered-grid-nearest-cell-v1
x-weather-source-id: eccc-hrdps
x-weather-product: ECCC-HRDPS
x-weather-units: percent
x-weather-valid-time: 2026-09-03T15:00:00+00:00
x-weather-reference-time: 2026-09-02T18:00:00+00:00
x-weather-licence: MSC Open Data licence
x-weather-attribution: Credit Environment and Climate Change Canada; ...
```

Live proxy adds `x-weather-wms-layer`, `x-weather-upstream-url` (the full
GeoMet GetMap URL with `TIME` and `DIM_REFERENCE_TIME`), and carries no
`source-id`, `product`, `units`, `colormap` or `derivation`. The reference
time on the raster header (`2026-09-02T18:00Z` for the HRDPS artifact,
`2026-09-03T06:00Z` for the HRDPS live proxy) is the only place a run time
is exposed for a frame, since `/layers` frames carry null. Published-model
and point layers return 501 with a JSON `detail` sentence.

### 2.6 `GET /layers/{id}/flow?from=&to=`

One frame pair, `image/png`, rendered-grid layers only (a live proxy returns
404 "derived motion exists only for rendered-grid layers"). Headers add
`x-weather-image-basis: derived_motion`, `x-weather-flow-texture`,
`x-weather-interpolation-method` (one of the six `/methods` ids; any other
value is 422), `x-weather-flow-shader`, `x-weather-flow-scale`,
`x-weather-frame-from`, `x-weather-frame-to`, and a
`x-weather-derivation` sentence of about 2,000 characters with
`x-weather-derivation-version: cloud-motion-bench-v6`. `render-semantics`
says explicitly "this is a display derivation ... not provider output, not
evidence".

### 2.7 `GET /layers/{id}/legend`

Not time-indexed. Rendered grid: a 256 x 24 PNG ramp with
`x-weather-legend-basis: renderer_colormap`, the colormap sentence and a
`legend-semantics` sentence ("presentation, not provider data"). Live proxy:
the upstream GetLegendGraphic (111 x 418 PNG) with
`x-weather-time-semantics: current image, not time-indexed`. Point and
published-model layers: 501. There is no structured legend (no stops, no
labels, no units in a machine form); a view that wants to draw its own
legend or a colour-vision-safe alternative has only the PNG and the sentence.

### 2.8 `GET /point`

One instant, one point. Query: `latitude`, `longitude`, `valid_time`,
`product`, `hrdps_fresh`, `rdps_fresh`, `consensus_evidence`, `member`,
`statistic`, `quantile`, `threshold`, `comparison`. Envelope:
`{data_mode, operational, latitude, longitude, valid_time, selection,
fields: [54], notices, comparability: [180]}`.

```json
"selection": {"mode": "fallback", "selected_source_id": "eccc-hrdps",
  "selected_product_id": "hrdps",
  "badge": "HRDPS primary - consensus unavailable",
  "reason": "minimum consensus evidence not met"}
```

One field with a value (trimmed provenance):

```json
{"field": "wind_speed", "value": 3.0, "key": "wind_speed_10m",
 "family": "wind", "phase": null, "storage": "stored",
 "absence_state": null, "blocked": null, "comparability": null,
 "provenance": {"evidence_class": "derived_here", "source_id": "eccc-hrdps",
   "provider": "...", "product": "HRDPS raw", "run_time": "2026-09-02T18:00:00Z",
   "valid_time": "2026-09-03T15:00:00Z", "retrieval_time": "...",
   "member": null, "member_control": null, "vertical_level": "...",
   "original_units": "m s-1", "normalized_units": "m s-1",
   "quality": {"status": "passed", "flags": []},
   "coverage": {"status": "complete", "fraction": 1.0},
   "freshness": {"status": "stale", "age_seconds": 48419, "threshold_seconds": 43200},
   "licence": "MSC Open Data licence", "attribution": "...",
   "derivation": "wind_speed_and_direction_from_components",
   "derivation_version": "...", "derivation_citation": "...",
   "derivation_inputs": [{"field": "wind_u_10m", "source_id": "eccc-hrdps",
       "product": "HRDPS raw", "valid_time": "...", "units": "m s-1",
       "evidence_class": "retrieved", "quality": {"status": "passed", "flags": []},
       "run_time": "2026-09-02T18:00:00Z"}, {"field": "wind_v_10m", "...": "..."}],
   "delivery_kind": "...", "source_display_primary": "...", "intermediary": null,
   "intermediary_method": null, "sampled_latitude": "...", "sample_distance_km": "...",
   "sample_method": "...", "contributing_evidence": [], "contributors": [],
   "last_valid_time": "...", "run_stale": "...", "run_stale_reason": "..."}}
```

Facts at the default focus (47.5615 N, 52.7126 W, 2026-09-03T15:00Z): 54
field entries, 30 with a value, 24 with `absence_state: "null"` and
`value: null`. `blocked` was null on every entry. The same field name recurs
per source: `temperature` appears three times (eccc-hrdps, eccc-rdps,
noaa-gfs), so the list is already "one value per source per field" at one
instant, keyed by `(field, provenance.source_id)`. Evidence classes seen:
`retrieved` and `derived_here`. Every valued entry's `freshness.status` is
`stale` (run 18:00Z the day before, threshold 43,200 s). All 24 null entries
come from `awc-taf`, whose artifact is skipped with the notice "provenance
could not be modelled: awc-taf/surface declares no evidence_classes"; their
provenance is filled with the literal string `"unavailable"` and a
`product` that is a UUID. `comparability[]` is 180 pairs
`{family, a, b, comparable, reason, detail}` covering every pair of keys
within a family.

`product=rdps` switches selection to `{"badge": "RDPS selected model",
"mode": "fallback"}` and returns only that source's 7 entries.
`product=reps` returns `data_mode: "unavailable"` and
`mode: "evidence_only"`; `product=gefs` and `product=noaa-gefs` are 422
"unknown product". `member=all` and `statistic=ensemble_mean` are accepted
on the default product and change nothing in the response (no member
entries, no notice). A `valid_time` in the planning tier
(2026-09-08T12:00Z) returns `mode: "evidence_only"`, `badge: "evidence
unavailable"` and zero valued fields, although `/timeline` lists `noaa-gfs`
in `available_products` for 27 instants and `/layers` gives GFS 27 frames.

### 2.9 `GET /astronomy`

Mixed: `sun_altitude_deg`, `moon_altitude_deg`, `core_altitude_deg` are for
one `valid_time`; `twilight_bands[121]`, `moon.above_horizon[15]` and
`milky_way_core.windows[15]` are `{kind, start, end}` intervals over the
15-day window. `moon` adds `rise`, `set`, `phase_deg`,
`illuminated_fraction`; `milky_way_core` adds `max_altitude_deg` and a
`caption` ("Geometry only - says nothing about cloud, transparency, or light
pollution"). One provenance block for the whole response:
`{source_id: "nasa-jpl-de442", kernel_id, kernel_sha256, derivation,
derivation_version: "astronomy-de442-v1", operational}`. No evidence class
field, no site horizon, no per-value provenance.

### 2.10 `GET /space-weather`

`{data_mode, operational, generated_at, kp_observed, kp_forecast,
solar_wind, notices}`. `kp_observed` and `kp_forecast` are
`{available, source_id, product, readings: [{time, value, status}],
freshness, notices}`; observed has 56 readings from 2026-08-27, forecast 81
with `status: "observed"` on the past ones. `solar_wind` is one sample
`{bz_gsm_nt, bt_nt, measured_at, feed_declared_spacecraft, freshness,
notices}`. All three blocks were `freshness.status: "stale"` (Kp 66,027 s
against 21,600; Bz 47,127 s against 900). No latitude, no evidence class,
no OVATION aurora oval although `noaa-swpc-ovation` has a live retrieval.

### 2.11 `GET /profile`

One instant, one point, `levels: [{pressure_hpa, fields: [temperature,
relative_humidity, wind_speed]}]` at 1000, 850, 700, 500, 300 hPa, each
field with the same 42-key provenance as `/point`. Every value was null
with the notice "no published artifact carries a pressure-level profile
here", although `/point` served `wind_speed_200hPa` and `wind_speed_300hPa`
from noaa-gfs at the same focus.

### 2.12 `GET /sources/status`

`{data_mode: "mixed", operational, statuses: [118], notices}`; each
`{source_id, state, data_mode, operational, last_retrieval, freshness:
{status, age_seconds, threshold_seconds}, detail}`. 14 sources have a
`last_retrieval` (eccc-hrdps, eccc-rdps, eccc-swob, eccc-radar,
eccc-lightning, eccc-cap-alerts, eccc-aqhi, noaa-gfs, noaa-goes-east,
noaa-swpc-kp, noaa-swpc-rtsw, noaa-swpc-ovation, awc-metar-speci, awc-taf)
and all 14 were `stale`; the other 104 are `data_mode: "unavailable"`,
`freshness.status: "unknown"`, with `detail` beginning "no live retrieval
recorded; " followed by the catalogue `status_reason`. No count of
artifacts, no last run time, no per-layer link, no fixture or smoke status
(those are on `/catalog`).

### 2.13 `GET /methods`

`{data_mode, operational, default_method: "baseline", methods: [6],
notices}`. Each method: `id, title, summary, shader, enabled, generative,
plain, gap, notes, generation_disabled, published, requirements: [{name,
met, detail, diagnostic}], scores: [8]`. A score row names
`layer_id`, `source_id`, `variable`, `held_out_frames`, four
`improvement_over_*` numbers, midpoint MAE, SSIM, sharpness and spectral
ratios, `derivation_version: "cloud-motion-bench-v6"`, `applied`,
`reduced_to_default`. Only `residual-generative` is `generative: true`;
`goes-transfer` has an unmet requirement ("the published cloud-mask artifact
carries 1 scan").

### 2.14 `POST /cross-section`, `/health`, `/ready`, `/refresh`, `/jobs`

`/cross-section` validates a body `{path: [{...}]}` before reaching the 501;
an empty body and a list-of-pairs body are both 422. `/ready` reports
`checks: {data_mode_configured, registry_catalog, job_store, live_store,
evidence_boundary}` all true. `/refresh` and `/jobs/{id}` are the ingestion
job hooks and carry nothing a view reads.

---

## 3. Gaps per view

What exists is stated against the live response; what is missing is the
thing a view would need and cannot get from any route today.

### 3.1 Map (layer stack, compare, on-map disclosure)

- **Short display title per layer: missing.** `/layers.title` is the only
  name and is a sentence of 30 to 280 characters. There is no short name,
  abbreviation, or separate source label; the product name is inside the
  sentence. The two WEonG layers put the disclosure text into `product`.
- **Family grouping per layer: missing.** `/layers` has `group` (delivery
  mechanism: satellite, forecast_proxy, published_model, rendered_grid,
  observation, alert) and `field` (a key or a bundle name), but no `family`.
  The `family` exists only in `/catalog.sources[].fields[].family` and in
  `/point.fields[].family`; joining a layer to a family requires matching
  `layer.field` to a catalogue field `key`, which works for rendered grids
  and live proxies (`total_cloud_opacity`, `relative_humidity`) and fails
  for bundle layers (`surface`, `upper_air`, `aqhi`, `radar`).
- **Same field from several sources (swipe, side by side): partially
  exists.** Total cloud exists as three rendered grids (HRDPS, RDPS, no GFS
  total) plus a live HRDPS proxy; low, middle, high cloud exist only for
  GFS. Matching is by `field` string equality; no route lists "layers for
  this family".
- **Run and run-stale across a stack: missing in `/layers`.** All 35
  layers have `run_time: null`, `runs: []`, and every frame has
  `run_time: null` and `provider_run_id: null`. The only run time a Map can
  show is the raster's `x-weather-reference-time` header, which is per
  image and arrives after the tile is fetched. `/timeline.coverage` carries
  `run_time` and `run_stale` but only on 2 of 361 instants.
- **Coverage per instant per layer: missing.** `/layers.times[]` says a
  frame exists; `/timeline.available_products` says a source has something;
  neither says a layer has a frame at an instant with a stale or fresh run.
- **Provenance beside every pixel: exists as headers only.** Evidence basis,
  colormap, derivation version, licence and attribution are response headers
  on `/raster`, `/flow` and `/legend`; a view must read them off each fetch.
  There is no evidence class enum on a raster (`evidence_basis` is
  `live_proxy` or `published_artifact`, `image_basis` is `rendered_grid`,
  `live_proxy` or `derived_motion`), so the six evidence classes of
  `CONTEXT.md` are not directly on the image contract.
- **Legend: PNG only.** No stops, labels or units in machine form.
- **Structured notices: missing.** `/layers.notices[]` are free strings that
  name a layer in their first token.
- **Point layers at the focus instant: mostly absent.** METAR has 3 frames,
  radar 30, lightning 17, but at 15:00Z every point and alert layer returned
  an empty collection.

### 3.2 Series (time series at a point across sources, ensembles)

- **A time series at a point: missing.** `/point` is one instant. The only
  series routes are `/timeline` (source availability, no values),
  `/space-weather` (Kp readings) and `/astronomy` (intervals). Building a
  24 h series of one field across three sources means 24 `/point` calls of
  205 KB each (54 fields with full provenance).
- **Across sources at one instant: exists.** `/point.fields[]` already
  holds the same field from eccc-hrdps, eccc-rdps and noaa-gfs side by side,
  with `family`, `key` and `comparability[]` to say which are comparable.
- **Ensemble members as series: missing.** No ensemble source has a live
  retrieval; `member`, `statistic`, `quantile`, `threshold`, `comparison`
  are accepted and inert on the default product, `product=reps` returns
  evidence_only, `product=gefs` is 422. Provenance has `member` and
  `member_control` slots, always null.
- **Planning tier at a point: missing.** `/point` at a planning-tier instant
  returned no values although GFS frames exist there in `/layers`.
- **Pressure-level series: missing.** `/profile` returned all nulls while
  `/point` served 200 and 300 hPa GFS winds.
- **Observations at the focus: absent at most instants.** METAR values exist
  in `/features` at 02:00Z but `/point` at 15:00Z has no observation entry.

### 3.3 Sky (astronomy, camera, transparency, aurora)

- **Sun, moon, core geometry: exists**, one instant plus 15-day intervals,
  one provenance block for all of it.
- **Site horizon and camera geometry: missing.** No `/sites`, no
  `/cameras`; `/astronomy` takes only latitude and longitude. The four
  camera sources are catalogued only (state `catalogued`, no retrieval).
- **Transparency and seeing: missing.** The `transparency` and `seeing`
  families exist in `/catalog` (one source each) with no live retrieval and
  no layer.
- **Aurora: missing.** `noaa-swpc-ovation` has a live retrieval in
  `/sources/status` but no layer (`/layers` notice: no map representation)
  and no block in `/space-weather`. Kp and Bz exist, all stale.
- **Cloud at the focus instant for the night: same gap as Series** (one
  instant per call).

### 3.4 Activity (verdicts, next windows, phone brief)

- **Verdicts: missing.** No scoring route exists (`/verdict`, `/verdicts`,
  `/activities`, `/scores` are 404). The map issue records this as in
  scope; nothing in the live API returns a score, a window, or a per-field
  contribution.
- **Activity profiles: missing from the API.** The four profile files are
  registered in the repo but no route lists them, their families, thresholds
  or windows.
- **Family membership for scoring: partial.** `/point.family` and
  `/point.comparability` give the decision layer its family view at one
  instant; there is no route giving a family's members over time.
- **Blocked state: exists as a slot.** `/point.fields[].blocked` is present
  and was null on every entry; `absence_state` was `"null"` on the TAF
  entries. No `aged_out` or `blocked` value was observed live.
- **Next windows: only the astronomical ones.** `/astronomy` gives dark and
  core windows; nothing gives cloud, wind or fog windows.

### 3.5 Sources (registry, freshness, admissions)

- **Registry and status: exist**, split across two routes: `/catalog`
  (118 sources with licence, attribution, cadence, fixture and smoke status)
  and `/sources/status` (14 live, 104 unavailable, freshness). A Sources
  view joins them by `source_id`.
- **Source to layer link: missing.** `/layers` has no `source_id` field; the
  raster header `x-weather-source-id` has it, and `/features` properties
  carry it. Live proxies carry no `source_id` anywhere.
- **Per-source run history: missing.** `last_retrieval` is a single
  timestamp; no artifact count, no run list, no previous run.
- **Evidence class per source: not stated.** `/catalog` has `delivery_kind`
  and `intermediary`; the evidence class appears only on `/point` values.
- **Verdict on why a source is unavailable: exists as text** in
  `status_reason` and the `detail` sentence.

### 3.6 Cross-cutting

- **Focus is not a server concept.** Each route takes its own
  `latitude`, `longitude`, `valid_time`; `/space-weather` and
  `/sources/status` take none; `/layers` snaps to nothing. Nothing returns
  the server's notion of "now".
- **Stale everywhere.** At audit time every live source and every valued
  `/point` entry was `stale` (the newest HRDPS run was 21 h old); a view's
  first render will be dominated by the stale state.
- **Provenance is 42 keys per value.** A `/point` response is 205 KB for 54
  values; there is no summary form (class, source, run, freshness) and no
  way to ask for fewer fields.
- **`operational: false` and `data_mode` on every envelope** are the
  experiment flags a view must surface.
