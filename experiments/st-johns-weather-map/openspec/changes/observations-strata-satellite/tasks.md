Ownership is disjoint by agent; do not edit another agent's files. Nobody edits
`registry/`, `ingest/adapters/awc.py` or `ingest/meteorology.py`. Files under
`openspec/` belong to the spec agent only, and `openspec/changes/
cloud-and-fog-evidence/tasks.md` is not edited by anyone in this change.

## 1. Agent A: API

Owned: `api/weather_api/app.py`, `api/weather_api/store.py`,
`api/weather_api/wms.py`, `api/weather_api/models.py`,
`ingest/adapters/eccc_geomet.py` (title parser only), `api/tests/*`,
`docs/geomet-layers.md`.

- [ ] A1.1 `app.py`: add `OBSERVATION_CATEGORIES = frozenset({
      "surface_observation", "marine_observation", "optional_observation",
      "radar", "satellite"})` next to `OBSERVATION_FIELDS` (:106). Expose
      `source_category(source_id) -> str | None` in `store.py` over
      `_registry_config`. In `_live_point` (:504-524) build
      `product_fields = [f for f in fields if f.provenance.source_id == source_id]`
      and `observation_fields = [f for f in fields if f.provenance.source_id !=
      source_id and source_category(f.provenance.source_id) in
      OBSERVATION_CATEGORIES]`; return `fields=product_fields + observation_fields`.
      The "nothing for this product" branch is unchanged (still `unavailable`
      naming the source even when observations exist). Add the notice
      `"observations from {ids} are shown alongside {selected}; each carries its
      own source"`. Selection, badge and reason unchanged; fixture path untouched.
      Verify: `cd api && uv run pytest -q tests/test_api.py`
- [ ] A1.2 `api/tests/test_api.py`: extend
      `test_product_selection_never_claims_a_source_that_published_nothing` (:381)
      so a published METAR artifact's fields appear with `source_id
      awc-metar-speci` under `product=HRDPS` while HRDPS's own values stay exactly
      `[9.25]`; a model source (`eccc-rdps`) is still excluded; unknown product
      still 422; window-edge reason unchanged; the product-published-nothing
      branch is still `unavailable` with observations present.
      Verify: `cd api && uv run pytest -q tests/test_api.py`
- A2 (no task; removed by owner decision, nothing to tick): No cloud derivation. `store.py:51-55` and the
      `UNAVAILABLE_POINT_FIELDS` note stay as they are; `cloud_low`,
      `cloud_middle`, `cloud_high` remain unavailable. Gate 4.2 in
      `cloud-and-fog-evidence/tasks.md` stays open and is not ticked.
- [ ] A3.1 `models.py:225`: `Layer.group` Literal gains `"satellite"`. `wms.py`:
      `ForecastLayerSpec` gains `group: str | None = None` and `legend: bool =
      True` (defaults keep the 13 existing specs byte-identical);
      `app.layer_group()` returns the spec's group when set.
      Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py tests/test_api.py`
- [ ] A3.2 `wms.py`: `SATELLITE_SEMANTICS` (observed imagery relayed by ECCC
      GeoMet from NOAA GOES-East; frames exist only for the past; never
      forecast; display evidence only; not sampled by `/point`; closest registry
      record `noaa-goes-east`). `SATELLITE_LAYERS` = four specs, ids
      `geomet-live-goes-east-dayvis-nightir`, `-snowfog-nightmicro`,
      `-naturalcolor`, `-nightir-2km`; WMS layers `GOES-East_1km_DayVis-NightIR`,
      `GOES-East_1km_SnowFog-NightMicrophysics`, `GOES-East_1km_NaturalColor`,
      `GOES-East_2km_NightIR`; fields `satellite_day_visible_night_ir`,
      `satellite_snow_fog_night_microphysics`, `satellite_natural_color`,
      `satellite_night_ir`; titles "GOES-East day visible / night IR (1 km, live
      proxy)" and so on; `product="GOES-East"`, `group="satellite"`. Iterate
      `FORECAST_LAYERS + SATELLITE_LAYERS` in `_FORECAST_BY_ID`, `forecast_spec`,
      `_proxied_forecast_layers`, `_resolve_imagery` and the legend path.
      `MAX_UPSTREAM_CALLS_PER_REQUEST = 32`; update the docstring at :284 and the
      assertion at `test_wms_proxy.py:493` to `17 <= budget`.
      Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py`
- [ ] A3.3 `eccc_geomet.py` title parser: a trailing bracket matching
      `^\d+(\.\d+)?\s*(km|m)$` is a resolution, not a unit; `parse_title_units`
      returns `(None, None, False)` for it; add `parse_title_resolution(title)
      -> str | None`. `forecast_coverage` publishes `units="unknown"` for such a
      layer and a notice `"{layer_id}: ECCC advertises {resolution} pixel
      resolution"`. Existing `[m]` behaviour unchanged (test both).
      Verify: `cd api && uv run pytest -q tests/test_adapter_eccc_geomet.py tests/test_wms_proxy.py`
- [ ] A3.4 Time semantics: confirm `_proxied_forecast_layers` needs no change for
      an all-past extent; the window notice ("N of 289 frames fall inside this
      experiment's window") reads sensibly. `X-Weather-Time-Semantics` on
      `/raster` for satellite specs: "observed at the instant in
      X-Weather-Valid-Time".
      Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py`
- [ ] A3.5 Live probe, one polite call each, before and after: for each of the
      four WMS layers, `GetMap` over `46.5,-55,48.5,-51` at 400x200 for the
      latest advertised instant and for `now-2h`, expecting 200 image/png;
      record sizes. `GetLegendGraphic` per layer: if 4xx or non-image, set
      `legend=False` on that spec so `legend_available` is `False` rather than
      the unconditional `True` at `app.py:~370`. Record every result in
      `docs/geomet-layers.md`.
      Verify: `for L in GOES-East_1km_DayVis-NightIR GOES-East_1km_SnowFog-NightMicrophysics GOES-East_1km_NaturalColor GOES-East_2km_NightIR; do curl -sS -o /dev/null -w "$L GetMap %{http_code} %{content_type} %{size_download}B\n" "https://geo.weather.gc.ca/geomet/?service=WMS&version=1.3.0&request=GetMap&layers=$L&crs=EPSG:4326&bbox=46.5,-55.0,48.5,-51.0&width=400&height=200&format=image/png&transparent=true&time=$(date -u -v-2H +%Y-%m-%dT%H:00:00Z)"; curl -sS -o /dev/null -w "$L Legend %{http_code} %{content_type} %{size_download}B\n" "https://geo.weather.gc.ca/geomet/?service=WMS&version=1.3.0&request=GetLegendGraphic&layer=$L&format=image/png&sld_version=1.1.0"; done`
- [ ] A3.6 `docs/geomet-layers.md`: "GOES-East satellite (live proxies)" table
      with WMS names, titles, time dimension, probe results (status, type,
      bytes, legend outcome) and the resolution-bracket trap.
- [ ] A3.7 Tests in `api/tests/test_wms_proxy.py` and
      `api/tests/test_adapter_eccc_geomet.py`: four ids present with `group ==
      "satellite"`, `product == "GOES-East"`, semantics containing "observed" and
      "never forecast"; a `FakeCapability` with `PT10M` over 48 h yields only
      frames inside the window and every frame <= reference;
      `staleness_tolerance_seconds == 300`; a `[1 km]` bracket is not a unit and
      publishes `units == "unknown"` with the resolution notice; `[m]` still
      parses; the 13 original specs are unchanged; `legend_available` follows
      the spec's `legend` flag; live smoke extended with one satellite
      capability read and one `GetMap`.
      Verify: `cd api && uv run pytest -q tests/test_wms_proxy.py tests/test_adapter_eccc_geomet.py`
- [ ] A.8 Verify Agent A end to end:
      `cd api && uv run pytest -q`;
      `cd api && WEATHER_LIVE_SMOKE=1 uv run pytest -m live_smoke -q tests/test_adapter_eccc_geomet.py`;
      `docker compose up -d --build api`;
      `B=localhost:8000/api/experiments/weather/v0`;
      `curl -s "$B/point?latitude=47.5615&longitude=-52.7126&product=HRDPS" | jq -c '[.fields[]|{f:.field,s:.provenance.source_id}]'` (HRDPS fields plus `awc-metar-speci` fields, no `eccc-rdps`);
      `curl -s "$B/layers" | jq -c '.layers[]|select(.group=="satellite")|{id,product,units,n:(.times|length),first:.times[0],last:.times[-1],legend_available}'` (4 rows, all times <= now, units `unknown`);
      `curl -s -o /dev/null -w '%{http_code} %{content_type}\n' "$B/layers/geomet-live-goes-east-dayvis-nightir/raster?south=46.5&west=-55&north=48.5&east=-51&width=512&height=512&valid_time=$(date -u -v-1H +%Y-%m-%dT%H:00:00Z)"` (200 image/png);
      `make test`.

## 2. Agent B: web

Owned: `web/src/App.tsx`, `web/src/api.ts`, `web/src/MapPanel.tsx`,
`web/src/types.ts`, `web/src/styles.css`, `web/src/fixtures.ts`,
`web/src/*.test.ts`, `web/src/*.test.tsx`.

- [ ] B1 `api.ts`: move `layerGroup()` from `MapPanel.tsx:242` to `api.ts` as
      `export function layerGroup(layer)`; add `LAYER_GROUP_ORDER` (satellite,
      observation, alert, forecast_proxy, published_model) and
      `LAYER_GROUP_LABELS` (`satellite: "Satellite (observed, past only)"`,
      `forecast_proxy: "Forecast · live proxy"`, and the existing labels for the
      rest). `types.ts` `LayerItem.group` gains `'satellite'`. The drawer uses
      the shared function and order; behaviour otherwise unchanged and
      `MapPanel.test.tsx` strings preserved.
      Verify: `cd web && npm test -- --run && npx tsc -b --force`
- [ ] B2 `App.tsx:695-722` coverage rows: group `layers` with the shared helper;
      render `<section role="group" aria-labelledby>` plus `<h4>` per non-empty
      group with a count ("Satellite · 4 layers"); rows unchanged inside; under
      the satellite heading add the line "observed imagery: frames exist only
      for the past". Empty groups are not rendered.
      Verify: `cd web && npm test -- --run`
- [ ] B3 `App.tsx:464-503` model row: group `forecastSources` by
      `source.producer`; BLEND first and ungrouped; a `<span
      class="model-group-label">` before each producer's buttons; the strip stays
      one horizontally scrolling row (`flex: 0 0 auto` rules in
      `styles.css:66-79` kept). Button semantics and `coverageOf` unchanged.
      Verify: `cd web && npm test -- --run`
- [ ] B4 `App.tsx:103-106, 357` station select: `Select` option gains optional
      `group?: string`; render `<optgroup label>` for "Live ingested source" /
      "No ingested source (place to query)" from `stationCoverage(...).state`.
      Disabled and empty states unchanged.
      Verify: `cd web && npm test -- --run`
- [ ] B5 `App.tsx` (~:604) cloud band filter: local state `cloudBands: {low,
      middle, high}` all `true`; a `role="group" aria-label="Cloud layer bands"`
      of three `aria-pressed` buttons labelled `Low · <6,500 ft`, `Middle ·
      6,500–20,000 ft`, `High · ≥20,000 ft`. Pure `filterCloudLayers(layers,
      bands)` in `api.ts` (band from `baseM` with 1981.2 m / 6096 m; `baseM ===
      null` is always kept). Metric value = filtered `cloudLayersText`; detail
      `"${shown} of ${total} reported layers shown · view filter, not a
      classification"` when any band is off, else the existing detail.
      Unfilterable layers render as `"<code> · base Unknown — not filterable"`.
      "Cloud L / M / H" (`App.tsx:608-618`) unchanged and still Unknown.
      `evidenceRows` unchanged.
      Verify: `cd web && npm test -- --run && npm run build`
- [ ] B6 Observations under a selected model: no web change expected;
      `pickField` prefers `selected_source_id` and falls back to the first field,
      and every metric shows its source tag. Assert in `App.test.tsx` with a
      `product` response carrying HRDPS temperature plus METAR visibility that
      the visibility metric is tagged `awc-metar-speci` under the HRDPS header.
      Verify: `cd web && npm test -- --run`
- [ ] B7 Tests (`App.test.tsx`, `MapPanel.test.tsx`, `api.test.ts`): coverage
      rows render group headings in order with satellite rows under "Satellite";
      model row shows producer labels with BLEND first; station select has two
      optgroups; band filter with FEW@609.6 m + BKN@3962.4 m and Low off leaves
      only BKN and the "1 of 2 reported layers shown" detail; a layer with
      `baseM null` survives every filter; all bands on equals the full list;
      `filterCloudLayers` unit tests; observation metric tagged METAR under
      HRDPS; `layerGroup('satellite')` and the fallback for a layer with no
      `group`.
      Verify: `cd web && npm test -- --run && npx tsc -b --force && npm run build`
- [ ] B.8 Verify Agent B end to end:
      `cd web && npm test -- --run && npx tsc -b --force && npm run build`;
      `docker compose up -d --build --no-deps web`;
      browser at `localhost:5173` at 1440 and 1024: select HRDPS and confirm
      hero/humidity/wind tagged `eccc-hrdps`, Cloud layers / Cloud low-middle-high
      / Fog / Visibility tagged `awc-metar-speci`, header still "HRDPS selected
      model"; Cloud layers with all bands on is the full as-reported list,
      toggling Low off hides FEW 610 m and the detail reads "1 of 2 reported
      layers shown" (re-read the live METAR when checking), "Cloud L / M / H"
      still Unknown; coverage rows show group headings, Satellite first with 4
      rows and frames only left of Now; toggling a satellite layer at Now draws
      an image, scrubbing to +1 h reads "no frame here" with nothing drawn and a
      jump to the nearest past frame; model row shows producer labels, BLEND
      first, still scrolls at 1024; station select has two optgroups; no
      horizontal page overflow.

## 3. Whole-change verification

- [ ] 3.1 `cd experiments/st-johns-weather-map && make test` (API >= 383 tests,
      web >= 89, registry, SQL, specctl).
- [ ] 3.2 `docker compose up -d --build api && docker compose up -d --build --no-deps web`,
      then the three `curl` readbacks in A.8 and the browser checks in B.8.
- [ ] 3.3 `openspec validate observations-strata-satellite --strict && openspec validate --all && make spec-validate`.

## 4. Owner gates that remain (owner decisions; agents do not tick these)

- [ ] 4.1 Gate 1 in `cloud-and-fog-evidence`: model `total_cloud` from WMO 0/6/1
      keys. Untouched here.
- [ ] 4.2 Gate 2 in `cloud-and-fog-evidence`: deriving `cloud_low/middle/high`.
      Still open; the owner chose a view filter instead. Not ticked there.
- [ ] 4.3 Gate 4 in `cloud-and-fog-evidence`: WEonG as fog `provider_diagnostic`.
      Untouched here.
- [ ] 4.4 New: whether any satellite layer whose `GetLegendGraphic` probe fails
      should be offered without a legend (default: offered, `legend_available:
      false`) or withheld.
