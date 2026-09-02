Non-normative research, 2026-09-02. Not a specification and not an admission
decision. Every "verified live" claim below was made against the endpoint on
2026-09-02 between 05:40Z and 06:05Z; re-probe before building.

# Fog and cloud line-of-sight sources for the ocean sectors

Ticket: [#9](https://github.com/TusharSariya/Astraeus/issues/9). Charter:
[#5](https://github.com/TusharSariya/Astraeus/issues/5).

Evidence box: **45.0 to 50.5 N, 58.0 to 46.0 W**.

## Scope and what is reused rather than repeated

Reused unchanged, not re-probed:

- `docs/research/wayfinder/geomet-wcs-inventory.md` (branch
  `research/geomet-wcs-inventory`) for the HRDPS `CONTINENTAL_*` set: 40/80/120 m
  temperature, dew point, humidity and wind; 28-level relative humidity;
  `_HPBL` boundary-layer height; `_SKINT` skin temperature; `_ICEC` ice cover
  (analysis-only, single instant); no layered cloud and no cloud base anywhere
  on GeoMet; the fog set at about 226 MB per HRDPS run; and the WCS request
  shape (`SUBSET` plus mandatory `FORMAT` and `SCALESIZE`, `BBOX` silently
  ignored).
- `experiments/st-johns-weather-map/openspec/config.yaml` for the GOES facts
  already held: ABI-L2-ACMF is Full Disk because the box straddles the CONUS
  eastern boundary; ACHAF cloud-top height is retained as a display-derivation
  input; HRDPS `NT` is opacity-weighted and temporally smoothed with a
  `[0.25, 0.5, 0.25]` hourly kernel.

Correction to `docs/research/cloud-fog-line-of-sight.md`: its GOES-East section
lists "fog and low stratus probabilities" and "cloud-top height, pressure,
temperature, layer, and phase" as retrievable observed products. **The fog and
low stratus product is not on the open NOAA bucket** (see below), and the doc
does not distinguish the 2 km from the 10 km publication of the cloud-top
family, which is the difference between 4.1 GB and 216 MB of wire traffic per
day. Everything else in its source tables held up.

Note: the charter points at a `CONTEXT.md` glossary at the repo root. **No
`CONTEXT.md` exists in this repository** (absent from the working tree and from
`HEAD`). Evidence classes below are therefore taken from the charter's own
Notes section and from `openspec/config.yaml`: *retrieved*, *reprocessed*,
*derived-here*, *generated-display*, *uncalibrated observation*. The ticket's
three-way split maps onto them as: an **observation** is retrieved; a
**producer diagnostic** is retrieved evidence too (the producer's own
statistic, stored as such and never recomputed here); a value this deployment
**would derive** is derived-here and needs inputs, method and citation.

---

## 1. GOES-19 ABI on `noaa-goes19`

Licence for the whole bucket: NOAA open data, no restrictions, attribution
requested. Access path: anonymous HTTPS/S3 REST, no credentials
(`https://noaa-goes19.s3.amazonaws.com/<Product>/<YYYY>/<DDD>/<HH>/`).
Full Disk (`...F`) is the only sector that covers the box.

### 1.1 What is published, and what is not

Verified live by listing the bucket's top-level prefixes (105 prefixes).

- **There is no fog / low-stratus product.** No `FLS` prefix of any kind. The
  GOES-R Fog and Low Stratus product is a CIRA/NOAA product distributed through
  AWIPS and VLab, not through the open bucket. A fog-and-low-stratus field for
  this box is therefore **derived-here** or absent; it is not retrievable.
- **There is no cloud-base product.** No `CBH`. The nearest published thing is
  `ABI-L2-CCL`, cloud cover *layers*, which gives fractional cover in five
  fixed altitude bands rather than a base height.
- Cloud-top height is published **twice**: `ABI-L2-ACHAF` at 10 km and
  `ABI-L2-ACHA2KMF` at 2 km. The existing adapter uses `ACHAF`.

### 1.2 Grid geometry in the box (measured)

Computed from the GOES fixed-grid projection attributes of a real granule
(`OR_ABI-L2-CCLF-M6_G19_s20262450500206...`), by inverting the fixed grid to
lat/lon and counting pixels inside the box:

| Native resolution | Grid | Pixels in box | Bounding sub-grid | Effective spacing at box centre |
| --- | --- | ---: | --- | --- |
| 10 km | 1086 x 1086 | **2 420** | 37 x 92 | 18.9 km N-S x 12.3 km E-W |
| 2 km | 5424 x 5424 | **60 500** (25x) | 185 x 460 | 3.8 km N-S x 2.5 km E-W |

The box sits at high local zenith angle from 75.2 W, so a "2 km" product is
2.5 to 3.8 km on the ground here and a "10 km" product is 12 to 19 km. This
also means the 10 km cloud-top family is only about a factor of five coarser
than the 2 km family *in this box*, for a twentieth of the bytes.

### 1.3 Per-product findings

All Full Disk, all mode M6. Cadence and per-file size measured from the
2026/245/05Z hour. Latency is S3 `LastModified` minus scan start.

| Product | Quantity | Evidence class | Cadence | Native res | Latency (measured) | Granule size | Box subset (retained) |
| --- | --- | --- | --- | --- | --- | ---: | ---: |
| `ABI-L2-ACMF` | Enterprise Cloud Mask + cloud probability | retrieved observation (producer retrieval) | 10 min | 2 km | 10.2 min after scan start, 0.7 min after scan end | 26.3 MB | ~60 KB mask (uint8) + ~242 KB probability (float32) |
| `ABI-L2-ACHAF` | cloud-top height | retrieved observation | 10 min | **10 km** | 12.2 min / 2.7 min | **1.54 MB** | ~9.7 KB (float32) |
| `ABI-L2-ACHA2KMF` | cloud-top height | retrieved observation | 10 min | 2 km | 12.4 min / 2.9 min | 29.2 MB | ~242 KB |
| `ABI-L2-CTPF` | cloud-top pressure | retrieved observation | 10 min | 10 km | 12.2 min / 2.6 min | 1.57 MB | ~9.7 KB |
| `ABI-L2-ACHTF` | cloud-top temperature | retrieved observation | 10 min | 2 km | 12.4 min / 2.9 min | 28.8 MB | ~242 KB |
| `ABI-L2-ACTPF` | cloud-top phase (`Phase`) + cloud type | retrieved observation | 10 min | 2 km | 10.6 min / 1.1 min | 3.59 MB | ~60 KB per categorical field |
| `ABI-L2-CCLF` | **layered cloud fraction**: `CF1` surface-5 000 ft, `CF2` 5-10 kft, `CF3` 10-18 kft, `CF4` 18-24 kft, `CF5` 24 kft-TOA, plus `TCF` total cloud fraction and `CL` cloud-layer flag | retrieved **producer diagnostic** (ABI L2+) | **hourly, on the hour** | 10 km | 17.2 min after scan start | 1.82 MB | ~2.4 KB per uint8 band, ~4.8 KB `TCF`; **~21 KB for the whole 8-field set** |
| `ABI-L2-CODF` | cloud optical depth | retrieved observation | 10 min | 2 km | 13.9 min / 4.4 min | 4.93 MB | ~242 KB |
| `ABI-L2-SSTF` | sea surface skin temperature | retrieved observation | **hourly** (1 h aggregation window) | 2 km | ~63 min after window start | 26.6 MB | ~242 KB |

`ABI-L2-CCLF` is the find. Nothing else in this stack publishes cloud fraction
*by altitude band* as retrieved evidence: HRDPS has no layered cloud, GEFS has
none instantaneous, and only ECMWF AIFS-ENS has per-member low/mid/high. `CF1`
(surface to 5 000 ft) is directly the low-cloud-and-fog-top band over the
Grand Banks, and `CF3`-`CF5` are the cirrus that ruins a sunrise. It is hourly,
not 10-minutely, and it is a **producer diagnostic** derived from the cloud-top
family, not an independent observation — do not present it as one.

### 1.4 Wire cost is the constraint, not storage

S3 has no server-side subsetting: the whole Full Disk granule is downloaded to
keep a few tens of KB. Per day, if every scan is taken:

| Product | Scans/day | Wire per day | Retained per day |
| --- | ---: | ---: | ---: |
| `ACMF` | 144 | **3.79 GB** | ~43 MB |
| `ACHAF` | 144 | 0.22 GB | ~1.4 MB |
| `CTPF` | 144 | 0.23 GB | ~1.4 MB |
| `ACTPF` | 144 | 0.52 GB | ~8.6 MB |
| `CODF` | 144 | 0.71 GB | ~35 MB |
| `ACHA2KMF` | 144 | 4.20 GB | ~35 MB |
| `ACHTF` | 144 | 4.15 GB | ~35 MB |
| `CCLF` | 24 | **0.044 GB** | **~0.5 MB** |
| `SSTF` | 24 | 0.64 GB | ~5.8 MB |

Under the charter's three-hour retention only the last 18 scans (or 3 hourly
files) are held, so retention is trivial in every row. The decision is entirely
about upstream bytes. The 10 km cloud-top family plus hourly `CCLF` costs
0.5 GB/day for the whole cloud picture; adding the 2 km cloud-top temperature
and height triples the total for a factor-of-five in a box where the ground
spacing only improves from 12 km to 2.5 km.

---

## 2. Sea-surface temperature

The air-sea temperature difference and the sea-minus-dew-point difference are
the two Grand Banks advection-fog discriminants. Neither is published anywhere
as a field: **both are derived-here** from an SST field and an HRDPS 2 m (or
40 m) dew point, and the derivation must record which SST and which model level
it used, because a 2 km CIOPS potential temperature at 0.5 m depth, a RIOPS
5 km value, an OSTIA foundation SST and a GOES skin SST are four different
quantities.

| Source | Quantity | Class | Cadence | Res | Latency (measured) | Access | Licence | Live | Box subset |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: |
| **CIOPS-East** `CIOPS-East_2km_SeaWaterPotentialTemp_0.5m` | sea water potential temperature at 0.5 m | retrieved (producer analysis/forecast) | hourly, to +48 h; runs every 6 h | **2 km** (0.030 deg lon x 0.020 deg lat; grid 1333 x 980 over 34.87-54.47 N, 77.015-37.025 W) | latest `reference_time` at 05:55Z was **2026-09-01T18:00Z**, ~12 h old | GeoMet WCS 2.0.1, `SUBSET`+`FORMAT`+`SCALESIZE` | OGL-Canada 2.0 | **yes** | **440 748 B** per hour at native `SCALESIZE=long(400),lat(275)`; 552 904 B if oversampled to 451x306 |
| **RIOPS** `RIOPS_VOTEMPER_DBS-0.5m` | sea water temperature at 0.5 m | retrieved | hourly, to +84 h; runs every 6 h | 5 km polar stereographic (grid 1770 x 1610) | latest `reference_time` **2026-09-02T00:00Z**, ~6 h old | GeoMet WCS 2.0.1 | OGL-Canada 2.0 | **yes** | **77 154 B** per hour at 160x110; ~88 KB at native ~180x122 |
| **CAPS-Ocean 3 km** `CAPS-Ocean_3km_SeaWaterTemp_0.5m` | sea water temperature at 0.5 m, coupled system | retrieved | hourly; runs every 12 h | 3 km | latest `reference_time` **2026-09-01T12:00Z**, ~18 h old | GeoMet WCS | OGL-Canada 2.0 | yes (capabilities + time extent only) | not measured |
| **OSTIA** `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | foundation SST (`analysed_sst`), L4 gap-filled analysis | retrieved (reprocessed L4 analysis; declare the delivery kind) | daily | 0.05 deg (3600 x 7200) | daily analysis, ~1 day behind | Copernicus Marine ARCO Zarr on CloudFerro S3, **anonymously readable over plain HTTPS** — `https://s3.waw3-1.cloudferro.com/mdl-arco-time-045/arco/SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001/METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2/timeChunked.zarr/` | Copernicus Marine licence: free with attribution; STAC declares `proprietary`, so read the terms before publishing derived values | **yes** — `.zarray` and `.zattrs` fetched with no credentials | ~110 x 240 cells x int16 = **52.8 KB/day**. Use `timeChunked` (chunks `[1,1024,1024]`) — the box falls in 1-2 chunks. **Do not use `geoChunked`** (chunks `[1245,16,32]`): one day over the box would pull ~56 chunks each carrying 1 245 days |
| **GOES-19 `ABI-L2-SSTF`** | sea surface **skin** temperature | retrieved observation | hourly | 2 km | ~63 min | `noaa-goes19` S3 | NOAA open | yes | ~242 KB/scan, 0.64 GB/day on the wire |
| HRDPS `CONTINENTAL_SKINT` | aggregate land surface skin temperature | retrieved | per HRDPS run | 2.5 km | as HRDPS | GeoMet WCS | OGL-Canada 2.0 | reused from `geomet-wcs-inventory` | 524 230 B |

Notes that matter:

- **`dd.weather.gc.ca` has moved.** `https://dd.weather.gc.ca/model_riops/` and
  `/model_ciops/` are both **404**. The live tree is date-partitioned:
  `https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/model_riops/netcdf/forecast/polar_stereographic/{2d,3d}/`
  answers 200. **`/<YYYYMMDD>/WXO-DD/model_ciops/` exists but is empty** — the
  same "directory answers 200, contains nothing" fingerprint the config records
  for the withdrawn feeds. CIOPS-East is only reachable through GeoMet.
- CIOPS-East is the best resolution and the worst latency; RIOPS is the best
  latency and reaches +84 h. Neither is a real-time observation: both are
  ocean-model analyses whose 0.5 m potential temperature is not the skin
  temperature the fog actually feels.
- OSTIA is the only genuinely observation-driven SST here, and it is a daily
  gap-filled L4 analysis, so it is *reprocessed*, not raw observation.

---

## 3. In-situ marine observation

| Source | Quantity | Class | Cadence | Latency | Access | Licence | Live | Size |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: |
| **SmartAtlantic St. John's buoy** (`SMA_st_johns`, Marine Institute) at **47.567 N, 52.631 W — inside the box** | `air_temp_avg`, `air_dewpoint_avg`, `air_humidity_avg`, **`surface_temp_avg` (sea surface)**, `air_pressure_avg`, wind speed/gust/direction (2 sensors), significant and max wave height, wave period/direction/spread, 20 levels of current speed and direction | retrieved observation (uncalibrated observation if the record is used without QC flags — ERDDAP exposes none) | **30 min** (`:00:01` and `:30:01`) | latest record `2026-09-02T05:30:01Z`, read at 05:52Z → **under 22 min** | ERDDAP tabledap, `https://www.smartatlantic.ca/erddap/tabledap/SMA_st_johns.csv?...` — anonymous, CSV/JSON, server-side column and time selection | **CC BY 4.0** (`license` global attribute) | **yes** | a few KB per query; ~65 columns x 48 records/day |
| `SMA_st_johns_wharf` | St. John's tide station | retrieved observation | — | — | same ERDDAP | CC BY 4.0 | yes (listed) | trivial |
| **ECCC moored buoys** on Datamart SWOB-ML, `.../observations/swob-ml/marine/moored-buoys/<YYYYMMDD>/<id>/` | `avg_air_temp_pst10mts`, **`avg_sea_sfc_temp_pst10mts`**, `avg_mslp_pst10mts`, wind (10 min avg, gust), significant/max wave height, wave period, direction, spread | retrieved observation | **hourly** (files at `HH05`) | file for 0505Z present well before 06Z | anonymous HTTPS, SWOB-ML XML | OGL-Canada 2.0 | **yes** | ~10 KB per station-hour |
| **DFO moored buoys** via SWOB partners, `.../swob-ml/partners/dfo-moored-buoys/<YYYYMMDD>/` | as above | retrieved observation | 30 min (`0530` file present) | current | anonymous HTTPS | OGL-Canada 2.0 | **yes** | ~10 KB |
| **METAR/SPECI** in the box | visibility, ceiling, layers, present weather (fog/mist), temperature, dew point, wind | retrieved observation | hourly + specials | current at probe | `https://aviationweather.gov/api/data/metar?bbox=45,-58,50.5,-46&format=json` | US public domain (relay of ECCC/NAV CANADA observations) | **yes** | trivial |

**The critical negative: there is no in-situ marine observation inside the
evidence box other than the single SmartAtlantic St. John's buoy.**

- Of the 40 ECCC moored buoys published today, the Atlantic ones nearest the box
  are **44139 Banquereau Bank (44.240 N, 57.103 W)**, **44137 East Scotian Slope
  (42.261 N, 61.999 W)**, **44150 La Have Bank (42.505 N, 64.018 W)**, and
  **East / West Chedabucto Bay (45.45 N, 60.95 W and 45.49 N, 61.14 W)**.
  Every one is **outside** the box — Banquereau is 0.76 deg south of it, the
  Chedabucto pair are 2.9 deg west of it. **Zero ECCC moored buoys report from
  inside 45.0-50.5 N, 58.0-46.0 W.** There is nothing on the Grand Banks.
- All seven DFO partner buoys (`azmp-esg`, `iml-7`, `iml-10`, `iml-14`,
  `iml-ba`, `pmza-riki`, `pmza-vas`) are in the Gulf of St. Lawrence and the
  Estuary; `azmp-esg` "Eastern South Gulf" is at 46.8 N, 62.0 W — again west of
  the box.
- **ECCC moored buoys report no dew point, no humidity and no visibility.**
  Their element list carries air temperature and sea surface temperature but
  nothing to compute a dew-point depression from. Only the SmartAtlantic buoy
  gives air temperature, dew point *and* sea surface temperature at one point —
  the whole advection-fog triple, at one location, at the harbour mouth.
- The ten METAR stations inside the box are **all coastal or inland**: CYYT
  (47.627, -52.748), CWRA Cape Race (46.659, -53.073), CWZN (47.368, -55.795),
  CWDO (49.688, -54.800), CXRH (49.570, -57.878), CXTP (48.557, -53.975), CYQX
  Gander, CYDF Deer Lake, plus LFVP St-Pierre (46.764, -56.169). Of these only
  CYYT, CYQX, CYDF and LFVP report visibility; the `CW`/`CX` automatic stations
  returned `visib: None`. **No station in the box is offshore.**

### Ship and platform SYNOP: nothing usable

Swept every ship-surface bulletin on Datamart for 2026-09-02
(`/20260902/WXO-DD/bulletins/alphanumeric/20260902/SS/`). Only two originating
centres publish there at all — **DEMS** (Offenbach) and **LFVW** (Toulouse);
Canada's own **CWAO issues no `SS` bulletins**. The full day's traffic is
1 062 lines carrying **223 reports, every one of them a `ZZYY` drifting-buoy
report and not one a `BBXX` ship report** (`grep -c BBXX` = 0). Decoding the
`Qc/lat/lon` groups, **none falls inside the box**.

The offshore production platforms (Hibernia, Terra Nova, White Rose,
Hebron) do not reach any open feed examined here: not as `SS` bulletins, not
as METAR in the aviationweather bbox query, not as SWOB partners. **Treat
platform observation as unavailable.**

---

## 4. HRDPS and the producer's own fog diagnostic

Reused from `research/geomet-wcs-inventory` for the `HRDPS.CONTINENTAL_*` set.
New here, and **not in that inventory**: the **WEonG** (Weather Element on Grid)
family, 34 coverages at 2.5 km.

| Coverage | Quantity | Class | Verified |
| --- | --- | --- | --- |
| `HRDPS-WEonG_2.5km_LiquidFogVisibility` | **the producer's own fog visibility diagnostic** | retrieved **producer diagnostic** | **yes** |
| `HRDPS-WEonG_2.5km_IceFogVisibility` | ice-fog visibility | retrieved producer diagnostic | listed |
| `HRDPS-WEonG_2.5km_SkyState` | producer sky-condition category | retrieved producer diagnostic | listed |
| `HRDPS-WEonG_2.5km_AirTemp`, `_DewPointTemp`, `_WindSpeed`, `_WindDir`, `_WindGust` | WEonG surface fields | retrieved | listed |
| `RDPS-WEonG_10km_*`, `GDPS-WEonG_15km_*` | same family, coarser | retrieved | listed |

`LiquidFogVisibility` measured live: `TIME` extent
`2026-09-02T01:00Z/2026-09-04T00:00Z/PT1H` (hourly, +48 h),
`reference_time` `2026-08-31T18:00Z/2026-09-02T00:00Z/PT6H` (runs every 6 h);
latest run **00Z, available by 05:55Z**, so about **6 h latency**, the usual
HRDPS figure. GetCoverage over the box at
`SCALESIZE=long(534),lat(245)` returned **200, `image/tiff`, 524 230 bytes,
0.65 s** — byte-identical in size to `HRDPS.CONTINENTAL_TT`, as expected on the
same grid. Licence OGL-Canada 2.0.

This changes the shape of the problem. The charter's fog work assumed the
deployment would derive a visibility from RH, dew-point depression and
boundary-layer height. **ECCC already publishes a fog visibility on the 2.5 km
grid.** It is a *producer diagnostic*, so under the config's rule it is stored
as retrieved evidence and never recomputed here — and it must not be blended
with a derived-here visibility. The same caution as `NT` applies: WEonG is the
post-processed product whose total cloud is temporally smoothed with a
`[0.25, 0.5, 0.25]` hourly kernel (technote v2.4.1 sec 7.9), so its hourly
timing is uncertain to about an hour by the producer's own admission.

Still absent from ECCC everywhere: **cloud base**, **layered cloud**, and any
cloud fraction by altitude. Those come only from GOES `CCLF`, and only as a
satellite-top view.

---

## 5. What a sunrise-cloud and Grand Banks fog assessment can be assembled from

### Sunrise-direction cloud, east over the water

Assemblable today:

1. **Cirrus and mid cloud in the sunrise sector** — GOES-19 `ABI-L2-CCLF`
   `CF3` (10-18 kft), `CF4` (18-24 kft), `CF5` (24 kft-TOA), hourly, 10 km,
   ~17 min latency, 2 420 cells in the box. This is the layer information the
   ECCC models do not publish, and it is what decides whether a sunrise lights
   up or goes flat.
2. **Where the cloud top is, for the ray geometry** — `ACHAF` (10 km, 10 min)
   for height, `CTPF` for pressure, `ACTPF` for phase (ice vs liquid decides
   whether the layer glows or greys). At 5 degrees elevation the ray is 11 km
   out for a 1 km top and 91 km out for an 8 km top, so the sector to be
   sampled is a function of the retrieved height — the box is big enough for
   all of it.
3. **The cloud mask and its motion** — `ACMF` at 10 min already ingested, with
   the parallax correction the adapter already does. Ten-minute cadence over
   the box is enough for an image-flow displacement in the hour before sunrise.
4. **Model background beyond the satellite's reach** — HRDPS `NT`/`N4` and
   `HRDPS-WEonG_2.5km_SkyState` to +48 h, understood as opacity-weighted and
   hour-smoothed and therefore not comparable with the GOES fractions.

Missing:

- **Cloud base.** Nothing published anywhere gives it: no GOES CBH product on
  the bucket, no ECCC cloud base on GeoMet, and the only ceiling observations
  are four land METAR stations. A base for an offshore ray is **derived-here**
  at best, from `CCLF` band occupancy plus an LCL from HRDPS 40 m temperature
  and dew point, and it should be published with wide uncertainty.
- **Anything at 10-minute cadence with layer information.** `CCLF` is hourly.
  A sunrise window is 20 minutes long; the layered evidence will usually be
  20-40 minutes stale at the moment that matters, inside the config's
  `staleness_tolerance_seconds` discipline but worth disclosing.
- **Illumination geometry.** Whether a cloud deck 60 km offshore is lit from
  below is a solar-geometry and cloud-base computation this deployment must do
  itself; no source supplies it.

### Grand Banks advection fog, south and east of the Avalon

Assemblable today:

1. **The producer's own answer** — `HRDPS-WEonG_2.5km_LiquidFogVisibility`,
   hourly to +48 h at 2.5 km, 524 KB per hour over the box, ~6 h latency.
   Retrieved producer diagnostic; the single strongest fog source found.
2. **The physical driver, derived here** — sea-minus-air and
   sea-minus-dew-point, from CIOPS-East 2 km (or RIOPS 5 km when CIOPS's ~12 h
   run age is too stale) against HRDPS 40/80/120 m temperature and dew point
   and `_HPBL`. Both differences are **derived-here** and must carry inputs,
   method and citation; the SST choice must be recorded because the four
   candidate SSTs are four different quantities.
3. **Where the fog top is, from above** — `CCLF` `CF1` (surface to 5 000 ft)
   hourly, plus `ACHAF` height and `ACTPF` liquid phase. A liquid-phase,
   low-`CF1`-band, sub-300 m top over the Banks is the advection-fog signature
   as GOES sees it.
4. **Advection itself** — HRDPS 40/80/120 m wind, and `ACMF`-derived
   displacement over 10-minute scans, under the config's carve-out (b)
   conditions.
5. **One ground truth** — the SmartAtlantic St. John's buoy at 47.567 N,
   52.631 W, 30-minute, CC BY 4.0, air temperature, dew point and sea surface
   temperature at one point, live within 22 minutes. Today at 05:30Z it read
   air 13.8, dew point 9.7, sea surface 16.3 degrees C: sea warmer than air,
   which is the *anti*-advection-fog configuration, and exactly the kind of
   check no gridded field can give.

Missing, and this is the substantive gap:

- **Verification over the water.** One buoy inside the box, at the harbour
  mouth, and zero over the Grand Banks. `LiquidFogVisibility` and any
  derived-here air-sea difference are therefore **unverifiable in the sector
  they are being used for**. Nearest support is Banquereau Bank (44.24 N,
  57.10 W), 0.76 deg outside, and it reports no dew point.
- **Offshore visibility of any kind.** No marine visibility observation exists
  in or near the box. The `CW`/`CX` automatic coastal stations return no
  visibility; only CYYT, CYQX, CYDF and LFVP do, all on land.
- **Platform and ship observation.** Verified absent from every open feed
  probed: no `BBXX` on Datamart at all, no offshore METAR, no SWOB partner.
- **A retrievable fog/low-stratus satellite product.** Not on the open NOAA
  bucket. The nighttime-microphysics RGB that forecasters use for fog is
  imagery, and would be an *uncalibrated observation* at best.
- **Night coverage caveat.** `CCLF`, `ACHAF` and `ACTPF` all carry solar and
  local zenith angle validity bounds; the box is at high zenith angle from
  75.2 W and the pre-sunrise window is exactly when the day algorithms are
  unavailable. The `DQF` band must gate every retained pixel, and the retained
  record should say how many pixels survived.

### Suggested minimum admission set, by cost

| Purpose | Source | Wire/day | Retained (3 h) |
| --- | --- | ---: | ---: |
| Layered cloud, sunrise sector | GOES `ABI-L2-CCLF` (8 fields) | 44 MB | ~63 KB |
| Cloud-top height and pressure | GOES `ABI-L2-ACHAF` + `CTPF` | 450 MB | ~350 KB |
| Cloud phase | GOES `ABI-L2-ACTPF` | 518 MB | ~1.1 MB |
| Cloud mask and motion | GOES `ABI-L2-ACMF` (already ingested) | 3.79 GB | ~5.4 MB |
| Producer fog visibility | `HRDPS-WEonG_2.5km_LiquidFogVisibility` | ~25 MB/run (48 leads) | ~1.6 MB |
| SST for the air-sea difference | `RIOPS_VOTEMPER_DBS-0.5m` hourly | ~7 MB/day | ~0.3 MB |
| SST, higher resolution | `CIOPS-East_2km_SeaWaterPotentialTemp_0.5m` hourly | ~38 MB/day | ~1.3 MB |
| Observation ground truth | SmartAtlantic `SMA_st_johns` | <1 MB | <1 MB |

Dropping `ACMF` to the same 10-minute cadence but taking `ACHAF`/`CTPF` instead
of `ACHA2KMF`/`ACHTF` is the single biggest saving available: 0.45 GB against
8.35 GB per day, for a resolution loss that is a factor of five here rather
than the nominal factor of five-and-a-bit everywhere else.

## Open questions this research did not settle

1. Whether `ABI-L2-CCLF`'s `CF1`-`CF5` bands are usable at the box's local
   zenith angle at night — the granule carries
   `retrieval_local_zenith_angle_bounds`, `quantitative_local_zenith_angle_bounds`
   and `retrieval_solar_zenith_angle_bounds` but they were not read out.
2. Whether `CAPS-Ocean_3km` is a better SST than CIOPS-East given its 18 h run
   age; its box subset size was not measured.
3. Whether the Copernicus Marine licence permits republishing an OSTIA-derived
   air-sea difference on a public map. The STAC declares `proprietary`.
4. Whether `RIOPS_VOTEMPER_DBS-0.5m` (sea water temperature) and
   `CIOPS-East_2km_SeaWaterPotentialTemp_0.5m` (potential temperature) differ
   enough at 0.5 m to matter for a 1-2 K fog threshold. They are not the same
   quantity.
5. Whether the WEonG `LiquidFogVisibility` unit and its missing-value
   convention (clear sky vs no retrieval) are documented; the technote was not
   read for this field.
6. Whether the SmartAtlantic ERDDAP exposes any QC flag stream that would let
   the buoy be admitted as a retrieved observation rather than an uncalibrated
   one.
