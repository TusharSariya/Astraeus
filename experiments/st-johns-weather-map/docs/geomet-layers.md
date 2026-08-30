# ECCC GeoMet layers — evidence trail

Everything `ingest/adapters/eccc_geomet.py` pins is recorded here with the
response it was read from. Nothing in that module is a guess: a layer that is
not in this file is not in the code.

**Endpoint** `https://geo.weather.gc.ca/geomet/` — WMS 1.3.0, credential-free.
**Verified** 2026-08-30, 02:45–03:35 UTC, service version `GeoMet-Weather 2.40.3`.
**User-Agent used** `astraeus-weather-experiment/0.1 (research; contact tushar.sariya77@gmail.com)`.

How to reproduce any row:

```
curl -A "astraeus-weather-experiment/0.1 (research; contact tushar.sariya77@gmail.com)" --max-time 60 \
  "https://geo.weather.gc.ca/geomet/?service=WMS&version=1.3.0&request=GetCapabilities&LAYERS=<layer>"
```

## Service facts established

| Fact | Evidence |
|---|---|
| Unfiltered `GetCapabilities` is **39,635,828 bytes** (641,737 gzipped), **7,606 distinct named layers** | one `--compressed` fetch, 2026-08-30 02:48Z |
| `parse_capabilities` handles that document in **1.7 s at 19.1 MB peak** (`tracemalloc`) | streaming `iterparse` + `clear()`, measured on the file above |
| A **single-layer** `LAYERS` filter works and returns 12–21 KB | every row below |
| A **group** name (`LAYERS=HRDPS`) is **rejected**, 477 bytes | `ServiceException code="InvalidLayersParameter"` — same as an unknown layer, so a wrong id fails loudly |
| An **unknown** layer is rejected the same way | `LAYERS=NOT_A_REAL_LAYER_XYZ` → `InvalidLayersParameter` |
| A `TIME` outside the advertised extent is **refused** | `TIME=2020-01-01T00:00:00Z` on `RADAR_1KM_RRAI` → `ServiceException code="NoMatch"`, "time outside valid hours" |
| `GetFeatureInfo` with `feature_count=1` returns exactly one feature | verified on `RADAR_1KM_RRAI` and `HRDPS.CONTINENTAL_TT` |

## Registered layers

These four registry source ids are served by this module. No other adapter
claims them, and the project had **no** radar, lightning, hazard or air-quality
ingestion before them.

### `eccc-radar` — `ECCCRadarGeoMetAdapter`

| Layer | `title_en` (verbatim) | Published unit → stored | `time` extent (2026-08-30 03:16Z) | `reference_time` |
|---|---|---|---|---|
| `RADAR_1KM_RRAI` | `Radar precipitation rate for rain [mm/h]` | `mm/h` → `mm h-1` | `2026-08-30T00:12:00Z/2026-08-30T03:12:00Z/PT6M` (31 scans) | none |
| `RADAR_1KM_RSNO` | `Radar precipitation rate for snow [cm/h]` | `cm/h` → `cm h-1` | same | none |

Live `GetFeatureInfo` at St. John's, `TIME=2026-08-30T03:06:00Z`:

```json
{"value": 0, "class": "Undetected",
 "title_en": "Radar precipitation rate for rain [mm/h]",
 "time": "2026-08-30T03:06:00Z", "dim_reference_time": "N/A"}
```

**This is the trap the adapter exists to survive.** The mosaic reports
`value: 0` with `class: "Undetected"` — it looked and detected nothing. That is
not a precipitation rate of zero. The artifact therefore carries:

* `radar_echo` (unit `flag`) — the **mandatory** field: `0` = no detected
  precipitating echo, `1` = echo detected, missing = the mosaic did not answer;
* `precipitation_rate` / `snow_rate` — present **only** where a positive rate
  was reported, absent otherwise. `0 mm/h` never appears in an artifact.

`dim_reference_time` is the literal string `"N/A"`: a mosaic has no run time,
and `parse_iso_instant` reads that as absence rather than a parse failure.

### `eccc-lightning` — `ECCCLightningGeoMetAdapter`

| Layer | `title_en` | Published unit → stored | `time` extent |
|---|---|---|---|
| `Lightning_2.5km_Density` | `Lightning Flash Density over Canada (2.5 km) [flash/km²/min]` | `flash/km²/min` → `flash km-2 min-1` | `2026-08-30T00:00:00Z/2026-08-30T03:00:00Z/PT10M` (19 intervals) |

Live `GetFeatureInfo` at St. John's, `TIME=2026-08-30T02:50:00Z`, returned
**`{}`** — a bare object with no `features` key at all. For a Canada-wide
gridded density product covering the Avalon that means *no flashes in this cell
over this interval*. The artifact records `lightning_observed = 0` (mandatory,
unit `flag`) with `lightning_strike` absent.

`flash/km²/min` → `flash km-2 min-1` is a **spelling** change only; no number is
touched, and "flash" is kept rather than dropped so the artifact does not claim
a density of something unspecified.

### `eccc-cap-alerts` — `ECCCCapAlertsGeoMetAdapter`

| Layer | `title_en` | Dimensions | Verified response |
|---|---|---|---|
| `Current-Alerts` | `Current Weather Alerts [experimental]` | **none** — time-independent | `{"type":"FeatureCollection","name":"Current-Alerts","features":[]}` |

No alert was in force over the Avalon at any point during verification, so the
**CAP feature property schema is unverified**. The adapter therefore never
interprets, renames or derives anything from a feature: it publishes the merged
`FeatureCollection` byte-for-byte as a second artifact, and validates only the
per-box feature *count*, which is a real measurement whose zero is genuine.

Quirk worth recording: the title ends in `[experimental]`, which the
bracket rule reads as an unrecognised unit. That is correct behaviour — it is
carried through unconverted and no alert value is ever unit-converted.

Run identity comes from the newest feature timestamp, falling back to the
service's own `updateSequence` (e.g. `2026-08-30T03:15:01Z`); never from our
clock. With neither available the adapter raises `AdapterUnavailable`.

**Re-verified 2026-08-30 04:30Z, after a report that "both cap-alerts layers
return 0 features".** Zero is the correct answer, not a fault:

* `api.weather.gc.ca/collections/weather-alerts/items?bbox=-55,46.5,-51,48.5`
  → `numberMatched: 0`, while the same collection reports **161** alerts in
  force nationally. Nothing is in force over the Avalon.
* `Current-Alerts` `GetFeatureInfo` does return features where an alert exists:
  sampling six pixels that `GetMap` had actually drawn over Canada returned one
  feature each. The layer is queryable and answering.
* Both published artifacts are intact. The Zarr object starts `PK\x03\x04` and
  reopens; the GeoJSON object is 127 bytes of valid, empty `FeatureCollection`.
  The `BadZipFile` reported against revision
  `30fd96b0-f563-4145-aa85-1f99d16ac22f` is against the **`alerts_features`
  GeoJSON** artifact — a reader opening it as Zarr, not a bad artifact. See the
  note in `test_every_cap_alerts_artifact_declares_the_media_type_of_its_own_bytes`.

The Zarr artifact is therefore kept. `alerts_in_force` is the only thing that
can distinguish "no alert is in force here" (`0`) from "this box was never
successfully queried" (missing); an empty `FeatureCollection` cannot express
that difference, so dropping the grid would lose the honesty it exists for.

### `eccc-aqhi` — `ECCCAqhiGeoMetAdapter`

| Layer | `title_en` | Dimensions |
|---|---|---|
| `AQHI-OBS` | `AQHI - Observations` | **none** — time-independent |

Live response, one query over the Avalon core box:

```json
{"_id": "AQ_OBS-ABEFS-20260830030000", "properties.aqhi": "1.81",
 "properties.location_name_en": "St. John's",
 "properties.observation_datetime": "2026-08-30T03:00:00Z"}
```

Live end-to-end run 2026-08-30 03:35Z returned three stations — St. John's
(1.81), Grand Falls-Windsor (1.54), Burin (1.00) — `complete=True`,
`coverage 0.3333` (3 observations in a 3×3 station outer product).

AQHI is published as `air_quality_health_index` with unit `index` and is never
converted to PM2.5, AOD or extinction.

**Query geometry, established the hard way.** A `GetFeatureInfo` on a vector
layer is resolved against a search area derived from the map resolution, not
against a mathematical point. Measured 2026-08-30:

| Query box | AQHI features returned |
|---|---|
| `47.4,-52.1,47.6,-51.9` (0.2°, centred on a lattice point) | **0** |
| `47.4,-52.9,47.7,-52.5` (0.3° × 0.4°, over St. John's) | 1 |
| `46.5,-55.0,48.5,-51.0` (the Avalon core box) | **3** |

The first version of this adapter probed a 3×3 lattice of 0.2° cells and got
nothing at all from AQHI. The adapters now query **declared boxes**
(`avalon_probe_boxes()`, one box covering the Avalon core by default), which is
also strictly fewer requests.

## Verified but deliberately NOT registered

`eccc-hrdps` and `eccc-rdps` belong to `ingest/adapters/eccc_datamart.py`.
Native GRIB2 gives strictly stronger provenance for a gridded forecast field —
run time from the file's own stamp, native units, native CRS, real lead hours,
a dense field — whereas `GetFeatureInfo` answers one pixel per request and
sources its provenance from a rendering service. `MODEL_SOURCE_OWNER` at the
foot of the module records that decision; setting it to `"eccc_geomet"`
registers the classes below instead. Every id was still verified live so the
fallback is not a guess.

All extents below read at 2026-08-30 02:45Z. Every HRDPS layer advertises
`time 2026-08-29T18:00:00Z/2026-08-31T18:00:00Z/PT1H` and
`reference_time 2026-08-28T18:00:00Z/2026-08-29T18:00:00Z/PT6H`
(default `2026-08-29T18:00:00Z`); every RDPS layer advertises
`time 2026-08-29T18:00:00Z/2026-09-02T06:00:00Z/PT1H` with the same
`reference_time`. Exceptions are noted.

### HRDPS (`ECCCHrdpsGeoMetAdapter`, anchor `HRDPS.CONTINENTAL_TT`)

| Variable | Layer | `title_en` | Unit → stored |
|---|---|---|---|
| `temperature_2m` | `HRDPS.CONTINENTAL_TT` | `HRDPS.CONTINENTAL - Air temperature at 2m above ground [°C]` | `°C` → `degC` |
| `dew_point_2m` | `HRDPS.CONTINENTAL_TD` | `HRDPS.CONTINENTAL - Dew point temperature at 2m above ground [°C]` | `°C` → `degC` |
| `relative_humidity_2m` | `HRDPS.CONTINENTAL_HR` | `HRDPS.CONTINENTAL - Relative humidity at 2m above ground [%]` | `%` → `percent` |
| `mean_sea_level_pressure` | `HRDPS.CONTINENTAL_PN-SLP` | `HRDPS.CONTINENTAL - Sea level pressure [Pa]` | `Pa` → `hPa` (a real conversion, done by `normalize_units`) |
| `total_cloud` | `HRDPS.CONTINENTAL_NT` | `HRDPS.CONTINENTAL - Total cloud cover [%]` | `%` → `percent` |
| `wind_speed_10m` | `HRDPS.CONTINENTAL_WSPD` | `HRDPS.CONTINENTAL - Wind speed at 10m above surface [m/s]` | `m/s` → `m s-1` |
| `wind_direction_10m` | `HRDPS.CONTINENTAL_WD` | `HRDPS.CONTINENTAL - Wind direction at 10m above surface [°]` | `°` → `degree` |
| `precipitation_accumulation` | `HRDPS.CONTINENTAL.DIAG_PR_PT1H` | `HRDPS.DIAG - Precipitation - 1-hour accumulation [mm]` | `mm` → `mm`; `time` starts `2026-08-29T19:00:00Z` (no accumulation at lead 0) |

Sample reading, `TIME=2026-08-30T03:00:00Z` at St. John's:
`value 18.165003`, `class "15 20"` (a legend bin, not a semantic class),
`dim_reference_time "2026-08-29T18:00:00Z"`.

Wind is stored as `wind_u_10m` / `wind_v_10m` using the meteorological
convention — direction is the bearing the wind comes **from**, so a 000° wind
gives negative `v`. Matches `eccc_ogc.parse_wind_uv` and `awc`.

### RDPS (`ECCCRdpsGeoMetAdapter`, anchor `RDPS_10km_AirTemp_2m`)

| Variable | Layer | `title_en` | Unit → stored |
|---|---|---|---|
| `temperature_2m` | `RDPS_10km_AirTemp_2m` | `RDPS - Air temperature at 2m above ground [°C]` | `°C` → `degC` |
| `dew_point_2m` | `RDPS_10km_DewPoint_2m` | `RDPS - Dew point [°C]` | `°C` → `degC` |
| `relative_humidity_2m` | `RDPS_10km_RelativeHumidity_2m` | `RDPS - Relative humidity [%]` | `%` → `percent` |
| `mean_sea_level_pressure` | `RDPS_10km_Pressure_MSL` | `RDPS - Sea level pressure [Pa]` | `Pa` → `hPa` |
| `total_cloud` | `RDPS_10km_TotalCloudCover` | `RDPS - Total cloud cover [%]` | `%` → `percent` |
| `wind_speed_10m` | `RDPS_10km_WindSpeed_10m` | `RDPS - Wind speed at 10m above surface [m/s]` | `m/s` → `m s-1` |
| `wind_direction_10m` | `RDPS_10km_WindDir_10m` | `RDPS - Wind direction at 10m above surface [deg true]` | `deg true` → `degree` |
| `precipitation_accumulation` | `RDPS_10km_Precip-Accum1h` | `RDPS - Precipitation - 1-hour accumulation [mm]` | `mm` → `mm`; `time` starts `2026-08-29T19:00:00Z` |

An earlier draft of this file claimed RDPS had no dew-point layer. That was
wrong: `RDPS_10km_DewPoint_2m` exists (`RDPS - Dew point [°C]`), was verified
against the full capabilities document, and is now bound. Recorded here because
the claim had already been written down before it was checked.

### Pressure-level relative-humidity profile — the one thing only GeoMet has

`HRDPS.CONTINENTAL.PRES_HR.{level}`, e.g.
`HRDPS.CONTINENTAL.PRES_HR.850` → `HRDPS.CONTINENTAL.PRES - Relative humidity at 850 mb [%]`.

All seventeen pinned levels confirmed present for **both** templates on
2026-08-30:

```
1000 985 970 950 925 900 875 850 800 750 700 650 600 550 500 400 300
```

RDPS equivalent: `RDPS_10km_RelativeHumidity_{level}mb`, e.g.
`RDPS_10km_RelativeHumidity_850mb` → `RDPS - Relative humidity at 850 mb [%]`.
GeoMet advertises 28 HRDPS levels spanning `50` … `1015` mb; the list above is
the subset a Skew-T needs, kept short because the profile costs one polite
request per level.

**This is the first real vertical humidity profile the project has access to**
— Datamart's HRDPS bundles do not carry it — so it is exposed as the
module-level function `humidity_profile(client, template, levels, moment,
point)` rather than being locked inside an adapter that is not registered.

**It has no registry source id.** `eccc-hrdps` now belongs to Datamart, and
`eccc-radiosonde` is category `humidity_profile` but its product is *"Upper-air
radiosonde observations"* — attaching a model-derived profile to an observation
record would be a category lie. `registry/source_data.py` is outside this
agent's ownership, so the capability ships implemented, tested and
**unregistered**. It needs a new record, something like
`eccc-hrdps-pressure-levels`, category `deterministic_forecast`, producer MSC,
cadence "4 runs/day", variables `("relative_humidity",)`, levels the list
above.

## Rendering: `GetMap` and `GetLegendGraphic`

**Correction.** An earlier revision of this file recorded these two client
methods as "removed … recoverable from history". That was wrong: this
experiment directory is untracked and has no commits, so there was no history
to recover them from and no code in the module. They were written from scratch
on 2026-08-30 and are verified below.

`GeoMetClient.map_image(layer, bounds, *, width, height, valid_time, resolve,
style, image_format, transparent)` returns a `GeoMetImage`; so does
`GeoMetClient.legend_graphic(layer, *, style, image_format)`. The image bytes
are never separated from the exact request URL, the layer name, the resolved
`TIME` and the `dim_reference_time` the layer advertises — `GeoMetImage.as_provenance()`
is the record.

| Fact | Evidence, 2026-08-30 |
|---|---|
| `GetMap` renders the Avalon | `LAYERS=RADAR_1KM_RRAI&CRS=EPSG:4326&BBOX=46.8,-53.6,48.2,-52.0&WIDTH=512&HEIGHT=512&FORMAT=image/png&TRANSPARENT=TRUE` → `200`, `image/png`, 1,096 bytes, 512×512 RGBA |
| `GetLegendGraphic` returns **ECCC's own** colour ramp | `…&REQUEST=GetLegendGraphic&LAYERS=RADAR_1KM_RRAI&FORMAT=image/png&STYLE=RADARURPPRECIPR` → `200`, `image/png`, 10,260 bytes, 113×490. This is why no scale is ever hand-written here: a legend we drew ourselves would be a fabricated key over real pixels. |
| Omitting `STYLE` renders the layer's default ramp | same request without `STYLE` → `200`, `image/png`, 124×413 |
| An unknown `STYLE` is refused | `STYLE=NOPE` → **`200`**, `text/xml`, `code="LayerNotDefined"` |
| **The trap:** an unadvertised `TIME` is a fault served as a success | `…&REQUEST=GetMap&…&TIME=2020-01-01T00:00:00Z` → **`200`**, `Content-Type: text/xml`, 477 bytes, `<ogc:ServiceException code="NoMatch" locator="time">`. A client that checks only the status code hands an XML blob to a PNG decoder. `_render` inspects the body for the OGC fault **and** checks the content type, and raises rather than returning bytes. |
| `DIM_REFERENCE_TIME` pins the run and is validated by the service | `HRDPS.CONTINENTAL_TT` with the advertised default → `200`, `image/png`; with `2020-01-01T00:00:00Z` → `200`, `text/xml`, `code="NoMatch"`. The run is therefore pinned wherever a layer advertises one, so the tile states which run drew it. |
| **Axis order:** WMS 1.3.0 + EPSG:4326 is `miny,minx,maxy,maxx` | the transposed box `BBOX=-53.6,46.8,-52.0,48.2` was answered `200`, `image/png`, **96 bytes** — a silent near-empty tile, no exception. The lat-first order is asserted in `test_the_getmap_bbox_is_latitude_first_as_wms_1_3_0_requires`. |

A `TIME` outside the extent is refused **client-side** by `TimeExtent.nearest`
before any request is sent (`resolve=True`, the default); the server-side guard
above is what protects a caller that supplies its own frame with `resolve=False`.
Renders reuse the same 300-second in-memory TTL cache as capabilities, keyed on
the fully-formed URL and capped at `IMAGE_CACHE_MAX_ENTRIES` entries, with an
`IMAGE_MAX_BYTES` body ceiling and a `MAX_IMAGE_PIXELS` guard on the size the
caller chooses.

## WEonG fog visibility (live proxies)

Four Weather Elements on Grid fog diagnostics are offered by the API as
**live-proxied imagery only** (`evidence_basis: live_proxy`, group
`forecast_proxy`), through `weather_api.wms.FORECAST_LAYERS`. They are ECCC's
post-processed "visibility through fog" product, not a raw model field. Nothing
numeric is ever read off them: they are not sampled by `/point`, and `fog_state`
is derived from METAR/TAF present weather alone. `HRDPS-WEonG` corresponds to
registry record `eccc-hrdps-weg-prognos` (nothing claims it as an ingest
adapter); `RDPS-WEonG` has **no registry record**.

| API layer id | WMS layer | `title_en` (verbatim) | Unit → published | `time` extent (2026-08-30) | `reference_time` |
|---|---|---|---|---|---|
| `geomet-live-hrdps-weong-fog-liquid` | `HRDPS-WEonG_2.5km_LiquidFogVisibility` | `HRDPS-WEonG - Visibility through liquid fog [m]` | `m` → `m` | `2026-08-30T07:00:00Z/2026-09-01T06:00:00Z/PT1H` | `…/PT6H` |
| `geomet-live-hrdps-weong-fog-ice` | `HRDPS-WEonG_2.5km_IceFogVisibility` | `HRDPS-WEonG - Visibility through ice fog [m]` | `m` → `m` | same | `…/PT6H` |
| `geomet-live-rdps-weong-fog-liquid` | `RDPS-WEonG_10km_LiquidFogVisibility` | `RDPS-WEonG - Visibility through liquid fog [m] [experimental]` | `m` → `m` | `…/2026-09-02T18:00:00Z/PT1H` | `…/PT6H` |
| `geomet-live-rdps-weong-fog-ice` | `RDPS-WEonG_10km_IceFogVisibility` | `RDPS-WEonG - Visibility through ice fog [m] [experimental]` | `m` → `m` | same | `…/PT6H` |

**The `[experimental]` trap.** ECCC appends `[experimental]` to the title of a
layer it has not made operational, in the same trailing-bracket position the
unit occupies. `parse_title_units` strips that flag before reading the unit
(otherwise the RDPS pair would have published `units: "experimental"`), and
`is_experimental` reports it separately. The API discloses it: the layer title
is prefixed `[experimental] ` and a notice names the layer. The flag is shown,
labelled, never hidden and never read as a unit.

Probe results (Avalon box `46.5,-55.0,48.5,-51.0`, 400×200, `TRANSPARENT=TRUE`):

| Request | Result, 2026-08-30 |
|---|---|
| `GetMap` all four, `TIME=2026-08-31T09:00:00Z` | `200 image/png`; HRDPS liquid **531 B**, the other three **390 B** — near-empty tiles: a reading ("no fog rendered here at that hour"), not an outage |
| `GetLegendGraphic` (`LAYER` singular, `SLD_VERSION=1.1.0`) | `200 image/png`; liquid ramps 6,788 B, ice ramps 6,559 B |

No non-trivial (foggy) tile has yet been observed over the Avalon, so rendering
of actual fog pixels is **not** claimed as verified; what is verified is that the
service answers the requests with the media type asked for.

## GOES-East satellite (live proxies)

Four NOAA GOES-East imagery layers, served by GeoMet as ECCC's copy of the
NOAA product, are offered by the API as **live-proxied imagery only**
(`evidence_basis: live_proxy`, group `satellite`, `product: GOES-East`),
through `weather_api.wms.SATELLITE_LAYERS`. They ride the same
`ForecastLayerSpec` mechanism as the forecast proxies but they are the one
proxied family that is **observed**: every frame is a scan the satellite has
already taken, the advertised extent ends at the latest received scan, and no
frame is ever offered forward of now. It is never a forecast. Nothing numeric
is read off the pixels: not sampled by `/point`, absent from `/timeline`. The
closest registry record is `noaa-goes-east` (category `satellite`, status
`implementing`); nothing here promotes it.

Probed live 2026-08-30 18:32Z (`GeoMetClient`, one capabilities fetch, two
`GetMap`s and one `GetLegendGraphic` per layer; Avalon box
`46.5,-55.0,48.5,-51.0`, 400×200, EPSG:4326 lat-first, `TRANSPARENT=TRUE`):

| API layer id | WMS layer | `title_en` (verbatim) | `time` extent (2026-08-30 18:32Z) | `GetMap` latest (`TIME=…18:10:00Z`) | `GetMap` now-2h (`…16:30:00Z`) | `GetLegendGraphic` |
|---|---|---|---|---|---|---|
| `geomet-live-goes-east-dayvis-nightir` | `GOES-East_1km_DayVis-NightIR` | `GOES-East Day Visible/Night IR [1 km]` | `2026-08-28T12:10:00Z/2026-08-30T18:10:00Z/PT10M` (325 scans) | `200 image/png` 111,448 B | `200 image/png` 90,764 B | `200 image/png` 82 B |
| `geomet-live-goes-east-snowfog-nightmicro` | `GOES-East_1km_SnowFog-NightMicrophysics` | `GOES-East Snow-Fog/Night Microphysics [1 km]` | same | `200 image/png` 107,723 B | `200 image/png` 82,417 B | `200 image/png` 82 B |
| `geomet-live-goes-east-naturalcolor` | `GOES-East_1km_NaturalColor` | `GOES-East Natural Color [1 km]` | same | `200 image/png` 106,617 B | `200 image/png` 84,187 B | `200 image/png` 82 B |
| `geomet-live-goes-east-nightir-2km` | `GOES-East_2km_NightIR` | `GOES-East Night IR [2 km]` | same | `200 image/png` 34,945 B | `200 image/png` 30,768 B | `200 image/png` 82 B |

Facts read off those responses:

* The extent ran **54 h back** to **22 min before now** at probe time, at
  `PT10M`; no `reference_time` dimension (a scan has no run). The API
  intersects that with its −3 h/+24 h window, so a layer carries roughly
  eighteen ten-minute frames, all ≤ now, cadence 600 s, staleness tolerance
  300 s; the window notice reads "… N of 325 frames fall inside this
  experiment's window …" and is expected.
* `GetMap` at `now-2h` resolved to the nearest advertised scan (`16:30:00Z`),
  as `TimeExtent.nearest` is meant to. The 1 km tiles are 80–110 kB over the
  Avalon: real imagery, not a near-empty tile.
* `GetLegendGraphic` (`LAYER` singular, `SLD_VERSION=1.1.0`, no `STYLE`)
  answers `200 image/png` for all four — an **82-byte, 35×5 RGBA strip** with
  700 of 705 pixel bytes non-zero. That is the service's own ramp for a
  picture layer, small as it is, so `legend` stays `True` on each spec and
  `legend_available` reports it. Had the probe answered 4xx or non-image, the
  spec would carry `legend=False` and `/layers` would say so; the flag is a
  recorded probe result, never an assumption.

**The `[1 km]` trap.** The titles end in `[1 km]` / `[2 km]` in the same
trailing-bracket position the unit occupies, and the bracket rule would have
published `units: "1 km"` — a pixel *resolution* presented as the unit of a
picture. `parse_title_units` now strips a bracket matching
`^\d+(\.\d+)?\s*(km|m)$` before reading the unit (a bare `[m]` has no number
and stays the WEonG fog-visibility unit), and `parse_title_resolution` reports
it separately. The API publishes `units: "unknown"` for these layers — the
capability declares no unit — and discloses the resolution in a notice:
`"<layer_id>: ECCC advertises 1 km pixel resolution for <wms_layer>; that is
not a unit"`.

`/raster` responses for these layers carry
`X-Weather-Time-Semantics: observed at the instant in X-Weather-Valid-Time`,
where a forecast proxy says *valid*. Seventeen proxied specs now cost
seventeen capability fetches on a cold cache; `MAX_UPSTREAM_CALLS_PER_REQUEST`
was raised from 16 to 32 so a cold `/layers` cannot exhaust its budget and
offer no proxies at all (capabilities are cached 300 s, so only cold requests
pay).

## Candidates examined and rejected

| Candidate | Status | Why not used |
|---|---|---|
| `HRDPS-WEonG_2.5km_AirTemp` and the rest of the `HRDPS-WEonG` family as an **ingest adapter** | **exists**, `HRDPS-WEonG - Temperature [°C]`, `time …/PT1H`, `reference_time …/PT6H` | This is the post-processed Weather Elements on Grid product, registry id `eccc-hrdps-weg-prognos`, which no ingest adapter claims. The four fog-visibility layers are offered as live-proxied imagery (section above); nothing else from the family is used, and nothing is mis-filed under `eccc-hrdps`. |
| WCS `GetCoverage` | not used | `GetCapabilities` returns 200 but a naive `GetCoverage` faults; axis labels must come from `DescribeCoverage` first. Unproven, so not built on. |
| `LAYERS=HRDPS` / `LAYERS=RDPS` group filter | rejected by the service | 477-byte `InvalidLayersParameter`. Capabilities must be fetched one leaf layer at a time. |
| Multi-layer `LAYERS=a,b` on `GetFeatureInfo` | rejected | `InvalidLayersParameter`. Every value costs its own request; the module's request budgets exist because of this. |
| `TIME=start/end/period` on `GetFeatureInfo` | rejected | `NoMatch`. One value per request. |
| Disk-backed capabilities cache | **removed** | It was keyed on the per-run `workdir`, so it could never be read back on a later run. In-memory TTL caching (300 s) is what actually saves the requests. |
| `RDPS_10km_DewPointDepression_*` | not used | Dew-point *depression* is a different quantity from dew point. `RDPS_10km_DewPoint_2m` publishes the dew point directly, so no subtraction is invented. |
