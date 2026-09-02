> Non-normative research, 2026-09-02. Nothing here promotes a registry state,
> publishes to the store, or binds a spec. Spec-Impact: none.

# Per-source size in the evidence box with every published field

Answers wayfinder task #29. The field-catalogue decision (#18) changed the
scope of the first size probe: the evidence layer stores **every field every
admitted source publishes**, not a candidate list. Same box (45.0 to 50.5 N,
58.0 to 46.0 W), same latest-run-only retention with three hours of history,
byte-range fetches for indexed feeds and whole files for ICON.

Builds on `docs/research/wayfinder/size-probe.md` (branch `research/size-probe`)
and does not repeat it. Method, accounting rules, cell counts, and the
observation, camera, ocean and space-weather families are unchanged by this
decision and are carried forward at their measured values. What changes is the
**field count per source**, and it changes the answer.

Provenance marks, as before:

- **measured-now** — an upstream call made for this ticket on 2026-09-02.
- **from-research** — reused from a closed wayfinder ticket.
- **estimated** — arithmetic over a measured or researched unit; no call was
  made for that particular combination.

## 0. The one-line result

Under a candidate field list the whole system was **284 to 505 MB** resident and
about **40 GB per cycle** on the wire. Under "every published field" it is
**7.5 to 18.2 GB** resident and **108 GB to 1.73 TB per cycle** on the wire.
Storage stops being comfortable and bandwidth stops being merely awkward.

---

## 1. Field counts per source

GeoMet counts are from one `GetCapabilities` fetched for this ticket
(1 190 020 B, **6123 coverage ids**), counted by prefix. One WCS coverage id is
one field at one level, so the coverage count *is* the field count.

| Source | Product ids counted | Fields | Mark |
| --- | --- | --- | --- |
| **HRDPS 2.5 km** | `HRDPS.CONTINENTAL*` 343 + `HRDPS-WEonG_2.5km_*` 34 | **377** | measured-now |
| **RDPS 10 km** | `RDPS_10km_*` 404 + `RDPS-WEonG_10km_*` 34 | **438** | measured-now |
| **GDPS 15 km** | `GDPS_15km_*` 386 + `GDPS-WEonG_15km_*` 34 (+ `GDPS-GEML_25km_*` 54 on a separate 25 km grid) | **420** at 15 km, **54** at 25 km | measured-now |
| **REPS 10 km** | `REPS.MEM.*` 1239 (59 fields x 21 members) + `REPS.DIAG.*` 534 | **1773** | measured-now |
| **GEPS 0.5 deg** | `GEPS.DIAG.*` 532, reductions only, zero members | **532** | measured-now |
| **NOAA GFS 0.25** | `pgrb2` 743 records + `pgrb2b` 349, per lead, from one `.idx` each | **1092** | measured-now |
| **NOAA GEFS**, per member | `pgrb2a` 85 + `pgrb2b` 505 at 0.5 deg, `pgrb2s` 38 at 0.25 deg | **628** x 31 members | measured-now |
| **ECMWF IFS oper 0.25** | `.index` records per lead file (48 distinct params over `sfc`, `pl`, `sol`) | **184** | measured-now |
| **ECMWF AIFS single 0.25** | `.index` records per lead (30 distinct params) | **122** | measured-now |
| **ECMWF IFS ENS 0.25** | `enfo-ef` `.index` per lead (47 distinct params x 51 members) | **8500** | measured-now |
| **ECMWF AIFS-ENS 0.25** | `enfo-pf` 5400 + `enfo-cf` 108 (29 distinct params) | **5508** | measured-now |
| **DWD ICON global** | files present at lead `024` across all 102 variable directories; 18 are time-invariant | **1288** files/lead over **84** time-varying variables | measured-now |
| **GOES-19 ABI L2**, cloud and fog set | 12 products (below) | **~31 fields** per granule set | estimated |

Two counting notes that matter. **REPS publishes 59 fields per member**, not the
three the candidate list used, and the 534 `REPS.DIAG.*` reductions are separate
fields again. **ICON's 1288 files per lead** are the multi-level expansions:
`t`, `u`, `v` at 138 levels each, `qc`/`qi`/`qv`/`p` at 120, `clc` at 82,
`tke` at 61, `relhum` at 18.

## 2. Unit sizes per field per lead

GeoMet subsets server side, so wire and stored are the same number. Every
GeoMet row below is a live `GetCoverage` made for this ticket, `FORMAT=image/tiff`,
`SUBSET` on long and lat, native `SCALESIZE`.

| Coverage sampled | Bytes | Mark |
| --- | --- | --- |
| `HRDPS.CONTINENTAL_TT` (surface) | 524 230 | measured-now |
| `HRDPS.CONTINENTAL.PRES_HR.500` (pressure level) | 524 230 | measured-now |
| `HRDPS-WEonG_2.5km_LiquidFogVisibility` (post-processed) | 524 230 | measured-now |
| `HRDPS-WEonG_2.5km_SkyState` (categorical) | 524 230 | measured-now |
| `RDPS_10km_TotalCloudCover` | 32 900 | measured-now |
| `RDPS_10km_RelativeHumidity_500mb` | 32 900 | measured-now |
| `RDPS_10km_SeeingIndex` | 32 900 | measured-now |
| `GDPS_15km_TotalCloudCover` | 12 266 | measured-now |
| `GDPS_15km_RelativeHumidity_700mb` | 12 266 | measured-now |
| `GDPS-GEML_25km_AirTemp_850mb` | 4 642 | measured-now |
| `REPS.MEM.ETA_NT.01` (member surface) | 40 224 | measured-now |
| `REPS.MEM.PRES_HR.850.01` (member pressure level) | 40 224 | measured-now |
| `GEPS.DIAG.3_TT.ERC50` | 1 474 | measured-now |

**Size is a function of pixel count only**, confirmed across surface, pressure,
post-processed and categorical coverages and across level types. That is what
makes sampling two or three coverages per level type sufficient: the field
count multiplies a constant.

Off-grid feeds, stored bytes at float32 over the box (cell counts *from-research*:
0.25 deg 1 127 cells = 4 508 B; 0.5 deg 300 cells = 1 200 B; ICON at 0.125 deg
4 365 cells = 17 460 B):

| Source | Wire per lead (whole file, no server subsetting) | Stored per lead | Mark |
| --- | --- | --- | --- |
| GFS `pgrb2` + `pgrb2b` | **766 MB** (536 653 178 + 229 447 312 B, f024; f120 546 761 486 B, f240 552 051 529 B) | **4.92 MB** | measured-now (wire); estimated (stored) |
| ECMWF IFS oper | **143 MB** (143 428 302 B) | **0.83 MB** | measured-now; estimated |
| ECMWF AIFS single | **85 MB** (85 029 212 B) | **0.55 MB** | measured-now; estimated |
| DWD ICON global | **3.109 GB** (3 108 577 137 B summed over 1288 files at lead 024) | **22.49 MB** | measured-now; estimated |
| GEFS, 31 members | **4.22 GB** (136.2 MB per member: 15 505 664 + 102 388 903 + 18 352 976) | **27.26 MB** | measured-now; estimated |
| ECMWF IFS ENS, 51 members | **6.65 GB** (6 650 603 281 B) | **38.32 MB** | measured-now; estimated |
| ECMWF AIFS-ENS, 51 members | **4.53 GB** (4 443 730 187 + 88 314 515 B) | **24.83 MB** | measured-now; estimated |

**Byte-range selection stops helping.** The whole point of an `.idx` or
`.index` is to fetch a few records out of many. When the catalogue takes every
record, the byte ranges are contiguous and their sum is the file, so the wire
cost of GFS, GEFS and all four ECMWF families is now the full file. ICON was
always in that position and is no longer exceptional — it is simply the largest.

## 3. Leads per run

| Source | Runs/day | Time dimension | Core leads (3 h back to +24 h) | Planning leads (to 336 h) | Mark |
| --- | --- | --- | --- | --- | --- |
| HRDPS | 4 | `2026-09-02T00Z/2026-09-04T00Z/PT1H` = 49 steps, reach 48 h | 28 | — | measured-now |
| RDPS | 4 | `2026-09-02T06Z/2026-09-05T18Z/PT1H` = 85 steps, reach 84 h | 28 | — | measured-now |
| REPS | 4 | `2026-09-02T00Z/2026-09-05T00Z/PT3H` = 25 steps, reach 72 h | 9 | — | measured-now |
| GDPS | 2 | 137 steps, hourly to +84 h then 3-hourly to 240 h | 28 | 137 | measured-now |
| GEPS | 2 | `2026-09-02T03Z/2026-09-18T00Z/PT3H` = 129 steps, reach 384 h | — | 129 | measured-now |
| GFS | 4 | hourly to f120 then 3-hourly to f384 | 25 | 193 | from-research |
| ECMWF IFS oper | 4 (360 h at 00z/12z only) | 3-hourly to 144 h then 6-hourly | 9 | 81 | from-research |
| ECMWF AIFS single | 4 | 6-hourly to 360 h | 5 | 57 | from-research |
| ICON global | 4 (180 h at 00z/12z) | hourly to +78 h then 3-hourly, 113 steps | 25 | 113 (reach 180 h, never 14 days) | from-research |
| GEFS | 4 | 3-hourly to f240 then 6-hourly | — | 97 | from-research |
| ECMWF IFS ENS | 4 (360 h at 00z/12z) | 3-hourly to 144 h then 6-hourly | — | 81 | from-research |
| ECMWF AIFS-ENS | 4 | 6-hourly to 360 h | — | 57 | from-research |

---

## 4. ECCC GeoMet family

Resident and wire are the same number throughout.

| Source | Fields | Bytes per step | Core window (28 steps hourly, 9 at 3-hourly) | Full reach | Mark |
| --- | --- | --- | --- | --- | --- |
| **HRDPS 2.5 km** | 377 | **197.6 MB** | **5.534 GB** | 9.684 GB to 48 h | measured-now (unit, count); estimated (total) |
| **REPS 10 km**, 21 members + 534 reductions | 1773 | **71.3 MB** | **0.642 GB** | 1.783 GB to 72 h | measured-now; estimated |
| **RDPS 10 km** | 438 | **14.4 MB** | **0.403 GB** | 1.225 GB to 84 h | measured-now; estimated |
| **GDPS 15 km + 25 km GEML** | 474 | **5.40 MB** | **0.151 GB** | 0.740 GB to 240 h | measured-now; estimated |
| **GEPS 0.5 deg**, reductions | 532 | **0.78 MB** | — | 0.101 GB to 384 h | measured-now; estimated |

HRDPS at 377 fields is **74 % of the core window on its own**. The first probe
warned that HRDPS is the one source whose cost is driven by the field list
rather than the horizon; taking every field is exactly the case it warned about.
Its 206 `.PRES_*` coverages are 3.02 GB of the 5.53 GB core figure.

REPS moves from a rounding error to the second-largest ECCC item, because
"every field" means 59 per member rather than three.

## 5. Global deterministic family

| Source | Fields/lead | Core stored | Core wire | Planning stored | Planning wire | Mark |
| --- | --- | --- | --- | --- | --- | --- |
| **DWD ICON global** | 1288 | **0.562 GB** | **77.7 GB** | 2.541 GB (180 h) | **351.3 GB** | measured-now (unit); estimated (total) |
| **NOAA GFS 0.25** | 1092 | **0.123 GB** | **19.2 GB** | 0.950 GB | **147.9 GB** | measured-now; estimated |
| **ECMWF IFS oper** | 184 | 0.007 GB | 1.29 GB | 0.067 GB | 11.6 GB | measured-now; estimated |
| **ECMWF AIFS single** | 122 | 0.003 GB | 0.43 GB | 0.031 GB | 4.85 GB | measured-now; estimated |

ICON's ratio is now **138 to 1** (3.109 GB fetched for 22.5 MB kept) — better
than the 237 to 1 of the candidate list, because more of each fetched file is
actually retained, but the absolute number is 750 times worse. GFS is
**156 to 1**.

## 6. Ensemble family, members subsetted to the box

| Source | Members | Fields/lead (all members) | Leads | Stored | Wire per run | Mark |
| --- | --- | --- | --- | --- | --- | --- |
| **ECMWF IFS ENS** | 51 | 8500 | 81 | **3.104 GB** | **538.7 GB** | measured-now; estimated |
| **NOAA GEFS** | 31 | 19 468 (628 x 31) | 97 | **2.644 GB** | **409.7 GB** | measured-now; estimated |
| **ECMWF AIFS-ENS** | 51 | 5508 | 57 | **1.415 GB** | **258.3 GB** | measured-now; estimated |
| **ECCC REPS** | 21 | 1239 members + 534 reductions | core only | counted in section 4 | server-side subset, 0.642 GB | measured-now |

REPS is the only ensemble that stays cheap, and only because GeoMet subsets
server side. Everything on S3 or `data.ecmwf.int` costs its whole file.

## 7. GOES-19 ABI, full cloud and fog product set

One S3 listing per product for hour 06Z on day 245, 2026 (measured-now for
granule counts and wire bytes; stored is estimated from the box footprints in
`fog-cloud-line-of-sight-sources`: ~9.7 KB per field on the 10 km products,
~242 KB per field on the 2 km products).

| Product | Granules/h | Bytes/h on the wire | Grid |
| --- | --- | --- | --- |
| `ABI-L2-ACHA2KMF` cloud-top height 2 km | 6 | 177 809 275 | 2 km |
| `ABI-L2-ACHTF` cloud-top temperature | 6 | 175 236 368 | 2 km |
| `ABI-L2-ACMF` clear-sky mask | 6 | 159 386 007 | 2 km |
| `ABI-L2-CPSF` cloud particle size | 6 | 85 461 323 | 2 km |
| `ABI-L2-CODF` cloud optical depth | 6 | 29 657 271 | 10 km |
| `ABI-L2-DSIF` derived stability indices | 6 | 21 776 088 | 10 km |
| `ABI-L2-ACTPF` cloud-top phase | 6 | 21 640 128 | 10 km |
| `ABI-L2-CTPF` cloud-top pressure | 6 | 9 529 273 | 10 km |
| `ABI-L2-ACHAF` cloud-top height 10 km | 6 | 9 338 300 | 10 km |
| `ABI-L2-ADPF` aerosol detection (smoke, dust) | 6 | 6 817 537 | 10 km |
| `ABI-L2-TPWF` total precipitable water | 6 | 6 413 940 | 10 km |
| `ABI-L2-CCLF` layered cloud fraction | 1 | 2 059 346 | 10 km |
| **Total** | | **705 MB/h = 16.9 GB/day** | |

Resident for three hours of history: **~29 MB** (estimated). The four 2 km
products are 85 % of the traffic and about 89 % of the stored bytes.

## 8. Carried over unchanged

The field-catalogue decision does not change these; figures are *from-research*
(`size-probe.md`), restated only so the totals close.

| Family | Resident, 3 h history |
| --- | --- |
| Radar composite + lightning density over the evidence box | 25.5 MB |
| Ocean SST (CIOPS-East 2 km, RIOPS 5 km, OSTIA) | 1.6 MB |
| Point and text (SWOB, METAR, TAF, CAP, AQHI, SmartAtlantic) | 0.3 MB |
| Space weather (SWPC, GFZ, Kyoto) | 0.2 MB |
| Cameras | excluded — licence unresolved |

Their upstream traffic is also unchanged: about 265 MB/day for OVATION alone,
and 4.4 GB/day if the Coast Guard MP4 sequences are ever admitted.

---

## 9. Scenario totals

Latest run only, three hours of history, no vintage archive. Quota is 25 GiB
(26.84 GB) on `weather-artifacts`.

### Scenario A — core window only (3 h back to 24 h ahead)

| Family | Resident | Wire per cycle |
| --- | --- | --- |
| HRDPS 2.5 km, 377 fields | **5.534 GB** | 5.53 GB |
| REPS, 1773 coverages | 0.642 GB | 0.64 GB |
| ICON global, 1288 fields x 25 leads | 0.562 GB | **77.7 GB** |
| RDPS 10 km, 438 fields | 0.403 GB | 0.40 GB |
| GDPS, 474 fields | 0.151 GB | 0.15 GB |
| GFS, 1092 fields x 25 leads | 0.123 GB | **19.2 GB** |
| GOES cloud and fog set, 3 h | 0.029 GB | 2.12 GB |
| Radar + lightning | 0.026 GB | 0.03 GB |
| ECMWF IFS + AIFS single, core leads | 0.010 GB | 1.72 GB |
| Ocean, point, text, space weather | 0.002 GB | 0.28 GB |
| **Total** | **~7.48 GB** | **~108 GB** |

**28 % of the 25 GiB quota.** With `STORAGE.md`'s two-run staging overlap,
**15.0 GB, or 56 %.**

### Scenario B — core plus planning, provider reductions only

Scenario A plus GDPS to 240 h, GEPS reductions to 384 h, GFS, IFS and AIFS
single to 336 h, ICON to 180 h. No ensemble members retrieved.

| Addition | Resident | Wire per cycle |
| --- | --- | --- |
| ICON planning leads (to 180 h) | +1.979 GB | 351.3 GB total |
| GFS planning leads (to 336 h) | +0.827 GB | 147.9 GB total |
| GDPS planning leads (to 240 h) | +0.589 GB | 0.74 GB |
| GEPS reductions (to 384 h) | +0.101 GB | 0.10 GB |
| ECMWF IFS planning leads | +0.060 GB | 11.6 GB |
| ECMWF AIFS single planning leads | +0.029 GB | 4.85 GB |
| **Total** | **~11.07 GB** | **~525 GB** |

**41 % of the quota; 22.1 GB (82 %) with two-run staging.**

### Scenario C — core plus planning with ensemble members

Scenario B plus GEFS, IFS ENS and AIFS-ENS members over the box.

| Addition | Resident | Wire per cycle |
| --- | --- | --- |
| ECMWF IFS ENS, 51 members, 8500 records/lead | +3.104 GB | **538.7 GB** |
| NOAA GEFS, 31 members, 628 fields each | +2.644 GB | **409.7 GB** |
| ECMWF AIFS-ENS, 51 members, 5508 records/lead | +1.415 GB | **258.3 GB** |
| **Total** | **~18.23 GB** | **~1 732 GB (1.73 TB)** |

**68 % of the quota — and 36.5 GB, or 136 %, with two-run staging, which does
not fit.**

## 10. What quota each scenario needs, and who dominates

**Quota needed** (resident, with the two-run staging overlap `STORAGE.md`
already mandates, plus ~20 % headroom for container and manifest overhead):

| Scenario | Steady resident | With staging | Quota it needs | Verdict at 25 GiB |
| --- | --- | --- | --- | --- |
| A, core only | 7.5 GB | 15.0 GB | **~18 GB** | fits |
| B, core + planning reductions | 11.1 GB | 22.1 GB | **~27 GB** | **does not fit** — needs ~32 GiB |
| C, core + planning + members | 18.2 GB | 36.5 GB | **~44 GB** | **does not fit** — needs ~50 GiB |

The plain statement: **only Scenario A fits the current 25 GiB quota, and only
with about 7 GB to spare.** Scenario B needs the quota roughly doubled to
50 GiB to be comfortable; Scenario C needs about 64 GiB. Alternatively, if the
staging overlap is dropped in favour of atomic single-run replacement,
Scenario B fits 25 GiB and Scenario C very nearly does.

**Who dominates resident bytes:**

- **Scenario A: HRDPS, 5.53 GB, 74 %.** Its 206 pressure-level coverages are
  3.02 GB of that; dropping them alone brings Scenario A to 4.5 GB.
- **Scenario B: HRDPS 50 %, then ICON 2.54 GB (23 %).**
- **Scenario C: the three off-GeoMet ensembles together, 7.16 GB (39 %)**, with
  HRDPS still 30 %.

**Who dominates upstream bandwidth** (the harder constraint, as the first probe
already found — this decision makes it an order of magnitude harder):

- **Scenario A: ICON 77.7 GB (72 %) and GFS 19.2 GB (18 %)** of 108 GB per
  cycle. Four cycles a day is **~430 GB/day**.
- **Scenario B: ICON 351 GB (67 %) and GFS 148 GB (28 %)** of 525 GB per cycle;
  **~2.1 TB/day**.
- **Scenario C: IFS ENS 539 GB, GEFS 410 GB, ICON 351 GB, AIFS-ENS 258 GB** —
  those four are 90 % of 1.73 TB per cycle, or **~6.9 TB/day**.

Every one of the dominant bandwidth sources has the same cause: **no server-side
subsetting**. GeoMet's WCS delivers 6.7 GB of ECCC evidence per cycle for
6.7 GB on the wire. S3 and `data.ecmwf.int` deliver 11.5 GB of stored evidence
for 1.72 TB. The ratio between the two access shapes is now about **150 to 1**,
and it is the single number that decides whether the full field catalogue is
affordable.

## 11. What the numbers say

1. **The field-catalogue decision is a 26x storage change and a 43x bandwidth
   change** against the candidate list (284 MB to 7.48 GB in the core window;
   40 GB to 1.73 TB at full scope). It is not a marginal widening.
2. **Byte-range fetching no longer buys anything.** It was the mechanism that
   made GFS and ECMWF affordable; taking every record makes the range the whole
   file. The scope note in #18 that indexed feeds get byte-range fetches is
   still correct in form and now empty in effect.
3. **ICON and the ensembles are the decision points.** Dropping ICON's planning
   leads removes 2.0 GB resident and 273 GB per cycle. Dropping the three
   off-GeoMet ensembles removes 7.2 GB resident and 1.21 TB per cycle. Nothing
   else moves the totals comparably.
4. **HRDPS pressure levels are the cheapest single reduction**: 206 of its 377
   coverages are 3.02 GB per run and 55 % of the core window's biggest item, and
   the same quantity is available from RDPS at 1/16 the bytes.
5. **A level-subset lever exists and is disclosed.** `SCALESIZE` on GeoMet and
   level selection on the index feeds are both documented producer-side
   resampling, not silent transformation. A "every field, but only levels the
   activity profiles reference" catalogue would land between the candidate list
   and this probe.
6. **The two constraints now point the same way.** In the first probe storage
   was easy and bandwidth was hard. Under the full catalogue, storage is tight
   at Scenario B and impossible at Scenario C with staging, and bandwidth is
   4 to 7 TB a day. The storage ticket should set the quota against Scenario A
   and treat B and C as explicit budget increases rather than defaults.

## 12. Not measured

- GOES per-product field counts were estimated from product documentation
  shape, not read out of a NetCDF header; the ~31-field figure and the 29 MB
  resident that follows are the softest numbers in this document.
- No compression ratio was measured for any stored artifact. Every stored
  figure is raw float32 or the retrieved bytes, so all three scenario totals are
  upper bounds; GRIB2 and GeoTIFF deflate would plausibly halve them.
- ICON was summed at lead `024` only; leads with more precipitation fields may
  differ by a few per cent, and the 06z/18z cycles reach 120 h rather than 180 h.
- GEFS member count is *from-research* at 31; the S3 listing was truncated at
  1000 keys rather than enumerated.
- REPS `DIAG` and GEPS `ERMEAN` coverage ids were sampled by pattern; two probe
  ids returned the 477-byte `NoMatch` exception already documented in
  `geomet-wcs-inventory` and were replaced by ids read from the capabilities.
- Whether every one of the 6123 GeoMet coverages actually answers `GetCoverage`
  over the box was not verified; the size arithmetic assumes it does, which is
  an upper bound on both counts.
- CAPS-Ocean 3 km, unmeasured in earlier tickets, is unmeasured here.
