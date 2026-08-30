# Live Endpoint Recon — St. John's Weather Map (46 credential-free sources)

Probed 2026-08-29 (UTC-ish, HRDPS/RDPS/GDPS run cycles seen: 00/06/12Z). All curl calls used
`-A "astraeus-weather-experiment/0.1 (research; contact tushar.sariya77@gmail.com)"` and `--max-time 30`.

## Summary Table

| id | status | notes |
|---|---|---|
| eccc-hrdps | VERIFIED | real path differs from registry root; see below |
| eccc-rdps | VERIFIED | |
| eccc-gdps | VERIFIED | |
| noaa-gfs | PENDING | |
| ecmwf-ifs | PENDING | |
| dwd-icon-global | PENDING | |
| awc-metar-speci | PENDING | |
| eccc-swob | PENDING | |
| (remaining 38) | PENDING | |

(table will be filled in as probing proceeds; this is a live working doc)

---

## eccc-hrdps

- **Status:** VERIFIED
- **Registry claims:** `https://dd.weather.gc.ca/today/model_hrdps/`
- **Reality:** that root IS correct as a directory, but it only contains subdirs — real data path requires
  walking further: `today/model_hrdps/continental/2.5km/{00,06,12,18}/{FFF}/`
- **Discovery URL (200 confirmed):**
  `https://dd.weather.gc.ca/today/model_hrdps/continental/2.5km/12/000/` (Apache autoindex HTML)
- **Fetch URL template (200 confirmed):**
  `https://dd.weather.gc.ca/today/model_hrdps/continental/2.5km/{HH}/{FFF}/{YYYYMMDD}T{HH}Z_MSC_HRDPS_{VAR}_{LEVEL}_RLatLon0.0225_PT{FFF}H.grib2`
  Example verified 200 (HEAD): `.../12/000/20260829T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2`
  - HH = run cycle (00/06/12/18), FFF = forecast hour zero-padded to 3 digits (000..048, HRDPS is short-range)
  - grid = RLatLon0.0225 (~2.5 km continental rotated lat-lon grid)
- **Subsetting:** NO `.idx`/`.index` sidecar exists (confirmed 404 on `<file>.idx`). BUT this is largely moot:
  each GRIB2 file already contains exactly ONE variable/level/forecast-hour message (ECCC datamart splits by
  var+level+hour into separate files), so there is nothing to subset — just fetch the whole small file.
  `Accept-Ranges: bytes` IS advertised by the Apache server if partial fetches are ever needed.
- **Size:** `TMP_AGL-2m` PT000H file = 3,574,309 bytes (~3.4 MB) via `curl -sI`. Sizes vary per field: e.g.
  ABSV_ISBL fields were 2.5–3.5 MB.
- **Variable naming (upstream GRIB abbreviations):**
  - 2m temp: `TMP_AGL-2m`
  - 2m dewpoint: `DPT_AGL-2m`
  - 2m RH: `RH_AGL-2m`
  - 10m wind: `UGRD_AGL-10m` / `VGRD_AGL-10m` / `WIND_AGL-10m` (speed) — no WDIR at 10m seen in HRDPS (RDPS/GDPS have WindDir)
  - precip: `APCP` (accum, not present at PT000H — appears from PT001H onward), `ACPCP` (convective), `PRATE` (rate)
  - precip type: `PTYPE`
  - visibility: NOT FOUND in HRDPS surface file list at PT000H or PT001H (checked both). Registry claims
    `visibility` as a variable — could not verify a `VIS` file exists; flagging as UNCONFIRMED/likely absent
    from continental 2.5km surface set.
  - cloud cover: only `TCDC` (total cloud) found — no LCDC/MCDC/HCDC (low/mid/high) in this directory,
    contradicting registry's `low_cloud`/`middle_cloud`/`high_cloud` claim for this specific product tier.
  - MSLP: `PRMSL_MSL`
  - gust: `GUST`
- **Auth/rate-limit:** none observed; plain Apache directory listing, no 403/429.
- **Sample (directory listing excerpt):**
  ```
  <a href="20260829T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2">...</a> 2026-08-29 14:54 3.4M
  ```

## eccc-rdps

- **Status:** VERIFIED
- **Registry claims:** `https://dd.weather.gc.ca/today/model_rdps/`
- **Reality:** root has subdirs `10km/`, `matrices/`, `stat-post-processing/`. Real path:
  `today/model_rdps/10km/{HH}/{FFF}/`
- **Fetch URL template (200 confirmed via listing):**
  `https://dd.weather.gc.ca/today/model_rdps/10km/{HH}/{FFF}/{YYYYMMDD}T{HH}Z_MSC_RDPS_{VAR}_{LEVEL}_RLatLon0.09_PT{FFF}H.grib2`
  Example: `.../10km/12/000/20260829T12Z_MSC_RDPS_AirTemp_AGL-2m_RLatLon0.09_PT000H.grib2`
- **IMPORTANT NAMING DIFFERENCE vs HRDPS:** RDPS (and GDPS) use human-readable CamelCase variable names,
  NOT GRIB2 abbreviation codes like HRDPS does. E.g. `AirTemp` not `TMP`, `DewPoint` not `DPT`,
  `WindSpeed`/`WindU`/`WindV`/`WindDir` not `UGRD`/`VGRD`/`WIND`/`WDIR`, `Pressure_MSL` not `PRMSL_MSL`,
  `TotalCloudCover` not `TCDC`. This is a real inconsistency across ECCC datamart products that a single
  parser cannot assume is uniform.
- **Level tokens:** `AGL-2m`, `AGL-10m`, `AGL-40m`, `AGL-80m`, `AGL-120m`, `IsbL-0001`..`IsbL-1015` (isobaric,
  note capitalization `IsbL` vs HRDPS's `ISBL`), `Sfc`, `MSL`, `EAtm`.
- **Variable naming confirmed present:** `AirTemp`, `DewPoint`, `DewPointDepression`, `SpecificHumidity`,
  `WindU`, `WindV`, `WindSpeed`, `WindDir`, `WindGust`, `Pressure_MSL`, `Pressure_Sfc`, `TotalCloudCover`,
  `CloudWater`, `Humidex`, `WindChill`. No plain `RH_` name seen at first pass — likely derive from
  DewPointDepression, needs follow-up. No visibility variable found in the sfc file list (same gap as HRDPS).
- **Subsetting:** not checked yet (expect same as HRDPS: no idx, one-var-per-file).
- **Size:** not checked yet (HEAD not run).
- **Auth/rate-limit:** none observed.

## eccc-gdps

- **Status:** VERIFIED (partial — same family as RDPS)
- **Registry claims:** `https://dd.weather.gc.ca/today/model_gdps/`
- **Reality:** root has `10km/`, `15km/`, `matrices/`, `stat-post-processing/`. GDPS is global — use `15km/`.
  Path: `today/model_gdps/15km/{HH}/{FFF}/` (HH cycles seen: 00, 12 only — GDPS runs 4x/day at 00/06/12/18
  but only 00/12 subdirs were populated at probe time, 06/18 may lag or not yet post).
- **Fetch URL template:** `https://dd.weather.gc.ca/today/model_gdps/15km/{HH}/{FFF}/{YYYYMMDD}T{HH}Z_MSC_GDPS_{VAR}_{LEVEL}_RLatLon0.15_PT{FFF}H.grib2` (grid spacing token unconfirmed — need to verify 0.15 vs another value)
  Confirmed 200 via listing: `.../15km/12/000/20260829T12Z_MSC_GDPS_TMP_AGL-2m...` — NOTE: need to recheck,
  GDPS var-name grep partial output showed CamelCase like RDPS (`AirTemp`, `DewPoint`), same convention family.
  ADDITIONAL var: `ConvectivePrecip-Accum` present in GDPS list not seen yet in RDPS partial grep.
- **Subsetting/size:** not yet checked.

---
(Recon continuing — remaining Group 1 sources noaa-gfs, ecmwf-ifs, dwd-icon-global, awc-metar-speci,
eccc-swob, plus Groups 2 and 3, to follow.)

---
# Continued recon (main session, 2026-08-29 ~20:40Z)

## noaa-gfs — VERIFIED (critical findings)

- **Listing:** `https://noaa-gfs-bdp-pds.s3.amazonaws.com/?list-type=2&prefix=gfs.{YYYYMMDD}/{HH}/atmos/` (anonymous, 200)
- **GRIB2:** `https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{YYYYMMDD}/{HH}/atmos/gfs.t{HH}z.pgrb2.0p25.f{FFF}`
- **Sidecar:** same key + `.idx` — EXISTS and is fetchable.
- **`Accept-Ranges: bytes` confirmed. Content-Length of ONE f003 file = 546,278,338 bytes (521 MiB).**
  Whole-file fetching is impossible: 25 lead hours x 546 MB = ~13.6 GB for GFS alone, before GEFS'
  30 members. Byte-range subsetting via .idx is MANDATORY, not an optimization.
- **.idx format** (colon-delimited, 6 fields, NO trailing end-offset):
  ```
  1:0:d=2026082900:PRMSL:mean sea level:3 hour fcst:
  581:423841774:d=2026082900:TMP:2 m above ground:3 hour fcst:
  583:425590808:d=2026082900:DPT:2 m above ground:3 hour fcst:
  584:426128305:d=2026082900:RH:2 m above ground:3 hour fcst:
  588:428490334:d=2026082900:UGRD:10 m above ground:3 hour fcst:
  589:429471366:d=2026082900:VGRD:10 m above ground:3 hour fcst:
  596:433732056:d=2026082900:APCP:surface:0-3 hour acc fcst:
  ```
  Range for record N = [offset(N), offset(N+1)-1]. THE LAST RECORD HAS NO SUCCESSOR — must send an
  open-ended `Range: bytes=<offset>-`. This is the edge case to unit-test.
  Worked example: TMP 2m = bytes 423841774-425590807 = ~1.7 MB (vs 521 MiB whole file).
- **Variable names:** `TMP`/`DPT`/`RH` @ `2 m above ground`; `UGRD`/`VGRD` @ `10 m above ground`;
  `APCP:surface:0-3 hour acc fcst` (accumulation WITH explicit interval — matches the project's
  precipitation-interval rule, do not convert to a rate); `VIS:surface`; `GUST:surface`;
  `PRMSL:mean sea level`; `TCDC:entire atmosphere`.
- **NOTE — GFS HAS VISIBILITY (`VIS:surface`) where HRDPS/RDPS appear NOT to.** Since fog is a headline
  output for St. John's, GFS may be our only gridded visibility source. Worth confirming against HRDPS.

## awc-metar-speci — VERIFIED
- `https://aviationweather.gov/api/data/metar?ids=CYYT&format=json&hours=4` -> 200, JSON array.
- Fields: `temp`, `dewp`, `wdir`, `wspd`, `visib`, `altim`, `slp`, `wxString`, `clouds[{cover,base}]`,
  `fltCat`, `rawOb`, `reportTime`, `lat`/`lon`/`elev`, `metarType` (METAR vs SPECI).
- `hours=` parameter gives us the -3h backward half directly. No auth, no key.
- Live sample confirms real signal: 18C/dewp 17C, visib 4SM, `-SHRA BR`, OVC008, IFR.

## awc-taf — VERIFIED
- `https://aviationweather.gov/api/data/taf?ids=CYYT&format=json` -> 200.
- Gives `rawTAF`, `validTimeFrom`/`validTimeTo` (epoch), `issueTime`. Covers our +24h forward half.

## ecmwf-ifs — VERIFIED
- Layout: `https://data.ecmwf.int/forecasts/{YYYYMMDD}/{HH}z/ifs/0p25/oper/`
- Files: `{YYYYMMDD}{HHMMSS}-{F}h-oper-fc.grib2` with a matching `.index` sidecar. Both confirmed present.
- `.index` is JSON-lines (ECMWF format, NOT the NOAA colon format) — needs its own parser with
  `_offset`/`_length` fields. Do not reuse the NOAA .idx parser.

## dwd-icon-global — VERIFIED
- `https://opendata.dwd.de/weather/nwp/icon/grib/{HH}/{var}/` e.g. `.../00/t_2m/`
- Files: `icon_global_icosahedral_single-level_{YYYYMMDDHH}_{FFF}_{VAR}.grib2.bz2`
- Split one variable/level/hour per file (like ECCC) AND bz2-compressed, so no byte-range needed —
  but the adapter MUST decompress. Native grid is ICOSAHEDRAL, not lat/lon: regridding is required
  before it can be sampled at a point. This is materially more work than the other global models.

## MAJOR SIMPLIFICATION: SWOB is an OGC API Features collection

`https://dd.weather.gc.ca/observations/swob-ml/latest/` returned NO parseable links, but
`api.weather.gc.ca` exposes SWOB (and much else) as OGC API Features. Prefer the API over raw
datamart XML: it collapses the planned "ECCC Datamart XML" adapter family into the SAME OGC client
used for AQHI/hydrometric/marine/hurricane. Fewer parsers, one auth-free JSON path.

**Confirmed collection ids** (from `GET /collections?f=json`):
- `swob-realtime`, `swob-stations`, `swob-partner-stations`, `swob-marine-stations`
- `aqhi-observations-realtime`, `aqhi-forecasts-realtime`, `aqhi-stations`
- `hydrometric-realtime`, `hydrometric-stations`
- `marineweather-realtime` (Marine forecasts and warnings [experimental])
- `hurricanes-cyclone-realtime`, `hurricanes-track-realtime`, `hurricanes-error_cone-realtime`, `hurricanes-wind_radii-realtime`
- `climate-hourly`, `climate-daily`, `climate-normals` (useful later for bias correction baselines)

### TRAP — default ordering is NOT newest-first
An unfiltered `items?bbox=...` query returned a SWOB record dated **2026-07-31** (a month stale) and an
AQHI record from **2026-08-27** flagged `latest: False`. An adapter that takes `features[0]` would
publish month-old data as current evidence. ALWAYS constrain with `datetime={start}/{end}`.

- **Working SWOB query (VERIFIED):**
  `https://api.weather.gc.ca/collections/swob-realtime/items?bbox=-55.0,46.5,-51.0,48.5&datetime={ISO}/{ISO}&limit=N&f=json`
  A 4-hour Avalon window returned `numberMatched: 510`. This covers our -3h backward half directly.
- **SWOB property names:** `air_temp`, `dwpt_temp`, `rel_hum`, `avg_air_temp_pst1hr`, `stn_nam-value`,
  `date_tm-value`, plus per-field `-uom` (units) and `-qa` / `-data_flag-value` (QC) siblings.
  **The `-qa` / `-data_flag` siblings must be carried into Provenance.quality — they are real QC flags
  and the project forbids presenting unvalidated values as passed.**
  `vis` was None at the Avalon stations sampled — visibility is NOT reliably present in SWOB either.
- Live sample: CAPE RACE (AUT) T=15.9 Td=15.9 RH=100 — saturated, i.e. fog at the headland at probe time.
- **AQHI:** St. John's `location_id` = `ABEFS`. `latest=True` as a query param returned nothing (wrong
  spelling — do not use it); filter by `datetime` instead and take the max observation_datetime.

## VISIBILITY / FOG — cross-source conclusion
Neither HRDPS, RDPS nor SWOB reliably carries visibility. Confirmed gridded sources for `VIS`:
**NOAA GFS (`VIS:surface`)**. Confirmed point source: **AWC METAR `visib` at CYYT**.
Fog is a headline output for St. John's, so fog_state must be driven by METAR + GFS VIS + RH/dewpoint
depression, and must return `unknown` rather than inferring fog from high RH alone — the existing
`science.py:fog_state` already encodes that rule and must not be loosened to fill this gap.
