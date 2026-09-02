# 01 — Atmospheric, NWP, satellite and remote-sensing sources for St. John's / Avalon Peninsula

**Target point:** 47.56 °N, 52.71 °W (St. John's, NL). Radiosonde site is **71802 / Mount Pearl NF** (~7 km SW of downtown). Airport is **CYYT**. Nearest ECCC radar is **CASHR, Holyrood NL** (S end of Conception Bay, ~30 km W).

**Scope:** NWP, AI/ML models, reanalysis/archives, satellite, lightning, upper-air & profiling, radar, fog-specific research. Marine/ocean/ice/hydrology and local/in-situ/climate/commercial are covered by sibling documents.

**Research date:** 2026-08-30. All "Verified" claims below were made with live HTTP requests from this machine on that date, with a research user agent. Anything marked *unverified* is from provider documentation only and should be re-checked before you build against it.

**Baseline:** `docs/research/00-current-inventory.md`, 59 sources. Two structural gaps stand out and drive most of the recommendations here:

1. **There is no reanalysis and no archive of any kind in the registry.** Not ERA5, not RDRS/CaSR, not ERA5-Land. That means the project has no way to answer "what normally happens here", no training/verification substrate for any statistical or ML post-processing, and no way to compute a fog climatology. This is the single largest gap.
2. **`noaa-goes-east` is the only satellite entry.** St. John's sits at roughly **60–63° satellite zenith angle from GOES-East at 75.2 °W** — heavily foreshortened, with low-cloud/fog detection degraded exactly where the project needs it most. Polar orbiters (VIIRS at ~750 m, twice-daily-plus at 47 °N with overlapping swaths from three platforms) matter *more* here than they would in Virginia. There are ~20 free, no-registration polar-orbiter products directly relevant to fog that the project does not have.

A third, smaller gap: the registry has NWP from ECCC, NOAA, ECMWF and DWD only. **UK Met Office global, JMA GSM, Météo-France ARPEGE-world and CMA GRAPES all verifiably return data at this exact point** and are free — cheap ensemble diversity.

---

## Legend

| Access term | Meaning |
|---|---|
| **Open** | Anonymous HTTP(S)/S3 GET. No account, no key, no click-through. |
| **Free registration** | Free account required; may involve a licence click-through or an API key. |
| **Application** | Free but a human reviews your request (form, days-to-weeks turnaround). |
| **Paid** | Contract or subscription. |
| **Research-only** | Free for non-commercial research, usually by request. |

---

# 1. NWP models

## 1.1 Confirmed-working national models NOT in the registry

Every row here was verified by an actual API call at 47.56 / −52.71 returning real numeric values on 2026-08-30, unless stated otherwise. The fastest route to all of them is Open-Meteo, which is free, keyless and non-commercial-use-licensed; the raw-provider route is given alongside for anything you want to ingest natively.

| Product | Producer | What it gives | Endpoint | Access | Licence | NL coverage | Verified? | Value here |
|---|---|---|---|---|---|---|---|---|
| **UKMO Global Deterministic 10 km** (`ukmo_global_deterministic_10km`) | UK Met Office | Global deterministic, ~10 km, hourly to 7 d, standard surface + pressure-level set | `https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=-52.71&models=ukmo_global_deterministic_10km&hourly=temperature_2m` ; raw at `https://openmeteo.s3.amazonaws.com/data/ukmo_global_deterministic_10km/` | Open (Open-Meteo); UKMO's own Data Hub is **paid** | Open-Meteo: CC-BY-4.0 / non-commercial use of API. UKMO upstream terms are stricter — attribution required | **Yes — returned 19.6 °C at the point** | The highest-resolution *global* model available for free at this location, and the only one that is not already in the registry from an operational centre with a strong North Atlantic record. Real ensemble diversity, not a near-duplicate of GFS/IFS. |
| **UKMO Global Ensemble 20 km** (`ukmo_global_ensemble_20km`, `_mean_20km`) | UK Met Office | ~18-member global ensemble, 20 km | same API, `models=ukmo_global_ensemble_20km` | Open via Open-Meteo | as above | **Returned nulls at this point in the 00Z run I tested** — either lag or a subset domain. Re-test before relying on it | Partially verified | Worth a re-test; if it populates it is a fourth independent ensemble. |
| **JMA GSM** (`jma_gsm`) | Japan Meteorological Agency | Global spectral model, ~0.5°/0.25°, 3-hourly to 11 d | `models=jma_gsm` on Open-Meteo | Open | Open-Meteo terms; JMA data is free for non-commercial | **Yes — 18.2 °C** | Genuinely independent data-assimilation lineage. Cheap ensemble spread. Low marginal value on its own; useful as a 5th member in a multi-model consensus. |
| **Météo-France ARPEGE World 0.25°** (`meteofrance_arpege_world025`) | Météo-France | Global, 0.25°, hourly, 4 d + | `models=meteofrance_arpege_world025` ; raw at `https://portail-api.meteofrance.fr/web/en/api/PaquetARPEGE` | Open (Open-Meteo); **free registration + API key** for Météo-France's own portal | Etalab / Licence Ouverte on the MF portal; attribution required | **Yes — 19.0 °C** | Fifth independent global. AROME does not reach Newfoundland (France domain only), so only ARPEGE-world is usable. |
| **CMA GRAPES Global** (`cma_grapes_global`) | China Meteorological Administration | Global, 0.25° | `models=cma_grapes_global` | Open via Open-Meteo | Open-Meteo terms | **Yes — 17.6 °C** | Marginal. Include only if you are explicitly building a max-diversity consensus; verification skill over the North Atlantic is the weakest of the set. |
| **MET Norway "seamless"** (`metno_seamless`) | MET Norway | Blended MEPS/EC — at 47 °N it falls through to the global backing model | `models=metno_seamless`, or MET Norway's own `https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=47.56&lon=-52.71` | Open (met.no requires a descriptive User-Agent, no key) | met.no: CC-BY-4.0, attribution required, rate-limited | **Yes — 17.8 °C via Open-Meteo; met.no locationforecast returned 200 directly** | **MEPS itself does NOT cover Newfoundland** (Nordic domain). What you get here is a repackaged global. Low added value beyond convenience. |
| **NAM 12 km North America** | NOAA/NCEP | 12 km, 3-hourly to 84 h. The 12 km parent domain **does** cover Newfoundland (unlike the CONUS nest) | `https://nomads.ncep.noaa.gov/pub/data/nccf/com/nam/prod/` (verified 200), also `s3://noaa-nam-pds` (verified 200) | Open | US Government work, public domain | Parent 12 km domain includes Atlantic Canada — *unverified at the grid-point level; check the `awphys` grid, not `conusnest`* | Endpoints verified; coverage inferred from domain definition | A genuine 12 km North American model outside ECCC's stable. Moderate value — RDPS at 10 km already covers this, so it is mostly a second opinion. |
| **ECMWF SEAS5 seasonal** (`ecmwf_seas5`, `..._ensemble_mean`, `..._monthly`) | ECMWF | Seasonal ensemble, monthly means, 7-month lead | `https://openmeteo.s3.amazonaws.com/data/ecmwf_seas5/` | Open | Open-Meteo terms | Global | Bucket prefix confirmed present; **API returned nulls at this point on 2026-08-30** | Out of scope for a nowcast/short-range map, but useful if the project ever wants a "how does this month compare" panel. |
| **ECMWF extended-range 46-day** (`ecmwf_ec46`, `ecmwf_ec46_weekly`) | ECMWF | Weekly means to 46 days | `https://openmeteo.s3.amazonaws.com/data/ecmwf_ec46/` | Open | as above | Global | Bucket prefix confirmed; `ecmwf_ec46_weekly` was **rejected as an invalid `models=` value** by the forecast API — use `ecmwf_ec46` | Sub-seasonal context. Low priority. |

**Models I tested that do NOT cover this point — do not waste effort on them:**
`ncep_hrrr_conus`, `ncep_nam_conus`, `ncep_nbm_conus`, `dwd_icon_eu`, `dwd_icon_d2`, `meteoswiss_icon_ch1/ch2`, `knmi_harmonie_arome_*`, `dmi_harmonie_arome_europe`, `italia_meteo_arpae_icon_2i`, `chmi_aladin_*`, `geosphere_arome_austria`, `meteofrance_arome_france*`, `ukmo_uk_deterministic_2km`, `metno_nordic_pp`. All returned either an explicit `"No data is available for this location"` or an all-null series. Newfoundland is outside every European and every US-CONUS convection-permitting domain. **The nearest thing to a high-resolution regional model over the Avalon is ECCC HRDPS at 2.5 km, which the registry already has.** There is no second 2.5 km opinion available anywhere for free.

`kma_gdps` and `bom_access_global` returned nulls at this point across both a forecast-only and a `past_days=2` query. Treat as not-usable until re-tested.

## 1.2 ECCC products in the datamart that the registry does not list

The MSC Datamart root (`https://dd.weather.gc.ca/today/`, verified 200) exposes these top-level directories. Cross-referencing against the registry, these are **absent**:

| Product | Endpoint | What it gives | Access / Licence | Verified? | Value |
|---|---|---|---|---|---|
| **RDPS vertical profiles ("ProgTephi")** | `https://dd.weather.gc.ca/today/vertical_profile/forecast/csv/ProgTephi_00_CYYT.csv` and `ProgTephi_12_CYYT.csv` | RDPS forecast sounding **at St. John's**: TT, dew-point depression, wind dir/spd, RH, geopotential height, vertical velocity on ~29 pressure levels, 0–48 h every 3 h. CSV, no GRIB decoding needed | Open; ECCC Open Government Licence – Canada, attribution required | **YES — fetched the file, header reads `GEM,regional,model,forecast,2026083000,CYYT,lat=47.620,lon=-052.730,St-Johns`** | **This is the highest-value single find in this document.** It is the forecast inversion structure over St. John's, as a plain CSV, updated twice daily, free. Advection fog is fundamentally a low-level stability + dew-point-depression problem, and this hands you exactly those two things in a machine-readable form with zero GRIB tooling. Ranked #1 below. |
| **Observed vertical profiles ("ObsTephi")** | `https://dd.weather.gc.ca/today/vertical_profile/observation/csv/ObsTephi_00_CYYT.csv` (and `_12_`) | The actual radiosonde ascent at St. John's, all levels, CSV | Open; OGL-Canada | **YES — `CYYT` confirmed present in the directory listing** (31 Canadian stations total) | The registry has `eccc-radiosonde` under `humidity_profile`, but if that entry points at BUFR bulletins, this CSV form is dramatically easier. Pairs with ProgTephi for a free forecast-vs-observed sounding verification loop. |
| **CanSIPS seasonal** | `https://dd.weather.gc.ca/today/model_cansips/100km/forecast/{YYYY}/{MM}/` | Canadian seasonal-to-interannual, 40 members (20 GEM-NEMO + 20 CanESM5), 1°, monthly out to 12 months. Hindcasts and verification products also published | Open; OGL-Canada | Directory `model_cansips` confirmed present in datamart listing; path pattern from MSC docs, *unverified at file level* | Only relevant if the project wants seasonal context. Not a forecast-map input. |
| **`model_gdps-geml`** | `https://dd.weather.gc.ca/today/model_gdps-geml/` | Directory exists in the datamart listing but was **empty at the time I checked**. Name suggests a GDPS machine-learning / emulator product | Presumably OGL-Canada | Directory verified present, **contents empty** | Worth watching — an ECCC-native AI emulator would be directly on-theme. Do not build against it yet. |
| **`model_caps`** | `https://dd.weather.gc.ca/today/model_caps/` | Directory present, **empty at check time** | — | Verified present, empty | Watch. |
| **`bulletins/alphanumeric/`** | `https://dd.weather.gc.ca/today/bulletins/alphanumeric/` | Raw WMO bulletins — SYNOP, TEMP, aviation, marine, in original alphanumeric form | Open; OGL-Canada | Directory verified | Only worth it if you need something not exposed in a friendlier form. Mostly redundant with SWOB and the aviation sources already registered. |
| **`satellite/himawari/`** | `https://dd.weather.gc.ca/today/satellite/himawari/` | ECCC-republished Himawari | Open | Directory verified | **No value here** — Himawari sees the western Pacific, not Newfoundland. Listed only so nobody chases it. |

The datamart also has `climate/` (`ahccd`, `cangrd`, `cmip5`, `cmip6`, `dcs`, `indices`, `ltce`, `spei`) — that is the climate-archive lane and belongs to the sibling research document, but flagging that it is there, it is open, and the registry has nothing from it.

## 1.3 Raw-provider NWP endpoints (verified reachable)

For anything you would rather ingest natively than via Open-Meteo:

| Provider | Endpoint | Status | Licence |
|---|---|---|---|
| ECMWF Open Data (IFS + AIFS, real-time) | `https://data.ecmwf.int/forecasts/` → `/{YYYYMMDD}/{HH}z/{aifs-single\|aifs-ens\|ifs}/0p25/oper/` | **200 verified**; `.../20260829/00z/aifs-ens/` confirmed present in the listing. Note: the deep path I guessed for a *future-dated* run 404'd — build the path from the directory listing, don't assume | **CC-BY-4.0**, redistribution and commercial use permitted with attribution. ECMWF's *entire* real-time catalogue is now open (2025 change) |
| NOAA NOMADS | `https://nomads.ncep.noaa.gov/` | **200** | US public domain |
| NOAA GFS on S3 | `s3://noaa-gfs-bdp-pds` → `https://noaa-gfs-bdp-pds.s3.amazonaws.com/?list-type=2` | **200** | Public domain, NODD |
| NOAA GEFS on S3 | `https://noaa-gefs-pds.s3.amazonaws.com/?list-type=2` | **200** | Public domain |
| NOAA NAM on S3 | `https://noaa-nam-pds.s3.amazonaws.com/?list-type=2` | **200** | Public domain |
| DWD Open Data (ICON global) | `https://opendata.dwd.de/weather/nwp/` | **200** | DWD open data, attribution |
| MET Norway THREDDS | `https://thredds.met.no/thredds/catalog.html` | **200** | CC-BY-4.0 (Nordic domains only — no NL) |
| MSC GeoMet OGC API | `https://api.weather.gc.ca/collections?f=json` | **200** | OGL-Canada |
| MSC GeoMet WMS | `https://geo.weather.gc.ca/geomet?service=WMS&version=1.3.0&request=GetCapabilities` | **200** | OGL-Canada |
| Open-Meteo raw Zarr-ish archive on S3 | `https://openmeteo.s3.amazonaws.com/data/{domain}/` | **200**, 100+ domains enumerated | AWS Open Data; Open-Meteo licence (CC-BY-4.0 for the data layer, non-commercial for the API) |
| Météo-France API portal | `https://portail-api.meteofrance.fr/` | Free registration + API key. The bare `public-api.meteofrance.fr/public/arpege/1.0/` path I tried returned 404 — use the portal-documented paths | Licence Ouverte / Etalab |

---

# 2. AI / ML weather models

The honest summary: **almost none of the headline AI models publish an open, operational, real-time forecast feed you can just GET.** Most publish weights and expect you to run inference. Two exceptions matter and both are already reachable.

| Model | Producer | Real-time open forecasts? | Endpoint | Access | Licence | Verified? | Assessment for this project |
|---|---|---|---|---|---|---|---|
| **ECMWF AIFS Single + AIFS ENS** | ECMWF | **Yes** — operational since 1 Jul 2025 for ENS. 0.25°, 6-hourly steps to 15 d, 4 runs/day, 51 members for ENS | `https://data.ecmwf.int/forecasts/{YYYYMMDD}/{HH}z/aifs-single/0p25/oper/` and `.../aifs-ens/`; also `models=ecmwf_aifs025_single` on Open-Meteo | **Open**, no key | **CC-BY-4.0** + ECMWF Terms of Use. Redistribution and commercial use allowed with attribution | **Yes — `ecmwf_aifs025_single` returned 18.3 °C at the point; `aifs-ens` directory confirmed on data.ecmwf.int** | **Already in the registry** (`ecmwf-aifs-single`, `ecmwf-aifs-ens`). Correctly prioritised. Note `models=ecmwf_aifs025` (no `_single`) returned all-nulls — the working id is `ecmwf_aifs025_single`. |
| **NOAA AI-GFS / AI-GEFS** (`ncep_aigfs025`, `ncep_aigefs025`) | NOAA/NCEP | **Yes** | `https://openmeteo.s3.amazonaws.com/data/ncep_aigfs025/`; `models=ncep_aigfs025` on Open-Meteo | Open | Public domain upstream | **Yes — `ncep_aigfs025` returned 48 non-null hourly values, first 18.5 °C** | **Not in the registry, and it should be.** NOAA now runs its own AI global model operationally and it is public-domain and free. This is the cheapest new AI model the project can add. Ranked #4 below. |
| **GraphCast (as run by NCEP)** (`ncep_gfs_graphcast025`) | DeepMind model, NCEP-run | Nominally yes | `https://openmeteo.s3.amazonaws.com/data/ncep_gfs_graphcast025/` | Open | Public domain | **Endpoint exists but returned zero non-null values at this point across a `past_days=2, forecast_days=3` window on 2026-08-30.** Either stalled or retired in favour of AI-GFS | Do not build against it without re-verifying. AI-GFS supersedes it in practice. |
| **Google WeatherNext 2 (GenCast lineage)** | Google DeepMind | Yes, but gated | Earth Engine asset `projects/gcp-public-data-weathernext/assets/weathernext_2_0_0`; BigQuery public dataset | **Application** — a "WeatherNext Data Request" form, reviewed weekly, 5–7 business days | **Split licence, and it splits on VALID TIME, not run age** (corrected 2026-09-02, definitions read): Historic Experimental Data is "any data that relates to a time that is more than 48 hours ago" and is CC-BY-4.0; Real-Time Experimental Data is "any data that relates to a time that is no more than 48 hours in the past" and falls under the "GDM Real-Time Weather Forecasting Experimental Data Terms of Use". A forecast for tomorrow relates to a time that is not in the past at all, so **every forward-looking value is in the restricted tier** and only the past is Creative Commons. Waiting does not buy you a permissively licensed forecast; it buys you history | **Band list verified 2026-09-02** from the Earth Engine catalogue (access to the data itself still requires approval) | Registry already has `google-weathernext-2` as `credential_required`, which is the correct classification. **The 64-member ensemble is genuinely excellent and publishes no cloud variable of any kind** — surface and single-level bands are 2 m temperature, 10 m and 100 m winds, MSLP, SST and 6-hourly total precipitation; pressure levels 50–1000 hPa carry geopotential, specific humidity, temperature, u, v and vertical velocity. For a map whose subject is cloud that is decisive, and it means any "cloud cover" an aggregator advertises for WeatherNext is that aggregator's own humidity closure, not model output. See `ensembles-and-source-plurality.md` §7. |
| **Microsoft Aurora 1.5** | Microsoft Research | **No public real-time feed.** Open weights only | GitHub + Hugging Face checkpoints; inference endpoints via Microsoft Foundry on your own compute | Weights: open. Running it: **paid** (your own GPU or Azure) | Model licence on the repo; check before any redistribution of outputs | Not verified — no anonymous forecast endpoint exists to verify | You would have to run inference yourself, on GPU, with your own initial conditions. Out of scope for this project unless it grows a GPU budget. **However, see AIWP below — NOAA archives Aurora runs.** |
| **NOAA AIWP reforecast archive** (GraphCast, Pangu, FourCastNet v1/v2, Aurora) | NOAA OAR | Twice-daily (00Z/12Z), from GFS *and* IFS initial conditions | `s3://noaa-oar-mlwp-data` → `https://noaa-oar-mlwp-data.s3.amazonaws.com/`. Prefixes verified: `AURO_v100_GFS/`, `AURO_v100_IFS/`, `FOUR_v100_GFS/`, `FOUR_v200_GFS/`, `FOUR_v200_IFS/`, `GRAP_v100_GFS/`, `GRAP_v100_IFS/`, `PANG_v100_GFS/`, `PANG_v100_IFS/`, plus `Derived/` and `parquet/` | **Open**, anonymous S3 | AWS Open Data / NOAA public domain | **Yes — bucket listed 200, all model prefixes enumerated, years 2021–2026 present under `GRAP_v100_GFS/`** | **This is the way to get Aurora, Pangu, FourCastNet and GraphCast without running a single GPU.** Four AI models, two initialisations each, archived back to 2021, free, no key. Latency is not nowcast-grade, but for *model comparison and skill assessment over the Avalon* it is exactly right. Ranked #3 below. |
| **ECMWF AIFS-ENS as Zarr** | dynamical.org | Icechunk/Zarr repackaging of AIFS ENS | AWS Open Data registry entry `dynamical-ecmwf-aifs-ens` | Open | CC-BY-4.0 (inherits ECMWF) | Registry page found via search; `dynamical.org/catalog/` returned 200 but I could not enumerate the catalogue (JS-rendered) — **treat the exact Zarr path as unverified** | Nice-to-have. Zarr is far more pleasant than GRIB. Verify the store path before committing. |
| **FuXi, FengWu, ArchesWeather, WeatherMesh** | Fudan/Shanghai AI Lab / academic / WindBorne | **No open real-time feed found.** Weights and papers only | — | Research-only | Varies | Not verified — nothing to verify | Reject. Weights-only, no operational path. |
| **Silurian "Earth API" (GFT)** | Silurian AI | Commercial API | `https://silurian.ai/` | **Paid** (no public free tier found) | Commercial | Not verified | Reject for this project — contract required. |
| **Jua EPT-2e** | Jua.ai | Commercial API, `pip install jua` | `https://jua.ai/` | **Paid** | Commercial | Not verified | Reject — contract required. |
| **Brightband, Excarta** | startups | No open feed found | — | Paid / not yet public | — | Not verified | Reject. |
| **WindBorne Atlas / WeatherMesh** | WindBorne Systems | Balloon *observations* API + WeatherMesh forecasts | `https://api.windbornesystems.com/` (**returned 200**), observations at `https://api.windbornesystems.com/data/version_1/observations/observations/` | Free tier existence is **unclear** — the company supplied free data to NOAA in 2025 as a gap-fill, but I could not confirm an open public tier for 2026. **Assume a key is required until you check.** | Commercial terms | Root endpoint verified 200; **access terms unverified** | Interesting as a *sounding* source over the North Atlantic where radiosondes are sparse. Worth an email. Do not assume it is open. |

---

# 3. Reanalysis and archives

**The registry has none of these. This is the biggest gap in the project.**

| Product | Producer | What it gives | Endpoint | Access | Licence | NL coverage | Verified? | Value |
|---|---|---|---|---|---|---|---|---|
| **ARCO-ERA5 on Google Cloud** | ECMWF data, Google-hosted | Full ERA5, 0.25°, hourly, 1940–present (ERA5T to ~6 days ago), as **analysis-ready cloud-optimised Zarr**. All 37 pressure levels | `https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/` | **Open — no account, no key, anonymous HTTPS** | CC-BY-4.0 (Copernicus), attribution to ECMWF/C3S required | Global, full coverage at 47 °N | **YES — fetched `.zmetadata`, which reports `valid_time_start: 1940-01-01`, `valid_time_stop_era5t: 2026-08-24`, `last_updated: 2026-08-30 02:56 UTC`** | **This is the single best reanalysis route for this project and it requires no registration at all.** 86 years of hourly atmosphere at the Avalon, in Zarr, laggy by ~6 days. Fog climatology, ML training targets, forecast verification baselines — all unlocked by one URL. Ranked #2 below. |
| **ERA5 via Copernicus CDS** | ECMWF / C3S | Same data, plus ERA5-Land (9 km) and the new **point time-series** collections | Catalogue API verified: `https://cds.climate.copernicus.eu/api/catalogue/v1/collections/reanalysis-era5-single-levels`. Python client `cdsapi` | **Free registration** + per-dataset licence acceptance + a personal access token in `~/.cdsapirc` | CC-BY-4.0 | Global | **YES — collection endpoint 200; 142 collections enumerated from the catalogue API** | Use CDS when you need ERA5-Land's 9 km land surface, or the timeseries collections. Use ARCO for bulk. The registration is genuinely free but it *is* a credential, so classify it `credential_required`. |
| **`reanalysis-era5-single-levels-timeseries`** and `-pressure-levels-timeseries`, `-land-timeseries` | C3S | **Point time-series extraction** rather than gridded downloads — you ask for a lat/lon and get the whole hourly history back | CDS, collection ids above | Free registration | **CC-BY-4.0** (confirmed from the collection metadata) | bbox `[-180, -89, 180, 89]` — **verified global, includes 47.56 N** | **YES — collection metadata fetched, licence and bbox confirmed** | For a *point-based* project this is enormously more efficient than pulling grids. Strongly recommended alongside ARCO. |
| **ECCC RDRS v2.1 / CaSR (Canadian Surface Reanalysis) v3.x** | ECCC / CCMEP | **10 km, hourly, North America.** RDRS v2.1 covers 1980–2018; CaSR v3.2 extends a 45-year precipitation analysis to 1980–2024. Variables include precipitation, T, RH, wind, radiation, pressure | Overview page **verified 200**: `https://hpfx.collab.science.gc.ca/~scar700/rcas-casr/overview.html` . Bulk data is distributed via the **CaSPAr** portal (`caspar-data.ca`) — **my curl to `https://caspar-data.ca/` returned connection failure (000)**; the host may block non-browser agents or the URL may have moved | CaSPAr requires a **free account** for order-based download. Some CaSR files are also published under the hpfx path above | Expected OGL-Canada; **licence text unverified — confirm before redistributing** | **North American domain at 10 km — covers Newfoundland properly, unlike every European regional reanalysis** | Overview page verified; **download endpoint NOT verified** | This is the Canadian answer to ERA5 at 2.5× the resolution over exactly this region. It is the reanalysis a Newfoundland project *should* have. The caveat is real though: I could not get the CaSPAr host to respond, and the record ends in 2018 (v2.1) / 2024 (v3.2), so it is an archive, not a live feed. Ranked #5 below, discounted for access friction. |
| **CERRA / CERRA-Land** | C3S | 5.5 km European regional reanalysis | `cds.climate.copernicus.eu` collections `reanalysis-cerra-*` | Free registration | CC-BY-4.0 | **European domain — does not reach Newfoundland** | Collection ids confirmed present in the CDS catalogue; domain from documentation | **Reject.** See "Not worth it". |
| **CARRA / pan-CARRA** | C3S | Arctic regional reanalysis, 2.5 km | `reanalysis-pan-carra`, `reanalysis-carra-*` on CDS | Free registration | CC-BY-4.0 | **bbox `[15.0, 60.0, 65.0, 72.0]` — 15–65 °E, 60–72 °N. Newfoundland (52.7 °W, 47.6 °N) is nowhere near it** | **YES — I fetched the collection metadata and read the bbox** | **Reject, definitively.** Worth recording because "Arctic reanalysis" sounds plausible for Newfoundland and is not. |
| **MERRA-2** | NASA GMAO | 0.5° × 0.625°, hourly, 1980–present, ~100 collections incl. aerosol | GES DISC. **The legacy OPeNDAP host `goldsmr4.gesdisc.eosdis.nasa.gov` returned HTTP 410 Gone** — GES DISC content is migrating into Earthdata during 2026 | **Free registration** (NASA Earthdata Login) | NASA open data, no restriction | Global | **Endpoint I tried is dead (410).** Find the current Earthdata path before use | Lower priority than ERA5 — coarser, and ERA5 is better over the North Atlantic. The one thing MERRA-2 has that ERA5 does not is its assimilated aerosol, which is irrelevant to fog here. |
| **JRA-3Q** | JMA | Global reanalysis, ~40 km (0.375°), 1947–present | NCAR **GDEX** `https://gdex.ucar.edu/datasets/d640000/` (**verified 200**) and the older `https://rda.ucar.edu/datasets/d640000/` (**also 200**) | **Free registration** with NCAR GDEX/RDA | **CC-BY-NC-SA-4.0 — non-commercial, share-alike.** This is the most restrictive licence in this document; it would contaminate any redistributable derived product | Global | Landing pages verified 200; data files not verified | Third-opinion reanalysis. The NC-SA licence makes it a poor fit for anything the project publishes. Low priority. |
| **NCEP/NCAR R1, NCEP/DOE R2, 20CR** | NOAA/NCAR | Coarse (2.5°), long records | NCAR RDA / NOAA PSL | Free registration (RDA) | Mostly public domain | Global but 2.5° is ~200 km — the Avalon is under two grid cells | Not individually verified | **Reject for forecasting.** 2.5° cannot resolve a peninsula 100 km across. Only useful for century-scale circulation context, which this project does not need. |
| **NCEI Integrated Surface Database (ISD) hourly** | NOAA NCEI | Global hourly surface obs archive; **St. John's is station `71801099999`** | `https://www.ncei.noaa.gov/access/services/data/v1?dataset=global-hourly&stations=71801099999&startDate=2025-07-01&endDate=2025-07-02&format=json` | **Open**, no key | US public domain | Yes | **YES — 200 with data.** (The bulk path `.../data/global-hourly/access/2026/71801099999.csv` returned 404; use the *services* API form) | Strictly this is the sibling document's climate lane, but noting it: it gives a decades-long hourly visibility/ceiling record at St. John's, which is the raw material for a fog climatology. Cheap. |

---

# 4. Satellite

## 4.1 The GOES-East caveat, stated plainly

St. John's is at ~47.6 °N, 52.7 °W. GOES-East sits at 75.2 °W on the equator. The satellite zenith angle at the Avalon is roughly **60–63°**. Consequences the project should encode explicitly:

- Effective ABI pixel footprint is stretched by ~1/cos(θ) ≈ **2×** in the along-scan direction. A nominal 2 km channel is ~4 km effective.
- **Parallax displaces cloud features tens of kilometres** — a 1 km-top fog bank appears displaced ~2 km, a 6 km cumulonimbus ~12 km, both away from the sub-satellite point. On a map at Avalon scale this is visible error.
- Low-cloud and fog detection at high zenith angle is the *worst* case for the 3.9–10.4 µm brightness-temperature-difference technique, because the slant path through the fog layer changes emissivity.

**Therefore: polar orbiters are not a nice-to-have at this latitude, they are the primary satellite source.** At 47.6 °N, VIIRS swaths from Suomi-NPP, NOAA-20 and NOAA-21 overlap enough to give several 750 m looks per day, viewed near-nadir.

## 4.2 GOES-19 L2 products the registry is probably not using

The registry has one entry, `noaa-goes-east`. The bucket carries **77 distinct L2 product prefixes** (I enumerated them all). The fog-relevant subset, all open and free on anonymous S3:

| Prefix | Product | Why it matters for fog |
|---|---|---|
| `ABI-L2-ACHAF` / `ACHAC` / `ACHAM` | Cloud Top Height | Fog is a cloud with a top below ~400 m. Height thresholds separate fog from stratus. |
| `ABI-L2-ACHTF` | Cloud Top Temperature | Combined with a surface/SST field, gives you fog-vs-low-stratus discrimination. |
| `ABI-L2-ACMF` | Clear Sky Mask | Baseline. |
| `ABI-L2-ACTPF` | Cloud Top Phase | Liquid at low levels = fog candidate. |
| `ABI-L2-CODF` / `COD2KMF` | Cloud Optical Depth | Optical depth maps to visibility. |
| `ABI-L2-CPSF` | Cloud Particle Size | Marine fog has a distinctive droplet-size signature; this is one of the better remote fog discriminants. |
| `ABI-L2-TPWF` / `TPWC` | Total Precipitable Water | Direct moisture-loading field. |
| `ABI-L2-LVMPF` / `LVTPF` | Legacy Vertical Moisture / Temperature Profiles | Coarse satellite soundings — the low-level inversion, from space. |
| `ABI-L2-DSIF` | Derived Stability Indices | Lifted index, CAPE, K-index. |
| `ABI-L2-SSTF` | Sea Surface Temperature | **Advection fog over the Grand Banks is an air-sea temperature-difference phenomenon.** SST is half the equation. |
| `ABI-L2-DMWF` / `DMWVF` | Derived Motion Winds | Satellite-tracked winds, incl. water-vapour winds. |
| `ABI-L2-CCLF` | Cloud Cover Layers | Multi-layer cloud. |
| `ABI-L2-RRQPEF` | Rainfall Rate QPE | Satellite precip where radar is blocked. |

Endpoint: `https://noaa-goes19.s3.amazonaws.com/{PREFIX}/{YYYY}/{DDD}/{HH}/` — **verified 200 with `ABI-L2-ACHAF/` present**. Access: **open**, no key. Licence: US public domain (NODD). All of these are subject to the zenith-angle caveat above.

## 4.3 Polar orbiter products — the real recommendation

These are free, keyless, anonymous-S3, and updated in near-real-time. I verified the bucket structure and pulled actual filenames dated **today, 2026-08-30**.

| Product family | Satellites | Endpoint | Verified? | Fog relevance |
|---|---|---|---|---|
| **VIIRS JRR Cloud suite**: `VIIRS-JRR-CloudBase`, `-CloudHeight`, `-CloudMask`, `-CloudPhase`, `-CloudCoverLayers`, `-CloudDCOMP`, `-CloudNCOMP` | NOAA-20 (`j01`), NOAA-21, S-NPP | `https://noaa-nesdis-n20-pds.s3.amazonaws.com/VIIRS-JRR-CloudBase/{YYYY}/{MM}/{DD}/` (also `-n21-pds`, `-snpp-pds`) | **YES — pulled `JRR-CloudBase_v3r2_j01_s202608300000065_e202608300001310_c202608300059477.nc` dated today** | **`CloudBase` is the single most fog-diagnostic satellite product that exists.** Cloud base at or near the surface *is* fog. At 750 m, near-nadir, several times daily over the Avalon. The project has nothing like this. Ranked #6 below. |
| **NUCAPS EDR** (CrIS + ATMS retrievals) | NOAA-20, NOAA-21, S-NPP | `https://noaa-nesdis-n20-pds.s3.amazonaws.com/NUCAPS-EDR/{YYYY}/{MM}/{DD}/` | **YES — pulled `NUCAPS-EDR_v3r2_j01_s202608300000189_e202608300000487_c202608300048050.nc` dated today** | Full temperature and water-vapour **profiles** from hyperspectral IR + microwave, globally, day and night. This is a satellite radiosonde. Over the Grand Banks where there are no balloons, it is the only vertical structure you can get. Also available as BUFR (`NUCAPS_C0431_BUFR/`, `NUCAPS_C2211_BUFR/`). |
| **ATMS SDR / TDR / BUFR** | NOAA-20/21, S-NPP | `.../ATMS-SDR/`, `ATMS_BUFR/` | Prefixes verified | Microwave sounding — sees through cloud. Raw radiances; you would need RTTOV-class tooling. High effort. |
| **CrIS FS SDR** | NOAA-20/21 | `.../CrIS-FS-SDR/` | Prefixes verified | Hyperspectral IR radiances. Same high-effort caveat; **use NUCAPS instead** unless you are doing your own retrieval. |
| **VIIRS-JRR-AOD**, `-ADP` | NOAA-20/21 | `.../VIIRS-JRR-AOD/` | Prefixes verified | Aerosol optical depth / dust-smoke-ash. Relevant to visibility that is *not* fog, and to CCN loading. |
| **VIIRS M-band and I-band SDRs, DNB** | NOAA-20/21, S-NPP | `.../VIIRS-M15-SDR/`, `VIIRS-I5-SDR/`, `VIIRS-DNB-SDR/` | Prefixes verified | Raw radiances. **DNB (Day-Night Band) is a genuinely underrated fog tool** — under moonlight, fog is visible at night at 750 m. |
| **JPSS Blended TPW / Rain Rate / Percent-of-Normal TPW** | multi-sensor | `https://noaa-jpss.s3.amazonaws.com/BHP_TPW/`, `BHP_RR/`, `BHP_PCT/`, `JPSS_Blended_Products/` | **YES — bucket 200, prefixes enumerated** | Blended microwave TPW is a strong moisture-advection indicator over ocean, and it is the ocean side of the fog problem. |
| **Sentinel-5P TROPOMI** | ESA/Copernicus | `https://meeo-s5p.s3.amazonaws.com/` with `NRTI/`, `OFFL/`, `RPRO/`, `COGT/` prefixes | **YES — 200, prefixes enumerated** | Trace gases and aerosol. Little direct fog value. Air-quality relevance only, and the registry already has CAMS. Low priority. |
| **Copernicus Data Space (Sentinel-3 SLSTR/OLCI, S-5P, S-1, S-2)** | ESA | OData API `https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$top=1` | **YES — 200** | SLSTR gives 1 km SST and a dual-view cloud product; OLCI gives 300 m visible. SST is directly on the fog critical path. **Free registration** for download (the catalogue query itself is open). |
| **NASA LAADS / MODIS (Aqua, Terra)** | NASA | `https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/details/allData/5200` | **YES — 200** | MODIS is aging (Terra/Aqua are well past design life) and VIIRS supersedes it. **Low priority — prefer VIIRS.** |
| **GPM IMERG** | NASA/JAXA | GES DISC OPeNDAP `https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/GPM_3IMERGHH.07/contents.html` — **verified 200**. NRT via `jsimpsonhttps.pps.eosdis.nasa.gov` — **returned 401, requires credentials** | **Free registration** (Earthdata Login for GES DISC; separate PPS registration for NRT) | 0.1°, half-hourly. Early run 4 h latency, Late ~14 h, Final ~3.5 months | **Half-verified: the archive OPeNDAP responds; the NRT host requires auth** | 0.1° ≈ 11 km. Over Newfoundland this is *worse* than the ECCC radar composite and HRDPA that the registry already has. **Value is over the open ocean upstream of the Avalon**, where there is no radar. Moderate. |
| **NASA CMR (search across all NASA EO)** | NASA | `https://cmr.earthdata.nasa.gov/search/collections.json?keyword=SMAP&page_size=1` | **YES — 200, no auth for search** | Discovery layer. Search is open; *downloads* generally need Earthdata Login. Useful for finding SMAP/SMOS soil moisture, ASCAT via PO.DAAC, etc. |
| **SMAP / SMOS soil moisture** | NASA / ESA | NSIDC `https://nsidc.org/data/spl3smp_e` — **200** | Free registration (Earthdata) | 9–36 km soil moisture | Landing page verified | **Low value here.** The Avalon is a small, largely bog-and-rock peninsula surrounded by ocean; a 36 km soil-moisture pixel is mostly water. Skip. |
| **ASCAT scatterometer winds** | EUMETSAT OSI SAF / KNMI, redistributed by NOAA and PO.DAAC | KNMI Data Platform `https://dataplatform.knmi.nl/dataset/osisaf-ascat-a-coa-nrt` — **403 to my agent**; NOAA OSPO `https://www.ospo.noaa.gov/products/atmosphere/ascat/`; KNMI scatterometer portal `https://scatterometer.knmi.nl/` — **200** | Free (KNMI states "granted to every interested user, free of charge"); **KNMI Data Platform needs a free API key** | 12.5 km coastal and 25 km global ocean vector winds, Metop-B/C | Portal verified; dataset endpoint 403'd for my agent | Ocean surface winds upstream of the Avalon. Genuinely useful for advection-fog trajectory reasoning — you want to know the wind that is carrying warm air across the Labrador Current. Moderate-to-good, but partly in the marine agent's lane. |
| **EUMETSAT Data Store** | EUMETSAT | `https://api.eumetsat.int/data/browse/collections` — **200**; `https://api.eumetsat.int/data/browse/1.0.0/collections` — **200** | **Free registration** (User Portal account + consumer key/secret) | Metop AVHRR/IASI/ASCAT, Sentinel-3, MSG. Data Tailor REST API for subsetting | Browse endpoints verified anonymously; downloads need credentials | **IASI on Metop is the best hyperspectral IR sounder flying**, and NUCAPS-equivalent retrievals exist. But NOAA's S3 route to NUCAPS is keyless and easier. Use EUMETSAT only if you need IASI or ASCAT natively. |
| **GNSS radio occultation (COSMIC-2, Spire, PlanetIQ, ROM SAF)** | UCAR CDAAC + partners | `https://gnss-ro-data.s3.amazonaws.com/` (**200**, prefixes `contributed/`, `dynamo/`); `https://data.cosmic.ucar.edu/gnss-ro/` (**200**) | **Open** | Refractivity, temperature, pressure, water-vapour profiles; ~6-week post-processing lag for COSMIC-2 | **YES — both endpoints 200** | Beautiful vertical humidity profiles over ocean, but **COSMIC-2's orbit is low-inclination and its density at 47 °N is much lower than in the tropics**, and the 6-week lag rules out operational use. Archive/verification value only. |
| **EarthCARE (cloud/aerosol profiling, CALIPSO/CloudSat successor)** | ESA/JAXA | Via ESA Copernicus/EO portals | Free registration, research-oriented | Cloud profiling radar + lidar | **Not verified** — I did not confirm an open endpoint | Narrow ground track, revisit measured in weeks at any one point. **For a single peninsula this is essentially never overhead.** Reject for operations; interesting for one-off case studies. |

## 4.4 What is NOT available

- `noaa-gpm-imerg-pds.s3.amazonaws.com` — **404. Does not exist.** IMERG on AWS is under different bucket names; do not assume this one.
- `sentinel5p.s3.amazonaws.com` — **404.** The working mirror is `meeo-s5p`.
- `noaa-nesdis-metop-pds` — **404.** There is no NOAA MetOp public S3 bucket; MetOp goes through EUMETSAT (registration) or NOAA CLASS.
- `noaa-nws-rtma-pds` — **404.** RTMA is CONUS-only anyway.
- `era5-pds.s3.amazonaws.com` — **403** to anonymous listing. Use ARCO-ERA5 on GCS instead, which *is* anonymous.
- `podaac-ops-cumulus-protected` — **403**, as the name says. Earthdata Login required.

---

# 5. Lightning

| Network | Operator | What it gives | Endpoint | Access | Licence | Verified? | Assessment |
|---|---|---|---|---|---|---|---|
| **ECCC CLDN lightning** | ECCC (Vaisala-operated) | CG + IC strokes over Canada | datamart `https://dd.weather.gc.ca/today/lightning/` | Open | OGL-Canada | Directory confirmed in datamart listing | **Already in the registry** (`eccc-lightning`). It is the right primary source — it is the Vaisala network, licensed for Canada, free. |
| **Blitzortung / LightningMaps** | volunteer VLF network, ~1800 stations | Real-time global strokes | `https://www.blitzortung.org/en/archive_data.php` (**200**), `https://map.blitzortung.org/` (**200**) | **Effectively closed for raw data.** Their stated terms: *"the use of raw lightning data is allowed only to the participants of the project or to those they explicitly have allowed it."* Maps on LightningMaps.org are CC-BY-SA-4.0 | Raw data: restricted. Map tiles: CC-BY-SA-4.0 | Pages verified 200; raw-data terms read from their own site | **Reject for raw ingest.** You would have to operate a station to become a participant. The CC-BY-SA map layer is usable but is a picture, not data, and SA is viral. |
| **WWLLN** | Univ. of Washington consortium | Global VLF stroke locations | `https://wwlln.net/` (**200**) | **Research-only, at "nominal cost"** — a per-institution data agreement | Restricted redistribution | Site verified 200; terms from documentation | Reject unless the project acquires an academic affiliation and is willing to sign. Adds little over CLDN inside Canada. |
| **Vaisala GLD360 / NLDN** | Vaisala | The commercial gold standard | `https://www.vaisala.com/en/lp/request-vaisala-lightning-data-research-use` | **Paid**, with a research-request path for unfunded students/faculty | Commercial | Not verified | **Reject.** Note that ECCC's CLDN *is* Vaisala hardware, so the marginal gain over the registry's existing `eccc-lightning` is near zero inside Canada. |
| **Earth Networks Total Lightning (now Xweather)** | Earth Networks / Xweather | Total lightning incl. in-cloud | `https://www.xweather.com/technology/xweather-lightning-network` | **Paid** | Commercial | Not verified | Reject. |
| **GOES-19 GLM** (Geostationary Lightning Mapper) | NOAA | Optical total lightning from geostationary orbit | `https://noaa-goes19.s3.amazonaws.com/GLM-L2-LCFA/` | **Open**, no key | US public domain | Bucket verified 200 (I enumerated ABI prefixes; GLM prefix path is documented, **not individually verified**) | **This is the one addition worth making.** Free, keyless, no contract, and it is *total* lightning (IC + CG) rather than CG-only. The high-zenith-angle caveat applies — GLM detection efficiency drops toward the limb — but for a project that already pulls from this bucket, adding a prefix is nearly zero work. |

**Honest summary of the lightning lane: there is essentially nothing open beyond what the registry has, plus GLM.** Thunderstorms are also not St. John's headline problem. Do not over-invest here.

---

# 6. Upper air and profiling

This is the second-richest gap after reanalysis, and it is where the fog problem actually lives.

| Source | What it gives | Endpoint | Access | Licence | Verified? | Value |
|---|---|---|---|---|---|---|
| **ECCC ProgTephi — RDPS forecast sounding at CYYT** | 29 pressure levels of T, dew-point depression, wind, RH, geopotential height, ω. 0–48 h at 3 h steps, 00Z and 12Z. CSV | `https://dd.weather.gc.ca/today/vertical_profile/forecast/csv/ProgTephi_00_CYYT.csv` | **Open** | OGL-Canada | **YES — file fetched, header confirms `CYYT, lat=47.620, lon=-052.730, St-Johns`** | **Top recommendation.** See §1.2. |
| **ECCC ObsTephi — observed sounding at CYYT** | The actual ascent, all levels, CSV | `https://dd.weather.gc.ca/today/vertical_profile/observation/csv/ObsTephi_00_CYYT.csv` | **Open** | OGL-Canada | **YES — `CYYT` present in directory listing** | Ground truth for the above. |
| **University of Wyoming sounding archive** | Decoded soundings + derived indices (CAPE, LI, PW, lifted parcel) for **station 71802 = "MT PEARL, NF, CANADA"** — the St. John's-area radiosonde | `https://weather.uwyo.edu/wsgi/sounding?datetime=2026-08-28+12%3A00%3A00&id=71802&type=TEXT%3ALIST&src=UNKNOWN` | **Open**, no key. Be polite — this is a small university server | Academic courtesy use; no formal open licence. **Do not hammer it and do not redistribute in bulk** | **YES — returned "Observations for Station 71802 at 12 UTC 28 Aug 2026 / MT PEARL, NF, CANADA"**. Note: the old `/cgi-bin/sounding` path is now **404**; the working form action is `/wsgi/sounding`. Station **71801 returned "unable to retrieve"** — use 71802 | Comes with derived thermodynamic indices already computed, plus **precipitable water**, which ECCC's CSV does not give you directly. Also has a per-year inventory endpoint. Good for backfill and verification. |
| **IGRA v2 (Integrated Global Radiosonde Archive)** | Full quality-controlled global sounding archive, 1905–present, with derived-parameter and monthly files | `https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/` (**verified 200**); also on CDS as `insitu-observations-igra-baseline-network` | **Open** on NCEI (no key); free registration on CDS | NCEI: US public domain. CDS copy: licence listed as `other` — **check before redistributing** | **YES — NCEI directory 200; CDS collection metadata fetched, global bbox confirmed** | The long-record backbone for a St. John's sounding climatology. Pair with ISD hourly for a proper fog-vs-inversion study. |
| **CUON — Comprehensive Upper-Air Observation Network** | Merged, homogenised upper-air record, **1901–present** | CDS `insitu-comprehensive-upper-air-observation-network` | Free registration | **CC-BY-4.0** (confirmed from collection metadata) | **YES — metadata fetched, licence and global bbox confirmed** | Better-licensed and longer than the CDS IGRA copy. Prefer this if you go the CDS route. |
| **CDS ground-based GNSS ZTD / IWV network** | **Zenith total delay and integrated water vapour from the ground GNSS network, 1996–present**, global | CDS `insitu-observations-gnss` | Free registration | Licence listed as **`other`** — read it before use | **YES — collection endpoint 200, global bbox `[-180,-89,180,89]` confirmed** | **This is the PWV source, and the brief was right that it matters.** GNSS IWV is a continuous, all-weather, 5-minute-cadence moisture measurement — exactly the variable radiosondes give you only twice a day. Whether a *Newfoundland* station is in the network is the open question; the collection is global but station density in Atlantic Canada is unconfirmed. **Check the station list before committing.** Ranked #8 below with that caveat attached. |
| **NRCan CACS (Canadian Active Control System) GNSS** | NRCan's Geodetic Survey computes final ZTD over Canada from CACS; literature reports GPS-PW vs radiosonde correlation 0.97, SD 2.04 mm over Canada | No machine-readable open endpoint found | **Unverified.** Documentation-level only — I could not locate a public ZTD/PWV product endpoint | Presumed OGL-Canada | **Not verified** | If a public NRCan ZTD feed exists it would be the single best fog predictor available for this location. **Worth an email to NRCan Geodetic Survey.** Treat as a research lead, not a source. |
| **MADIS** (mesonet, ACARS/AMDAR aircraft, profilers) | Aircraft ascent/descent soundings near CYYT, plus mesonet and profiler data | `https://madis-data.ncep.noaa.gov/` (**200**), API docs at `/madis_api_doc.shtml`, application at `https://madis.ncep.noaa.gov/data_application.shtml` | **Free registration by application** — you fill in a form, they create an account and FTP access | **Aircraft data is proprietary to the airlines.** MADIS restriction tiers: government/research/education, sponsored, public-full, NOAA-only. Aircraft generally sits in the research tier | Portal verified 200; account not obtained | Registry already has `noaa-madis` marked `credential_required` — **correct**. Aircraft ascent/descent profiles at CYYT would be a superb complement to twice-daily radiosondes, but the redistribution restriction is real: **you likely cannot publish airline-derived observations on a public map.** Read the restrictions page before designing anything around it. |
| **Mode-S / ADS-B derived winds** | Winds and (lower-quality) temperature from ATC surveillance downlink; ~100× the report density of AMDAR | EMADDC (`https://emaddc.knmi.nl`) covers **Europe only**. No North American equivalent found | Not applicable to Newfoundland | — | **Not verified — and I found no Canadian/North Atlantic network** | **Reject for this location.** The technique is excellent but the receiver networks are European. You would have to build your own ADS-B receiver, which is a different project. |
| **WindBorne balloon observations** | Global sounding balloons, pole to pole, long-duration | `https://api.windbornesystems.com/data/version_1/observations/observations/` | **Terms unconfirmed** — see §2 | Commercial | Root endpoint 200; terms not verified | The North Atlantic is a radiosonde desert. If there is a free tier, this is valuable. Ask. |
| **Wind profilers** | — | No Canadian public profiler network at/near the Avalon found | — | — | **Not verified — I found none** | Nothing to recommend. |

---

# 7. Radar

| Source | What it gives | Endpoint | Access | Licence | Verified? | Value |
|---|---|---|---|---|---|---|
| **ECCC radar — Holyrood NL (`CASHR`)** | The single-site radar covering the Avalon. S-band, dual-pol, **17 elevation slices per 6-minute volume**. ECCC publishes DPQPE (dual-pol QPE) and imagery per site | Site-level products are reachable via **MSC GeoMet** (`https://api.weather.gc.ca/collections`, **200**; WMS GetCapabilities **200**) and via the datamart `radar/` tree. **Note: `https://dd.weather.gc.ca/{YYYYMMDD}/radar/` and `/today/radar/volume-scans/` both returned 404/empty to me** — the layout is not what the obvious guess suggests. Get the exact paths from `https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radarimage-datamart_en/` | Open | OGL-Canada | Station identity **verified** (`CASHR: Holyrood NL — S end of Conception Bay`); **the per-site volume-scan endpoint was NOT verified — my path guesses 404'd** | The registry has `eccc-radar` (composite). A **single-site** feed from CASHR, at native resolution and 6-minute cadence, is meaningfully better for a map of one peninsula than a national mosaic. **Worth doing, but budget time to find the right path** — I could not confirm it. |
| **Marble Mountain NL (`CASMM`)** | Second NL radar, ~40 km S of Deer Lake — western Newfoundland | as above | Open | OGL-Canada | Station id verified from ECCC docs | Irrelevant to the Avalon (600+ km away). Note only for completeness. |
| **Canadian Level-II-equivalent raw volume data** | — | — | — | — | **I found no evidence ECCC publishes raw volume scans in a NEXRAD-Level-II-like open form.** The published products are DPQPE and imagery | **Do not assume Level II exists for Canada.** This is a real difference from the US. |
| **NOAA MRMS** | 1 km, 2-minute multi-radar mosaic. **MRMS ingests Canadian radars** including CASHR | `https://noaa-mrms-pds.s3.amazonaws.com/` — **verified 200**. Sectors enumerated: `ALASKA/`, `ANC/`, `CARIB/`, `CONUS/`, `CONUS_5KM/`, `ConvectProb/`, `GUAM/`, `HAWAII/`, `ProbSevere/` | Open, no key | US public domain | **Bucket and sector list verified. There is NO Atlantic-Canada sector.** Canadian radars feed the CONUS product but Newfoundland is far outside the CONUS grid | **Reject.** MRMS ingests Canadian data but does not publish a product covering Newfoundland. This is a trap worth recording — the phrase "MRMS ingests Canadian radars" makes it sound usable here, and it is not. |
| **Research radar** | — | — | — | — | Not found | Memorial University has atmospheric research activity but I found no publicly served research radar over the Avalon. |

---

# 8. Fog-specific: Grand Banks / Avalon

St. John's is among the foggiest inhabited places on Earth. The mechanism is well-characterised: warm, moist air advected off the Gulf Stream over the cold Labrador Current produces **advection fog**, most frequently in spring and summer, with the highest frequency when winds come from over the warm water and **air temperature runs ~2 °C above SST**. Reported dense-fog frequency on the Grand Banks reaches **~50% of the time in spring and summer**.

**What this implies for source selection, concretely:** the controlling variables are (a) the **air–sea temperature difference**, (b) the **low-level dew-point depression and inversion structure**, and (c) the **wind trajectory over the SST gradient**. Every recommendation in this document is weighted by how directly it delivers one of those three.

| Resource | What it is | Endpoint | Access | Verified? | Value |
|---|---|---|---|---|---|
| **FATIMA Grand Banks 2022** (Fog and Turbulence Interactions in the Marine Atmosphere) | July 2022 field campaign in the Grand Banks. R/V *Atlantic Condor* + autonomous surface vehicles + an instrumented Sable Island site. Visibility, precip rate, T, RH-over-water, pressure, wind, turbulence, and **>550 hours of in-situ fog cloud-microphysics data described as unique** | NSF NCAR EOL field data archive: `https://data.eol.ucar.edu/project/FATIMA` (**200**), `https://data.eol.ucar.edu/master_lists/generated/fatima/` (**200**), project page `https://www.eol.ucar.edu/field_projects/fatima` (**200**) | EOL archives are generally **open with free registration**; per-dataset terms vary | **Pages verified 200 but they are JavaScript-rendered** — I could not enumerate the dataset list without a browser. **The dataset inventory is unverified** | **The single most relevant observational dataset in existence for this exact problem.** Not an operational feed — it is a one-month research archive — but it is the right validation and model-development substrate for anything fog-related the project builds. Ranked #9 below. |
| **Fatima-GB overview** | *Bulletin of the American Meteorological Society* 106(6), 2025, "Fatima-GB: Searching Clarity within Marine Fog" (BAMS-D-23-0050.1) | `https://journals.ametsoc.org/view/journals/bams/106/6/BAMS-D-23-0050.1.xml` | Open access status unconfirmed | Citation verified via search | Read this first — it is the campaign overview and will tell you what is in the EOL archive. |
| **Marine fog ML/nowcasting literature (Grand Banks specific)** | A coherent body of work exists specifically on this problem: "Machine learning analysis and nowcasting of marine fog visibility using FATIMA Grand Banks campaign measurements" (*Frontiers in Earth Science* 11:1321422, 2023); "Generative Nowcasting of Marine Fog Visibility in the Grand Banks area and Sable Island in Canada" (arXiv:2402.06800); "Open-Loop Generative AI Nowcasting of Dense Marine Fog Visibility from the FATIMA Grand-Banks Campaign" (*Atmosphere* 17(8):749, doi 10.3390/atmos17080749) | DOIs/arXiv above | Open access (Frontiers, MDPI, arXiv) | Citations verified via search | **Key finding to inherit rather than rediscover: probabilistic ML models outperformed fully deterministic systems; satellite-derived fog data provided real short-term skill; Bayesian neural networks were promising for both skill and predictability assessment.** If the project ever adds fog prediction, this is the prior art. |
| **"Characterizing and Predicting Marine Fog Offshore Newfoundland and Labrador"** and **"Predicting Marine Fog on the Grand Banks of Newfoundland & Labrador"** | Multi-year predictability assessment; source of the ~50% spring/summer dense-fog figure | ResearchGate / AGU abstracts | Varies | Citations verified | Climatological framing. |
| **"Spatial and temporal structure of the fog life cycle over Atlantic Canada and the Grand Banks"** | *QJRMS* 2025, doi 10.1002/qj.4953 | `https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4953` | Journal | Citation verified | Fog life-cycle structure — directly informs what temporal resolution a fog product needs. |
| **"Thermodynamic and microphysical properties of summertime marine fog observed from Sable Island"** | *QJRMS*, doi 10.1002/qj.70098 | `https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.70098` | Journal | Citation verified | Companion to FATIMA. |
| **"Climatological perspectives on fog from the Hibernia platform"** | Memorial University thesis using offshore platform observations | `https://memorial.scholaris.ca/items/8ac3045b-9b05-4222-90ad-cea4e6e580eb` | Open (institutional repository) | URL from search, **not fetched** | Local, offshore, long-record. Worth reading. |
| **EUMETSAT / NWC SAF fog & low-cloud products** | Night Microphysics RGB (10.4−3.9 µm and 12.4−10.4 µm differences), Cloud Type with a "low broken/low thick" class, and a Precipitable Water product | `https://user.eumetsat.int/catalogue/EO:EUM:DAT:MSG:FOG` (MSG, **wrong hemisphere**); NWC SAF software at `https://nwc-saf.eumetsat.int/` | NWC SAF software: **free registration, licence agreement**. You run it on your own satellite input | Not verified | **The MSG fog product does not see Newfoundland.** But the *NWC SAF algorithms* are portable and could be run on VIIRS or ABI input. That is a real software project, not a data ingest. Note the technique; the free VIIRS `JRR-CloudBase` product gets you most of the way for a fraction of the effort. |
| **GOES Night Microphysics RGB** | The standard operational fog/low-cloud discriminant | Derivable from `noaa-goes19` ABI channels 7 (3.9 µm), 13 (10.3 µm), 15 (12.3 µm); NOAA STAR serves rendered imagery at `https://www.star.nesdis.noaa.gov/goes/sector_band.php?sat=G16&sector=eus&band=NightMicrophysics` | Open | Imagery page found via search, not individually fetched | Cheap to compute from data the project already ingests. **But at 60°+ zenith angle over the Avalon the BTD technique degrades** — this is precisely the case where the polar-orbiter route wins. |

---

# Top 10 additions, ranked by value per unit of work

**1. ECCC `ProgTephi` + `ObsTephi` vertical profiles at CYYT — `https://dd.weather.gc.ca/today/vertical_profile/{forecast,observation}/csv/{Prog,Obs}Tephi_{00,12}_CYYT.csv`**
Open, OGL-Canada, **verified fetched**, CSV, no GRIB parsing, twice daily, and it is *literally the St. John's grid column* — the file header says so. It hands you the low-level inversion and dew-point-depression profile that governs advection fog, forecast and observed, side by side. There is nothing else in this document with this ratio of relevance to effort. Two HTTP GETs.

**2. ARCO-ERA5 on Google Cloud Storage — `https://storage.googleapis.com/gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3/`**
Anonymous, keyless, CC-BY-4.0, Zarr, **verified current to 2026-08-24**. The registry has *zero* reanalysis. This closes that gap with one URL and no registration. It is the substrate for a fog climatology, for forecast verification, and for any ML the project ever wants to do. The only cost is learning Zarr, which you want to learn anyway.

**3. NOAA AIWP archive — `s3://noaa-oar-mlwp-data`**
Four AI models (GraphCast, Pangu, FourCastNet, **Aurora**), two initialisations each (GFS and IFS), 2021–present, twice daily, **verified open S3 with all prefixes enumerated**. This is how you get Aurora and Pangu without a GPU, a contract, or an approval form. Compare it against the ECCC/ECMWF operational stack over the Avalon and you have a real AI-vs-physics evaluation for free.

**4. NOAA AI-GFS — `models=ncep_aigfs025`, raw at `https://openmeteo.s3.amazonaws.com/data/ncep_aigfs025/`**
**Verified returning 48 non-null hourly values at 47.56/−52.71.** NOAA's own operational AI global model, public domain, free, real-time. The registry has AIFS and (gated) WeatherNext; this is the third operational AI model and the least encumbered of the three.

**5. VIIRS `JRR-CloudBase` / `CloudHeight` / `CloudPhase` from NOAA-20, NOAA-21 and S-NPP**
`https://noaa-nesdis-n20-pds.s3.amazonaws.com/VIIRS-JRR-CloudBase/{YYYY}/{MM}/{DD}/` — **verified with a file dated today**. Open S3, no key, 750 m, near-nadir at 47 °N, several passes daily across three platforms. **Cloud base near the surface is the definition of fog.** This is the correct answer to the GOES zenith-angle problem, and the registry's single satellite entry does not cover it.

**6. UK Met Office Global 10 km — `models=ukmo_global_deterministic_10km`**
**Verified 19.6 °C at the point.** The finest-resolution free global model available here, from a centre with a strong North Atlantic record, and a genuinely independent forecast from everything in the registry. One API call. (Add JMA GSM and ARPEGE-world in the same motion — both verified, both trivial.)

**7. NUCAPS EDR soundings — `https://noaa-nesdis-n20-pds.s3.amazonaws.com/NUCAPS-EDR/{YYYY}/{MM}/{DD}/`**
**Verified with a file dated today.** Satellite temperature and water-vapour profiles, day and night, global, open, no key. Over the Grand Banks — where there are no radiosondes at all — this is the only vertical structure available. Ranked below CloudBase only because netCDF granule handling is more work than a cloud mask.

**8. CDS ground-based GNSS ZTD/IWV — collection `insitu-observations-gnss`**
**Collection endpoint verified 200, global bbox confirmed.** Continuous all-weather column water vapour at 5-minute cadence is exactly the variable that twice-daily soundings miss, and PWV is a well-established fog predictor. **Ranked 8th rather than higher purely because I could not confirm that a Newfoundland station is in the network** — check the station list first. Requires free CDS registration and the licence is listed as `other`, so read it.

**9. FATIMA Grand Banks 2022 archive — `https://data.eol.ucar.edu/project/FATIMA`**
Not an operational feed, and the dataset list is behind a JS-rendered page I could not enumerate. But it is a month of shipborne and Sable Island fog microphysics, turbulence and visibility from *this exact water*, and the accompanying ML nowcasting literature has already established what works (probabilistic beats deterministic; satellite fog data has real skill). If the project ever builds a fog product, starting anywhere else is wasted motion.

**10. GOES-19 L2 fog-relevant prefixes — `ACHAF`, `ACHTF`, `ACTPF`, `CPSF`, `CODF`, `TPWF`, `SSTF`, `LVMPF`, plus `GLM-L2-LCFA`**
The project already ingests from `noaa-goes19`. Adding prefixes to an existing ingest is close to zero marginal work, and `SSTF` in particular gives you the sea-surface side of the air–sea temperature difference that drives the whole fog mechanism. Discounted from a higher rank *only* by the 60°+ zenith-angle degradation, which is real and should be documented wherever these are surfaced.

**Runners-up, in order:** ECCC single-site CASHR radar (high value, but I could not verify the endpoint path); University of Wyoming station 71802 soundings with derived indices (verified working, tiny, but be gentle with their server); IGRA/CUON long-record soundings; ASCAT ocean winds; Copernicus Data Space Sentinel-3 SLSTR SST; ECCC RDRS/CaSR.

---

# Not worth it, and why

**Domain misses — these simply do not cover Newfoundland. Verified by test or by published bbox.**

- **CERRA / CERRA-Land** (5.5 km) — European domain. Newfoundland is not in Europe. The name invites the mistake.
- **CARRA / pan-CARRA** — I fetched the bbox: `[15.0, 60.0, 65.0, 72.0]`, i.e. 15–65 °**E**. Not remotely close. "Arctic reanalysis" sounds applicable to Newfoundland; it is not.
- **MEPS / `metno_nordic_pp`, HARMONIE-AROME (KNMI, DMI), ICON-EU, ICON-D2, ICON-CH1/CH2, AROME-France, ALADIN-CZ, ICON-2I, AROME-Austria, UKMO UK 2 km** — every European convection-permitting model. All returned `"No data is available for this location"` or all-nulls. **There is no free 2.5 km alternative to ECCC HRDPS here. Stop looking for one.**
- **HRRR, NAM-CONUS-nest, NBM-CONUS, RTMA** — US CONUS domains stop well short of Newfoundland. Verified by API error.
- **NOAA MRMS** — bucket verified, sectors enumerated: CONUS, Alaska, Caribbean, Guam, Hawaii, Anchorage. **No Atlantic Canada sector.** MRMS *ingests* Canadian radars but publishes nothing covering Newfoundland. Specifically flagged because the ingest fact makes it sound usable.
- **ECCC `satellite/himawari/`** — western Pacific. Present in the datamart, useless here.
- **EUMETSAT MSG Fog RGB product** (`EO:EUM:DAT:MSG:FOG`) — Meteosat at 0°/9.5 °E. Does not see Newfoundland.

**Access-blocked — you cannot use these without a contract or an approval you do not have.**

- **Vaisala GLD360 / NLDN** — paid. And redundant: ECCC's CLDN, already in the registry, *is* the Vaisala network over Canada.
- **Earth Networks / Xweather Total Lightning** — paid.
- **Blitzortung raw data** — their own terms restrict raw data to project participants. You would have to run a VLF station. The CC-BY-SA map layer is an image, and SA is viral into your project.
- **WWLLN** — research agreement at nominal cost; per-institution. Adds little over CLDN inside Canadian coverage.
- **Silurian Earth API, Jua EPT-2e, Brightband, Excarta** — all commercial. No free tier found for any of them. Do not let the marketing copy suggest otherwise.
- **UK Met Office Data Hub direct** — paid. (Their global model reaches you *free* only via the Open-Meteo repackaging, whose non-commercial terms you must then respect.)
- **MADIS aircraft (ACARS/AMDAR)** — the account is free, but **the aircraft data is proprietary to the airlines** and the restriction tiers are explicit. You very likely cannot publish it on a public map. The registry's `credential_required` classification is right; the redistribution constraint is the bigger problem and deserves recording too.
- **NASA `podaac-ops-cumulus-protected`** — 403, as designed. Earthdata Login required for PO.DAAC downloads (CMR *search* is open).

**Weights-only, no operational path.**

- **FuXi, FengWu, ArchesWeather, WeatherMesh, Aurora-run-yourself** — published weights, no open real-time forecast feed. Running them means your own initial conditions and your own GPU. **Use the NOAA AIWP archive instead**, which serves the outputs of the ones that matter (Aurora, Pangu, GraphCast, FourCastNet) for free.

**Real but low value here — I considered these and reject them on merit, not access.**

- **SMAP / SMOS soil moisture** — 9–36 km pixels over a narrow rocky peninsula surrounded by ocean. Most of every pixel is water. The registration cost is not repaid.
- **MODIS (Terra/Aqua)** — superseded by VIIRS on every axis that matters here (resolution, radiometry, mission life). Prefer VIIRS.
- **Sentinel-5P TROPOMI** — trace gases and aerosol. Little fog relevance, and the registry already has CAMS for air quality.
- **EarthCARE / CloudSat-CALIPSO successors** — narrow nadir track, revisit at any single point measured in weeks. Over one peninsula it is effectively never overhead. Case-study interest only.
- **NCEP/NCAR R1, R2, 20CR** — 2.5° puts the entire Avalon inside a couple of grid cells. Cannot represent the problem.
- **JRA-3Q** — **CC-BY-NC-SA-4.0**. Non-commercial *and* share-alike. Using it would constrain the licence of anything derived. ERA5 is better over the North Atlantic and CC-BY-4.0. Not worth the contamination.
- **GNSS radio occultation (COSMIC-2)** — genuinely open and verified, but COSMIC-2's low-inclination orbit means sparse profiles at 47 °N, and the ~6-week post-processing lag rules out operational use. Archive value only.
- **Mode-S / ADS-B derived winds** — the technique is excellent and EMADDC proves it works, but the receiver networks are European. There is no North Atlantic equivalent to tap. Building one is a different project.
- **ECCC `bulletins/alphanumeric/`** — raw WMO bulletins, largely redundant with SWOB and the aviation sources already registered, and far more parsing work.
- **CanSIPS, SEAS5, ECMWF EC46** — all real, all free, all covering the point. Rejected only as *out of scope* for a nowcast/short-range map. Revisit if a seasonal panel is ever added.
- **`model_gdps-geml`, `model_caps`** — directories exist in the MSC datamart but were **empty when I checked**. Watch, do not build.

**Endpoints that do not exist. Recorded so nobody re-derives them.**

`noaa-gpm-imerg-pds.s3.amazonaws.com` (404) · `sentinel5p.s3.amazonaws.com` (404, use `meeo-s5p`) · `noaa-nesdis-metop-pds` (404, no such bucket — MetOp is EUMETSAT/CLASS) · `noaa-nws-rtma-pds` (404) · `era5-pds.s3.amazonaws.com` anonymous listing (403 — use ARCO on GCS) · `goldsmr4.gesdisc.eosdis.nasa.gov/opendap/MERRA2/` (**410 Gone** — GES DISC is migrating into Earthdata during 2026) · `weather.uwyo.edu/cgi-bin/sounding` (**404 — the path moved to `/wsgi/sounding`**) · `public-api.meteofrance.fr/public/arpege/1.0/` (404 — use the `portail-api.meteofrance.fr` documented paths) · `dd.weather.gc.ca/{YYYYMMDD}/radar/` and `/today/radar/volume-scans/` (404/empty — the real per-site radar layout must be read from the MSC docs).

---

# Explicit uncertainty register

Things I could **not** verify, stated so they are not mistaken for confirmed:

1. **CaSPAr portal (`caspar-data.ca`) did not respond to my client at all** (curl exit 000). RDRS/CaSR may be harder to obtain than the literature implies, or the host may block non-browser agents. The `hpfx.collab.science.gc.ca/~scar700/rcas-casr/overview.html` overview page *does* return 200.
2. **ECCC per-site radar (CASHR) endpoint path.** Station identity confirmed from ECCC documentation; the data path was not. My two obvious guesses 404'd.
3. **Whether a Newfoundland GNSS station exists in the CDS `insitu-observations-gnss` network.** The collection is global; station density in Atlantic Canada is unconfirmed. This materially affects recommendation #8.
4. **FATIMA dataset inventory.** The EOL archive pages are JavaScript-rendered; I confirmed they exist and return 200 but could not list what is in them.
5. **WindBorne access terms.** API root returns 200; whether there is a free tier in 2026 is unconfirmed.
6. **NRCan CACS public ZTD/PWV product.** Referenced in the literature as computed by NRCan Geodetic Survey; I found no public machine-readable endpoint. Research lead only.
7. **UKMO ensemble, KMA GDPS, BOM ACCESS, GraphCast-at-NCEP, SEAS5, AI-GEFS-mean** all returned all-null series at this point on 2026-08-30. That could be run-timing rather than absence of coverage — **re-test before either adopting or rejecting them.**
8. **GOES-19 `GLM-L2-LCFA` prefix** — the bucket is verified and the prefix is documented, but I enumerated ABI prefixes specifically and did not individually confirm the GLM one.
9. **Licence text for RDRS/CaSR** and for the CDS collections listed as `other` (`insitu-observations-gnss`, the CDS IGRA copy, `satellite-cloud-properties`, `satellite-humidity-profiles`). Read them before redistributing anything derived.
10. **ECCC's own ensembles have left the open HTTP feed** (added 2026-09-02).
    `https://dd.weather.gc.ca/today/model_geps/` and `model_reps` both 404, as
    do `ensemble/geps` and `ensemble/reps` on `dd.weather.gc.ca` and on the
    `hpfx.collab.science.gc.ca` mirror; the `ensemble/` tree holds only
    `cansips/` and `doc/`, and neither directory appears in the `today/`
    listing where it would sort. **The registry declares the dead path**, and
    MSC's own product readme still documents it. They survive through GeoMet:
    REPS publishes 1239 individual member coverages as `REPS.MEM.<VAR>.<NN>`
    for members 01-21 in both WMS and WCS, while GEPS publishes no members at
    all, only its own mean, spread, percentiles and threshold probabilities.
    The one open ECCC route not probed is MetPX Sarracenia over AMQP. Full
    detail in `ensembles-and-source-plurality.md` §2 and §3.

---

# Re-verification pass, 2026-09-02

Prompted by the owner asking what else could be pulled in for cloud, moisture,
humidity and wind. Every row below was re-probed from this machine on
2026-09-02. **Three of this document's ECCC recommendations had died in three
days**, which is the reason the pass happened at all and the reason anything
ECCC here should be re-probed before it is built against.

## R1. What died

| What | Was | Now |
|---|---|---|
| ECCC CYYT forecast sounding, ranked **#1** in `04-gap-analysis.md` | the whole vertical-profile answer, plain CSV | `https://dd.weather.gc.ca/today/vertical_profile/` returns 200 and contains **only `doc/`**. Every path under `forecast/` and `observation/` is 404, on `dd.weather.gc.ca` and on the `hpfx.collab.science.gc.ca` mirror |
| GEPS and REPS raw GRIB2 | `today/model_geps/`, `today/ensemble/geps/` | 404 everywhere; see uncertainty-register entry 10 |

The pattern is the same in both cases: the directory still exists, the
documentation folder inside it still exists, and the data is gone. That is not
how a transient outage usually looks, and MSC's own readmes still document the
dead paths. **Do not trust an ECCC Datamart path in this document without
re-probing it.** Everything that vanished has a GeoMet equivalent, which is
the strong hint about where ECCC has moved.

## R2. GeoMet is the largest untapped source, and the stack already talks to it

The project proxies 17 GeoMet WMS layers. GeoMet's WCS advertises **6123
coverages**, of which **377 are HRDPS at 2.5 km**. A WCS coverage is a gridded
field that can be subset and decoded, not a picture and not the single-pixel
`GetFeatureInfo` answer of hard-won fact 1. **VERIFIED** by reading both
capabilities documents.

What HRDPS carries there that the stack does not ingest today:

| Layer family | What it gives | Why it matters here |
|---|---|---|
| `HRDPS.CONTINENTAL_{TT,TD,HR,HU,ES,WSPD,WD,UU,M3}_{40m,80m,120m}` | temperature, dew point, relative and specific humidity, dew-point depression, wind speed, direction and components at 40, 80 and 120 m | **A boundary-layer stack sampled three times inside the first 120 m.** This is the fog layer itself. The stack currently jumps from 2 m to 1015 hPa |
| `HRDPS.CONTINENTAL.PRES_HR.<L>` | relative humidity on **28 pressure levels**, 50 to 1015 hPa | the Datamart GRIB ingest carries 9 levels, 1015 to 850 |
| `HRDPS.CONTINENTAL.PRES_{HU,QQ,WP,ES,UU,WD,WSPD,TT,GZ}` | specific humidity, mixing ratio, vertical motion, dew-point depression, wind, temperature, height on the same levels | the residual timing options already want omega and RH; this is a second route to both |
| `HRDPS.CONTINENTAL_HPBL` | boundary layer height | separates fog from lifted stratus directly |
| `HRDPS.CONTINENTAL_SKINT` | skin temperature | **half of the air-sea temperature difference that drives Grand Banks advection fog**; the other half is SST, already available from GOES `ABI-L2-SSTF` |
| `HRDPS.CONTINENTAL_ICEC` | ice cover | the registry has no ice at all (structural gap 4) |
| `HRDPS-WEonG_2.5km_SkyState` | ECCC's own sky-state diagnostic | sits beside the fog visibility layers already proxied |

`HRDPS.CONTINENTAL_NT` is the total cloud already ingested from GRIB, so the
two routes can be cross-checked against each other.

**GAP:** no coverage was actually fetched. The cost of a WCS subset per layer
per lead over the Avalon is unmeasured, and `geomet-wms-access` already
budgets upstream calls per request and per process. Measure before committing.

## R3. Satellite, re-verified and still the right answer at this latitude

Section 4.1's zenith-angle argument stands and is the reason this matters:
polar orbiters look near-nadir at 47.6 N while GOES-East looks through roughly
twice the air.

| Product | Route | Probed 2026-09-02 |
|---|---|---|
| VIIRS `JRR-CloudBase` | `https://noaa-nesdis-n20-pds.s3.amazonaws.com/VIIRS-JRR-CloudBase/2026/09/02/` | **live**, granules timestamped today |
| NUCAPS-EDR soundings | `https://noaa-nesdis-n20-pds.s3.amazonaws.com/NUCAPS-EDR/2026/09/02/` | **live**, granule timestamped today |
| GOES-19 `ABI-L2-ACHAF`, `-TPWF`, `-DMWF`, `-CODF`, `-ACMF` | `https://noaa-goes19.s3.amazonaws.com/<PREFIX>/2026/245/` | **all five populated today** |

Cloud top height, total precipitable water, derived motion winds, cloud
optical depth and the clear-sky mask cover cloud, moisture and wind between
them, all keyless and public domain. NUCAPS is the only vertical structure
available over the Grand Banks now that the ECCC sounding has gone.

## R4. Two more, both live

- **ARCO-ERA5** on Google Cloud: `.zmetadata` fetched 2026-09-02, reporting
  1940-01-01 through 2026-08-26 with `last_updated` 2026-09-01. Anonymous
  Zarr, CC-BY-4.0, humidity and wind on 37 levels. Still the best reanalysis
  route and still requires no account. **VERIFIED.**
- **Mode-S winds aloft** via `https://api.adsb.lol/v2/point/47.56/-52.71/250`:
  11 aircraft over the Avalon at the moment of the probe, **9 reporting wind
  direction, speed and outside air temperature** between 22,900 and 37,000
  feet. With the nearest radiosonde 600 km away and the ECCC forecast sounding
  now gone, this is the only routinely available in-situ wind aloft over this
  point. ODbL, no key. **VERIFIED.**

## R5. The aggregator question, and what changed because of it

Section 1.1's foreign models - UKMO Global 10 km, JMA GSM, ARPEGE-world, CMA
GRAPES - are reachable only through Open-Meteo at this location. That route
does not hand back a published grid cell. Open-Meteo selects a cell by a
policy that defaults to finding nearby land at similar elevation rather than
the nearest cell, applies statistical downscaling against a 90 m elevation
model, and interpolates a model's native step up to hourly. **VERIFIED** from
its own documentation, 2026-09-02.

That collided with `point-evidence-sampling`'s requirement that a value is one
published cell, unmodified. The owner's decision on 2026-09-02 was to loosen
that rule rather than reject the sources: a value that an intermediary
reprocessed is still a value somebody retrieved, and the honest fix is to
declare what kind of source it came from rather than to pretend the
distinction does not exist. The normative text is in
`openspec/changes/ensemble-members-and-source-plurality/`. The short version:
a source declares whether it delivers published cells or reprocessed values;
a reprocessed value names both the originating producer and the intermediary,
and the reprocessing that was applied; and it is never the declared primary,
because a downscaled global has no business outranking a 2.5 km regional model
that publishes its own cells.

---

## Source count

**94 distinct products, feeds, archives and networks assessed** across the eight brief areas: 24 NWP (including 14 domain-miss rejections), 15 AI/ML, 13 reanalysis and archive, 22 satellite, 7 lightning, 12 upper-air and profiling, 5 radar, and 8 fog-specific datasets and literature items. **41 endpoints were verified with live HTTP requests** on 2026-08-30; the rest are documentation-only and marked as such throughout.
