# Transparency, seeing and light-pollution source access

**Non-normative research, dated 2026-09-02.** Nothing here is a specification, an
admission decision or a registry change. It records what each service answered
to live requests on 2026-09-02 and what was read from the services' own
documentation. No artifact was published, no registry state was touched.

Resolves wayfinder research ticket
[#10](https://github.com/TusharSariya/Astraeus/issues/10). Evidence box: 45.0 to
50.5 N, 58.0 to 46.0 W (5.5 deg latitude by 12.0 deg longitude; about 611 km by
898 km, roughly 549 000 km²). Evidence classes are used as `CONTEXT.md` defines
them.

Request shapes, `SCALESIZE` values and per-model byte costs are **not repeated
here**; they are established in
[`geomet-wcs-inventory.md`](geomet-wcs-inventory.md) (branch
`research/geomet-wcs-inventory`). How the astronomy tools derive seeing and
transparency, and the Falchi atlas licence, are established in
[`astronomy-tool-needs.md`](astronomy-tool-needs.md) (branch
`research/astronomy-tool-needs`). Prior background: the aerosol and light
pollution sections of `docs/research/data-sources.md` and
`docs/research/sota-models.md`.

## 0. The three findings that change the picture

1. **ECCC's seeing and sky transparency forecasts are on GeoMet as WCS
   coverages.** `RDPS_10km_SeeingIndex` and `RDPS_10km_SkyTransparencyIndex`
   both exist and both returned a 200 GeoTIFF subset to the box. Ticket
   [#7](https://github.com/TusharSariya/Astraeus/issues/7) left this as an open
   probe on the assumption the fields were imagery-only. They are not. This is
   the only operational seeing product covering the box and it is retrievable at
   ~33 KB per hour per field.
2. **The values are unlabelled integer class indices, not physical units.** A
   live subset at `2026-09-03T03:00:00Z` decoded to exactly `{0, 3, 4, 5}` for
   seeing and `{0, 2, 3, 4}` for transparency across all 8113 cells. No arcsecond
   and no magnitude anywhere. The WMS leaf titles are bare — `RDPS - Seeing
   index` and `RDPS - Sky transparency index` — with **no unit bracket**, unlike
   every other RDPS layer. The class definitions could not be verified from a
   machine-readable source (see §7).
3. **Precipitable water does not exist on GeoMet for any ECCC model.** Nothing in
   the 6123 advertised coverages matches precipitable water, integrated water
   vapour or total column water vapour for HRDPS, RDPS or GDPS. The only `PW*`
   ids are GDWPS wave-period layers, and `*_CloudWater_EAtm` /
   `HRDPS.CONTINENTAL_IH` are condensate (`Cloud water [mm]`, title verified),
   not vapour. GFS on S3 is the only precipitable-water path in the box.

A fourth, smaller correction: **`dd.weather.gc.ca` air-quality paths are not
gone, they moved.** Every flat path 404s, but the dated layout answers.

## 1. Source table

Cadence, latency and size are as measured on 2026-09-02 unless marked.
"Verified live" means a request was issued in this session and returned the
stated status with usable content.

| # | Source | Quantity | Evidence class | Cadence | Latency (measured) | Resolution | Access path | Licence | Verified live | Size in box |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | RDPS seeing index (GeoMet WCS) | seeing, unitless class 0–5 | retrieved | hourly steps, 6-hourly runs, to +84 h | run 00Z advertised by 06:04Z | 10 km (0.090298 deg) | `COVERAGEID=RDPS_10km_SeeingIndex` | MSC Open Data / OGL-Canada 2.0 | **yes** — 200, 32 900 B, 0.35 s | 32.9 KB per step; **0.95 MB** per run over a 29-step core window |
| 2 | RDPS sky transparency index (GeoMet WCS) | transparency, unitless class 0–4 | retrieved | as above | as above | 10 km | `COVERAGEID=RDPS_10km_SkyTransparencyIndex` | as above | **yes** — 200, 32 900 B, 0.32 s | as above |
| 3 | RAQDPS column PM2.5 (GeoMet WCS) | entire-column PM2.5 mass, kg/m² | retrieved | hourly to +72 h, runs 00Z/12Z | 00Z f000 on Datamart at 03:49Z → **~3.8 h** | 10 km | `COVERAGEID=RAQDPS.EATM_PM2.5` | MSC Open Data / OGL-Canada 2.0 | **yes** — 200, 32 900 B, 0.26 s | 32.9 KB per step; ~0.95 MB per run per field |
| 4 | RAQDPS wildfire smoke plume, column (GeoMet WCS) | column PM2.5/PM10 attributable to fire plumes, kg/m² | retrieved | as #3 | as #3 | 10 km | `RAQDPS.EAtm_PM2.5-WildfireSmokePlume`, `...PM10-...` | as #3 | **yes** — 200, 40 348 B, 0.27 s | ~40 KB per step |
| 5 | RAQDPS surface PM2.5 (GeoMet WCS) | surface PM2.5, kg/m³ | retrieved | as #3 | as #3 | 10 km | `RAQDPS.SFC_PM2.5`, `RAQDPS.Sfc_PM2.5-WildfireSmokePlume` | as #3 | **yes** — 200, 32 900 B | 32.9 KB per step |
| 6 | RDAQA preliminary analysis (GeoMet WCS) | surface PM2.5/PM10/O3/NO2/SO2 analysis | retrieved | hourly | latest hour 04Z at 06:04Z → **~2 h** | 10 km | `RDAQA-Prelim_10km_PM2.5` etc. | as #3 | **yes** — 200, 32 900 B, 0.28 s | 32.9 KB per hour per species |
| 7 | RDAQA-FW analysis (GeoMet WCS) | surface PM2.5/PM10 with FireWork contribution | retrieved | hourly | latest hour 03Z at 06:04Z → **~3 h** | 10 km | `RDAQA-FW_10km_PM2.5`, `RDAQA-FW_10km_PM10` | as #3 | **yes** — 200, 32 900 B, 0.33 s | 32.9 KB per hour per species |
| 8 | RAQDPS on Datamart (GRIB2) | same fields as #3–#5, full NA grid | retrieved | hourly to +72 h | 00Z f000 posted 03:49:07Z | 10 km | `https://dd.weather.gc.ca/YYYYMMDD/WXO-DD/model_raqdps/10km/grib2/00/000/` | as #3 | **yes** — 200, `Content-Length: 504 585` | **504 KB on the wire per field per step for 33 KB of box**; use GeoMet instead |
| 9 | CAMS global composition forecast (ADS) | total AOD at 469/550/670/865/1240 nm; 8 speciated AODs; 42 multi-level aerosol mixing ratios | retrieved | 2 runs/day (00Z, 12Z), hourly to +120 h | not measurable anonymously; catalogue temporal extent ended `2026-09-01T00:00Z` on 2026-09-02 → ~1 day behind | 0.4 deg (~44 km), 137 model levels or 25 pressure levels | `POST https://ads.atmosphere.copernicus.eu/api/retrieve/v1/processes/cams-global-atmospheric-composition-forecasts/execute` | **CC-BY-4.0** per the ADS catalogue `license` field and its `rel=license` link (see §3) | **partly** — catalogue 200; execute **401 "authentication required"** | 0.4 deg over the box ≈ 31 × 15 = 465 cells ≈ **1.9 KB** per field per step |
| 10 | NASA MAIAC `MCD19A2` (MODIS Terra+Aqua) | column AOD 470/550 nm, plus AOD uncertainty and QA | retrieved | 1 km daily composite of all overpasses | obs 2026-08-31, produced 2026-09-01T16:08Z, latest available on 2026-09-02 → **~1.7 days** | 1 km, sinusoidal tiles h13–h14 / v03–v04 | LAADS/LP DAAC via CMR; granule URL under `data.lpdaac.earthdatacloud.nasa.gov` | NASA Earth Science data policy, open with attribution | **partly** — CMR search 200 with granules in the box; granule GET **401** anonymously | ~549 000 cells at 1 km ≈ **2.2 MB** float32 per day before masking |
| 11 | VIIRS Deep Blue `AERDB_L2_VIIRS_SNPP` / `_NOAA20` | column AOD 550 nm, Ångström exponent, QA | retrieved | per overpass, ~2 useful passes/day per satellite | obs 2026-08-31T16:42Z, produced 2026-09-01T10:15Z → **~17.5 h** | 6 km at nadir, L2 swath | LAADS via CMR | as #10 | **partly** — CMR 200; download credential-gated | ~15 000 pixels ≈ **60 KB** per granule |
| 12 | VIIRS Deep Blue NRT (`..._NRT`) | as #11 | retrieved | per overpass | obs 2026-09-01T18:06Z, produced 19:10Z → **~1.1 h** | 6 km | LANCE/LAADS via CMR | as #10 | **partly** — CMR 200 (`AERDB_L2_VIIRS_SNPP_NRT` and `_NOAA20_NRT` both return granules in the box) | as #11 |
| 13 | NASA Black Marble `VNP46A2` | BRDF-corrected nighttime DNB radiance, lunar/atmosphere/terrain corrected, with QA | retrieved | daily | obs 2026-08-30, ingested 2026-08-31T10:15Z, latest on 2026-09-02 → **~2 days** | 500 m (15 arcsec) | LAADS `allData/5000/VNP46A2` via CMR; the HTML archive listing is a JS shell | NASA Earth Science data policy, open with attribution | **partly** — CMR 200 with granules; download credential-gated | 2880 × 1320 = 3.80 Mpx at 15 arcsec ≈ **15.2 MB** float32, one-off static |
| 14 | NASA Black Marble `VNP46A1` / `VNP46A1_NRT` | at-sensor DNB radiance | retrieved | daily | NRT obs 2026-09-01, updated 2026-09-02T05:15Z → **~5 h** | 500 m | as #13 | as #13 | **partly** — CMR 200 | as #13 |
| 15 | EOG VIIRS Nighttime Lights (VNL V2.2 annual, monthly VCM/VCMSL) | cloud-free composite DNB radiance | retrieved | monthly and annual | not measurable — listing redirects before any file | 15 arcsec (~500 m) | `https://eogdata.mines.edu/nighttime_light/{annual/v22,monthly/v10}/` | **CC BY 4.0** per the EOG products page, with citation of EOG and the product paper | **no** — 200 on the directory but the body is a redirect to `eogauth.mines.edu/realms/eog/protocol/openid-connect/auth`; **credential-blocked** (free registration) | as #13, ~15 MB one-off |
| 16 | Falchi et al. World Atlas of Artificial Night Sky Brightness (2016) | modelled zenith artificial sky brightness | retrieved | static, single 2015 epoch | n/a | 30 arcsec | GFZ Data Services, DOI `10.5880/GFZ.1.4.2016.001` | **CC BY-NC 4.0** — non-commercial only (established in ticket #7, not re-probed) | not re-probed | 1440 × 660 ≈ 0.95 Mpx ≈ **3.8 MB** float32 one-off |
| 17 | CWFIS hotspots (WFS) | fire detection points, time, confidence, FRP | retrieved | continuous, satellite-pass driven | n/a (rolling 24 h layer) | point detections | `https://cwfis.cfs.nrcan.gc.ca/geoserver/public/wfs` `typeNames=public:hotspots_last24hrs` with `bbox=45,-58,50.5,-46,urn:ogc:def:crs:EPSG::4326` | OGL-Canada 2.0 (NRCan) | **yes** — 200, valid GeoJSON, `numberMatched: 0` (no active hotspots in the box on 2026-09-02) | **147 B empty**; a few KB when the box is active |
| 18 | CWFIS hotspot daily CSV | as #17, daily archive | retrieved | daily file | latest file `20260901.csv` on 2026-09-02 → **~1 day** | point detections | `https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/YYYYMMDD.csv` | OGL-Canada 2.0 | **yes** — directory 200; `20260902.csv` **404** (not yet posted) | national file, box subset trivial |
| 19 | CWFIS CFFEPS emissions input | fire emissions / plume-rise inputs feeding FireWork | retrieved | daily | `in20260901.csv` latest | point | `https://cwfis.cfs.nrcan.gc.ca/downloads/hotspots/cffeps/` | OGL-Canada 2.0 | **yes** — directory 200 | small |
| 20 | Standalone FireWork (`model_raqdps-fw`) | — | — | — | — | — | `dd.weather.gc.ca/YYYYMMDD/WXO-DD/model_raqdps-fw/` | — | **no — 404 under the dated layout too.** Retired; smoke lives inside RAQDPS as `*-WildfireSmokePlume` (#4, #5) and inside RDAQA-FW (#7) | n/a |
| 21 | BlueSky Canada / firesmoke.ca | modelled surface smoke PM2.5 | — | — | — | — | `https://firesmoke.ca/forecasts/current/` | not stated on the page | **viewer only** — 200 but the page is a Leaflet client; no directory listing and no documented machine endpoint found | unknown |
| 22 | HRDPS 200–300 hPa wind and temperature (GeoMet WCS) | `TT`, `WSPD`, `WD`, `GZ`, `HR`, `HU`, `ES` at 200, 225, 250, 275, 300 hPa | retrieved | hourly to +48 h | as HRDPS | 2.5 km | `HRDPS.CONTINENTAL.PRES_WSPD.250` etc. | MSC Open Data / OGL-Canada 2.0 | **yes** — 200, 524 230 B, 0.62 s | **0.52 MB** per field per step; the 5-level × 3-field jet set is ~7.9 MB per step, ~228 MB per run over 29 steps |
| 23 | RDPS 200–300 hPa (GeoMet WCS) | `AirTemp`, `WindSpeed`, `WindDir`, `GeopotentialHeight`, `RelativeHumidity`, `SpecificHumidity`, `DewPointDepression` at all five levels; `AbsoluteVorticity_250mb`, `VerticalVelocity_250mb` | retrieved | hourly to +84 h | as RDPS | 10 km | `RDPS_10km_WindSpeed_250mb` etc. | as #22 | **yes** — 200, 32 900 B, 0.31 s | 32.9 KB per field per step; the 15-coverage jet set is ~0.49 MB per step, **~14 MB per run** |
| 24 | GDPS 200–300 hPa (GeoMet WCS) | same field set as #23 plus `RelativeVorticity` | retrieved | 3-hourly to +192 h, then 6-hourly to +240 h (verified in the WMS time dimension) | as GDPS | 15 km | `GDPS_15km_AirTemp_250mb` etc. | as #22 | **yes** — 200, 12 266 B, 0.44 s | 12.3 KB per field per step |
| 25 | GFS precipitable water and 200–300 hPa (S3) | `PWAT:entire atmosphere`, `TMP`/`UGRD`/`VGRD` at 200/250/300 mb | retrieved | 4 runs/day, hourly to +120 h | 06Z f000 index still **404** at 06:04Z — consistent with the ~5.3 h GFS latency measured in ticket #15 | 0.25 deg | `noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fFFF` plus `.idx` byte ranges | NOAA open data, public domain | **yes** — `.idx` 200 (41 214 B); ranged GETs 206 | **PWAT 1 221 201 B on the wire, 0.60 s**; `TMP:250` 733 314 B; `UGRD:250` 586 384 B. Box is 49 × 23 = 1127 cells ≈ **4.5 KB**. Wire-to-store ratio ~270:1 |

## 2. GeoMet: what is not there

Grepped over all 6123 `wcs:CoverageId` values in the 2026-09-02 WCS
`GetCapabilities` (1 190 020 B):

- **No aerosol optical depth of any kind.** Zero matches for `aod`, `aerosol`
  or `optical`. ECCC publishes mass concentration, never optical depth. Any AOD
  in the box must come from CAMS (#9) or NASA (#10–#12).
- **No precipitable water / total column water vapour** for HRDPS, RDPS or GDPS
  (see §0.3). This is the single largest gap for a transparency derivation from
  ECCC alone.
- **No seeing or transparency outside RDPS.** `RDPS_10km_SeeingIndex` and
  `RDPS_10km_SkyTransparencyIndex` are the only two matches for
  `seeing|transparen|astro` in the whole catalogue. No HRDPS equivalent, no GDPS
  equivalent. This matches ticket #7's finding that the Clear Sky Chart lineage
  runs on the Regional model.
- **RAQDPS-FW appears only as difference layers** (`RAQDPS-FW.CE_PM2.5-DIFF-*`,
  monthly and yearly averages). The operational smoke signal is the
  `WildfireSmokePlume` variants of RAQDPS and the `RDAQA-FW` analyses.

## 3. CAMS through the Atmosphere Data Store

- **Anonymous path: partial.** The STAC catalogue
  (`/api/catalogue/v1/collections/...`) and the process description
  (`/api/retrieve/v1/processes/...`) both return 200 with no credentials. A
  `POST .../execute` with a valid CAMS request body returned **HTTP 401,
  `{"type":"permission denied", ..., "detail":"authentication required"}`**.
  There is no anonymous data path. The registry's `credential_required` state
  for `copernicus-cams` is correct.
- **Licence: the catalogue now reports `CC-BY-4.0`**, with a `rel=license` link
  to `https://spdx.org/licenses/CC-BY-4.0` titled "CC-BY licence", and the
  dataset overview page says the same. The registry record
  `copernicus-cams` carries `"Licence to use Copernicus Products"` with
  `review_state: verified` and a `cds.climate.copernicus.eu/licences/...` URL.
  These are not the same instrument. **Flagged, not resolved**: an admission
  decision should re-verify which licence the ADS actually requires acceptance
  of at download time, since acceptance is recorded per-licence in the ADS
  account and only an authenticated request can show it.
- **AOD fields available** (single level, verified in the ADS request form):
  `total_aerosol_optical_depth_550nm` plus 469, 670, 865 and 1240 nm; and
  speciated 550 nm AOD for `dust`, `sea_salt`, `organic_matter`,
  `black_carbon`, `sulphate`, `nitrate`, `ammonium`,
  `secondary_organic_aerosol`. Sea salt matters here: the box is maritime and
  sea-salt AOD is the term a continental transparency model would miss.
- **Composition fields**: 42 multi-level variables including size-binned dust
  (0.03–0.55, 0.55–0.9, 0.9–20 µm) and sea salt (0.03–0.5, 0.5–5, 5–20 µm),
  hydrophilic/hydrophobic black carbon and organic matter, and `specific_humidity`
  on the same levels — enough to compute a hygroscopic-growth-aware extinction
  profile rather than a column scalar.
- **Shape**: `type=forecast` only, `time` in `{00:00, 12:00}`,
  `leadtime_hour` 0–120 hourly, `data_format` in `{grib, netcdf_zip}`,
  25 pressure levels 1000→1 hPa or 137 model levels, 0.4 deg. Server-side `area`
  subsetting is supported in the request body, so unlike GFS the wire cost is
  the box cost.

## 4. `dd.weather.gc.ca` re-probe

Per the charter's standing instruction. Every flat path is gone; the dated
layout is live.

| Path | Status |
|---|---|
| `https://dd.weather.gc.ca/` | 200 |
| `https://dd.weather.gc.ca/model_raqdps/` | **404** |
| `https://dd.weather.gc.ca/model_raqdps/10km/00/` | **404** |
| `https://dd.weather.gc.ca/model_raqdps-fw/10km/00/` | **404** |
| `https://dd.weather.gc.ca/air_quality/` | **404** |
| `https://dd.weather.gc.ca/air_quality/aqhi/atl/observation/realtime/csv/` | **404** |
| `https://dd.weather.gc.ca/model_gem_regional/` | **404** |
| `https://dd.weather.gc.ca/20260902/WXO-DD/` | **200**, lists `air_quality/` and `model_raqdps/` |
| `https://dd.weather.gc.ca/20260902/WXO-DD/model_raqdps/10km/grib2/00/000/` | **200**, GRIB2 files present |
| `https://dd.weather.gc.ca/20260902/WXO-DD/model_raqdps-fw/` | **404** (product genuinely retired) |
| `https://hpfx.collab.science.gc.ca/` | 200; `/20260902/WXO-DD/` 200 but `.../model_raqdps/10km/00/` 404 |

**Correction to carry forward**: "the Datamart RAQDPS feed is 404" is only true
of the flat path. The product is live at
`dd.weather.gc.ca/YYYYMMDD/WXO-DD/model_raqdps/10km/grib2/HH/FFF/` with names of
the form `20260902T00Z_MSC_RAQDPS_PM2.5_EAtm_RLatLon0.09_PT000H.grib2`. It is
still the wrong path to use — 504 585 B on the wire for the same 32 900 B GeoMet
returns from a box subset — but it is not withdrawn, and the 00Z `Last-Modified`
of `03:49:07Z` is the cleanest RAQDPS latency measurement available.

## 5. What the seeing and transparency indices actually contain

One GeoTIFF of each, subset to the box at `TIME=2026-09-03T03:00:00Z`, decoded
from the strip data:

| Coverage | Distinct values over 8113 cells | Range |
|---|---|---|
| `RDPS_10km_SeeingIndex` | `0.0, 3.0, 4.0, 5.0` | 0–5 |
| `RDPS_10km_SkyTransparencyIndex` | `0.0, 2.0, 3.0, 4.0` | 0–4 |

Every value is an exact integer. These are class indices. Whether `0` is a
class or a no-data/not-computed sentinel is unresolved and matters: ticket #7
recorded that CMC refuses to compute transparency above 30% cloud and seeing
above 80% cloud, which would make `0` a masked cell rather than "worst". Under
the field catalogue's comparability rule this field is **not** unit-comparable
with 7Timer's mag/air mass, meteoblue's 1–5 indices, or any arcsecond seeing —
it is a fourth incompatible encoding on top of the three ticket #7 found.

Time dimensions verified in the WMS capabilities:

- seeing: `2026-09-02T01:00:00Z/2026-09-05T12:00:00Z/PT1H`,
  `reference_time` `2026-08-31T18:00:00Z/2026-09-02T00:00:00Z/PT6H`
- transparency: `2026-09-02T00:00:00Z/2026-09-05T12:00:00Z/PT1H`, same runs

So: hourly, four runs a day, ~84 h horizon — the core window in full and a
useful slice of the planning window, at 0.95 MB per field per run.

## 6. A derived-here seeing and transparency field

### Seeing — buildable now, from GeoMet alone

Everything a Cn²-integration seeing proxy needs is retrievable in the box:

- **Upper-level wind shear and thermal gradient.** HRDPS (#22) carries `TT`,
  `WSPD`, `WD`, `GZ` and `HR` at 200, 225, 250, 275 and 300 hPa at 2.5 km,
  hourly to +48 h. RDPS (#23) carries the same at 10 km to +84 h and adds
  `AbsoluteVorticity_250mb` and `VerticalVelocity_250mb`. GDPS (#24) extends to
  +240 h at 15 km. This is the jet-stream term meteoblue exposes explicitly and
  the other tools fold into a single number.
- **Boundary-layer turbulence.** `HRDPS.CONTINENTAL_HPBL`, `SKINT` and the
  40/80/120 m `TT`/`TD`/`HR`/`WSPD` set, all established in the GeoMet
  inventory. Ground-layer seeing is the term the surveyed tools handle worst.
- **Full-column stability.** HRDPS 28 pressure levels of `TT` and `HR`; RDPS and
  GDPS 31 levels each.

The honest framing is that this would be a **derived-here** field with the
method cited (a Cn² parameterisation integrated over the column), inputs listed,
and `derived: True` in provenance. Cost is the constraint, not availability: the
HRDPS five-level three-field jet set alone is ~228 MB per run before any other
field, against ~14 MB for the same set from RDPS. RDPS is the sane input tier,
which also makes the derivation directly comparable against ECCC's own
`RDPS_10km_SeeingIndex` on the same grid — a free sanity check that no other
candidate field in this experiment gets.

**Missing for seeing**: nothing retrievable. What is missing is *verification* —
there is no seeing monitor, no DIMM, no Cn² profiler anywhere near the box, so a
derived seeing field can be compared with ECCC's index but never validated. This
is the same in-situ hole ticket #9 found for marine fog.

### Transparency — one term short

Available:

- **Aerosol mass, column and surface**, hourly at 10 km from RAQDPS (#3–#5) with
  the wildfire contribution separated out (#4), and an hourly analysis (#6, #7)
  to anchor the forecast. This is a better aerosol input than any surveyed tool
  uses except Astrospheric's RAP smoke.
- **Aerosol optical depth**, speciated and spectral, from CAMS (#9) at 0.4 deg
  and 1.9 KB per field per step — but credential-blocked, and one day behind at
  0.4 deg it is climatological context, not a local-site term.
- **Independent AOD observation** from MAIAC at 1 km (#10) and VIIRS Deep Blue
  NRT at ~1.1 h latency (#12) — both credential-blocked, both cloud-masked, so
  in a maritime box they are absent exactly when the sky is interesting.
- **Column moisture as a proxy**: 28–31 levels of `HR` and `HU` on GeoMet, from
  which precipitable water can itself be integrated.

Missing:

1. **Precipitable water as a published field from ECCC.** Confirmed absent (§0.3,
   §2). Clear Sky Chart's transparency is total-column water vapour and cannot be
   reproduced from an ECCC published field. Either integrate it derived-here from
   the pressure-level `HU` set — at ~424 MB per HRDPS run or ~1 MB per RDPS run
   for the 31-level `SpecificHumidity` stack, so RDPS again — or take GFS `PWAT`
   from S3 at 1.2 MB on the wire per step for 4.5 KB of box.
2. **An openly retrievable AOD with no credential.** Every AOD path in the box
   is credential-blocked. Until an Earthdata or ADS credential exists, the only
   aerosol term available is RAQDPS mass, and PM mass is not optical depth: it
   carries no wavelength dependence and no hygroscopic growth. A mass-to-
   extinction conversion is a citable method, but it is an assumption, not a
   measurement, and must be declared as such in the derivation.
3. **Any ground truth.** No SQM, no photometer, no AERONET site in or near the
   box (AERONET was not probed; the nearest Canadian sites are far outside it).
   Ticket #7's practitioner list wants limiting magnitude; nothing in the box
   measures it.

So a derived-here transparency field is buildable today as
`f(column PM2.5, wildfire plume PM2.5, integrated water vapour, cloud)` at 10 km
hourly for under 5 MB per run — with an explicit, declared gap where the aerosol
optical term should be, and with `RDPS_10km_SkyTransparencyIndex` alongside it as
the producer's own value rather than as a competitor.

### Light pollution

The baseline is static and cheap (~15 MB one-off), but every candidate has a
catch: EOG VNL is CC BY 4.0 yet **credential-blocked behind Keycloak SSO**;
Black Marble `VNP46A2` is the better-corrected product and openly licensed but
**credential-blocked behind Earthdata Login**; Falchi is the only one that
answers the actual question (zenith sky brightness rather than upward radiance)
and is **CC BY-NC 4.0**, which forecloses any commercial path. All three measure
or model something other than directional sky brightness at a site, so the
directional light-dome exposure sketched in `data-sources.md` remains
derived-here with no way to validate it inside the box.

## 7. Open items

1. **The class definitions for `RDPS_10km_SeeingIndex` and
   `RDPS_10km_SkyTransparencyIndex`.** `weather.gc.ca/astro/seeing_e.html` only
   points at an information page, and
   `canada.ca/.../astronomy/seeing-forecast.html` returned **403** to a
   programmatic fetch. Whether `0` is "worst" or "not computed" is unresolved and
   changes how the field must be masked.
2. **Which licence instrument the ADS enforces for CAMS** (§3) — the catalogue
   says CC-BY-4.0, the registry says Licence to use Copernicus Products.
3. **BlueSky Canada / firesmoke.ca machine access** (#21) — a viewer was found,
   no endpoint. Probably a `link-only` record.
4. **AERONET or any photometric ground truth** in or near the box; not probed.
5. **Whether the GeoMet RAQDPS reference-time depth (12-hourly, two runs
   advertised) is enough** for the three-hour retention rule, or whether the
   Datamart dated layout is needed as a backstop despite its wire cost.

## 8. Method and honesty notes

- 6123 coverage ids came from one WCS `GetCapabilities` and were grepped
  locally; no per-coverage enumeration was attempted. WMS single-leaf
  `GetCapabilities` was used for titles and time dimensions, one call per
  coverage, as established in the GeoMet inventory.
- Latency figures are single observations on one day at ~06:00Z. RAQDPS's 3.8 h
  is a `Last-Modified` header and is solid; the CAMS figure is inferred from a
  catalogue temporal extent and is the weakest number in the table.
- The seeing and transparency value ranges are from one time step of one run.
  A wider sample could show classes not present in this box at this hour.
- CAMS resolution (0.4 deg), level counts and forecast length are from the ADS
  dataset overview page, not from a returned file — no file could be retrieved
  without a credential.
- Falchi licence and the astronomy tools' derivation methods are carried over
  from ticket #7 unverified in this session, by design.
- About four dozen upstream requests were made. No source was promoted, no
  artifact published, no registry state changed.
