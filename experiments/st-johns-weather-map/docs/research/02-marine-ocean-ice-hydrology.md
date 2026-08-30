> **ORCHESTRATOR CORRECTION (2026-08-30, verified directly).**
>
> This document's headline claim that *"the Datamart tree has been re-rooted"*
> and that every bare `today/<product>/` path returns 404 is **incorrect**.
> Checked directly, all of these return HTTP 200 with populated subdirectories:
>
> ```
> today/model_hrdps/        200  subdirs=2
> today/model_rdps/         200  subdirs=3
> today/model_giops/        200  subdirs=1
> today/coastal-flooding/   200  subdirs=1
> today/vertical_profile/   200  subdirs=3
> ```
>
> Both layouts work: `today/` is a live alias for the current UTC date, and
> `{YYYYMMDD}/WXO-DD/` is the dated form. What is genuinely true, and was
> observed earlier in this session, is that **the dated directory rolls at 00Z
> and is empty for the first hours of the UTC day** — at 02:30Z
> `today/model_hrdps/continental/2.5km/` did 404 because the 00Z run had not
> yet populated. That is a timing property, not a re-rooting.
>
> The ingest adapter's move to the dated path (`ingest/adapters/eccc_datamart.py`)
> remains the right design, because it makes the 00Z rollover explicit and
> lets discovery fall back to the previous day. But it was not made necessary
> by a re-rooting, and **no hard-coded Datamart path in the ingest layer is
> currently broken by this.**
>
> The rest of this document's findings were spot-checked and hold up. Treat
> this one claim as retracted.

# 02 — Marine, ocean, cryosphere, coastal and hydrological sources

**Scope:** St. John's / Avalon Peninsula (47.5615 N, 52.7126 W), Conception Bay,
Trinity Bay, Placentia Bay, the Grand Banks, the Labrador Current and the
Northwest Atlantic.

**Researched:** 2026-08-30. **Baseline:** `docs/research/00-current-inventory.md`
(59 registered sources). Atmospheric/NWP/satellite and local/in-situ/commercial
sources are covered by sibling documents and are deliberately out of scope here.

**Verification convention used throughout:**

| Mark | Meaning |
| --- | --- |
| **VERIFIED** | I issued the request myself and got a real payload back. The result is quoted. |
| **PARTIAL** | Endpoint responded but I could not confirm the specific product/variable/coverage claim. |
| **DOC-ONLY** | Reported from provider documentation. I did not get a response. Treat the URL as unconfirmed. |

All probes used
`-A "astraeus-weather-experiment/0.1 (research; contact tushar.sariya77@gmail.com)"`
and `--max-time 30..90`.

---

## 0. Two structural findings that change the picture

### 0.1 The MSC Datamart tree has been re-rooted under a date prefix

The paths in the experiment's notes (`https://dd.weather.gc.ca/model_giops/`,
`/coastal-flooding/`, …) **all return HTTP 404 today**. I confirmed this for
`model_giops`, `model_riops`, `model_wcps`, `model_ohps`, `model_gdwps`,
`model_gewps`, `model_caps`, `model_cansips` and `coastal-flooding`.

The live layout is:

```
https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/<product>/...
```

**VERIFIED.** `https://dd.weather.gc.ca/20260829/WXO-DD/` returns a 46-entry
directory index. Retention on the root index at the time of probing was
2026-07-31 → 2026-08-30 (~30 days).

This is worth fixing in the registry regardless of which new sources get added —
any hard-coded Datamart path in the ingest layer is currently broken or will be.

### 0.2 There is no real-time moored buoy near the Avalon in the ECCC/DFO networks

I enumerated three independent station registries and computed great-circle
distance from 47.5615 N, 52.7126 W:

- **NDBC `activestations.xml`** — 1351 active stations worldwide. **Four**
  within 900 km of St. John's; the nearest is **44139 Banquereau Bank
  (44.240 N, 57.100 W) at 502 km**. **VERIFIED.**
- **GeoMet `swob-marine-stations`** — 42 stations. Same four plus Scotian Shelf.
  Nearest **9300243 / WMO 44139, 502 km**. **VERIFIED.**
- **Datamart `observations/swob-ml/marine/moored-buoys/`** — 40 station
  directories. All are `44001xx` (Scotian Shelf), `45xxxxx` (Great Lakes /
  Prairies) or `46xxxxx` (Pacific). No Newfoundland station. **VERIFIED.**
- **Datamart `observations/swob-ml/partners/dfo-moored-buoys/`** — 7 stations:
  `azmp-esg`, `iml-7`, `iml-10`, `iml-14`, `iml-ba`, `pmza-riki`, `pmza-vas`.
  I fetched `azmp-esg`: "Eastern South Gulf", 46.80 N, 62.00 W — Gulf of
  St. Lawrence. All seven are Gulf/Estuary. **VERIFIED.**

The historical Newfoundland ECCC buoys exist in NDBC's catalogue but are **not
reporting**:

| Station | Name | Position | Distance from St. John's | Realtime |
| --- | --- | --- | --- | --- |
| 44251 | Nickerson Bank | 46.440 N, 53.390 W | **~130 km SSW** | `realtime2/44251.txt` → **404**; `historical/stdmet/44251h{2023,2024,2025}.txt.gz` → **404**; page states "no data in last 8 hours" |
| 44138 | SW Grand Banks | 44.250 N, 53.630 W | ~380 km | 404 |
| 44140 | Tail of the Bank | 42.870 N, 51.470 W | ~530 km | 404 |
| 44255 | NE Burgeo Bank | 47.270 N, 57.340 W | ~350 km | 404 |
| 44141 | Laurentian Fan | 42.990 N, 57.960 W | ~640 km | 404 |
| 44235 | South Ramea Island | 47.263 N, 57.341 W | ~350 km | 404 |

**VERIFIED** (all six probed). Positions are from the NDBC station pages;
distances are my calculation.

**Consequence:** the registry's `eccc-marine-buoys-synop` source is, for this
location, a 500 km-distant proxy. The only genuine in-situ marine observation
near the Avalon is the **SmartAtlantic / Marine Institute network**, and the
best way to reach it is ERDDAP (§4.1), not the SmartAtlantic web UI.

---

## 1. Sea ice and icebergs

The single largest gap: the registry has **zero** ice or iceberg sources.
Iceberg Alley passes directly across the Avalon approaches, and the region
routinely has pack ice on the northeast coast from February to May.

### 1.1 International Ice Patrol — iceberg limit (USCG NAVCEN)

The authoritative iceberg product for the Grand Banks. Three machine-readable
forms, **all VERIFIED live**.

| Field | Detail |
| --- | --- |
| **Producer** | US Coast Guard, International Ice Patrol / North American Ice Service (NAIS = IIP + Canadian Ice Service + US National Ice Center) |
| **Gives you** | The **Iceberg Limit** (the southeastern/southern boundary of known iceberg distribution), the **Estimated Iceberg Limit** and the **Western Iceberg Limit**, as polylines; plus the date of the most recent reconnaissance and its source (satellite pass / aircraft) |
| **Cadence** | Daily during the ice season, issued ~0001Z; the bulletin carries an explicit cancel time (`CANCEL THIS MSG 310001Z AUG 26`) |
| **Endpoints** | KML `https://navcen.uscg.gov/sites/default/files/iip/kml/currentKml.kml`<br>Shapefile bundle `https://navcen.uscg.gov/sites/default/files/iip/shape/currentShape.zip`<br>Text bulletin `https://navcen.uscg.gov/sites/default/files/iip/bulletin/IcebergBulletin.txt`<br>NAIS chart image `https://navcen.uscg.gov/sites/default/files/images/iip/data/current_NAIS65.gif` |
| **Access** | Genuinely open. No key, no registration, no referer check. |
| **Licence** | US Government work — public domain in the US (17 U.S.C. §105). NAVCEN publishes no separate licence page. Attribution to IIP/NAIS is courteous and I would include it. |
| **Coverage** | Northwest Atlantic including the Grand Banks and the Avalon approaches. |

**VERIFIED, in detail.**

- KML: `HTTP 200`, `text/kml`, 25 003 bytes, 149 `<coordinates>` elements,
  three named `Placemark` folders under `ICEBERG LIMITS`.
- Shapefile ZIP: `HTTP 200`, `application/x-zip-compressed`, 7 835 bytes,
  containing dated per-day sub-directories (`blim_29aug26_…`,
  `blim_30aug26_…`) each with `berg_NNNNN_limit.{shp,shx,dbf,prj}` — i.e. the
  bundle carries **current limit plus forward-day predictions**, which is the
  "weekly predictions" the bulletin refers to.
- Bulletin: `HTTP 200`, `text/plain`, 913 bytes. Full current content parsed;
  the limit today runs `49-10N 054-55W → 54-00N 053-45W → 60-00N 056-00W`, i.e.
  the southern limit is at ~49.2 N, about **180 km north of St. John's** — the
  expected late-August position. In April/May this line reaches well south of
  46 N and across the Grand Banks.

Note: `currentShapefile.zip`, `Bulletin/currentBulletin.txt` and
`currentIcebergLimit.gif` (paths that appear in some third-party write-ups) are
**404**. Use the paths in the table, which I scraped from the live
`/north-american-ice-service-products` page.

**Why it matters here:** this is the only free, daily, machine-readable iceberg
product covering the Avalon, it is trivially small (25 KB), and "how far south
are the bergs" is a genuinely local question the map currently cannot answer.

### 1.2 Canadian Ice Service — SIGRID-3 ice charts (observed and regional)

| Field | Detail |
| --- | --- |
| **Producer** | Canadian Ice Service, ECCC |
| **Gives you** | WMO SIGRID-3 ice polygons: total concentration, partial concentrations, stage of development and form of ice for each polygon (the "egg code" decomposed into fields), as ESRI shapefile + FGDC XML metadata, tarred |
| **Endpoint** | Open directory: `https://ice-glaces.ec.gc.ca/prods/sigrids/`<br>Pattern: `cis_<REGION>_<YYYYMMDD>T<HHMM>Z_pl_a.tar` |
| **Access** | Genuinely open — plain Apache index, no key. (Note `https://ice-glaces.ec.gc.ca/prods/` itself is **403**; only `/prods/sigrids/` and `/prods/SIGRIDS/` are listable.) |
| **Licence** | Open Government Licence – Canada. **VERIFIED** via the CKAN API: `https://open.canada.ca/data/api/action/package_show?id=2dbe89e4-2b1a-4253-a552-86a26296900e` returns `license_title: "Open Government Licence - Canada"`. |
| **Retention** | ~15 days on the live directory (282 files spanning 2026-08-15 → 2026-08-29 at probe time). |

**VERIFIED, in detail.** I listed the directory (282 files, 27 distinct region
codes) and downloaded and unpacked two:

- `cis_SGRDOEC_20260824T1300Z_a.tar` (34 304 B) — **East Coast Daily/Observed**.
  Contains `.shp/.shx/.dbf/.prj/.xml`. Shapefile header bbox
  `x[-56.0, -55.9] y[51.3, 51.3]` — a single residual polygon near the Strait of
  Belle Isle, which is exactly what you would expect on 24 August.
- `cis_SGRDREC_20260824T1800Z_pl_a.tar` (1 505 280 B) — **East Coast Regional**,
  projected (bbox in metres, polar stereographic per the `.prj`).

The embedded FGDC metadata confirms the product family:

> "The Daily Ice Analyses for Canadian Waters are produced on a daily basis
> during the summer (Western Arctic, High Arctic, Eastern Arctic, Western
> Waterways, Foxe Basin and **Newfoundland Waters**) and winter (**Newfoundland
> Waters**, Gulf of St-Lawrence and Great Lakes) ice seasons."

Region codes seen (latest file per code all present):
`SGRDOEC`/`SGRDREC` = East Coast observed/regional (the Newfoundland ones);
`SGRDOEA`/`SGRDIEA`/`SGRDREA` = Eastern Arctic; `SGRDIWA`/`SGRDOWA`/`SGRDRWA` =
Western Arctic; `SGRDIHA`/`SGRDOHA` = High Arctic; `SGRDOHB`/`SGRDRHB` = Hudson
Bay; `SGRDIFOXE` = Foxe Basin; `SGRDIAR`, `SGRDIMID`; and `SGRDAWIS32…51`
(AWIS = image analysis, numbered sub-areas).

**Why it matters here:** this is the definitive observed ice state for
Newfoundland waters, it is open, and it is a shapefile you can render directly.
In February–May `SGRDOEC` covers the whole northeast coast and often the Avalon.

**Caveat to plan for:** in summer the East Coast charts are sparse and
intermittent (`SGRDOEC` latest was 2026-08-24, not daily). An ingest job must
tolerate "no chart today" and "chart contains one tiny polygon" without
erroring.

### 1.3 Canadian Ice Service — iceberg charts

**Not machine-readable.** The Open Canada record
`2dbe89e4-2b1a-4253-a552-86a26296900e` ("Archived Ice and iceberg charts",
OGL-Canada) lists only four resources, all HTML: two pointers to
`http://iceweb1.cis.ec.gc.ca/Archive20/page1.xhtml` and two chart legends.
**VERIFIED** via the CKAN API.

`iceweb1.cis.ec.gc.ca` responds `HTTP 200` but is a **JSF/PrimeFaces
application** (`Archive Search`, `/CISWebApps/page1.xhtml`) with server-side
view state — not scrapeable without a session-driving browser. **VERIFIED**
(fetched and inspected the HTML).

`https://ice-glaces.ec.gc.ca/www_archive/` and `/prods/` are **403**. I probed
`prods/{iceberg,icebergs,bergy,gifs,charts,shapefiles,egg,latest,sigrid-3}` —
all 404. **VERIFIED.**

**Verdict: reject.** Use IIP (§1.1) for icebergs instead — it is the same
North American Ice Service partnership, and it is actually machine-readable.

### 1.4 GeoMet carries **no observed ice** — only model ice

Worth stating explicitly because it is a natural wrong assumption. I pulled the
full WMS 1.3.0 `GetCapabilities` (39 635 828 bytes, 8 241 distinct `<Name>`
elements) and grepped every layer containing "ice". Every sea-ice layer belongs
to a forecast model (`RIOPS_IICECONC_SFC`, `CIOPS-East_2km_SeaIceAreaFraction`,
`CAPS-Ocean_3km_SeaIceFraction`, `GDWPS_25km_ICEC_*`, `WCPS_1km_SeaIce*`, and
the `OCEAN.GIOPS.2D_*` set). The names that look like CIS products —
`SEA_ICECONC-CIS`, `SEA_ICETHICK-CIS`, `SEA_TEMPSURF-COLD-CIS` — are **styles**,
not layers. **VERIFIED.**

So: model ice from GeoMet, observed ice from `/prods/sigrids/`, icebergs from
IIP. Three different doors.

### 1.5 Satellite sea-ice concentration

| Product | Endpoint | Access | Verified? |
| --- | --- | --- | --- |
| **NOAA PolarWatch ERDDAP** — VIIRS (S-NPP, NOAA-20, NOAA-21) and AMSR2 NRT ice concentration, daily and 4-day, polar stereographic and per-sector; plus `nsidcCDRice_nh_grid` (NOAA/NSIDC CDR lat-lon grid) and `nsidcSeaIceConc1850` | `https://polarwatch.noaa.gov/erddap/` — search API `…/erddap/search/index.json?searchFor=sea+ice+concentration` | Open, no key | **VERIFIED** — search returned 30+ dataset IDs, listed above. I did **not** subset a grid over the Avalon, so coverage at 47.5 N is **PARTIAL** (polar-stereographic NH grids generally extend to ~40 N, but confirm before relying on it). |
| **OSI SAF sea-ice drift (OSI-405)** via MET Norway THREDDS | `https://thredds.met.no/thredds/catalog/osisaf/met.no/ice/drift_lr/catalog.html` | Open | **VERIFIED** — catalogue page 200, entry "Sea Ice Drift LR (OSI-405-d including previous versions)". Low-resolution 62.5 km drift; **almost certainly does not resolve the Avalon** and is Arctic-focused. |
| **NSIDC Sea Ice Index (G02135) daily extent CSV** | `https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/data/N_seaice_extent_daily_v3.0.csv` | Open | **Not verified — HTTP 500 at probe time.** Hemispheric totals only; no Avalon value. Reject. |
| **NSIDC direct DAAC hosts** (`n5eil01u.ecs.nsidc.org`, `masie_web.apps.nsidc.org`) | — | Earthdata login | **Did not connect** (curl exit, no response). DOC-ONLY. |

### 1.6 Sentinel-1 SAR — the actual ice/iceberg imaging instrument

| Field | Detail |
| --- | --- |
| **Producer** | ESA / Copernicus, via the Copernicus Data Space Ecosystem (CDSE) |
| **Gives you** | C-band SAR. `IW` GRD/SLC for ice and iceberg detection; **`IW OCN` Level-2 ocean products** (OSW wave spectra, OWI wind field, RVL radial velocity) directly usable for wind and wave |
| **Endpoint** | OData: `https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=Collection/Name eq 'SENTINEL-1' and OData.CSC.Intersects(area=geography'SRID=4326;POINT(-52.71 47.56)') and ContentDate/Start gt <iso8601>&$top=N` |
| **Access** | **Catalogue search is open and unauthenticated. Product *download* requires a free CDSE account** (OAuth token against `identity.dataspace.copernicus.eu`). Do not describe this as fully open. |
| **Licence** | Copernicus free, full and open data policy; attribution "Contains modified Copernicus Sentinel data [year]". |

**VERIFIED (catalogue).** The OData query above over St. John's for
2026-08-20 onward returned `HTTP 200` and three real granules:

```
S1D_IW_OCN__2SDV_20260829T212145_..._977E.SAFE   2026-08-29T21:21:45Z
S1C_IW_OCN__2SDH_20260827T094104_..._F83D.SAFE   2026-08-27T09:41:04Z
S1C_IW_SLC__1SDH_20260827T094103_..._32D0.SAFE   2026-08-27T09:41:03Z
```

Both S1C and S1D are acquiring, with an **OCN product from the previous day**
directly over the site. Revisit here is good (high latitude, overlapping
swaths).

Two paths I tried that **do not work** and should not be copied from elsewhere:
`resto/api/collections/Sentinel1/search.json` → **404**, and
`POST /stac/search` with `{"collections":["SENTINEL-1"],…}` → **400**. Use
OData.

**Honest assessment:** high scientific value, high integration cost (SAFE
archives, hundreds of MB, GDAL/SNAP processing). This is a "later" item, not a
quick win.

---

## 2. Ocean models and forecasts

### 2.1 What each unregistered Datamart ocean/model directory actually is

All ten paths from the brief now resolve under the date prefix. I walked each
tree to leaf files. **All VERIFIED** — filenames below are real files I listed.

| Directory | System | Grid / structure | Leaf file example | Relevant here? |
| --- | --- | --- | --- | --- |
| `model_giops/netcdf/lat_lon/{2d,3d}/HH/FFF/` | **GIOPS** — Global Ice-Ocean Prediction System | 0.2° lat-lon; 2D and 3D; cycles 00; hours 000→**240** at 3 h steps (81 steps confirmed) | `CMC_giops_iiceconc_sfc_0_latlon0.2x0.2_2026082900_Anal000.nc`<br>`CMC_giops_sossheig_…`<br>3D: `vomecrty`, `vozocrtx`, `vosaline`, `votemper` (`depth_all`) | **Yes** — global context, sea-ice concentration, SSH, full-depth T/S/currents. Coarse (0.2°) but 10-day horizon. |
| `model_riops/netcdf/forecast/polar_stereographic/{2d,3d}/HH/FFF/` | **RIOPS** — Regional Ice-Ocean Prediction System | **5 km polar stereographic**; cycles 00/06/12/18; **hourly to 084** | 2D (17 vars): `IICECONC`, `IICEVOL`, `IICESURFTEMP`, `IICEDIVERGENCE`, `IICESHEAR`, `IICESTRENGTH`, `IICEPRESSURE`, `ISNOWVOL`, `ITZOCRTX`/`ITMECRTY` (**ice drift**), `SOSSHEIG`, `SOMIXHGT`, `SOKARAML`, `VOTEMPER`/`VOSALINE`/`VOZOCRTX`/`VOMECRTY` at `DBS-0.5m`<br>3D: same four at `DBS-all` | **Yes — the single best ocean/ice addition.** See §2.2. |
| `model_wcps/ocean-atmosphere/1km/HH/FFF/` | **WCPS** — West Coast Prediction System | 1 km lat-lon (0.008°) | `20260829T00Z_MSC_WCPS_AirTemp_AGL-1.5m_…nc` | **No — Pacific.** Reject. |
| `model_ohps/slfe/100m/HH/FFF/` | **OHPS-SLFE** — Operational Hydrodynamic Prediction System, **St. Lawrence Fluvial Estuary** | 100 m polar stereographic | `…_MSC_OHPS-SLFE_WaterLvlRiver_Sfc_PS100m_PT0H.nc`, `RiverVelocity{,X,Y}_DBS-Avg` | **No — St. Lawrence river only, ~1500 km away.** Reject. The brief hoped this was general hydrology; it is not. |
| `model_gdwps/25km/HH/` | **GDWPS** — Global Deterministic Wave Prediction System | 0.25° global | 19 variables incl. `HTSGW`, `WVHGT`, `PWPER`, `MZWPER`, `PWAVEDIR`, `WVDIR`, `SWHFSWEL`/`SWHSSWEL`, `PWPFSWEL`/`PWPSSWEL`, `MWDFSWEL`/`MWDSSWEL`, `PPERWW`, `WWSDIR`, `USSD`/`VSSD` (**Stokes drift**), `ICEC`, `UGRD`/`VGRD` @10 m | **Yes** — global waves incl. swell partitions and Stokes drift. §3.1. |
| `model_gewps/25km/HH/` | **GEWPS** — Global Ensemble Wave Prediction System | 0.25°, **21 members**, 3-hourly | 16 variables (same minus `ICEC`, `UGRD`/`VGRD`) | **Yes** — wave uncertainty. §3.2. |
| `model_caps/3km/HH/FFF/` | **CAPS** — Coupled Arctic Prediction System (atmosphere) | 3 km rotated lat-lon (0.03°) | `…_MSC_CAPS_AbsoluteVorticity_IsbL-0250_…grib2` | **No — Arctic domain, does not reach the Avalon.** Confirmed by GetFeatureInfo, §2.4. Reject. |
| `model_cansips/100km/forecast/YYYY/MM/` | **CanSIPS** — Canadian Seasonal to Interannual Prediction System | 1.0° lat-lon, monthly-to-seasonal (P00M–P12M), probabilistic | `202306_MSC_CanSIPS_AirTemp-ProbAboveNormal_AGL-2m_LatLon1.0_P00M-P03M.grib2` | **Marginal** — seasonal outlook, not a weather map product. §9.2. |
| `coastal-flooding/risk-index/` | **MSC Coastal Flooding Risk Index** | GeoJSON polygons per region | **`…_MSC_CoastalFloodingRiskIndex_NLWO_NL_PT014H30M_v1.json`** and PT038H30M / PT062H30M / PT086H30M / PT110H30M | **Yes — and it has an explicit Newfoundland region.** §5.2. |
| `model_gdps-geml/25km/HH/FFF/` | **GDPS-GEML** — GDPS Global Ensemble Machine Learning | 0.25° | `…_MSC_GDPS-GEML_AirTemp_AGL-2m_LatLon0.25_PT0H.grib2`, plus `IsbL-0050…` pressure levels | Atmospheric — **belongs to the NWP agent's lane**, flagged here only because the brief asked. |

### 2.2 RIOPS — Regional Ice-Ocean Prediction System ⭐

The most valuable single addition in this document.

| Field | Detail |
| --- | --- |
| **Producer** | ECCC / Canadian Centre for Meteorological and Environmental Prediction |
| **Gives you** | Sea-ice concentration, volume (→ thickness), surface temperature, snow volume, **ice drift velocity (u,v)**, divergence, shear, strength, internal pressure; SSH; mixed-layer depth; turbocline depth; and T/S/u/v at 0.5 m and full depth |
| **Resolution** | **5 km** polar stereographic — vastly better than GIOPS 0.2° (~15–22 km here) |
| **Cadence / horizon** | 4 cycles/day (00/06/12/18 Z), **hourly out to +84 h** (confirmed 000…084) |
| **Format** | NetCDF, one variable per file |
| **Endpoint** | `https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/model_riops/netcdf/forecast/polar_stereographic/2d/<HH>/<FFF>/<YYYYMMDD>T<HH>Z_MSC_RIOPS_<VAR>_<LEVEL>_PS5km_P<FFF>.nc`<br>WMS: `https://geo.weather.gc.ca/geomet/?service=WMS&…&layers=RIOPS_IICECONC_SFC` (161 RIOPS layers in GetCapabilities) |
| **Access** | Genuinely open, no key |
| **Licence** | Open Government Licence – Canada (MSC Datamart / `https://eccc-msc.github.io/open-data/`) |
| **Coverage over the Avalon** | **Confirmed.** |

**VERIFIED, two ways.**

1. Directory listing of all 17 2D variables and 4 3D variables at
   `.../2d/00/000/` and `.../3d/00/000/`, plus the full 000→084 hour range.
2. GeoMet `GetFeatureInfo` at a Grand Banks point (46.0–47.0 N, 49.6–48.4 W):
   - `RIOPS_SOSSHEIG_SFC` → `-0.028862953` m — **in domain.**
   - `RIOPS_VOTEMPER_DBS-0.5m` at St. John's (47.6089 N, 52.7586 W) →
     `290.88281 K` = **17.7 °C**, valid `2026-08-30T03:00Z`, reference time
     `2026-08-29T18:00Z`. Sensible for late August, and consistent with the
     SmartAtlantic buoy reading of 16.7 °C (§4.1).
   - `RIOPS_IICECONC_SFC` returned an **empty** FeatureCollection — this is
     *no ice in August*, not *out of domain*, since SSH at the same point
     returns a value. Ingest must handle empty responses.

**Why it matters:** it gives the project sea ice, ice drift, SST, currents and
mixed-layer depth at 5 km across the whole Newfoundland shelf, hourly, from one
open source. CIOPS-East (already registered) is finer at 2 km but has a smaller
domain; RIOPS is the shelf-and-Labrador-Current-scale companion.

### 2.3 GIOPS — Global Ice-Ocean Prediction System

Same access model as RIOPS. **VERIFIED**: 2D (`iiceconc`, `sossheig`) and 3D
(`votemper`, `vosaline`, `vozocrtx`, `vomecrty`) files listed; horizon 000→240
at 3 h. GeoMet `OCEAN.GIOPS.2D_SSH` at the Grand Banks returned
`-0.37336445` m — **in domain, VERIFIED**. (`OCEAN.GIOPS.2D_GL` returned empty;
the short-code layer names in that family are not self-documenting — inspect
`<Abstract>` in GetCapabilities before using them.)

**Honest assessment:** at 0.2° it adds little over RIOPS *for the Avalon
itself*, but it is the only registered-or-proposed source that extends 10 days
and covers the whole Labrador Sea / Gulf Stream basin. Add it after RIOPS, not
before.

### 2.4 CAPS-Ocean — reject, out of domain

390 `CAPS-Ocean_*` layers in GeoMet (3 km, sea ice + T/S at ~50 depth levels).
`GetFeatureInfo` for `CAPS-Ocean_3km_SeaIceFraction` at the Grand Banks
returned an **empty FeatureCollection**, as did the atmospheric CAPS check.
**VERIFIED negative.** The Coupled Arctic Prediction System domain does not
reach 46–48 N. Reject.

### 2.5 Non-Canadian global ocean models

| Source | Endpoint | Access | Verified? | Assessment |
| --- | --- | --- | --- | --- |
| **NOAA RTOFS-Global** (HYCOM-based, ~1/12°, incl. sea ice) | `https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtofs/prod/rtofs.<YYYYMMDD>/rtofs_glo_2ds_f<FFF>_{prog,diag,ice}.nc` | Open | **VERIFIED** — directory listed; `rtofs_glo_2ds_f000_ice.nc`, `…_prog.nc`, `…_diag.nc` present through the forecast range | Genuine independent alternative to GIOPS/RIOPS. Good for model-disagreement display. Files are large. |
| **HYCOM THREDDS** (`GLBy0.08/expt_93.0`) | `https://tds.hycom.org/thredds/catalog.html` | Open | **PARTIAL** — catalogue root 200, but the FMRC `.das` I tried returned an empty body. Dataset path unconfirmed. | Overlaps RTOFS. Low marginal value. Deprioritise. |
| **Copernicus Marine (CMEMS)** — `GLOBAL_ANALYSISFORECAST_PHY_001_024` (1/12° physics), `GLOBAL_ANALYSISFORECAST_WAV_001_027` (waves), `SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001` (OSTIA) | `https://data.marine.copernicus.eu/product/<PRODUCT_ID>/description`; data via `copernicusmarine` Python toolbox or the STAC catalogue `https://stac.marine.copernicus.eu/metadata/catalog.stac.json` | **Free account required.** Not anonymous. | **PARTIAL** — product description page and the STAC root both returned 200 (`61 212` B JSON). I did **not** authenticate, so I have not confirmed any variable, grid or time range. Product IDs are **DOC-ONLY**. `https://data.marine.copernicus.eu/api/datasets` is **404** — there is no such open REST endpoint. | High quality, but it is a credentialed dependency and it duplicates RIOPS/GIOPS/GDWPS for this region. See §9.1. |

---

## 3. Waves

Registry has RDWPS and REWPS (regional). Nothing global, nothing ensemble,
nothing observational.

### 3.1 GDWPS — Global Deterministic Wave Prediction System

| Field | Detail |
| --- | --- |
| **Producer** | ECCC/CCMEP (WAVEWATCH III based) |
| **Gives you** | 19 fields: `HTSGW` (combined Hs), `WVHGT` (wind-wave Hs), `SWHFSWEL`/`SWHSSWEL` (1st/2nd swell Hs), `PWPER`, `MZWPER`, `PPERWW`, `PWPFSWEL`/`PWPSSWEL`, `PWAVEDIR`, `WVDIR`, `WWSDIR`, `MWDFSWEL`/`MWDSSWEL`, `USSD`/`VSSD` (**Stokes drift**), `ICEC`, `UGRD`/`VGRD` @10 m |
| **Resolution** | 0.25° global; hourly (`PT1H`) to +48 h and 3-hourly (`PT3H`) beyond — both layer sets present in GeoMet |
| **Endpoint** | `https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/model_gdwps/25km/<HH>/<YYYYMMDD>T<HH>Z_MSC_GDWPS_<VAR>_Sfc_LatLon0.25_PT<FFF>H.grib2`<br>WMS layers `GDWPS_25km_<VAR>_PT1H` / `_PT3H` |
| **Access / licence** | Open; OGL-Canada |

**VERIFIED.** Full variable list enumerated from the live directory.
`GetFeatureInfo` on the Grand Banks (46.0–47.0 N, 49.6–48.4 W):
`GDWPS_25km_HTSGW_PT1H` → **1.87939 m**, `GDWPS_25km_PWPER_PT1H` →
**9.77346 s**, valid `2026-08-30T03:00Z`.

**Important gotcha, VERIFIED:** the same query centred on **47.5 N, 52.75 W**
returned `value: 9999` ("`>= 15.0 (m)`"). At 0.25° that cell is land-masked, and
`9999` is the fill value, **not** a 15 m sea. Any ingest must treat 9999 as
missing and sample offshore. This is exactly the kind of bug that would
otherwise ship a "15 m waves in St. John's harbour" tile.

### 3.2 GEWPS — Global Ensemble Wave Prediction System

**VERIFIED.** 16 variables × **21 members** (`_01`…`_21`), 3-hourly, 0.25°.
Datamart files listed; GeoMet layer names follow
`GEWPS_25km_<LongVarName>_<NN>`. `GetFeatureInfo` for
`GEWPS_25km_SignificantWaveHeight_01` at the Grand Banks → **1.941812 m**,
consistent with GDWPS's 1.879 m. Same land-mask 9999 caveat applies.

**Why it matters:** turns "waves will be 4 m" into "waves will be 3–6 m, 21
members" — the honest version, and a natural fit for a map that already carries
GEPS/REPS ensembles.

### 3.3 NOAA GFS-Wave (WAVEWATCH III) via NOMADS GRIB filter ⭐

| Field | Detail |
| --- | --- |
| **Producer** | NOAA/NCEP |
| **Gives you** | WW3 `HTSGW`, `PERPW`, `DIRPW`, `WIND`, `WDIR`, swell partitions |
| **Grid** | Several; **`atlocn.0p16`** — Atlantic Ocean regional at **0.16°**, better than GDWPS's 0.25°. (`arctic.9km`, `gnh_10m`, `global.0p16` also present.) |
| **Endpoint** | `https://nomads.ncep.noaa.gov/cgi-bin/filter_gfswave.pl?file=gfswave.t<HH>z.atlocn.0p16.f<FFF>.grib2&lev_surface=on&var_HTSGW=on&var_PERPW=on&var_DIRPW=on&subregion=&toplat=49&leftlon=-55&rightlon=-50&bottomlat=45&dir=%2Fgfs.<YYYYMMDD>%2F<HH>%2Fwave%2Fgridded` |
| **Access** | Open, no key. NOMADS has rate limits — be polite. |
| **Licence** | US Government work, public domain. |

**VERIFIED, and the best-behaved endpoint I tested.** The exact URL above
returned `HTTP 200`, `application/octet-stream`, **828 bytes**, beginning
`47 52 49 42` = `GRIB`. Server-side spatial and variable subsetting means you
download under a kilobyte per field for the Avalon box instead of a
continent-sized GRIB.

**Why it matters:** an independent, higher-resolution wave forecast for
model-comparison, at near-zero bandwidth and near-zero parsing cost.

### 3.4 Satellite altimeter significant wave height

**Not separately verified.** Jason-3 / Sentinel-6 Michael Freilich / SWOT /
CryoSat-2 along-track SWH is available through NOAA CoastWatch, PO.DAAC and
CMEMS `WAVE_GLO_PHY_SWH_L3_NRT_014_001`. All are **DOC-ONLY** here —
PO.DAAC OPeNDAP did not respond to my probe and CMEMS needs credentials.

**Honest verdict: not worth it for this project.** Altimeters are nadir-only
tracks; the chance of a pass over the Avalon at a useful time is low, and the
data are for validation, not for a map. Reject for now. Note that
**Sentinel-1 OCN (§1.6) is the better satellite wave product here** because it
is swath, not track.

### 3.5 Grand Banks wave climate — measured

See **`wsp_grand_banks_waypoint3_wave_buoy`** in §4.1 and the **MEDS wave
archive** in §4.5.

---

## 4. Buoys, moorings, gliders and profiling floats

### 4.1 CIOOS Atlantic ERDDAP ⭐⭐ — the biggest find in this document

| Field | Detail |
| --- | --- |
| **Producer** | CIOOS Atlantic (Canadian Integrated Ocean Observing System), aggregating Marine Institute / Memorial University, DFO NAFC, DFO BIO, Ocean Networks Canada, College of the North Atlantic and industry |
| **Endpoint** | `https://cioosatlantic.ca/erddap/` — full ERDDAP: `tabledap`/`griddap`, `.csv` `.json` `.nc` `.htmlTable`, server-side filtering, `search/advanced.json` with a lat-lon box |
| **Access** | **Genuinely open. No key, no registration, no rate-limit challenge.** |
| **Licence** | **`https://creativecommons.org/licenses/by/4.0/` — CC-BY 4.0**, read from each dataset's `NC_GLOBAL.license`. Attribution required; redistribution permitted. This is unusually clean for Canadian ocean data. |

**VERIFIED, extensively.** A bounding-box search
(`minLat=45&maxLat=50&minLon=-56&maxLon=-50`) returned **48 datasets**. The ones
that matter, with global attributes read from `info/<id>/index.json`:

| Dataset ID | What | Position | Dist. from St. John's | Time coverage | Verified? |
| --- | --- | --- | --- | --- | --- |
| **`SMA_st_johns`** | St. John's Buoy — 3 m AXYS met/ocean buoy in St. John's Bay just north of Cape Spear | 47.56716 N, 52.63058 W | **~6 km** | 2013-07-10 → **2026-08-29T20:30Z** | **VERIFIED with live data** |
| **`SMA_Holyrood_Buoy2`** | 1.7 m AXYS buoy, mouth of Holyrood Bay, **Conception Bay**, ~50 m water | 47.461835 N, 53.10811 W | **~32 km** | 2018-08-29 → **2026-08-29T20:26Z** | **VERIFIED (live)** |
| **`SMA_st_johns_wharf`** | St. John's Tide Station, Pier 18, Port Authority | 47.5689 N, 52.6922 W | **~1.5 km** | 2014-05-22 → 2021-09-15 (**dormant**) | **VERIFIED** |
| **`nafc_station_27_ctd_profiles`** | **Station 27** — DFO's flagship hydrographic station off Cape Spear | 47.50–47.568 N, 52.683–52.535 W | **~5–15 km** | 1983-08-10 → **2025-12-18** (summary notes historical 1946–1997 from MEDS) | **VERIFIED with live data** |
| **`wsp_grand_banks_waypoint3_wave_buoy`** | Grand Banks wave buoy, Waypoint 3 (industry) | 47.24 N, 50.95 W | **~135 km E** | **2022-03-01 → 2022-04-30 only** | **VERIFIED** |
| `SMA_MouthofPlacentiaBayBuoy`, `SMA_head_of_placentia_bay-come_by_chance_point`, `SMA_red_island_shoal` | Placentia Bay buoys | — | ~100–150 km SW | — | Listed, **PARTIAL** |
| `SMA_bonavista`, `SMA_bay_of_exploits`, `SMA_manolis_buoy`, `SMA_Fortune_Bay_Buoy` | Other NL buoys | — | 200–400 km | — | Listed, **PARTIAL** |
| `DFO_Sutron_NHARB`, `DFO_Sutron_KLUMI` | Placentia Bay shore stations | — | — | — | Listed, **PARTIAL** |
| `nafc_azmp_ctd_profiles` | **AZMP** NL-region rosette profiles | NL shelf | — | — | Listed, **PARTIAL** |
| `bio_maritimes_glider_*` (10 deployments) | Slocum gliders in **Bonavista Bay** and **Trinity Bay**, 2018–2024 | — | — | delayed-mode | Listed, **PARTIAL** |
| `bio_remote_sensing_occci_poly4`, `…modis_aqua_chl_poly4`, `…occci_nwa_poly4_spring_bloom` | NW Atlantic satellite chlorophyll and spring-bloom metrics | — | — | 1997–present | Listed, **PARTIAL** |

**`SMA_st_johns` — full variable set (65 vars; the `curr_{spd,dir}N_avg`
family is a 20-bin ADCP profile):**
`air_temp_avg`, `air_dewpoint_avg`, `air_humidity_avg`, `air_pressure_avg`,
`wind_spd_avg`, `wind_spd_max`, `wind_dir_avg`, `wind_spd2_avg`,
`wind_spd2_max`, `wind_dir2_avg`, `wind_chill`, `wind_chill_2`, `humidex`,
`wave_ht_sig`, `wave_ht_max`, `wave_period_max`, `wave_dir_avg`,
`wave_spread_avg`, `surface_temp_avg`, `curr_spd_avg`, `curr_dir_avg`,
`curr_spd2..20_avg`, `curr_dir2..20_avg`, `precise_lat`, `precise_lon`.

**Live pull, VERIFIED verbatim:**

```
GET https://cioosatlantic.ca/erddap/tabledap/SMA_st_johns.csv
    ?time,wave_ht_sig,wave_ht_max,wave_period_max,wave_dir_avg,
     surface_temp_avg,curr_spd_avg,air_temp_avg,wind_spd_avg
    &time>=2026-08-29T18:00:00Z

time,wave_ht_sig,wave_ht_max,wave_period_max,wave_dir_avg,surface_temp_avg,curr_spd_avg,air_temp_avg,wind_spd_avg
UTC,m,m,s,degree,degree_C,mm s-1,degree_C,m s-1
2026-08-29T18:00:01Z,0.9,1.3,10.5,52,16.7,511.0,17.3,4.9
2026-08-29T19:00:01Z,1.0,1.7,10.5,48,16.7,750.0,17.0,3.6
2026-08-29T19:30:01Z,1.1,1.7,10.5,46,16.7,435.0,17.1,4.2
2026-08-29T20:00:01Z,1.0,1.6,11.1,49,16.7,82.0,17.0,3.0
2026-08-29T20:30:01Z,1.1,2.6,10.0,45,16.7,644.0,17.0,3.2
```

**Cross-validation, which is the real payoff:** this buoy's `surface_temp_avg`
of **16.7 °C** sits between RIOPS's modelled 17.7 °C (§2.2) and MUR SST's
satellite 16.61 °C (§6.1) at the same time and place. That is three independent
sources agreeing to about a degree — exactly the kind of triangulation this
project is for.

**Station 27, VERIFIED live:**

```
GET https://cioosatlantic.ca/erddap/tabledap/nafc_station_27_ctd_profiles.csv
    ?time,latitude,longitude,depth,TEMPS901,PSALST01&time>=2025-12-01T00:00:00Z

2025-12-18T12:21:00Z,47.5455,-52.586666,NaN,2.3758,31.7178
```

2.4 °C and 31.7 PSU in mid-December — the cold, fresh Labrador Current
signature. Note `depth` was `NaN` in this slice; the pressure variable
`PRESPR01` should be used instead. Station 27 also carries **`ice_bergs`,
`ice_conc`, `ice_stage`, `ice_sandt`** as observer fields — a nearly
80-year local record of iceberg presence off Cape Spear.

**Why it matters:** this one server supplies the project's only genuine local
marine ground truth — waves, SST, currents, air, tide and a historic
hydrographic series — under CC-BY, over plain HTTP, with server-side filtering.
It should be the first thing added.

### 4.2 SmartAtlantic's own ERDDAP

`https://www.smartatlantic.ca/erddap/` — a second, **partly disjoint** ERDDAP.
**VERIFIED**: the same Avalon bbox search returned **38 datasets**, overlapping
CIOOS Atlantic but adding:

- `uvic_onc_mun_mi_conception_bay_ctd` and
  `uvic_onc_mun_mi_conception_bay_fluorometer` — **Ocean Networks Canada /
  MUN / Marine Institute cabled Conception Bay instruments**, deployed
  2021-02-14. This is ONC data reachable **without an ONC token** (see §4.4).
- `mun_glider_unit_472_trinity_bay_2014`, `…_473_trinity_bay_{2014,2016,2018}`,
  `…_334_placentia_bay_2022`, `…_048_fortune_bay_2012`,
  `…_049_newfoundland_shelf_2006`, `mun_glider_data_pearldiver_labrador_sea_2019`,
  `sunfish_labrador_sea_2022_…` — **MUN glider deployments in Trinity Bay,
  Placentia Bay and the Labrador Sea.**
- `SMA_Holyrood_Buoy1_wind_raw`, `SMA_holyrood_shore_station_W60-G500`.
- `eccc_opp_atlantic` — "MSC Datamart realtime moored buoy data", i.e. a
  pre-digested ERDDAP mirror of the ECCC buoys.
- `eccc_opp_44488_east_chedabucto_bay`, `…44489…`, `…44490_west_bay_of_fundy`.
- `DFO_Sutron_DOGIS`, `DFO_Sutron_POOLC` (Fortune Bay).

**Practical note:** query both servers. Neither is a superset of the other.

### 4.3 Argo profiling floats ⭐

| Field | Detail |
| --- | --- |
| **Producer** | International Argo Programme; Coriolis/Ifremer GDAC |
| **Gives you** | T, S, pressure profiles 0–2000 m, ~10-day cycle per float; adjusted and real-time modes; `ArgoFloats-synthetic-BGC` for BGC variables |
| **Endpoint** | `https://erddap.ifremer.fr/erddap/tabledap/ArgoFloats.csv?<vars>&time>=…&latitude>=…&latitude<=…&longitude>=…&longitude<=…` |
| **Access** | **Genuinely open, no key.** Ifremer asks that you always constrain time and lat/lon (the table is enormous). |
| **Licence** | Argo data are freely available without restriction; the programme requests the standard acknowledgement ("These data were collected and made freely available by the International Argo Program…"). |

**VERIFIED with live data.** Query over 44–50 N, 56–46 W, August 2026,
pressure ≤ 10 dbar:

```
1902112,2026-08-29T09:46:06Z,49.8169,-49.377,4.23,14.449,32.5822
1902789,2026-08-22T07:13:17Z,44.31815,-47.57393,1.08,18.981,31.951
1902789,2026-08-12T00:57:53Z,44.25751,-47.47396,1.0,16.79,32.248
```

Float **1902112** was profiling at 49.82 N, 49.38 W on **2026-08-29** — on the
Newfoundland shelf edge, showing 14.4 °C / 32.58 PSU, the low-salinity
Labrador Current signature. Float **1902789** was south of the Tail of the Bank
in warmer, fresher near-surface water.

**Why it matters:** this is the only source in this whole document that gives
**subsurface temperature and salinity structure** in the Labrador Current in
near-real time, free and without credentials. It is what makes "the cold water
is 40 m deep here" sayable. Floats drift, so coverage is opportunistic — some
weeks there will be nothing within 200 km. Design for intermittency.

### 4.4 Ocean Networks Canada

`https://data.oceannetworks.ca/api/locations` returned **HTTP 401** with a JSON
error body. **VERIFIED that a token is required.** ONC accounts are free but
must be requested. Given that ONC's Conception Bay instruments are already
mirrored token-free through the SmartAtlantic ERDDAP (§4.2), **the direct ONC
API is not worth the credential dependency for this project.**

### 4.5 MEDS / ISDM Canadian wave archive (DFO)

| Field | Detail |
| --- | --- |
| **Producer** | DFO Marine Environmental Data Section |
| **Gives you** | Historical Canadian wave-buoy records — hourly wind and wave time series, non-directional spectra, and Oceanweather hindcast series |
| **Formats** | CSV; "FormatB" (non-directional spectral); Co-Quad |
| **Entry point** | `https://www.meds-sdmm.dfo-mpo.gc.ca/isdm-gdsi/waves-vagues/data-donnees/index-eng.asp` — **VERIFIED HTTP 200** |
| **Access** | Open, but via an **interactive ASP search UI**. I found **no documented REST/bulk endpoint.** |
| **Licence** | No machine-readable licence found. Requested citation: "DFO (year). Marine Environmental Data Section Archive, https://meds-sdmm.dfo-mpo.gc.ca". **DOC-ONLY.** |

Note the sibling path `…/search-recherche/list-liste-eng.asp` returns a
**soft 404** (HTTP 200 with a "We couldn't find that Web page" body) — do not
trust it.

**Assessment:** this is the archive that holds the decommissioned Newfoundland
buoys (44251 etc.). Valuable for **wave climatology**, useless for real time,
and it would need scraping. **Reject for the live map; note as the source to
use if a climatology panel is ever built.**

### 4.6 OceanSITES

`https://oceansites.org/` did not respond to my probe (no HTTP status).
**DOC-ONLY.** OceanSITES is a deep-water reference-mooring network; I found no
site on the Newfoundland shelf. **Reject** — Argo (§4.3) covers this need
better here.

---

## 5. Tides, water level and storm surge

### 5.1 DFO IWLS — station identification (refinement of an existing source)

`dfo-iwls` is already registered, but the registry does not appear to pin the
station. **VERIFIED**: `https://api-iwls.dfo-mpo.gc.ca/api/v1/stations`
returns `HTTP 200`, 851 671 bytes, **1575 stations**. Nearest to St. John's:

| Dist. | Code | Name | Position | Internal `id` | Time series |
| --- | --- | --- | --- | --- | --- |
| **1.0 km** | **00905** | **St. Johns** | 47.5670, −52.7023 | `5cebf1e33d0f4a073c4bc176` | `wlo`, `wlf`, `wlp`, `wl1`, `wl2`, `wl3`, `wlp-hilo` |
| 10.0 km | 00907 | Middle Cove | 47.6509, −52.6959 | `5cebf1e13d0f4a073c4bbebf` | `wlp`, `wlp-hilo` |
| 10.6 km | 00903 | Petty Harbour | 47.4667, −52.7000 | `5dd3064de0fdc4b9b4be6697` | (none) |
| 12.9 km | 00912 | Portugal Cove | 47.6257, −52.8567 | `5cebf1e13d0f4a073c4bbec1` | `wlp`, `wlp-hilo` |
| 17.5 km | 00915 | Bell Island | 47.6298, −52.9235 | `5cebf1e33d0f4a073c4bc178` | `wlo`, `wlp`, `wlp-hilo` |
| 20.6 km | 00920 | Long Pond | 47.5174, −52.9786 | `5cebf1e13d0f4a073c4bbec3` | `wlo`, `wlp`, `wlp-hilo` |
| 28.4 km | 00900 | Bay Bulls | 47.3138, −52.8061 | `5dd30650e0fdc4b9b4be6bb8` | `wlo`, `wlp`, `wlp-hilo` |
| 37.1 km | 00925 | Holyrood Bay | 47.3891, −53.1354 | `5cebf1e33d0f4a073c4bc17a` | `wlo`, `wlp`, `wlp-hilo` |

**Station 00905 is the one to use — it is the only nearby station with `wlf`
(forecast) alongside `wlo` (observed) and `wlp` (predicted).**

**Live data VERIFIED:**

```
GET https://api-iwls.dfo-mpo.gc.ca/api/v1/stations/5cebf1e33d0f4a073c4bc176/data
    ?time-series-code=wlo&from=2026-08-29T00:00:00Z&to=2026-08-29T06:00:00Z

[{"eventDate":"2026-08-29T00:00:00Z","qcFlagCode":"1","reviewed":false,
  "timeSeriesId":"5cebf1e33d0f4a073c4bc171","value":1.391}, …]
```

**1-minute cadence**, with per-observation QC flags. Note the API is addressed
by the opaque `id`, not the human `code`.

### 5.2 MSC Coastal Flooding Risk Index — has a Newfoundland region ⭐

| Field | Detail |
| --- | --- |
| **Producer** | MSC / ECCC, in partnership with regional authorities |
| **Gives you** | A GeoJSON `FeatureCollection` of coastal-flooding risk polygons with `publication_datetime`, `validity_datetime`, `expiration_datetime` |
| **Endpoint** | `https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/coastal-flooding/risk-index/<YYYYMMDD>T<HHMM>Z_MSC_CoastalFloodingRiskIndex_<REGION>_<PROV>_PT<HH>H<MM>M_v1.json`<br>Also a GeoMet-OGC-API collection: `coastal-flooding-risk-index` |
| **Regions** | Includes **`NLWO_NL`** (Newfoundland and Labrador). Also `PSPC_BC`. |
| **Lead times** | For NL: PT014H30M, PT038H30M, PT062H30M, PT086H30M, PT110H30M — **five daily-ish steps out to ~110 h** |
| **Access / licence** | Open; OGL-Canada |

**VERIFIED, schema confirmed.** I fetched
`20260829T2130Z_MSC_CoastalFloodingRiskIndex_NLWO_NL_PT014H30M_v1.json`:
`HTTP 200`, 197 bytes:

```json
{"publication_datetime":"2026-08-29T21:30:00Z",
 "validity_datetime":"2026-08-30T12:00:00Z",
 "expiration_datetime":"2026-08-31T12:00:00Z",
 "type":"FeatureCollection","features":[]}
```

**`features: []` is the correct, healthy response for a calm August day** — the
file is published on schedule regardless. In an autumn storm this array
populates with risk polygons. An ingest job must not treat an empty feature
array as a failure.

**Why it matters:** it is a purpose-built, official, NL-specific coastal hazard
product; it is ~200 bytes; it is already in the tree the project reads; and it
is currently unused. Highest value-per-byte in this document.

### 5.3 RESPS-Atlantic-North-West — the storm-surge ensemble members

`eccc-resps` is registered, but GeoMet exposes **21 individual members**:
`RESPS-Atlantic-North-West_9km_StormSurge_01…21` and
`RESPS-Atlantic-North-West_9km_SeaSfcHeight_01…21`, at **9 km**.
`GDSPS_15km_SeaSfcHeight` is the global deterministic counterpart.

**VERIFIED**: `GetFeatureInfo` for
`RESPS-Atlantic-North-West_9km_StormSurge_01` at the Grand Banks returned
**`0.032371998` m**. Domain confirmed.

**Why it matters:** if the registry currently ingests only the mean, the members
give a surge probability distribution for free from an already-integrated
source.

### 5.4 PSMSL — St. John's mean sea level record

| Field | Detail |
| --- | --- |
| **Producer** | Permanent Service for Mean Sea Level (NOC Liverpool); GLOSS-affiliated |
| **Station** | **393 — "ST. JOHN'S, NFLD.", 47.566667 N, −52.716667 W** (~0.7 km from the city centre). Nearby: **1321 Argentia**, **2135 Bonavista**, **2354 St Lawrence**. |
| **Endpoint** | Catalogue `https://psmsl.org/data/obtaining/rlr.monthly.data/filelist.txt`<br>Monthly `https://psmsl.org/data/obtaining/rlr.monthly.data/393.rlrdata`<br>Annual `https://psmsl.org/data/obtaining/rlr.annual.data/393.rlrdata` |
| **Format** | `decimal_year; RLR_mm; missing_days_flag; quality_flags` |
| **Access** | Genuinely open, no key |
| **Licence** | Free for research/education; PSMSL requests citation of Holgate et al. (2013) and the PSMSL website. Commercial redistribution terms are not clearly stated. **PARTIAL on licence.** |

**VERIFIED.** Catalogue 139 329 B; the four NL stations extracted above.
Monthly file 27 898 B, **1073 values, 1935.625 → 2024.958**. Annual file spans
1957 → 2024, ending `2024; 7137; N; 000`.

**Why it matters:** this is the long-term sea-level-rise baseline for
St. John's. It is a climatology layer, not a forecast layer — **low priority for
a weather map**, but it is the correct source if the project ever contextualises
a surge against the local trend.

---

## 6. Sea surface temperature and fronts

The Labrador Current / Gulf Stream boundary and the Grand Banks front drive the
region's fog, and the registry has **no SST source at all**.

### 6.1 JPL MUR SST (GHRSST L4) via NOAA CoastWatch ERDDAP ⭐

| Field | Detail |
| --- | --- |
| **Producer** | NASA JPL (MUR = Multi-scale Ultra-high Resolution), served by NOAA CoastWatch West Coast Node |
| **Gives you** | `analysed_sst`, plus `analysis_error`, `mask`, `sea_ice_fraction` |
| **Resolution** | **0.01° (~1 km)**, global, daily, gap-free L4 |
| **Endpoint** | `https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csv?analysed_sst[(<time>)][(<latMin>):(<latMax>)][(<lonMin>):(<lonMax>)]` (also `.nc`, `.json`, `.png`) |
| **Access** | **Genuinely open, no key.** |
| **Licence** | NASA/NOAA data, public domain in the US; GHRSST/JPL attribution requested. |
| **Latency** | ~2–4 days behind real time (L4 analysis). |

**VERIFIED with live data**, subset directly over St. John's:

```
GET .../jplMURSST41.csv?analysed_sst[(2026-08-26T09:00:00Z)][(47.55):(47.60)][(-52.65):(-52.60)]

time,latitude,longitude,analysed_sst
UTC,degrees_north,degrees_east,degree_C
2026-08-26T09:00:00Z,47.55,-52.65,16.61
2026-08-26T09:00:00Z,47.55,-52.64,16.608
2026-08-26T09:00:00Z,47.55,-52.63,16.614
2026-08-26T09:00:00Z,47.55,-52.62,16.628
```

**Why it matters most of all:** at 1 km, MUR **resolves the Grand Banks thermal
front and the Labrador Current's cold tongue**, which no model in this document
does. And it agrees with the SmartAtlantic buoy (16.7 °C) to 0.1 °C. Fog on the
Avalon is fundamentally a warm-air-over-cold-water problem; an SST field is the
missing half of that story.

### 6.2 NOAA OISST v2.1 (daily, 0.25°)

| Field | Detail |
| --- | --- |
| **Endpoint** | `https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr/<YYYYMM>/oisst-avhrr-v02r01.<YYYYMMDD>.nc` (recent days carry a `_preliminary` suffix) |
| **Access / licence** | Open; US Government, public domain |

**VERIFIED.** Directory listing returned `oisst-avhrr-v02r01.20260825_preliminary.nc`
through `…20260828_preliminary.nc`. **Note the `_preliminary` suffix on recent
files** — an ingest job that assumes the plain name will 404 for the last
~2 weeks.

**Assessment:** 0.25° is too coarse to see the front. Value is the **1981–present
daily climatology** for anomaly calculations. Lower priority than MUR.

### 6.3 Model SST

`RIOPS_VOTEMPER_DBS-0.5m` (5 km, hourly, +84 h) and
`CIOPS-East_2km_SeaWaterPotentialTemp_0.5m` (already registered, 2 km) give
**forecast** SST, which MUR and OISST cannot. **VERIFIED** for RIOPS (17.7 °C
at St. John's). Use MUR for the observed front and RIOPS/CIOPS-East for where
it is going.

### 6.4 OSTIA, Coral Reef Watch, front-detection

- **OSTIA** (`SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001`, 1/20°): only via CMEMS
  with credentials. **DOC-ONLY.** Duplicates MUR at coarser resolution.
  **Reject.**
- **NOAA Coral Reef Watch 5 km**: `https://coralreefwatch.noaa.gov/product/5km/index.php`
  returned HTTP 200 (**VERIFIED reachable**), but the product is bleaching-alert
  and DHW for tropical reefs. **Irrelevant at 47 N. Reject** — the brief listed
  it, and the honest answer is no.
- **Operational SST front-detection products** (Cayula-Cornillon edge
  detection): I found no free, machine-readable, real-time front product for the
  Northwest Atlantic. Fronts are derivable from MUR gradients in a few lines.
  **Reject as a source; note as a derived layer.**

---

## 7. Hydrology

### 7.1 GeoMet-OGC-API hydrometric collections (refinement)

`eccc-hydrometric` is registered. GeoMet-OGC-API exposes six collections —
`hydrometric-stations`, `hydrometric-realtime`, `hydrometric-daily-mean`,
`hydrometric-monthly-mean`, `hydrometric-annual-statistics`,
`hydrometric-annual-peaks` — the last five of which give the **Water Survey of
Canada historical archive** the brief asked about, over the same open API.
**VERIFIED** via `https://api.weather.gc.ca/collections`.

**Stations near St. John's, VERIFIED** (`hydrometric-stations` with
`bbox=-53.6,47.0,-52.2,48.3`, 22 results; distances mine):

| Dist. | ID | Status | Name |
| --- | --- | --- | --- |
| **2.7 km** | **02ZM020** | **Active** | Learys Brook at Prince Philip Drive |
| **3.5 km** | **02ZM018** | **Active** | Virginia River at Pleasantville |
| **4.4 km** | **02ZM008** | **Active** | Waterford River at Kilbride |
| 12.4 km | 02ZM006 | Active | Northeast Pond River at Northeast Pond |
| 17.1 km | 02ZM022 | Active | Raymond Brook at outlet of Bay Bulls Big Pond |
| 3.8 / 4.5 / 6.3 / 7.3 / 7.6 / 8.4 / 9.4 / 11.6 / 11.9 / 31.2 km | 02ZM017, 02ZM019, 02ZM024, 02ZM023, 02ZM021, 02ZM010, 02ZM011, 02ZM001, 02ZM007, 02ZM002 | Discontinued | — |

**Live data VERIFIED:**

```
GET https://api.weather.gc.ca/collections/hydrometric-realtime/items
    ?f=json&STATION_NUMBER=02ZM020&sortby=-DATETIME&limit=3

{"STATION_NUMBER":"02ZM020","STATION_NAME":"LEARYS BROOK AT PRINCE PHILIP DRIVE",
 "DATETIME":"2026-08-29T22:40:00Z","LEVEL":0.537,"DISCHARGE":0.05, …}
```

**5-minute cadence.** Three active gauges inside 4.5 km of downtown, with both
level and discharge — much better urban-flooding coverage than the registry
implies.

### 7.2 Water Office direct CSV service

`https://wateroffice.ec.gc.ca/services/real_time_data/csv/inline?stations[]=02ZM020&parameters[]=46&start_date=…&end_date=…`
returned **`HTTP 200`, `text/csv`, 18 432 bytes. VERIFIED.**

Caveats: the bare form without date parameters returns **422**; the documented
service-links page `https://wateroffice.ec.gc.ca/services/links_e.html` is
**404**. The GeoMet OGC-API (§7.1) is the better-documented door. Include this
only as a fallback.

### 7.3 NL provincial water resources — `nl-water` on Datamart ⭐

This resolves the registry's `provincial-hydrometric [licence_review]` entry.

| Field | Detail |
| --- | --- |
| **Producer** | Government of Newfoundland and Labrador, Department of Environment, Climate Change and Municipalities, **Water Resources Management Division (NL-DECCM-WRMD)** — redistributed through ECCC's Datamart |
| **Endpoint** | `https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/observations/swob-ml/partners/nl-water/<YYYYMMDD>/<YYYY-MM-DD>-<HHMM>-nl-deccm-wrmd-<STNID>-AUTO-swob.xml` |
| **Format** | SWOB-ML (OGC O&M 1.0 XML) — the same schema the registry already parses for `eccc-swob` |
| **Cadence** | ~30 min (288 files/day across 12 stations) |
| **Access** | Open, no key |
| **Licence** | ⚠️ The embedded `data_attrib_not` reads: *"Data provided by the Government of Newfoundland and Labrador … Water Resources Management Division (NL-DECCM-WRMD). **All rights reserved.**"* This is **not** an open licence statement. Attribution is mandatory; redistribution rights are unclear. Keep the `licence_review` flag. |

**VERIFIED.** 12 stations; I resolved each one's coordinates from its SWOB-ML:

| Dist. | Station ID | Position | Name |
| --- | --- | --- | --- |
| **2.9 km** | **`nl-deccm-wrmd-nlencl0001`** | 47.58036, −52.73936 | **Pippy Park in St. Johns** |
| **24.4 km** | `nl-deccm-wrmd-nlencl0015` | 47.483928, −53.016842 | Conception Bay South |
| 84.5 km | `nl-deccm-wrmd-nlencl0013` | 47.430339, −53.820658 | Vale LH2 |
| 291.8 km | `nlencl0002` | 48.975, −56.03472 | Exploits River at Badger |
| 299.7 km | `nlencl0010` | 48.84467, −56.26941 | Exploits below Noel Paul's Brook MET |
| 341.9 km | `nlencl0014` | 48.346044, −57.152025 | Marathon Gold |
| 359.9 km | `nlencl0005` | 49.27444, −56.85166 | Sandy Lake near Birchy Narrows |
| 457.4 km | `nlencl0003` | 49.98277, −57.76055 | Humber River at Humber Village Bridge |
| 831.2 / 850.0 / 936.7 / 1112.2 km | `nlencl0011`, `nlencl0006`, `nlencl0009`, `nlencl0008` | Labrador | Mud Lake Rd, Muskrat Falls, Metchin River, TLH |

**Full observed elements at Pippy Park (2026-08-29T23:30Z), VERIFIED:**
`air_temp` 17.9 °C, `rel_hum` 99 %, `stn_pres` 1038 hPa, `mslp` 1050.6 hPa,
`dwpt_temp` 17.7 °C, `tot_globl_solr_radn_pst1hr` 0.0 kJ/m², `brght_sunshn_pst1hr`
0.0 h, `avg_wnd_spd_pst1hr` 0.0 km/h, `avg_wnd_dir_pst1hr` 0°,
`max_wnd_spd_pst1hr` 2.1 km/h, `wnd_dir_pst1hr_max_spd` 197°,
`pres_tend_amt_pst3hrs` −1 hPa, `batry_volt` 13.04 V, `stn_elev` 101.2 m,
`wnd_snsr_vert_disp` 10 m.

**Two honest caveats.** (1) Despite being run by the Water Resources Management
Division, `nlencl0001` reports **meteorological** elements — no water level or
discharge in this file. Treat it as a met station, not a stream gauge, unless a
different element set appears in winter. (2) The `mslp` of 1050.6 hPa against
`stn_pres` 1038 hPa at 101 m elevation looks suspect; validate before display.

### 7.4 Other NL partner feeds on Datamart

Also present and unregistered, **VERIFIED as existing directories**:
`partners/nl-firewx/` (NL Dept. of Fisheries, Forestry and Agriculture fire-weather
stations, hourly, e.g. `2026-08-29-0000-nl-dffa-001-AUTO-swob.xml`) and
`partners/dnd-ccg-lighthouse/` (DND/Canadian Coast Guard **lighthouse**
stations, 3-hourly, e.g. `20260829T0230Z_DND-CCG_SWOB_1060080.xml`). I did not
enumerate NL-specific lighthouses; the example I walked to (`addenbroke`) is
British Columbia. **PARTIAL** — worth an enumeration pass, since CCG lighthouse
stations around the Avalon would be genuinely local marine observations.

### 7.5 `model_ohps/` — reject

The brief hoped OHPS was a general hydrological prediction system. **It is
not.** `model_ohps/slfe/100m/` = **St. Lawrence Fluvial Estuary** only, with
variables `WaterLvlRiver_Sfc` and `RiverVelocity{,X,Y}_DBS-Avg` on a 100 m grid.
**VERIFIED** by walking to leaf files. Roughly 1500 km from St. John's, wrong
watershed. Reject.

### 7.6 Snow water equivalent

I did not find a dedicated open SWE product for Newfoundland.
`CaLDAS`/`HRDLPS` (both already registered) carry snow state, and Datamart has
`partners/bc-env-snow/` — **British Columbia only**. **Reject**: no NL-specific
SWE source located. Stated as a gap, not a finding.

---

## 8. Offshore industry and research data

Honest summary: **there is very little genuinely open Grand Banks platform
met-ocean data, and what exists is fragmentary.**

| Source | Finding | Verified? |
| --- | --- | --- |
| **`wsp_grand_banks_waypoint3_wave_buoy`** (CIOOS Atlantic) | The one real industry met-ocean dataset I could reach. WSP Global Inc., 47.24 N, 50.95 W (~135 km E of St. John's), **CC-BY 4.0**. Variables: `Significant_Wave_Height`, `Hm0`, `Max_Wave_Height`, `Average_Wave_Height`, `H10`, `Mean_Wave_Period`, `Significant_Wave_Period`, `Peak_Wave_Period`, `T10`, `Mean_Magnetic_Direction`, `Mean_Spread`, `Number_of_Zero_Crossings`, `Tp5_Tp_READ_method`. **But the record is 2022-03-01 → 2022-04-30 only** — two months, four years stale. | **VERIFIED** |
| **C-NLOPB / C-NLOER** (regulator) | Publishes Environmental Effects Monitoring reports for Hibernia, Terra Nova, White Rose and Hebron as **PDFs** at `https://www.cnlopb.ca/environment/projects/`. No met-ocean data service, no API. Archived material available "by request". | **DOC-ONLY** |
| **Hibernia / Terra Nova / White Rose / Hebron platform met-ocean feeds** | Operators collect extensive wind/wave/current data. I found **no public feed and no open archive.** Some of it reaches ECCC/NAV CANADA via synoptic reports but is not separately published. | **Negative finding.** Do not promise this. |
| **C-CORE Ice Chart Service** (`https://icechart.c-core.app/`) | HTTP 200 (`text/html`, 8 423 B) — a JS single-page app. C-CORE states it converts CIS products to cloud-native formats and exposes "CIS Viewer and API". I found **no public, documented, unauthenticated API endpoint**; `/api/` returns the SPA shell, not JSON. Almost certainly a **commercial/registered service**. | **PARTIAL — reachable, but no open API confirmed.** |
| **DFO NAFC** (Northwest Atlantic Fisheries Centre, St. John's) | Reachable, and better than expected — its data flow through CIOOS Atlantic as `nafc_station_27_ctd_profiles`, `nafc_azmp_ctd_profiles`, `nafc_multispecies_ctd_profiles`, `nafc_nsrf_ctd_profiles`, `nafc_bulk_unsorted_ctd_profiles`, all CC-BY. **This is the realistic route to DFO research-cruise data.** | **VERIFIED (listing); Station 27 VERIFIED with data** |
| **Marine Institute** | `https://www.marineinstitute.ca/` did not respond to my probe. But MI is the `institution` on every `SMA_*` dataset in CIOOS Atlantic — so **MI data are already accessible via ERDDAP**, which is the better door anyway. | **VERIFIED indirectly** |
| **MEOPAR**, **Ocean Frontier Institute** | Research networks and funders, not data services. Their outputs land in CIOOS. No separate machine-readable endpoint found. | **Negative finding. Reject.** |

**The realistic conclusion:** stop looking for platform feeds and take
**CIOOS Atlantic** as the aggregation point. It is where MI, DFO NAFC, DFO BIO,
ONC and at least one industry dataset actually surface, under a clean licence.

---

## 9. Credentialed and lower-value sources — stated precisely

### 9.1 Copernicus Marine Service (CMEMS)

**The user must not be told this is open.** Access requires a free
`marine.copernicus.eu` account and either the `copernicusmarine` Python toolbox
(which does an interactive/stored login) or credentialed S3/STAC access.
`https://data.marine.copernicus.eu/api/datasets` is **404 — VERIFIED**; there
is no anonymous REST API.

Product IDs relevant here (`GLOBAL_ANALYSISFORECAST_PHY_001_024`,
`GLOBAL_ANALYSISFORECAST_WAV_001_027`,
`SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001`) are **DOC-ONLY** — I did not
authenticate and cannot confirm their grids, variables or time ranges.

Licence: the Copernicus Marine Service Licence permits free use including
commercial, with attribution. **DOC-ONLY.**

**Verdict:** genuinely excellent data, but for the Avalon it is largely
**duplicated by RIOPS + GIOPS + GDWPS + MUR, all of which are anonymous**. Add
CMEMS only if a specific product (e.g. reanalysis for climatology) is actually
needed. It should not be in the first ten.

### 9.2 CanSIPS

**VERIFIED as existing** (`model_cansips/100km/forecast/YYYY/MM/`, 1.0°,
probabilistic monthly/seasonal). It is a seasonal outlook at 100 km. For a
weather map of St. John's it is the wrong time scale and the wrong resolution.
**Reject** unless a seasonal-outlook panel is planned.

### 9.3 GEBCO / CHS NONNA bathymetry

`https://download.gebco.net/` → 200; `https://data.chs-shc.ca/geoserver/web/`
→ 200. **VERIFIED reachable, contents unverified.** Bathymetry is static
context, not weather. Useful for making current and wave maps legible (shelf
break, Grand Banks edge). **Low priority, one-time fetch, not an ingest source.**

---

## 10. Top 10 additions, ranked by value per unit of work

1. **CIOOS Atlantic ERDDAP — `SMA_st_johns`, `SMA_Holyrood_Buoy2`,
   `nafc_station_27_ctd_profiles`** (§4.1). *Verified live, CC-BY 4.0, no key,
   `.csv` over HTTP with server-side filtering, buoy is 6 km away.* One HTTP GET
   returns waves, SST, currents, wind and pressure at the exact location the map
   is about. It is also the only thing here that can **validate** every model
   layer the project already ingests — it already agreed with RIOPS and MUR to
   within a degree during this research. Nothing else comes close on
   value-per-hour.

2. **RIOPS** (§2.2). *Verified in-domain two ways.* Sea ice + ice drift + SST +
   currents + mixed-layer depth at **5 km, hourly, +84 h**, from the Datamart
   the project already reads, in the NetCDF the project already parses. It
   single-handedly closes the sea-ice gap on the model side and adds ocean
   physics between CIOPS-East's 2 km box and GIOPS's 0.2° globe.

3. **International Ice Patrol iceberg limit** (§1.1). *All three formats
   verified 200.* 25 KB of KML, daily, no key, and it answers the most
   distinctively Newfoundland question there is. Two hours of work.

4. **MUR SST** (§6.1). *Verified with a live subset over St. John's.* 1 km SST
   is the only source in this document that resolves the Labrador Current front
   — the physical driver of Avalon fog. ERDDAP griddap does the spatial subset
   server-side, so the payload is tiny.

5. **MSC Coastal Flooding Risk Index, `NLWO_NL`** (§5.2). *Verified, schema
   confirmed.* ~200 bytes, five lead times to +110 h, an official NL-specific
   coastal hazard product, sitting unused in a Datamart directory the project
   already walks. Nearly free.

6. **GDWPS + GEWPS** (§3.1–3.2). *Verified with values at the Grand Banks.*
   Global deterministic and 21-member ensemble waves including swell partitions
   and Stokes drift — the registry currently has regional waves only. Same
   Datamart, same GRIB2 tooling. **Ship the 9999 land-mask guard with it.**

7. **NL provincial `nl-water` SWOB feed** (§7.3). *Verified; Pippy Park is
   2.9 km away.* Resolves an existing `licence_review` entry with a concrete
   endpoint, in a schema the project already parses. Ranked here rather than
   higher because of the "All rights reserved" attribution string — the
   engineering is trivial, the licence question is not.

8. **CIS SIGRID-3 East Coast ice charts** (§1.2). *Verified: downloaded,
   unpacked, bbox and metadata read. OGL-Canada.* The authoritative observed ice
   state for Newfoundland Waters. Ranked eighth only because it needs shapefile
   handling and seasonal-gap tolerance, and because RIOPS already provides
   modelled ice. For fidelity in February–May, it is indispensable.

9. **Argo via Ifremer ERDDAP** (§4.3). *Verified with a live 2026-08-29 profile
   on the Newfoundland shelf.* The only free, keyless source of subsurface T/S
   in the Labrador Current. Coverage is opportunistic, so build it as an
   "if a float is nearby" layer, not a guaranteed one.

10. **NOAA GFS-Wave via NOMADS GRIB filter** (§3.3). *Verified — returned an
    828-byte GRIB for the Avalon box.* An independent, 0.16° wave forecast at
    almost no bandwidth. Pure model-diversity value on top of GDWPS/RDWPS.

**Runners-up, in order:** RESPS 21 storm-surge members (§5.3) — likely a
one-line change if RESPS is already wired; SmartAtlantic ERDDAP for the ONC
Conception Bay instruments and MUN Trinity Bay gliders (§4.2); IWLS station
`00905` pinning (§5.1); Water Survey historical collections (§7.1); GIOPS
(§2.3); RTOFS (§2.5).

---

## 11. Not worth it, and why

**Rejected on domain — the data exist and are fine, but not here.**

- **WCPS** (`model_wcps/`) — West Coast. Verified as 1 km Pacific.
- **OHPS-SLFE** (`model_ohps/`) — St. Lawrence Fluvial Estuary, 100 m, ~1500 km
  away, wrong watershed. Verified.
- **CAPS and CAPS-Ocean** (`model_caps/`) — Arctic domain. Verified negative by
  `GetFeatureInfo` returning empty at the Grand Banks while other layers at the
  same point returned values.
- **NOAA Coral Reef Watch** — reachable, but bleaching alerts and Degree Heating
  Weeks for tropical reefs. Meaningless at 47 N.
- **OSI SAF sea-ice drift LR** — 62.5 km, Arctic-focused; will not resolve
  Newfoundland shelf ice. RIOPS ice drift at 5 km is strictly better here.
- **NSIDC Sea Ice Index (G02135)** — hemispheric extent totals only; no Avalon
  value even if the 500 error were transient.
- **OceanSITES** — no site on the Newfoundland shelf; endpoint did not respond.
  Argo covers the need.
- **`partners/bc-env-snow/`** — British Columbia.

**Rejected on access — obtainable, but the cost outweighs the marginal gain.**

- **Copernicus Marine (CMEMS)** — free but **credentialed**, and for this
  location it duplicates RIOPS, GIOPS, GDWPS and MUR, all of which are
  anonymous. Adding a credential dependency to re-derive data the project can
  already get is a bad trade. Revisit only for reanalysis/climatology.
- **OSTIA** — CMEMS-only, and coarser than MUR. Strictly dominated.
- **Ocean Networks Canada API** — verified 401 without a token. Its Conception
  Bay instruments are already exposed token-free through the SmartAtlantic
  ERDDAP. Do not take the credential.
- **CIS iceberg charts via `iceweb1`** — a JSF/PrimeFaces app with server-side
  view state; would need a headless browser to scrape, for a product IIP already
  publishes as KML and shapefile.
- **`ice-glaces.ec.gc.ca/www_archive/` and `/prods/`** — verified 403.
  `/prods/sigrids/` is the one open door; use it and stop.
- **MEDS/ISDM wave archive** — open in principle, but interactive-ASP only with
  no documented bulk endpoint, and one of its listed paths is a soft-404.
  Historical climatology only. Note it for a future climatology feature; do not
  build a scraper now.
- **C-CORE Ice Chart Service** — an SPA with no confirmed public API; almost
  certainly commercial. Its input (CIS) is free at `/prods/sigrids/`.

**Rejected on cost/benefit — real, open, and still not worth it yet.**

- **Sentinel-1 SAR granules** — genuinely valuable for ice and icebergs, and
  the catalogue is verified working with an OCN product over St. John's from
  yesterday. But download needs a CDSE account, granules are SAFE archives of
  hundreds of MB, and turning them into a map layer means SNAP/GDAL processing.
  This is a project, not an ingest job. Defer.
- **Satellite altimeter SWH (Jason-3 / Sentinel-6 / SWOT / CryoSat-2)** —
  nadir-only tracks; the probability of a useful pass over the Avalon at a
  useful time is low, and the data are for validation rather than display.
  Sentinel-1 OCN is the better satellite wave product here because it is swath.
- **HYCOM THREDDS** — root catalogue verified 200 but the FMRC dataset path I
  tried returned nothing, and it overlaps RTOFS, which is verified working and
  simpler.
- **CanSIPS** — verified to exist; 100 km seasonal probabilities are the wrong
  time and space scale for this map.
- **PSMSL** — verified end to end (station 393, 1935–2024), but it is a
  decadal sea-level-rise record. Correct for context, wrong for a weather map.
  Add only alongside a sea-level-trend feature.
- **GEBCO / CHS bathymetry** — static context, fetched once, not an ingest
  source.
- **NOAA OISST v2.1** — verified, but 0.25° cannot see the front. Its value is
  the 1981-present anomaly baseline; add it with a climatology feature, not now.
- **MEOPAR, Ocean Frontier Institute, Marine Institute (direct)** — networks and
  institutions, not data services. Their data are already in CIOOS Atlantic.
- **C-NLOPB / offshore platform met-ocean** — PDFs and access-by-request. There
  is no public feed. This should be recorded as a **negative finding** so nobody
  re-searches it.

**Existing registry entries this research says are weaker than they look —
flagged, not rejected.**

- **`eccc-marine-buoys-synop`** — verified to have **no station within 500 km**
  of St. John's. It is a Scotian Shelf proxy here, and the UI should not present
  it as local.
- **`municipal-hydrometric [unavailable]` / `provincial-hydrometric
  [licence_review]`** — the `nl-water` Datamart feed (§7.3) supersedes the
  latter with a working endpoint; the licence flag should stay.

---

## 12. Cross-cutting implementation notes

These came out of the verification work and will each cost someone an afternoon
if not written down.

1. **Datamart paths are date-prefixed.** `https://dd.weather.gc.ca/<YYYYMMDD>/WXO-DD/<product>/`.
   Every bare `/model_*/` and `/coastal-flooding/` path 404s. Retention ~30 days
   on the root index.
2. **Wave models use `9999` as a land/ice fill.** Verified: GDWPS at
   47.5 N, 52.75 W returns `9999` styled as `">= 15.0 (m)"`. Mask it, and sample
   offshore for coastal points.
3. **Empty is normal, not broken.** `RIOPS_IICECONC_SFC` returns an empty
   FeatureCollection in summer; the NL coastal-flooding GeoJSON returns
   `"features": []` on calm days; CIS `SGRDOEC` charts are intermittent in
   summer and may contain a single polygon. None of these are errors.
4. **OISST recent files carry a `_preliminary` suffix.** Verified for
   2026-08-25 → 2026-08-28.
5. **IWLS is addressed by opaque `id`, not station `code`.** St. John's is
   code `00905`, id `5cebf1e33d0f4a073c4bc176`.
6. **Query both ERDDAPs.** `cioosatlantic.ca` (48 datasets in bbox) and
   `smartatlantic.ca` (38) overlap but neither contains the other.
7. **Sentinel-1: use OData.** `resto/api/collections/Sentinel1/search.json`
   → 404; `POST /stac/search` with `collections: ["SENTINEL-1"]` → 400; the
   OData `$filter` form → 200 with results.
8. **GeoMet WMS `GetCapabilities` is 39.6 MB** with 8 241 layer/style names.
   Cache it; do not fetch it per request. Some `OCEAN.GIOPS.2D_*` layer names
   are opaque short codes — read `<Abstract>` before trusting a guess.
9. **`GetFeatureInfo` is an excellent cheap probe.** A 1° bbox at 100×100 px
   with `i=j=50` and `info_format=application/json` returns value, units,
   valid time and reference time. It is how most of the domain-coverage claims
   in this document were settled.

---

## 13. Source count

**52 distinct sources, products or endpoints assessed.**

| Category | Count |
| --- | --- |
| Verified live with a real payload | 27 |
| Reachable but claim unconfirmed (PARTIAL) | 9 |
| Documentation only, not reached | 8 |
| Confirmed negative (404 / 403 / 401 / out of domain) | 8 |

**Recommended for addition: 10 primary + 6 runners-up.**
**Explicitly rejected with reasons: 26.**
