> Non-normative research, 2026-09-02. Nothing here promotes a registry state,
> publishes to the store, or binds a spec. Spec-Impact: none.

# Per-source artifact size in the evidence box

Answers wayfinder task #16: what each candidate source weighs per run when
subset to the **evidence box** (45.0 to 50.5 N, 58.0 to 46.0 W) — or the
**Avalon detail box** (46.6 to 48.2 N, 54.3 to 52.4 W) for high-cadence
products — with its candidate field list, and what the two-tier horizon with
three hours of history implies for the 25 GiB `weather-artifacts` quota
(`experiments/st-johns-weather-map/infra/STORAGE.md`).

Every number carries a provenance mark:

- **measured-now** — one HTTP call made for this ticket on 2026-09-02.
- **from-research** — reused from a closed wayfinder research ticket rather
  than re-measured, as the ticket instructed.
- **estimated** — arithmetic over a measured or researched unit size; no call
  was made for that particular combination.

## Accounting rules used throughout

- **Bytes on the wire** is what the retrieval costs upstream, after any
  server-side subsetting the provider offers and after byte-range selection
  where an index exists.
- **Bytes stored** is the artifact after subsetting to the box, float32 unless
  the field is categorical, before any container compression. Cell counts:
  HRDPS 2.5 km `534 x 245 = 130 830`; RDPS/REPS 10 km `133 x 61 = 8 113`;
  GDPS 15 km `80 x 37 = 2 960`; GEPS 0.5 deg `24 x 11 = 264`; global 0.25 deg
  `49 x 23 = 1 127` (**4 508 B** per field per lead); global 0.5 deg
  `25 x 12 = 300` (**1 200 B**); ICON at 0.125 deg `97 x 45 = 4 365`
  (**17 460 B**). All *from-research* (`geomet-wcs-inventory`,
  `ensemble-access`, `planning-horizon-matrix`).
- **Core window** = 3 h back to 24 h ahead. For hourly gridded products that is
  **28 time steps**; for 3-hourly products **9 steps within the forecast half**.
- **Planning window** = to 14 days (336 h) ahead, from global products only.
- **Resident size** = only the latest complete run retained, plus three hours
  of observation history. Eviction order and the three-hour floor are
  `STORAGE.md` policy.

---

## 1. Observation and nowcast, ECCC GeoMet raster

| Source | Candidate fields | Wire per frame | Stored per frame | Frames/day | Core window (3 h history) | Planning | Resident, core | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Radar composite** `RADAR_1KM_RRAI` (+ `RADAR_1KM_RSNO`) | rain rate; snow rate | **754 B** PNG over the Avalon box, **3 568 B** PNG over the evidence box — both a *clear-sky floor*, there was no echo at probe time | uint8 1 km: **25 454 B** Avalon (143 x 178), **551 412 B** evidence box (901 x 612) | **240** (`PT6M`, verified from the WMS time dimension `2026-09-02T05:30Z/08:30Z/PT6M`) | 30 frames | none (observation) | ~**16 MB** for two products over the evidence box; ~0.8 MB if kept at Avalon extent only | measured-now (sizes, cadence); estimated (stored, echo-filled) |
| **Lightning density** `Lightning_2.5km_Density` | flash density | **24 376 B** Avalon (`SCALESIZE=long(57),lat(71)`); **526 366 B** evidence box (`long(534),lat(245)`) | same, GeoTIFF float32 | **144** (`PT10M`, window `05:20Z/08:20Z`) | 18 frames | none | **9.5 MB** evidence box; 0.44 MB Avalon only | measured-now |

**New finding, measured-now: GeoMet does not serve radar over WCS.** A
`GetCoverage` on `RADAR_1KM_RRAI` with the same parameter shape that works for
HRDPS returns HTTP **200** with an `ows:ExceptionReport` body of 559 B:
`msWCSDispatch(): WCS server error. WCS request not enabled.` The radar
composite is reachable only as **WMS `GetMap`**, i.e. as a rendered raster, not
as a coverage. `geomet-wcs-inventory`'s warning that a 200 status alone proves
nothing applies here too. Lightning density *is* on WCS and behaves normally.
Both layers advertise a rolling **three-hour** time dimension, which matches the
charter's history floor exactly — GeoMet keeps no more than we intend to.

---

## 2. Observation and nowcast, point and text

| Source | Candidate fields | Wire per cycle | Stored per cycle | Cycles/day | Core window | Resident, core | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **SWOB-ML XML**, MSC stations | air/dew temp, RH, MSLP, wind avg/gust/dir, visibility, precip, snow depth | **8 107 B** (`CAAB`, AUTO), **6 356 B** (`CYYT`, MAN), **5 881 B** (`CYQX`, MAN) per station-hour | ~1 KB per station-hour after field selection | 24 | **25 stations in the box**, 5 in the Avalon box | wire ~**510 KB** for 3 h; stored ~**75 KB** | measured-now |
| **SWOB-ML XML**, partner stations | as above, provider-dependent | ~7 KB per station-hour | ~1 KB | 24 | **26 stations in the box**, 6 in the Avalon box | wire ~**546 KB** for 3 h; stored ~**78 KB** | measured-now (counts); estimated (size) |
| **SWOB marine** | sea surface temp, waves | n/a | n/a | n/a | **0 stations in the box** — confirms `fog-cloud-line-of-sight-sources` | 0 | measured-now |
| **METAR/SPECI**, box | visibility, ceiling, layers, present weather, temp, dew point, wind | **3 991 B** for the whole box (10 ICAO stations), **482 B** for `CYYT` alone | ~0.5 KB | 24 + specials | 10 stations | ~**12 KB** | measured-now |
| **TAF** `CYYT` | forecast ceiling, visibility, wind, weather groups | **2 926 B** | ~3 KB | 4 | latest only | ~**3 KB** | measured-now |
| **CAP alerts** via `weather-alerts` | event, severity, urgency, area, onset/expiry | **10 165 B** for the box | ~10 KB | event-driven, poll 10 min | latest set | ~**10 KB** | measured-now |
| **AQHI observations** `aqhi-observations-realtime` | AQHI index by community | **58 808 B** for the box | ~5 KB | 24 | 3 h | ~**15 KB** | measured-now |
| **AQHI forecasts** `aqhi-forecasts-realtime` | AQHI forecast by community | **116 567 B** for the box | ~10 KB | 2-4 | latest only | ~**10 KB** | measured-now |
| **SmartAtlantic** `SMA_st_johns` ERDDAP | air/dew temp, RH, **sea surface temp**, pressure, wind, waves, currents | **1 683 B** for the last hour; **2 986 B** for the last 3 h (CSV, server-side time selection) | ~3 KB | 48 (`PT30M`) | 3 h | ~**3 KB** | measured-now |

The dataset id is `SMA_st_johns` with underscores; `SMA_stjohns` is a **404**
(measured-now) — worth recording because the wrong spelling fails silently as a
plain not-found rather than an ERDDAP error page.

The whole point-and-text family is **under 1 MB resident**. It is the cheapest
evidence in the system and the only ground truth over water.

---

## 3. Space weather

| Source | Wire per fetch | Stored per fetch | Fetches/day | Resident, core (3 h) | Mark |
| --- | --- | --- | --- | --- | --- |
| SWPC RTSW magnetic field `rtsw_mag_1m.json` | **1 537 483 B** (rolling 24 h) | ~15 KB for 3 h of 1-min records | poll 5 min, 288 | ~**15 KB** | measured-now |
| SWPC RTSW plasma `rtsw_wind_1m.json` | **2 640 869 B** (rolling 24 h) | ~25 KB for 3 h | 288 | ~**25 KB** | measured-now |
| SWPC 1-minute Kp `planetary_k_index_1m.json` | **27 925 B** | ~3 KB | 288 | ~**3 KB** | measured-now |
| SWPC alerts `alerts.json` | **40 957 B** | ~41 KB | event-driven | ~**41 KB** | measured-now |
| SWPC NOAA scales `noaa-scales.json` | **1 099 B** | ~1 KB | 24 | ~**1 KB** | measured-now |
| SWPC OVATION `ovation_aurora_latest.json` | **921 312 B** (global 1 deg grid) | box subset ~6 x 12 cells, **< 1 KB** | 288 (`PT5M`) | ~**36 KB** for 36 frames | measured-now (wire); estimated (subset) |
| GOES magnetometer, GOES XRS, GFZ Hp30, Kyoto Dst | 261 KB / 654 KB / small / 7 KB | few KB each | 1-min to hourly | ~**50 KB** total | from-research (`space-weather-sources`) |

Space weather is **~0.2 MB resident**, but **~265 MB/day of upstream traffic
for OVATION alone** if polled at its 5-minute cadence, for under 1 KB of
retained evidence per frame. The whole family is a bandwidth question, never a
storage one.

---

## 4. Satellite and ocean

| Source | Candidate fields | Wire per frame | Stored per frame | Frames/day | Core window (3 h) | Resident, core | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOES-19 `ABI-L2-CCLF` | `CF1`-`CF5`, `TCF`, `CL` — layered cloud fraction | 1.82 MB granule | **~21 KB** for the 8-field set | 24 (hourly) | 3 frames | ~**63 KB** | from-research (`fog-cloud-line-of-sight-sources`) |
| GOES-19 `ABI-L2-ACHAF` + `ABI-L2-CTPF` (10 km) | cloud-top height, cloud-top pressure | 1.54 + 1.57 MB | ~9.7 KB each | 144 each | 18 frames each | ~**350 KB** | from-research |
| GOES-19 `ABI-L2-ACHA2KMF` (2 km) | cloud-top height | 29.2 MB | ~242 KB | 144 | 18 frames | ~**4.4 MB** (and **4.2 GB/day** on the wire) | from-research |
| CIOPS-East 2 km SST | sea water potential temp 0.5 m | **440 748 B** per hour, server-side subset | same | 24 | 3 hours | ~**1.3 MB** | from-research |
| RIOPS 5 km SST | sea water temp 0.5 m | **77 154 B** per hour | same | 24 | 3 hours | ~**231 KB** | from-research |
| OSTIA L4 Zarr | foundation SST | ~52.8 KB/day (`timeChunked`) | same | 1 | latest | ~**53 KB** | from-research |

The 2 km cloud-top family is the only satellite item whose *wire* cost is in
gigabytes per day for megabytes retained; the 10 km family plus hourly `CCLF`
delivers most of the signal for about 1 % of the traffic.

---

## 5. Cameras

| Source | Wire per frame | Stored per frame | Cadence | Resident, core (3 h) | Mark |
| --- | --- | --- | --- | --- | --- |
| NTV sky-dome cam `thumb_st-johns-sky-cam.jpg` | **181 321 B** | same (JPEG kept as retrieved) | ~13 min, undocumented | ~**2.5 MB** (14 frames) | measured-now |
| City of St. John's road JPEGs (6 cameras) | **32 935 B** measured for Shea Heights; 34-73 KB across the set | same | ~10 min | ~**5.4 MB** (6 x 18 frames) | measured-now (one); from-research (`camera-inventory`) |
| Coast Guard MP4 sequences (3 cameras) | 14.0-31.7 MB each | same | ~20 min | ~**190 MB** if admitted — **4.4 GB/day** on the wire | from-research |

Cameras are the largest observation item by a wide margin, and the Coast Guard
MP4 sequences alone would consume more resident bytes than every gridded model
in the core window combined. `camera-inventory` leaves their redistribution
unresolved and NTV's rights reserved, so **no camera is costed into the
scenario totals below**; the JPEG figures are recorded so the licence decision
can be made against a real number.

---

## 6. ECCC gridded models over the box (GeoMet WCS)

Unit sizes all *from-research* (`geomet-wcs-inventory`), at native `SCALESIZE`
with `FORMAT` set and `SUBSET` rather than `BBOX`. GeoMet subsets server side,
so wire and stored bytes are the same number.

| Source | Candidate fields | Bytes per field per step | Runs/day | Core leads | Planning leads | Resident, core | Resident, planning | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **HRDPS 2.5 km** | 2 m temp, dew point, 2 m RH, 40/80/120 m temp and wind, wind speed and direction, MSLP, `LiquidFogVisibility`, skin temp, boundary-layer height, UV index, humidex, wind chill — **14 fields** | **524 230 B** | 4 | 28 (hourly, 3 h back to +24 h) | — (reach 48 h) | **205 MB** | n/a | from-research (unit); estimated (total) |
| **RDPS 10 km** | the 14 above plus seeing and sky transparency — **16 fields** | **32 900 B** | 4 | 28 | — (reach 84 h) | **14.7 MB** | n/a | from-research; estimated |
| **GDPS 15 km** | total cloud, 2 m RH, RH 850/700/500, 2 m temp, wind speed and direction, MSLP, UV index — **10 fields** | **12 266 B** | 2 | 25 | 137 steps to 240 h | 3.1 MB | **16.8 MB** | from-research; estimated |
| **REPS 10 km**, 21 members | `ETA_NT` cloud, `ETA_HR` RH, `ETA_WSPD` speed — **3 fields** | **40 224 B** per member per field per step | 4 | 9 (3-hourly to +24 h) | — (reach 72 h) | **22.8 MB** | n/a | from-research; estimated |
| **GEPS 0.5 deg**, reductions only | mean, stdev and 10 percentile reductions over cloud, temp, wind speed, humidex — **48 series** | **~1 500 B** | 2 | — | 129 steps (3-hourly to 384 h) | — | **9.3 MB** | from-research; estimated |

HRDPS dominates the core window: at 0.52 MB per field per step it costs more
resident bytes than every other model and every observation source put
together. It is also the only source whose cost scales badly with the field
list — `geomet-wcs-inventory` measured the 28 pressure-level RH coverages at
**424 MB per run**, which is why they are excluded from the candidate list
above and RH is taken at three levels from the global models instead.

---

## 7. Global deterministic models

| Source | Candidate fields | Wire per lead | Stored per lead | Runs/day | Core leads | Planning leads (to 336 h) | Resident, core | Resident, planning | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **NOAA GFS 0.25** | `TCDC`/`LCDC`/`MCDC`/`HCDC` (instantaneous), `RH:2m`, `TMP:2m`, `DPT:2m`, `UGRD:10m`, `VGRD:10m`, `PWAT`, `VIS:surface` — **11 fields** | **8 553 996 B** summed from the `.idx` byte spans; one range fetch confirmed (`TCDC` 839 114 B, HTTP 206, 0.76 s) | **49 588 B** | 4 | 25 | 193 (hourly to 120 h, 3-hourly to 336 h) | **1.24 MB** | **9.6 MB** (**1.65 GB** on the wire) | measured-now |
| **ECMWF IFS oper 0.25** | `tcc`, `2t`, `2d`, `10u`, `10v`, `tcwv`, `msl`, `r` at 850/700/500 — **10 fields** | **6 245 027 B** from the `.index` (`4 615 233` surface + `1 629 794` for three RH levels); whole per-lead file is **143 534 892 B** | **45 080 B** | 4 (full 360 h reach only at 00z/12z) | 9 (3-hourly) | 81 (3-hourly to 144 h, 6-hourly to 336 h) | **0.4 MB** | **3.7 MB** (**506 MB** on the wire) | measured-now |
| **ECMWF AIFS single 0.25** | `tcc`, `lcc`, `mcc`, `hcc`, `2t`, `2d`, `10u`, `10v`, `tcw`, `msl` — **10 fields** | **8 910 199 B** from the `.index`; whole per-lead file is **84 930 520 B** | **45 080 B** | 4 (full reach every cycle) | 5 (6-hourly) | 57 (6-hourly to 336 h) | **0.23 MB** | **2.6 MB** (**508 MB** on the wire) | measured-now |
| **DWD ICON global** | `clct`, `clcl`, `clcm`, `clch`, `relhum_2m`, `t_2m`, `td_2m`, `u_10m`, `v_10m`, `tqv` — **10 fields** | **4 136 447 B** per field per lead (`CLCT` f024, bz2, whole global icosahedral field — **no index, no server-side subsetting**) | **17 460 B** at 0.125 deg | 4 | 25 | 113 steps but reach is **180 h**, so it never enters the 14-day tier | **4.4 MB** (**1.03 GB** on the wire) | **19.7 MB** to 180 h (**4.67 GB** on the wire) | measured-now |

ICON is the pathological case: the fastest producer in the matrix
(`planning-horizon-matrix` measured T+2 h 44 m) and the only one with no byte
selection at all, so **4.1 MB must cross the wire for every 17 KB retained** —
a ratio of 237 to 1. GFS by contrast costs 8.6 MB per lead for 49 KB retained,
a ratio of 172 to 1, but pays it once per lead for eleven fields rather than
once per field.

---

## 8. Ensembles, members subsetted to the box

Wire figures *from-research* (`ensemble-access`); stored figures are the box
cell count times the member and field count.

| Source | Members | Candidate fields | Wire per field per lead, all members | Stored per member per field per lead | Planning leads | Resident, planning | Mark |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **ECCC REPS** | 21 | 3 (`ETA_NT`, `ETA_HR`, `ETA_WSPD`) | **844 704 B** (server-side subset, 40 224 B per member) | **40 224 B** | core only, 72 h reach | counted in section 6 | from-research |
| **NOAA GEFS** | 31 | 4 (`HGT:cloud ceiling`, `CWAT`, `TCDC:475 mb`, `RH:2m`) — **no instantaneous column cloud exists** | **~7.7 MB** (0.5 deg `pgrb2a`), ~2.3 MB for the 475 mb cloud | **1 200 B** (0.5 deg) | 97 (3-hourly to 240 h, 6-hourly to 336 h) | **14.4 MB** (**2.99 GB** on the wire) | from-research; estimated |
| **ECMWF IFS ENS** | 51 | 4 (`tcc`, `r850`, `10u`, `10v`) | **~29 MB** | **4 508 B** | 81 | **74.4 MB** (**9.4 GB** on the wire) | from-research; estimated |
| **ECMWF AIFS-ENS** | 51 | 6 (`tcc`, `lcc`, `mcc`, `hcc`, `10u`, `10v`) — **the only per-member layered cloud anywhere** | **~72 MB** | **4 508 B** | 57 | **78.5 MB** (**24.6 GB** on the wire) | from-research; estimated |

Subsetting is what makes ensembles affordable. AIFS-ENS costs **24.6 GB of
upstream traffic per run** — very nearly the entire 25 GiB quota in bandwidth
alone — to leave **78.5 MB** on disk. The storage question and the bandwidth
question have opposite answers for every ensemble family.

---

## 9. Scenario totals

Latest run only, three hours of observation history, no vintage archive.

### Scenario A — core window only (3 h back to 24 h ahead)

| Family | Resident |
| --- | --- |
| HRDPS 2.5 km, 14 fields | 205 MB |
| REPS, 21 members, 3 fields | 22.8 MB |
| RDPS 10 km, 16 fields | 14.7 MB |
| Radar composite + lightning density, evidence box | 25.5 MB |
| GDPS core leads | 3.1 MB |
| ICON global core leads | 4.4 MB |
| Satellite and ocean (10 km cloud-top, `CCLF`, CIOPS-East, RIOPS, OSTIA) | 6.4 MB |
| GFS core leads | 1.2 MB |
| ECMWF IFS + AIFS single, core leads | 0.6 MB |
| Point, text, AQHI, alerts, SmartAtlantic | 0.3 MB |
| Space weather | 0.2 MB |
| **Total** | **~284 MB** |

**Fits in 25 GiB: yes, with about 1.1 % of the quota used.**

### Scenario B — core plus planning, provider reductions only

Scenario A plus GDPS to 240 h, GEPS reductions to 384 h, GFS, IFS and AIFS
single to 336 h, ICON to 180 h. No ensemble members retrieved.

| Addition | Resident |
| --- | --- |
| ICON planning leads (to 180 h) | +15.3 MB |
| GDPS planning leads (to 240 h) | +13.7 MB |
| GFS planning leads (to 336 h) | +9.6 MB |
| GEPS reductions (to 384 h) | +9.3 MB |
| ECMWF IFS planning leads | +3.3 MB |
| ECMWF AIFS single planning leads | +2.4 MB |
| **Total** | **~338 MB** |

**Fits in 25 GiB: yes, about 1.3 % of the quota.**

### Scenario C — core plus planning with ensemble members subsetted

Scenario B plus GEFS, IFS ENS and AIFS-ENS members over the box.

| Addition | Resident |
| --- | --- |
| ECMWF AIFS-ENS, 51 members, 6 fields | +78.5 MB |
| ECMWF IFS ENS, 51 members, 4 fields | +74.4 MB |
| NOAA GEFS, 31 members, 4 fields | +14.4 MB |
| **Total** | **~505 MB** |

**Fits in 25 GiB: yes, about 2.0 % of the quota.**

`STORAGE.md`'s eviction order retains "model runs older than the latest and
previous complete run", so a two-run overlap during staging roughly doubles
every figure: **~1.0 GB** at Scenario C, still **4 %** of the quota. Even
retaining every candidate camera stream, including the Coast Guard MP4
sequences at 190 MB resident, keeps the total under 1.3 GB.

## 10. What the numbers actually say

1. **Storage is not the binding constraint. Bandwidth is.** All three scenarios
   fit in 25 GiB with room to spare, but Scenario C costs roughly **40 GB of
   upstream traffic per model cycle** — AIFS-ENS 24.6 GB, IFS ENS 9.4 GB, GEFS
   3.0 GB, ICON 4.7 GB — against about 220 MB of new resident bytes. The
   charter's instruction that every admission decision state its size in the
   box should be read as **two** numbers: bytes retained and bytes fetched.
2. **HRDPS is 72 % of the core window on its own** and is the only source where
   the field list, not the horizon, drives the cost. Adding its 28 pressure-level
   RH coverages would take the core window from 284 MB to 708 MB in one step.
3. **The cheapest signal per byte is the point network.** Fifty-one SWOB
   stations, ten METARs, the SmartAtlantic buoy, AQHI and CAP alerts together
   are **under 1 MB resident** and are the only in-situ evidence in the box.
4. **Cameras are the observation cost centre**, not the models: the six road
   JPEGs plus the NTV sky cam are 7.9 MB resident, and the three Coast Guard
   MP4 sequences would be 190 MB and 4.4 GB/day. Every one of them is
   licence-unresolved, so the cost is hypothetical until permission exists.
5. **Radar is WMS-only.** Any ingest design that assumed a WCS coverage for the
   1 km composite needs rewriting against `GetMap`, and the retained artifact is
   a rendered raster rather than a coverage — which bears on whether it can be
   called retrieved evidence at all.
6. **Both nowcast rasters already expire at three hours upstream.** GeoMet's
   own time dimension for radar and lightning is exactly the charter's history
   floor, so nothing is lost by matching it and nothing deeper is available.

## 11. Not measured

- Echo-filled radar frame sizes. Every radar probe landed on a clear scene, so
  the compressed per-frame figure is a floor; only the uncompressed bound is
  reliable.
- Partner SWOB per-station file sizes were taken from the MSC files rather than
  fetched for all 26 stations.
- REPS, GEPS and GDPS lead-step enumerations were reused rather than
  re-enumerated; the step counts above are the researched cadences applied
  arithmetically.
- CAPS-Ocean 3 km, still unmeasured in `fog-cloud-line-of-sight-sources`, is
  unmeasured here too.
- No compression ratio was measured for any stored artifact. Every "stored"
  figure is raw float32 or the retrieved bytes, so all three scenario totals are
  upper bounds.
