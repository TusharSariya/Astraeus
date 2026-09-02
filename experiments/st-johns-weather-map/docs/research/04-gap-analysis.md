# Consolidated gap analysis — what the experiment is missing

Three deep-research passes assessed **209 sources** (94 atmospheric/NWP/satellite,
52 marine/ocean/ice, 63 local/climate/commercial) against the 59 in the registry.
Full detail in `01-`, `02-` and `03-`. This file is the ranked answer and the
orchestrator's own verification.

**Everything in the "verified by orchestrator" column was re-checked directly,
not taken from an agent's report.** Two agent claims were wrong and are
corrected below.

---

## The five structural gaps

These are not missing feeds. They are missing *capabilities* — the experiment
cannot do these things at all today.

1. **No verification.** No archive of past forecasts, so the project cannot
   measure whether any forecast it shows was any good. No bias correction, no
   skill score, no model ranking is possible.
2. **No historical or climate data.** No normals, no reanalysis, no long series.
   Nothing to compute an anomaly against or to train a correction on.
3. **No vertical profile.** `/profile` and any future Skew-T have no real data
   source. (The GeoMet agent preserved a capability but it needs a registry
   record that does not exist.)
4. **No sea ice, and no icebergs.** Iceberg Alley runs past the Avalon. Zero
   coverage.
5. **Only one satellite source, and it is the wrong one for this latitude.**
   St. John's sits at ~60-63 degrees GOES-East zenith angle — the worst case for
   the fog/low-cloud brightness-temperature-difference technique, with roughly
   2x pixel stretch and tens of km of parallax. Polar orbiters are the *primary*
   satellite source here, not a supplement.

---

## Top 12, ranked by value per unit of work

| # | Source | Closes | Effort | Verified by orchestrator |
|---|---|---|---|---|
| 1 | ~~**ECCC CYYT forecast sounding**~~ **DEAD as of 2026-09-02** | — | — | ❌ `https://dd.weather.gc.ca/today/vertical_profile/` now returns 200 containing **only `doc/`**; every `forecast/` and `observation/` path is 404 on Datamart and on the hpfx mirror. Same shape as the GEPS and REPS disappearance. Replacement for vertical structure is **NUCAPS-EDR** satellite soundings plus **Mode-S winds aloft**, both verified live 2026-09-02. See `01-atmospheric-nwp-satellite.md` R1 and R3 |
| 2 | **NL Water Resources via SWOB partners** `swob-ml/partners/nl-water/` | best local surface obs; snow water equivalent, snow depth, solar radiation, soil moisture the airport lacks | low — same SWOB parser already written | ✅ `NLENCL0001` "Pippy Park in St. Johns" 47.58036/-52.73936, **2.2 km from map centre**, live 00:30Z: 18.0 °C, RH **99 %**, QA flags present |
| 3 | **Open-Meteo historical-forecast archive** | **verification** — past forecasts as issued, from 2021; also lead-time-aligned previous runs from 2024 | low — plain JSON, no key | agent-verified 200 at 47.56/-52.71; CC BY 4.0 |
| 4 | **ARCO-ERA5** on Google Cloud | reanalysis, from nothing | low — anonymous Zarr | agent-verified `.zmetadata`, 1940-01-01 → 2026-08-24, CC-BY-4.0 |
| 5 | **ECCC climate collections** on `api.weather.gc.ca` | climate archive, normals, **146-year AHCCD homogenized St. John's series (1874-2020)** | low — OGC API Features, same client as SWOB | agent-verified; 104 collections exist, registry uses ~none |
| 6 | **Mode-S winds aloft** `api.adsb.lol/v2/point/47.56/-52.71/250` | upper-air winds; nearest radiosonde is Stephenville, **600 km west** | low — JSON, no key, ODbL | ✅ 21 aircraft overhead, **16 carrying wind dir/speed + OAT** at FL340-380 |
| 7 | **VIIRS `JRR-CloudBase`** on `noaa-nesdis-n20/n21/snpp-pds` | the satellite gap; **cloud base at the surface *is* fog** at 750 m near-nadir | medium — NetCDF from S3 | agent-verified keyless, files current |
| 8 | **RIOPS** | sea ice concentration/**drift**/divergence, SST, currents, 5 km hourly +84 h | medium — GRIB2 (blocked until #12) | agent-verified in-domain twice |
| 9 | **CIOOS Atlantic ERDDAP** | 48 datasets in the Avalon bbox incl. Station 27 off Cape Spear with iceberg fields | low — ERDDAP, CC-BY 4.0 | agent pulled live CSV |
| 10 | **International Ice Patrol + CIS SIGRID-3** | icebergs and ice charts, from nothing | medium — KML/shapefile | agent-verified 200; limit today ~180 km north |
| 11 | **CoCoRaHS `CAN-NL-2`** | manual gauge; automated gauges undercatch winter precipitation | low | agent: 47.564/-52.713, **within 400 m of map centre** |
| 12 | ~~**Fix cfgrib/numpy**~~ **DONE 2026-08-30 - and it was never cfgrib/numpy** | unblocked HRDPS, RDPS, GFS | small - one function | Real cause: `crop_to_bbox` assumed 1-D lat/lon; HRDPS/RDPS are on a **rotated** grid so cfgrib returns **2-D** coords. Pins were never changed. See the retraction in `docs/live-stack-report.md`. |

~~**#1 and #12 are the two that matter most.**~~ **Superseded 2026-09-02.**
#12 is done. #1 is dead: the feed it depended on was withdrawn. The ranking
that replaces it, after the re-verification pass in
`01-atmospheric-nwp-satellite.md`:

1. **GeoMet WCS.** 6123 coverages, 377 of them HRDPS at 2.5 km, and the stack
   already talks to GeoMet over WMS. It carries the 40/80/120 m boundary-layer
   stack, humidity on 28 pressure levels, boundary-layer height, skin
   temperature and ice cover — none of which the project has, and most of
   which are the fog problem directly. It is also where the withdrawn ECCC
   feeds appear to have gone.
2. **VIIRS `JRR-CloudBase` and NUCAPS-EDR.** The satellite gap and, now, the
   only vertical structure available over the Grand Banks.
3. **ARCO-ERA5.** Unchanged from the old #4, still verified, still keyless.
4. **Mode-S winds aloft.** Cheapest real wind aloft at this point, verified
   with 9 reporting aircraft at the moment of probing.

**Standing warning added 2026-09-02:** three ECCC Datamart recommendations in
these documents died within three days of being written, each leaving an empty
directory containing only `doc/`. Re-probe any ECCC path here before building
against it.

---

## Corrections to the research

- **"The Datamart tree has been re-rooted; every bare path 404s."** — **WRONG.**
  Checked directly: `today/model_hrdps/`, `today/model_rdps/`,
  `today/model_giops/`, `today/coastal-flooding/` and `today/vertical_profile/`
  all return 200 with populated subdirectories. Both layouts work; `today/` is a
  live alias. The real property is that the dated directory **rolls at 00Z and
  is empty for the first hours** — which is a timing fact, not a re-rooting, and
  no ingest path is broken by it. Retraction is prepended to `02-`.
- **"`ObsTephi_00_CYYT.csv` exists alongside the forecast."** — **WRONG at that
  path** (404). Observed soundings are real but live under
  `vertical_profile/observation/csv/`.

---

## Licence traps — do not build against these

Quoted from the providers' own terms by the research pass:

| Source | The problem |
|---|---|
| **Tomorrow.io** | forbids caching outright |
| **Visual Crossing** | *"Raw data can never be shared and distributed publicly… only be shown for viewing purposes"* — external storage is Enterprise-only |
| **Weatherbit** | requires deleting stored data on cancellation |
| **OpenWeatherMap** | ODbL share-alike would **infect the project's blended database** |
| **NL provincial site** | "all rights reserved" — use the ECCC SWOB *partner* feed instead, which carries the permissive MSC licence |
| **NL-DECCM-WRMD** | ✅ confirmed: the SWOB XML carries a `data_attrib_not` element reading "All rights reserved" that **must survive decoding**, not be stripped |
| **MADIS aircraft** | free to *access* but proprietary to the airlines — likely not publishable on a public map. A bigger constraint than the credential. |

---

## Verified negatives — recorded so nobody re-searches them

- **CARRA is a trap.** Its bbox is `[15, 60, 65, 72]` — 15-65 degrees **East**.
  "Arctic reanalysis" does not mean Atlantic Canada.
- **MRMS** ingests Canadian radars but publishes **no Atlantic Canada sector**.
- **No free 2.5 km alternative to HRDPS exists.** Every European CPM and US
  CONUS domain tested returns "no data at this location".
- **No real-time buoy near the Avalon.** 1,351 NDBC stations, 42 GeoMet marine
  stations and both Datamart trees enumerated: nearest active is **44139
  Banquereau Bank at 502 km**. The Newfoundland buoys (44251 Nickerson Bank,
  ~130 km) 404 on realtime *and* historical. **`eccc-marine-buoys-synop` is a
  Scotian Shelf proxy and the UI must say so.**
- **No public Grand Banks platform met-ocean feed.** C-NLOPB publishes PDFs only.
- **No NL RWIS.** NB, NS and PE have `nl-rwin/`-style SWOB partner feeds;
  Newfoundland does not. Confirms the existing registry tombstone.
- **MUN publishes no live station data.** Its Signal Hill and Chemistry-Physics
  stations are display-only — an email lead, not an engineering task.
- **City of St. John's has no data host** — `data.stjohns.ca` and
  `maps.stjohns.ca` both fail to resolve.
- `api.weather.gov` 404s for Canada. ECCC `meteocode/` has no Atlantic region.
  `metnotes/` was empty. OpenSky returns `"states": null` anonymously and its
  schema lacks the met fields anyway.
- Dead endpoints: MERRA-2 `goldsmr4` OPeNDAP is **410 Gone**; UWyo moved
  `/cgi-bin/sounding` → `/wsgi/sounding`; `noaa-gpm-imerg-pds`, `sentinel5p`,
  `noaa-nesdis-metop-pds`, `noaa-nws-rtma-pds` do not exist.

---

## Data-quality gotchas that would otherwise ship as bugs

- **GDWPS returns `9999` at 47.5 N/52.75 W**, styled `">= 15.0 (m)"`. That is a
  **land-mask fill, not a 15 m sea.**
- **Empty responses are normal and meaningful**: RIOPS ice concentration in
  summer, CIS charts in August, the NL flooding GeoJSON on calm days. This
  codebase already treats absence as evidence — that is correct here.
- ✅ **Station pressure is not MSLP.** Pippy Park reports `stn_pres` 1038 hPa at
  101 m elevation while CYYT reports MSLP 1011.8. Different quantities.
- ✅ **Local RH varies across the Avalon**: 99 % at Pippy Park vs 93.9 % at the
  airport at the same hour. A single-station fog signal is not the peninsula.
- ISD/IEM list an active Avalon station, **`CWWU`/`719455` LONG POND
  (47.5158, -52.9803)**, that the ECCC `climate-stations` query does not return.
