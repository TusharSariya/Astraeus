# Open-Meteo marine, air-quality and radiation endpoints as reprocessed sources

**Non-normative research. Dated 2026-09-02.** Answers wayfinder ticket
[#28](https://github.com/TusharSariya/Astraeus/issues/28). Nothing here changes
registry state, and nothing here was published to the store. Terms follow
`CONTEXT.md`; evidence classes are its five.

Everything marked *verified live* was fetched anonymously on 2026-09-02 between
about 09:00Z and 09:30Z from the machine running this work. Points probed:
**47.6 N 52.6 W** (off St. John's), **47.0 N 51.0 W** (Grand Banks), **49.5 N
56.5 W** (Notre Dame Bay), and the St. John's land point **47.5675 N 52.7072 W**.

## 0. What this ticket does not repeat

The six transformations Open-Meteo applies to every value, the run-time exposure
problem and the four client rules are already recorded in
`docs/research/wayfinder/aggregator-models.md` §4 and §7 (branch
`research/aggregator-models`). **They apply unchanged to every endpoint below**,
and any `reprocessed` declaration written from this file must name them. Only
the deltas that are specific to these endpoints are recorded here:

- **Marine, air-quality and satellite calls take no `elevation` parameter that
  matters** — the marine endpoint returns `elevation: 0.0` and transformation 2
  (90 m DEM statistical downscaling) has nothing to act on over water. Client
  rule 2 therefore reduces to sending an explicit `cell_selection` on marine
  calls, which does bite: land-preferring selection on a peninsula returns nulls
  (§1.4).
- **Transformation 1 (regridding) is not universal here.** `ecmwf_wam` returned
  the irregular cell centre **47.627415 / −52.635925** — an O1280 reduced
  Gaussian centre, not a regular lat/lon snap (*verified live*; `crs_wkt` in its
  `meta.json` reads `Reduced Gaussian Grid O1280 (ECMWF)`). That model is served
  on its native mesh. Every other marine domain snapped to a regular grid.
- **Transformation 1 runs the wrong way for CAMS.** §2.2.
- Client rule 1 (`meta.json` beside every call) works on all four hosts and is
  the only run stamp any of these endpoints offers. All run times below come
  from it.

---

## 1. Marine API — `marine-api.open-meteo.com/v1/marine`

### 1.1 Which models are offered, and who actually produces each

Model names were found by probing, because the API's rejection message does not
enumerate them (`"Cannot initialize MultiDomains from invalid String value …"`).
Seven domains answer over this box. `meteofrance_wam`, `mfwam`, `ncep_gfswave`
and `copernicus_marine` are **not** valid names; `ewam` is valid but returns
`"No data is available for this location"` (it is DWD's European regional wave
grid and does not reach 52 W).

| Open-Meteo `models=` | Producer / upstream product | Grid (from `meta.json` `crs_wkt` and returned centres) | Run cadence | Latency (init → availability, *verified live*) | Reach from init |
|---|---|---|---|---|---|
| `meteofrance_wave` | Météo-France **MFWAM** global | 1/12° regular (bbox −79.958…90.042 / −179.958…179.958) | 12 h | init 2026-09-01T12:00Z, available 2026-09-02T00:03:53Z → **T+12 h 04 m** | to 2026-09-11T03:00Z (~9.6 d), **3-hourly** |
| `meteofrance_currents` | Ocean analysis on the same 1/12° grid, Open-Meteo-labelled Météo-France. **Producer not confirmable from the API** — see §1.5 | 1/12° regular, identical bbox to `meteofrance_wave` | 24 h | init 2026-09-01T00:00Z, available 2026-09-01T12:05:38Z → **T+12 h 06 m** | to 2026-09-11T00:00Z (~10 d), hourly |
| `ecmwf_wam` | ECMWF **WAM** coupled to IFS, native mesh | **O1280 reduced Gaussian** (~9 km), not regridded | 6 h | init 2026-09-02T00:00Z, available 06:31:02Z → **T+6 h 31 m** | to 2026-09-17T01:00Z (~15 d), hourly |
| `ecmwf_wam025` | ECMWF WAM, 0.25° regular product | 0.25° | 6 h | init 2026-09-02T00:00Z, available 07:36:00Z → **T+7 h 36 m** | to 2026-09-17T03:00Z (~15 d), 3-hourly |
| `ncep_gfswave025` | NOAA/NCEP **GFS-Wave** global 0.25° | 0.25° | 6 h | init 2026-09-02T00:00Z, available 05:23:10Z → **T+5 h 23 m** | to 2026-09-18T01:00Z (~16 d), hourly |
| `ncep_gfswave016` | NOAA/NCEP **GFS-Wave** Atlantic/Arctic 0.16° | 0.16°, bbox lat −15…52.5 (the box is inside, just) | 6 h | init 2026-09-02T00:00Z, available 05:20:53Z → **T+5 h 21 m** | to 2026-09-18T01:00Z, hourly |
| `dwd_gwam` | DWD **GWAM** global wave | ~0.25°, bbox −85.25…89.25 | 12 h | init 2026-09-02T00:00Z, available 04:32:57Z → **T+4 h 33 m** — the fastest | to 2026-09-09T09:00Z (~7.4 d), 3-hourly |
| `era5_ocean` | ECMWF ERA5 reanalysis | 0.5° | reanalysis | — | **all-null in forecast mode** (0/24), as expected |
| `best_match` | resolved to **`meteofrance_wave`** at this point (identical values 1.28 / 1.24 m, identical cell centre) | — | — | — | 16-day request returned 384 rows but **216 non-null** — silently the MFWAM 9-day reach padded with nulls |

**The spread between producers at one point and hour is large and real**
(*verified live*, 47.6 N 52.6 W, first forecast hour): MFWAM 1.28 m, GFS-Wave
0.16° 1.12 m, GFS-Wave 0.25° 1.32 m, ECMWF WAM native 1.30 m, ECMWF WAM 0.25°
1.60 m, DWD GWAM 1.42 m. A 0.48 m range on a 1.3 m sea. Whichever is admitted,
`best_match` must not be, because it names no producer per value.

### 1.2 Which fields each model actually carries

Probed per model with a nine-field request (*verified live*). The split is
clean and it is the most important structural fact about this endpoint:

| Field | MFWAM | MF currents | ECMWF WAM (both) | GFS-Wave (both) | DWD GWAM |
|---|---|---|---|---|---|
| `wave_height`, `wave_period`, `wave_direction` | yes | — | yes | yes | yes |
| `swell_wave_*`, `wind_wave_*` | yes | — | **no** | yes | yes |
| `sea_surface_temperature` | — | **yes** | — | — | — |
| `ocean_current_velocity` / `_direction` | — | **yes** | — | — | — |
| `sea_level_height_msl` | — | **yes** | — | — | — |

**SST, currents and sea level exist on exactly one domain**,
`meteofrance_currents` — the one domain whose producer the API does not let you
name (§1.5). Units: currents in **km/h**, SST in °C, waves in m and s.

### 1.3 Verified-live values

At **47.6 N 52.6 W** (returned cell 47.625 / −52.624992), first hours: wave
height 1.28 → 1.22 m, wave period 6.1 → 6.2 s, wave direction 8°, swell 1.14 m
at 5.25 s from 8°, wind wave 0.46 m at 2.65 s, **SST 16.0 → 15.9 °C**, current
1.0 → 0.7 km/h toward 158–169°, sea level −0.14 m. 72/72 non-null over three
days; `past_days=3` also answers, span 2026-08-30T00:00 onward.

At **47.0 N 51.0 W** (Grand Banks, cell 47.041664 / −51.041656): wave 1.84 m at
6.85 s from 326°, swell 1.42 m at 5.95 s, wind wave 0.70 m, **SST 15.8 °C**,
current 0.5 km/h, sea level −0.24 m. 48/48 non-null.

The 16.0 °C Open-Meteo SST sits about 0.3 °C below the **16.3 °C** the
SmartAtlantic St. John's buoy reported at 47.567 N 52.631 W on this date
(`research/fog-cloud-sources` §in-situ). That is a plausible agreement, not a
verification — one point, one hour, and the buoy has no QC flags.

### 1.4 The coastal-null trap

At **49.5 N 56.5 W** (Notre Dame Bay), **every marine field is null, 0/48**
(*verified live*). The default land-preferring `cell_selection` picks a land
cell and the marine domains have no value there. This is transformation 3 from
`aggregator-models.md` §4 behaving exactly as documented, and it is worse on a
marine endpoint than on the forecast endpoint: the failure is a silent column of
`null`, not a wrong number. **Any marine client must send
`cell_selection=sea` and must treat a null run as a retrieval failure, not as
"calm".** Sheltered bays and fjord arms inside the box will null out even with
`cell_selection=sea` where the 1/12° or 0.25° ocean mask says land.

### 1.5 Why `meteofrance_currents` cannot be declared as it stands

A `reprocessed` record must name the producer. Open-Meteo labels this domain
Météo-France, but the fields it carries (surface current, sea level, SST on a
1/12° global grid) are the signature of a Mercator Ocean / Copernicus Marine
global analysis rather than a Météo-France product, and its `meta.json` carries
no producer string — only a bbox. **I could not confirm the producer from the
API, and I am not confident enough to write one into a registry record.** The
same reasoning refused Meteosource in `aggregator-models.md` §7: if the
declaration cannot be written truthfully, the class does not apply. This is
resolvable by reading Open-Meteo's marine documentation attribution and the
upstream licence, and it should be resolved before this domain is admitted,
because it is the only source of SST and currents on the endpoint.

### 1.6 Does it fill a gap the native sources cannot?

**Waves: yes, and it is the only route.** `research/fog-cloud-sources` found
`dd.weather.gc.ca/model_riops/` and `/model_ciops/` both 404, with CIOPS-East
reachable only through GeoMet; that research inventoried SST but recorded **no
wave field on any native path** — no significant wave height, period, direction
or swell partition from GeoMet, Datamart or GOES. `research/size-probe` found
51 SWOB stations in the box and **no marine ones**, and the single in-situ
marine record in the box is the SmartAtlantic buoy. So sea state over the box
today is one point or nothing. Six independent wave models with a 0.48 m spread
is a real addition.

**SST: no.** `research/fog-cloud-sources` already has three native SST paths
verified live — CIOPS-East 2 km at ~440 KB/hour, RIOPS 5 km at ~77 KB/hour, and
anonymous OSTIA Zarr at ~53 KB/day — plus GOES-19 `ABI-L2-SSTF` skin SST. That
file's warning applies directly: those are four *different quantities*, and
adding a fifth from an unnameable producer makes the air-sea dew point
depression derivation harder to write honestly, not easier. **Refuse the marine
SST.**

**Currents and sea level: catalogue only.** No admitted activity profile scores
them, and the producer question is open.

---

## 2. Air Quality API — `air-quality-api.open-meteo.com/v1/air-quality`

### 2.1 The domain question is settled: `cams_europe` does not reach this box

*Verified live* at 47.5675 N 52.7072 W:

- no `domains` parameter → **HTTP 200**, cell 47.600006 / −52.699997, elevation 46 m
- `domains=cams_global` → **HTTP 200**, byte-identical values to the default
- `domains=cams_europe` → **HTTP 400, `"No data is available for this location"`**

So the default resolves to `cams_global` here and there is no domain choice to
make. This also settles the pollen finding in `research/running-sources`: pollen
lives only on the European domain, so **alder, grass and ragweed remain 0/216
non-null over 9 days** (*verified live*, re-confirmed today). Pollen is still
blocked; nothing in this ticket changes that.

### 2.2 Run time, cadence, latency, reach

From `air-quality-api.open-meteo.com/data/cams_global/static/meta.json`
(*verified live*): `last_run_initialisation_time` **2026-09-01T12:00Z**,
`last_run_availability_time` **2026-09-01T22:15:42Z** → **T+10 h 16 m**;
`update_interval_seconds` 43200 (two runs a day, 00Z and 12Z);
`temporal_resolution_seconds` 3600; `data_end_time` **2026-09-06T13:00Z**.

The run was **21 hours old** when read at 09:04Z. A `forecast_days=7&past_days=2`
call returned 216 rows spanning 2026-08-31T00:00 → 2026-09-08T23:00 with
**157 non-null, last non-null 2026-09-06T12:00** — i.e. the honest forward reach
from now is about **4.1 days**, not 7, and the trailing nulls carry no marker.
`cams_europe` is a day behind that (init 2026-09-01T00:00Z, available 11:34:50Z,
T+11 h 34 m, daily, end 2026-09-05T01:00Z) and is irrelevant here anyway.

**A resolution problem specific to this endpoint.** `cams_global`'s `crs_wkt`
bbox is `−180.0 … 179.6`, i.e. the **0.4°** grid `research/transparency-seeing-sources`
recorded for the CAMS global composition forecast (~44 km). But the returned
cell centres step in **0.1°**: requests at −52.70, −52.55, −52.40 and −52.25
came back at −52.699997, −52.5, −52.4 and −52.199997 (*verified live*). The API
is serving a grid four times finer than the producer publishes. This is
transformation 1 running as an *upsample*, and it is the most misleading thing
on this endpoint: a stored value looks like a 0.1° field and is not one. Any
declaration must record the native 0.4° resolution, not the returned coordinate.

### 2.3 Verified-live values, and the one that matters

At St. John's, `forecast_days=3`, all **72/72 non-null** unless noted:

| Field | First hours | Note |
|---|---|---|
| **`aerosol_optical_depth`** | **0.20, 0.19** (max 0.27 over 9 days) | 550 nm per Open-Meteo documentation; not separable per response |
| `pm2_5` | 5.5, 5.4 µg/m³ (max 11.6) | |
| `pm10` | 8.5, 8.4 µg/m³ | |
| `ozone` | 67, 68 µg/m³ | |
| `nitrogen_dioxide` | 1.0, 0.9 µg/m³ | |
| `sulphur_dioxide` | 0.5 µg/m³ | |
| `carbon_monoxide` | 108 µg/m³ | |
| `dust` | **0.0 throughout** | plausible for a maritime box far from any dust source; not a null, a real zero |
| `uv_index` / `uv_index_clear_sky` | 0.0 at night, max 4.85 | |
| `methane` | 1391 ppb | |
| `carbon_dioxide` | 430 ppm | |
| `european_aqi` / `us_aqi` | 27 / 30 | index, not a physical field |
| `ammonia` | **0/72 null** | European domain only |
| `alder_pollen`, `grass_pollen`, `ragweed_pollen` | **0/216 null** | European domain only |

### 2.4 Does it fill a gap the native sources cannot?

**Aerosol optical depth: yes, and this is the single strongest find in the
ticket.** `research/transparency-seeing-sources` (issue #10) established that
GeoMet has **zero** matches for `aod`, `aerosol` or `optical` — ECCC publishes
mass concentration and never optical depth — and that *every* AOD path is
credential-blocked: CAMS through the ADS returns **HTTP 401** on `execute`, NASA
MAIAC `MCD19A2` and VIIRS `AERDB_L2` granule GETs return **401** anonymously.
That file names the open question outright: *"an openly retrievable AOD with no
credential"*. **Open-Meteo serves CAMS global AOD over this box anonymously,
hourly, with values, under CC BY 4.0.** It closes the named gap.

It closes it at a cost that must be declared: reprocessed rather than retrieved,
0.4° native served as 0.1°, a run stamp only from a second call, a ~21 h old run,
and about 4 days of usable reach. It also does **not** carry the speciated AODs
that `research/transparency-seeing-sources` §3 flagged as the ones that matter
in a maritime box — sea-salt AOD in particular. Total AOD only.

**PM2.5 and ozone: yes, with a caveat.** `research/running-sources` found the
only timely PM2.5 and ozone in the box is the provincial hourly CSV, provisional,
therefore an **uncalibrated observation**. Under the evidence-class ADR
(issue #17) uncalibrated is never primary and never a derivation input, so the
running profile currently has no admissible PM2.5. CAMS via Open-Meteo is
`reprocessed`, which is also never primary — but reprocessed is at least a
forecast rather than a provisional observation, and RAQDPS (native, on the dated
WXO-DD Datamart path, 3.8 h latency, per `research/transparency-seeing-sources`)
remains the right primary. **Open-Meteo PM and ozone add a cross-centre
comparison, not a primary.**

**UV index: no.** `research/running-sources` verified UV index live as
**producer output** on GeoMet HRDPS, RDPS and GDPS and on Datamart. Retrieved
beats reprocessed. Refuse.

**Dust, CO, NO2, SO2, CH4, CO2: no gap named by any research file.** Catalogue.

**European and US AQI: refuse.** They are index constructions over other
fields, not fields in the `CONTEXT.md` sense, and importing a foreign index
would put a fifth incompatible encoding beside the four transparency encodings
`research/astronomy-tool-needs` already flagged.

---

## 3. Satellite radiation — `satellite-api.open-meteo.com/v1/archive`

### 3.1 What answers over this box

`models=satellite_radiation_seamless` answers, and probing shows it resolves
here to **`eumetsat_lsa_saf_msg`** — identical values, identical cell centre
47.550003 / −52.699997, `max` 574.3 W/m² and last non-null hour identical
(*verified live*). `eumetsat_sarah3`, `jma_jaxa_himawari` and
`eumetsat_lsa_saf_iodc` return no data at this location;
`eumetsat_msg_cdr`, `nasa_ceres`, `goes_east` are not valid names.

So the producer is **EUMETSAT LSA SAF**, from **Meteosat MSG/SEVIRI at the
0° sub-satellite point**, on a 0.05° grid, and the intermediary is Open-Meteo.

**A physical caveat that belongs in the declaration.** St. John's at 52.7 W is
near the western limb of the Meteosat 0° disc; the satellite viewing zenith
angle over this box is very large. Limb-viewing degrades a surface radiation
retrieval (long slant path, parallax, poor cloud geometry) and it is why the
GOES-based products in `research/fog-cloud-sources` were preferred for this box.
I did not measure the retrieval error here and cannot state a magnitude — **this
is the open question that gates admission** (§6).

### 3.2 Cadence, latency, reach, values

*Verified live*, 2026-09-01 → 2026-09-02 at 47.5675 N 52.7072 W: 33/48 non-null,
**last non-null hour `2026-09-02T08:00`, read at about 09:10Z → latency about
one hour**. Hourly. **Archive only — no forward reach**: a request for
2026-09-02 → 2026-09-04 returned nothing. Peak 574.3 W/m² on 2026-09-01.

### 3.3 The field set, and why it is the answer to the WBGT problem

`research/running-sources` recorded the gap precisely: *"every model publishes
accumulated or averaged shortwave only, no direct or diffuse beam, so radiation
is derived-here at best"*, across HRDPS `_N4`/`_AS`, RDPS, GDPS and CAPS on
GeoMet — therefore **wet-bulb globe temperature is not reachable**, because a
globe temperature needs an instantaneous direct beam.

This endpoint publishes both halves and both time conventions, distinctly
(*verified live*, 2026-09-01T12:00Z, W/m²):

| | shortwave | direct | diffuse | DNI |
|---|---|---|---|---|
| hour mean | 278.0 | 159.0 | 119.0 | 364.8 |
| `_instant` | 325.0 | 185.9 | — | — |

The mean and instant series genuinely differ (159.0 vs 185.9 at the same hour),
so the distinction is carried, not cosmetic. `global_tilted_irradiance` and
`terrestrial_radiation` are also served.

**This fills the named gap: an observation-derived, instantaneous, direct-beam
irradiance over the box at ~1 h latency, which no native source publishes.**

### 3.4 The trap on the forecast endpoint

`api.open-meteo.com/v1/forecast` also serves `direct_radiation`,
`diffuse_radiation` and `direct_normal_irradiance` — verified live returning
48/48 non-null for `models=ecmwf_ifs025`. **These are not the same thing.** They
are transformation 5 from `aggregator-models.md` §4: Open-Meteo splitting a
producer's total shortwave into beam and diffuse by its own decomposition, for a
producer that publishes no such split. That is an intermediary's derivation
presented without a method name, and it should be **refused** — the same
reasoning that refused WeatherNext 2 cloud in `aggregator-models.md` §7. The
satellite endpoint's split is a retrieval from measured radiance; the forecast
endpoint's split is a model of a model. They must never be catalogued as one
field.

---

## 4. Flood, Climate, Seasonal, Elevation

### 4.1 Flood — `flood-api.open-meteo.com/v1/flood`

*Verified live*, `daily=river_discharge`, `forecast_days=30&past_days=5`,
35/35 non-null at all three points, span 2026-08-28 → 2026-10-01, ~0.05° cells:

| River | Cell | Discharge span |
|---|---|---|
| Exploits, near Grand Falls (48.93 N 55.66 W) | 48.925 / −55.675 | 243.34 → 211.81 m³/s |
| Humber (49.23 N 57.44 W) | 49.225 / −57.425 | 186.93 → 176.42 m³/s |
| Waterford, St. John's (47.55 N 52.85 W) | 47.525 / −52.875 | 0.21 → 0.69 m³/s |

Producer **GloFAS** (Copernicus Emergency Management Service, ECMWF-run);
intermediary Open-Meteo; daily; 30-day reach. It works, and the two large NL
rivers give sane magnitudes. The Waterford values are the warning: a 0.05° cell
is ~5 km, which does not resolve an urban catchment that size, and the numbers
are a global routing model's guess rather than a gauge.

No activity profile in issue #5 scores river discharge — running, astronomy,
aurora and landscape photography do not. **No gap is named by any research file.**

### 4.2 Climate — `climate-api.open-meteo.com/v1/climate`

*Verified live*: `models=EC_Earth3P_HR`, 2026-09-01 → 2026-09-10 returned daily
maxima 20.6, 19.7, 20.1, 20.5, 16.5, 19.6, 21.2, 20.5, 15.6, 21.8 °C at
St. John's. These are **CMIP6 HighResMIP downscaled projection values, not a
forecast**, and the API answers for dates inside the 14-day horizon with no
marker distinguishing them from one. That is exactly the hazard the evidence
classes exist to prevent. It adds nothing inside 14 days and is actively
confusable there.

### 4.3 Seasonal — `seasonal-api.open-meteo.com/v1/seasonal`

Producer **ECMWF SEAS5**, the only valid `models=` value found
(`ecmwf_seas5`; `cfs`, `ncep_cfs`, `ncep_cfsv2`, `seasonal_forecast` all
rejected). `meta.json` (*verified live*): O320 reduced Gaussian,
`temporal_resolution_seconds` 21600 (6-hourly), `update_interval_seconds`
2678400 (**monthly**), `last_run_initialisation_time` **2026-08-01T00:00Z**,
`last_run_availability_time` **2026-08-05T13:22:25Z** → **T+4.4 days**,
`data_end_time` 2027-03-04.

A monthly run, four days late, 6-hourly, on an O320 (~36 km) mesh. Inside a
14-day horizon it is a month-old climate signal. **It adds nothing**, as the
ticket anticipated.

### 4.4 Elevation — `api.open-meteo.com/v1/elevation`

*Verified live*, one call, three points: 47.5675 N 52.7072 W → **46 m**;
47.0 N 51.0 W → **0 m** (open ocean, correct); 49.5 N 56.5 W → **222 m**. The
46 m agrees exactly with the `elevation: 46.0` echoed by the air-quality
response, so the same DEM backs both. Open-Meteo documents this as **Copernicus
DEM GLO-90** (90 m), which is what transformation 2 in `aggregator-models.md`
§4 downscales against.

This is not a forecast field and not evidence in the `CONTEXT.md` sense. It is
worth noting for one reason only: it is the **same DEM whose downscaling client
rule 2 tells us to switch off** with `&elevation=nan`. Having it addressable
separately means a station or site elevation can be recorded once, deliberately,
rather than leaking into every temperature value invisibly.

---

## 5. Recommendation per endpoint

### Admit as `reprocessed`

1. **Air Quality API, `aerosol_optical_depth` from `cams_global`.** The one
   clear win. Fills the gap `research/transparency-seeing-sources` (issue #10)
   named and could not close: no AOD on GeoMet at all, and CAMS/ADS, NASA MAIAC
   and VIIRS all HTTP 401 anonymously. Producer **ECMWF CAMS global atmospheric
   composition forecast**; intermediary **Open-Meteo**; CC BY 4.0 with CAMS
   upstream; two runs a day at **T+10 h 16 m**; hourly; ~4 days of usable reach.
   Declaration must name all six transformations from `aggregator-models.md` §4
   **plus** the 0.4° → 0.1° upsample (§2.2), must store native 0.4° as the
   resolution, must store `last_run_initialisation_time` from `meta.json`, and
   must record that this is **total AOD only, no speciation** — sea-salt AOD,
   the term that matters most in a maritime box, is not served. Never primary,
   never a derivation input, per the issue #17 ADR.

2. **Satellite radiation, `eumetsat_lsa_saf_msg` — direct, diffuse and DNI,
   mean and `_instant`.** Fills the gap `research/running-sources` (issue #11)
   named: no direct or diffuse beam anywhere on GeoMet, so WBGT is unreachable.
   Producer **EUMETSAT LSA SAF** from Meteosat MSG/SEVIRI; intermediary
   Open-Meteo; 0.05°; hourly; **~1 h latency**; **archive only, no forecast**.
   **Admit conditionally on the limb-geometry question in §6.1.** Until that is
   answered, `implemented-unverified` is the honest ceiling. Declaration must
   record the viewing geometry caveat and must never merge these values with the
   forecast endpoint's derived split (§3.4).

3. **Marine API waves — one named model, not `best_match`.** Fills a real gap:
   `research/fog-cloud-sources` (issue #9) found no wave field on any native
   path, and `research/size-probe` found no marine SWOB station in the box, so
   sea state is the SmartAtlantic buoy or nothing. Recommend **`ncep_gfswave016`**
   as the admission: fastest useful combination of latency (**T+5 h 21 m**),
   hourly steps, 16-day reach, the finest grid of the wave set (0.16°), and it
   carries the swell and wind-wave partition that `ecmwf_wam` lacks.
   **`dwd_gwam` is the earliest (T+4 h 33 m)** and is the right second if
   cross-centre spread is wanted; it stops at 7.4 days. Client must send
   `cell_selection=sea` and treat an all-null column as a retrieval failure
   (§1.4). NOAA open licence upstream, CC BY 4.0 from Open-Meteo.

### Catalogue only

4. **Air Quality PM2.5, PM10, ozone, NO2, SO2, CO, dust.** RAQDPS native is the
   primary (`research/transparency-seeing-sources`); this is a cross-centre
   comparison, useful but not gap-filling. Catalogue with the licence and the
   §2.2 resolution caveat recorded, ingest only if the running profile later
   asks for a second opinion on PM.

5. **Marine currents and sea level (`meteofrance_currents`).** Blocked on the
   producer question in §1.5, not on licence or access. Catalogue with the open
   question written down; no profile scores them today.

6. **Flood / GloFAS river discharge.** Works, covers NL rivers, is plausible on
   the large ones and unresolved on the small ones. No profile scores it and no
   research file names a gap it fills. Catalogue.

7. **Elevation.** Not evidence. Record the DEM (Copernicus GLO-90) in the
   provenance vocabulary so `&elevation=nan` has a documented counterpart.

### Refuse

8. **Marine `sea_surface_temperature`.** Four native SST paths already verified
   (`research/fog-cloud-sources`), all better provenance, and that file warns
   that they are four different quantities. A fifth from an unnameable producer
   makes the air-sea derivation harder to write honestly.
9. **`uv_index`.** Producer output on GeoMet, verified live in
   `research/running-sources`. Retrieved beats reprocessed.
10. **Pollen (`alder`, `grass`, `ragweed`) and `ammonia`.** 0/216 non-null over
    this box, re-confirmed today; `cams_europe` returns HTTP 400 here. Unchanged
    from `research/running-sources`: pollen stays blocked.
11. **`european_aqi` and `us_aqi`.** Index constructions, not fields; a fifth
    incompatible encoding beside the four transparency encodings.
12. **Radiation beam split from `api.open-meteo.com/v1/forecast`.** §3.4. An
    intermediary's decomposition of a producer's total, with no method name —
    the WeatherNext 2 cloud refusal reasoning applies exactly.
13. **`best_match` on any endpoint.** Names no producer per value, and on the
    marine endpoint it silently pads MFWAM's 9-day reach to 16 days with nulls.
14. **Climate API.** CMIP6 projections that answer for forecast dates with no
    marker. Confusable, and adds nothing inside 14 days.
15. **Seasonal API / SEAS5.** Monthly run at T+4.4 days, 6-hourly, ~36 km. As
    predicted, nothing inside the horizon.
16. **`era5_ocean`, `ewam`, `eumetsat_sarah3`, `jma_jaxa_himawari`,
    `eumetsat_lsa_saf_iodc`.** Null or no coverage over this box.

---

## 6. What this leaves open

1. **How badly Meteosat limb geometry degrades LSA SAF radiation at 52.7 W.**
   §3.1. This gates recommendation 2 and is the most consequential unknown in
   the ticket — the direct-beam field is the only route to WBGT.
2. **Who actually produces `meteofrance_currents`.** §1.5. Gates the only SST,
   current and sea-level fields on the marine endpoint.
3. **Whether the CAMS AOD served here is subject to the ADS licence dispute**
   that `research/transparency-seeing-sources` §3 recorded — the ADS catalogue
   `license` field and the registry entry disagree. Open-Meteo's own CC BY 4.0
   may or may not survive that upstream.
4. **Whether the 0.4° → 0.1° CAMS upsample is interpolation or nearest-cell.**
   §2.2. Determines whether stored neighbouring cells are independent values or
   four copies of one.
5. **Wave field size in the box.** No size measurement was made here; the
   marine endpoint is point-query only, so a gridded wave surface over the box
   would be many calls against the 10 000/day budget, or a different access
   route entirely. `research/size-probe`'s method should be applied before
   recommendation 3 is ticketed.
6. **Whether `single-runs-api` covers the marine, air-quality and satellite
   domains**, which would let client rule 3 (caller-asserted run provenance)
   apply here as it does on the forecast endpoint. Not probed.
