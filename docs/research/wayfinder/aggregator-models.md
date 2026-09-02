# Foreign models reachable only through aggregators

**Non-normative research, 2026-09-02.** Nothing here changes a registry state,
a spec or a stored value. Classification: Experiment, Spec-Impact none.
Resolves wayfinder research ticket
[#14](https://github.com/TusharSariya/Astraeus/issues/14) under the map ticket
[#5](https://github.com/TusharSariya/Astraeus/issues/5).

**Method.** Roughly thirty-five upstream calls between 06:05 and 06:35 UTC on
2026-09-02, against `api.open-meteo.com`, `ensemble-api.open-meteo.com`,
`single-runs-api.open-meteo.com`, `historical-forecast-api.open-meteo.com`,
`opendata.dwd.de`, `api.brightsky.dev`, `noaa-nbm-grib2-pds.s3.amazonaws.com`
and `www.meteosource.com`. **Verified live** means a call made here returned
the thing claimed. **Documentation** means a provider's own written statement.
Every point probe used 47.5615 N, 52.7126 W (St. John's), inside the evidence
box (45.0 to 50.5 N, 58.0 to 46.0 W).

Reach, latency and licence for ICON global and WeatherNext 2 are **not
repeated** here; they are in
`docs/research/wayfinder/planning-horizon-matrix.md` on branch
`research/planning-horizon-matrix`. This ticket adds only what that matrix does
not cover: the intermediary path, its transformations, and whether a
`reprocessed` declaration is honest.

---

## 1. The rule this has to satisfy

`openspec/config.yaml`, owner decision 2026-09-02: a value an intermediary
transformed before delivering it is still retrieved and **may** be served, but
only from a source the registry declares `reprocessed`, **naming the producer
and the intermediary separately and every documented transformation**, and
**never as the display primary and never as an input to a derivation**.

Two consequences run through everything below.

1. A `reprocessed` declaration is only honest if the intermediary **documents**
   what it did. An undocumented or discretionary transformation cannot be
   named, so the record cannot be written truthfully and the source is not
   admissible under this rule.
2. A field the producer **never published at all** is not a transformed
   producer value. It is the intermediary's own computation. `reprocessed`
   would launder it, and `derived-here` is false because this deployment did
   not compute it and cannot cite the method's inputs. There is no honest class
   for it, so it must be refused. This is not hypothetical — see WeatherNext 2
   cloud in §5.

---

## 2. Models the stack already reaches natively — never take these through an aggregator

Taking any of these through an intermediary would demote a `retrieved` value to
`reprocessed` for nothing, and cost the display primary and every derivation
that depends on it.

| Model | Native path in this stack | Adapter |
| --- | --- | --- |
| ECCC HRDPS | GeoMet WCS/WMS, server-side subset | `ingest/adapters/eccc_geomet.py`, `eccc_ogc.py` |
| ECCC RDPS | GeoMet | same |
| ECCC GDPS | GeoMet | same |
| ECCC REPS (21 members) | GeoMet, subset server side | same |
| ECCC GEPS (reductions) | GeoMet | same |
| NOAA GFS | `noaa-gfs-bdp-pds` S3, GRIB2 + `.idx` byte ranges | `ingest/adapters/noaa_s3.py` |
| NOAA GEFS (31 members) | `noaa-gefs-pds` S3 | same |
| ECMWF IFS, IFS ENS, AIFS single, AIFS-ENS | ECMWF open data, CC BY 4.0 | `ingest/adapters/ecmwf_opendata.py` |
| ECCC Datamart products (RAQDPS, FireWork, …) | Datamart HTTPS | `ingest/adapters/eccc_datamart.py` |
| GOES-19 ABI | `noaa-goes19` S3 | `ingest/adapters/goes_abi.py` |

**DWD ICON global is the one native path that is implemented and does not
work** — `ingest/adapters/dwd_icon.py` registers the source, raises
`AdapterUnavailable` from both `discover` and `fetch`, and states why: the
open-data files are `icon_global_icosahedral_single-level_*` on an unstructured
R03B07 mesh, and `crop_to_bbox` and every point sample downstream assume
rectilinear lat/lon. The module refuses to invent a regrid. §6 resolves that
without an aggregator.

---

## 3. Aggregators surveyed

### Open-Meteo (`api.open-meteo.com`) — the only one that matters here

Open-source (AGPLv3), operates its own ingest of national open data, serves
point and bounding-box time series as JSON.

- **Licence:** API data offered under **CC BY 4.0** (documentation, licence
  page read 2026-09-02). Attribution must be a link next to any location the
  data is displayed, the page's own example being
  `<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a>`.
- **Commercial terms:** the free API is **non-commercial use only** (terms page,
  read 2026-09-02), with Creative Commons' own definition of non-commercial
  cited. A private, non-advertising, non-subscription map is inside that; the
  moment this experiment grows a subscription or advertising it is not.
- **Rate limits (free tier, documentation):** fewer than **10 000 calls/day,
  5 000/hour, 600/minute**. Open-Meteo reserves the right to block abusers
  without notice. No `X-RateLimit-*` headers were returned on any probe here,
  so a client cannot see its own budget; it must count its own calls.
- **Upstream licences are not uniform and Open-Meteo says so.** Its licence
  page lists per-producer terms, and **UK Met Office is CC BY-SA**. A
  share-alike obligation reaching into a derived product is a different
  question from CC BY and has to be answered before any UKMO value is stored,
  never mind displayed.

### Bright Sky (`api.brightsky.dev`) — **not Germany-only, and this is a real find**

The ticket's premise was that Bright Sky is Germany-only. It is not. Bright Sky
serves DWD **MOSMIX**, and MOSMIX is a global station set.

`GET /weather?lat=47.5615&lon=-52.7126&date=2026-09-02` returned **HTTP 200**
with a full hourly series, sourced from station **WMO 71801
"ST.JOHNS NEUFUNDL."** at 47.62 N, 52.73 W, height 134 m, **6 642 m from the
request point** — *verified live*. Records ran `2026-09-02T04:00Z` to
`2026-09-12T10:00Z`, so roughly **ten days** of hourly point forecast.

Fields returned per hour (*verified live*): `temperature`, `dew_point`,
`relative_humidity`, `cloud_cover`, **`visibility`**, `pressure_msl`,
`wind_speed`, `wind_direction`, `wind_gust_speed`, `wind_gust_direction`,
`precipitation`, `precipitation_probability`, `sunshine`, `solar`, `condition`,
`icon`. In the 04:00Z record `cloud_cover` was 64 %, `visibility` 23 800 m, and
`dew_point` equalled `temperature` at 10.6 °C. Several fields
(`relative_humidity`, `sunshine`, `solar`, gusts, probabilities) were **null**
at this station, so MOSMIX's element set for 71801 is narrower than the API's
schema.

- **Producer:** Deutscher Wetterdienst. **Intermediary:** Bright Sky (Jakob de
  Maeyer), open source, code MIT, `dwdparse` parsing core.
- **Documented transformation:** the parse of DWD's MOSMIX KMZ into JSON, plus
  Bright Sky's own nearest-station selection when the request is a coordinate
  rather than a station id. The station chosen is returned in `sources` with
  its `distance`, so the selection is inspectable per response — *verified
  live*.
- **The deeper transformation is DWD's, not Bright Sky's.** MOSMIX is model
  output statistics: a statistical post-processing of ICON and IFS onto station
  points. That makes it a DWD **product**, so a MOSMIX value fetched from DWD
  directly would be `retrieved`. Fetched from Bright Sky it is `reprocessed`
  with producer DWD and intermediary Bright Sky, and only the parse and the
  station pick need naming.
- **Licence:** DWD open data / GeoNutzV, attribution to Deutscher Wetterdienst,
  the same terms already recorded as `verified` on `dwd-icon-global`.
- **Rate limits:** none documented on the public instance; the README offers
  self-hosting for heavier use. Treat as fair use, unmeasured.

### Meteosource — catalogue, do not ingest

`GET /api/v1/free/point` returned **HTTP 403**, `"Neither the "key" query
parameter nor the X-API-Key header was specified"` — *verified live*. Sign-up
required, paid tiers above a free allowance. Its own marketing page describes a
proprietary blend ("How our forecasts are made"). **A blend whose producer
cannot be named cannot satisfy the `reprocessed` declaration**, which requires
producer and intermediary separately. That is decisive independent of the
licence, and it is the same reason `consensus` was removed from the vocabulary.

### NOAA NBM — named for completeness; not an aggregator, and out of area

The National Blend of Models is NOAA's own statistical post-processing of NOAA
and partner models, so its output is **producer output** — a value fetched from
NOAA would be `retrieved`, not `reprocessed`. It is live on
`noaa-nbm-grib2-pds` (*verified live*: `blend.20260902/00/core/` enumerated,
`f012` present for every domain). The published domains are **`ak`, `co`,
`gu`, `hi`, `oc`, `pr`** — Alaska, CONUS, Guam, Hawaii, Oceanic, Puerto Rico.
**No domain covers Newfoundland**: the evidence box is neither CONUS nor
Pacific-oceanic. The grids were not decoded here, so this is reasoned from the
published domain set rather than measured; but no plausible reading of that set
puts 47.5 N 52.7 W inside it. NBM is out on coverage, not on class.

### Named and not pursued

meteoblue, Windy, Stormglass, Weatherbit, Tomorrow.io: all key-gated
commercial resellers whose terms restrict redistribution and whose blends do
not name a single producer. They belong in the paid-provider catalogue with a
licence decision, per issue #5's scope, and nowhere near a data path.

---

## 4. What Open-Meteo actually does to a value — the transformation list a `reprocessed` record must name

These are Open-Meteo's own documented behaviours, several of them **on by
default**, all of them measured or read on 2026-09-02. Any registry record that
declares an Open-Meteo source `reprocessed` has to name all of them.

1. **Regridding off the native grid.** For ICON global, the returned cell
   centres were 47.5 / −52.75 by default and 47.5 / −52.625 with
   `cell_selection=sea` — a **0.125° regular lat/lon spacing**, not the
   icosahedral R03B07 mesh (*verified live*, spacing inferred from the two
   returned cell centres). That matches DWD's own
   `ICON_GLOBAL2WORLD_0125_EASY` weight set. The regrid happens; its exact
   method is not stated per response.
2. **Statistical elevation downscaling, on by default.** Documentation: "The
   elevation used for statistical downscaling. Per default, a 90 meter digital
   elevation model is used… If `&elevation=nan` is specified, downscaling will
   be disabled and the API uses the average grid-cell height." Measured
   (*verified live*): the default response reported `elevation: 34.0` m and
   12.2 °C at 00:00Z; `&elevation=nan` reported `elevation: 148.0` m and
   11.5 °C. **A 0.7 °C difference at hour zero, from the intermediary, not the
   model.** The default response is *not* the model's grid-cell value.
3. **Grid-cell selection policy.** `cell_selection=land|sea|nearest`, defaulting
   to a land-preferring choice. `cell_selection=sea` moved the cell one column
   east and the 00:00Z temperature from 12.2 °C to 14.0 °C (*verified live*).
   For a fog map on a peninsula this is not a detail: the intermediary is
   choosing land or water for you.
4. **Temporal interpolation to the finest available step.** Open-Meteo's
   `open-data` README (documentation): the rolling timeseries distribution
   "always interpolates all data to the highest available temporal resolution",
   while `data_run/` and `data_spatial/` keep native resolution. ICON global
   goes 3-hourly beyond +78 h and IFS beyond +144 h; those hours come back
   **hourly** from `/v1/forecast` with no marker. This collides directly with
   the governing rule's "never interpolate into a gap" — the interpolation is
   the intermediary's, and it is invisible in the response.
5. **Derivation of fields the producer did not publish.** Documented per model.
   Relative humidity from specific humidity, wind speed and direction from u/v,
   dew point from temperature and RH, low/mid/high cloud from RH on pressure
   levels, total cloud by combining those layers, weather code from
   precipitation, temperature and derived cloud. §5 is the case where this
   matters most.
6. **Accumulation redistribution.** Documented for 6-hourly models: a 6-hour
   precipitation total is "distributed over" the hourly steps.
   `temporal_resolution=native` returns the original intervals.

**Run-time exposure — better than expected, and in three separate places.**

- The `/v1/forecast` response body carries **no run reference time at all**
  (*verified live*: top-level keys are `latitude`, `longitude`, `elevation`,
  `generationtime_ms`, `utc_offset_seconds`, `timezone`,
  `timezone_abbreviation`, `hourly`, `hourly_units` — nothing else). A bare
  forecast call cannot tell you which run it drew from.
- **`https://api.open-meteo.com/data/<domain>/static/meta.json` does**, and it
  is public and unauthenticated (*verified live*). It carries
  `last_run_initialisation_time`, `last_run_availability_time`,
  `last_run_modification_time`, `data_end_time`, `temporal_resolution_seconds`
  and `update_interval_seconds` as Unix seconds. This is the honest way to
  stamp a run on an Open-Meteo value: read `meta.json` beside the data call.
  It is **per domain, not per response**, so a value and its run stamp are two
  calls and can skew.
- **`single-runs-api.open-meteo.com/v1/forecast?...&run=YYYY-MM-DDTHH:MM`**
  returns a named run (*verified live*, HTTP 200 for `run=2026-09-02T00:00` on
  `icon_global`; the same `run=` parameter is rejected with HTTP 400
  `"Parameter 'run' must not be set"` on both `api.` and `previous-runs-api.`).
  Documentation: most models archived from **2026-04-02**, ECMWF IFS HRES 9 km
  from March 2024. This is the strongest form — the caller *names* the run, so
  the value's provenance is not inferred.

**Historical forecast runs — three distinct products, all live.**

- `historical-forecast-api.open-meteo.com/v1/forecast` with `start_date` /
  `end_date`: HTTP 200 for 2026-08-30 `icon_global` cloud cover (*verified
  live*).
- Previous-model-run offsets on the main API: `cloud_cover_previous_day1` …
  `_previous_day7` returned alongside `cloud_cover` (*verified live*).
  Documentation: `_previous_day1` is the value predicted 24 h before valid
  time, up to day 7; most models archived from January 2024, GFS 2 m
  temperature from March 2021.
- Single Runs, above.

Note what this means against issue #5's storage constraint: **the aggregator
holds the forecast-vintage archive this deployment has explicitly decided not
to keep.** Vintage retention is out of scope for now, but if it returns, this
is where it is cheapest.

---

## 5. Per-model findings

Measured with one call requesting `cloud_cover` for eleven models at once
(HTTP 200, *verified live*, 2026-09-02 ~06:20 UTC), plus `meta.json` per
domain. "Run lag" is `last_run_availability_time − last_run_initialisation_time`
at the instant probed — one sample, not a distribution.

### Reachable only through an aggregator

| Model | Producer | Intermediary | Latest run seen | Run lag | Cloud over St. John's | Live? |
| --- | --- | --- | --- | --- | --- | --- |
| **JMA GSM** `jma_gsm` | Japan Meteorological Agency | Open-Meteo | 2026-09-01 18z | 9.54 h | 62, 62, 63 % | **yes** |
| **UKMO global deterministic 10 km** `ukmo_global_deterministic_10km` | UK Met Office | Open-Meteo | 2026-09-01 18z | 7.43 h | 20, 19, 36 % | **yes** |
| **Météo-France ARPEGE world 0.25°** `meteofrance_arpege_world025` | Météo-France | Open-Meteo | 2026-09-02 00z | 4.20 h | 25, 31, 19 % | **yes** |
| **CMA GRAPES global** `cma_grapes_global` | China Meteorological Administration | Open-Meteo | 2026-09-02 00z | 6.35 h | 0, 0, 0 % | **yes**, but see below |
| **KMA GDPS** `kma_gdps` | Korea Meteorological Administration | Open-Meteo | **2026-03-31 18z** | 3 560 h | **all null** | **no — dead** |
| **ICON-EPS (40 members)** via `icon_seamless` | Deutscher Wetterdienst | Open-Meteo | 2026-09-02 00z (`dwd_icon_eps`) | 3.86 h | 40 members, all populated; member 01 gave 69, 72, 88, 100 % | **yes** — but §6 makes it native |
| **GraphCast 0.25°** `gfs_graphcast025` | NOAA/DeepMind | Open-Meteo | no run fields in `meta.json` | — | **all null** | **no** |
| **WeatherNext 2 ensemble (64 members)** `google_weathernext2_ensemble` | Google DeepMind | Open-Meteo | no run fields in `meta.json` | — | 128 variables returned, member 01 total cloud 56, 54, 55, 58, 60 % and low cloud 62, 61, 62, 65, 68 % | **yes — and this is the trap** |
| **MOSMIX point forecast, station 71801** | Deutscher Wetterdienst | Bright Sky | n/a (station product) | — | 64 % at 04:00Z, with **visibility** 23 800 m | **yes** |

Notes on individual rows.

- **KMA GDPS is dead over this box and would fail silently.**
  `last_run_initialisation_time` is 2026-03-31 18z and `data_end_time` is
  2026-04-04 — five months stale — which is why every hour came back null.
  Nulls are correct behaviour, but nothing in the response says "this domain
  stopped updating in April". Same shape as the SWPC stale-but-HTTP-200 finding
  in issue #8.
- **CMA GRAPES returned exactly 0 % for all 24 hours.** A flat zero over a
  September night on the Avalon is not credible beside ICON's 62 to 67 % and
  GEM's 56 %. Either the field is not what it is labelled or the domain is
  degraded. Unresolved; do not use without decoding what the zero is.
- **GraphCast is null over the box** despite the model name resolving, and its
  `meta.json` carries no run fields at all. Not usable.
- **AIFS single** also resolved through Open-Meteo (`ecmwf_aifs025_single`,
  values returned, 5.74 h lag) — listed only to say **do not**: it is already
  native via `ecmwf_opendata.py`.

### The WeatherNext 2 cloud trap — the sharpest result in this ticket

`config.yaml` and the registry both record, verified from the Earth Engine
band list on 2026-09-02, that **WeatherNext 2 publishes no cloud variable of
any kind**. Open-Meteo nonetheless serves total, low, mid and high cloud cover
for it, per member, for 64 members — *verified live* here.

Open-Meteo documents exactly how, and deserves credit for the clarity
(WeatherNext API docs, read 2026-09-02):

> Low cloud cover — Derived from relative humidity at 1000, 925 and 850 hPa.
> Mid cloud cover — Derived from relative humidity at 700, 600, 500 and 400 hPa.
> High cloud cover — Derived from relative humidity at 300, 250, 200, 150, 100
> and 50 hPa. Total cloud cover — Calculated by combining the derived low, mid
> and high cloud layers. … **Cloud cover is an estimate based on the vertical
> humidity profile. It is not a native cloud fraction forecast from
> WeatherNext.**

And the relative humidity is itself derived: WeatherNext publishes specific
humidity, which Open-Meteo converts. So a WeatherNext cloud value is two
derivations deep and **zero producer values deep**.

This is exactly the case §1.2 anticipates. It is **not `reprocessed`** — there
is no producer cloud value that an intermediary transformed. It is not
`derived-here` — this deployment did not compute it and cannot list its inputs
as retrieved values. Under `config.yaml`'s own note it is "that reseller's
humidity closure", a **generated** value, and generated values are display-only
under a carve-out that covers interpolation between retrieved frames, not
importing a stranger's diagnostic. **Refuse it.** The licence is a second,
independent bar: every forward-looking WeatherNext value sits in the revocable
GDM Real-Time Experimental Data tier, and Open-Meteo proxying it does not move
it into CC BY.

---

## 6. The native path for ICON global — the aggregator is not needed

Four things were established live on `opendata.dwd.de` on 2026-09-02.

1. **There is no regular-lat-lon variant of ICON global.** The `00/clct/`
   listing holds **113 files, every one `icon_global_icosahedral_*`, and zero
   matches for `regular-lat-lon`** (*verified live*, counted). By contrast
   `icon-eu/grib/00/clct/` serves
   `icon-eu_europe_regular-lat-lon_single-level_*` — DWD publishes the regular
   grid for the **European** model only, which does not reach Newfoundland.
   The `dwd_icon.py` docstring's hope of an `icon_global_lat-lon_*` variant is
   therefore **settled: it does not exist.** The adapter comment should say so.
2. **The CDO weight archives exist and are small.** `opendata.dwd.de/weather/lib/cdo/`
   (*verified live*) holds `ICON_GLOBAL2WORLD_0125_EASY.tar.bz2`
   (**50 677 442 B**, ~48 MB) and `ICON_GLOBAL2WORLD_025_EASY.tar.bz2`
   (**43 938 502 B**, ~42 MB), alongside `ICON_GLOBAL2EUAU_*` and
   `ICON_D2_002_EASY`. These are one-time downloads, static between grid
   changes. At 0.125° the evidence box is 97 × 45 cells (from the horizon
   matrix). The full R03B07 grid description
   `icon_grid_0026_R03B07_G.nc.bz2` is also there but is **937 689 167 B**
   (~894 MB) — do not fetch it if the weights suffice.
3. **There is a lighter path than CDO: DWD ships the mesh coordinates as
   GRIB.** `00/clat/` and `00/clon/` serve
   `icon_global_icosahedral_time-invariant_2026090200_CLAT.grib2.bz2`
   (**1 264 334 B**, ~1.2 MB) — cell-centre latitude and longitude for every
   mesh cell, in the same GRIB2 the stack already reads with ecCodes/cfgrib
   (*verified live*). With CLAT/CLON in hand, a **nearest-cell point sample**
   at a coordinate needs no regrid, no CDO and no invented interpolation: pick
   the cell whose centre is nearest, and record its centre in provenance. That
   is a `retrieved` value at a named cell — the strongest class available —
   and it is the honest answer for `/point`. A rendered grid layer still needs
   the weights from (2), and that regrid would be **`derived-here`**, with DWD's
   own published weights as the cited method and the input listed.
4. **Per-field cost is modest.** One lead of global CLCT,
   `icon_global_icosahedral_single-level_2026090200_012_CLCT.grib2.bz2`, is
   **4 123 300 B** (~3.9 MB) compressed for the whole globe (*verified live*).
   DWD publishes no server-side subsetting, so that is the wire cost per field
   per lead to keep a 97 × 45 box — the same shape of waste already measured
   for GEFS and ECMWF in issue #13, and an order of magnitude cheaper than
   either.

**ICON-EPS is reachable natively too, and is expensive.**
`icon-eps/grib/00/clct/` serves `icon-eps_global_icosahedral_single-level_*`
(*verified live*, the 00 run enumerated; other cycles not probed here). It has
the **same icosahedral geometry and the same CLAT/CLON fix**. One lead of
`clct` across all members is **43 261 662 B** (~41 MB) compressed — ten times
an ICON deterministic field, because all 40 members are in one global file with
no subsetting. Open-Meteo's `icon_seamless` returned the same 40 members
already interpolated and downscaled for a few kilobytes. That is a real
cost/class trade: **41 MB for `retrieved`, or kilobytes for `reprocessed` that
can never be a display primary or a derivation input.** For a map whose subject
is cloud, the class wins.

---

## 7. Recommendations

**Admit as `reprocessed`, named honestly, non-primary:**

- **JMA GSM**, **UKMO global deterministic 10 km**, **Météo-France ARPEGE
  world 0.25°** via Open-Meteo. Producer = the national service; intermediary =
  Open-Meteo; transformations = all six in §4, plus the run-time caveat. These
  three are the only genuinely new information in this ticket: three
  independent global models over the box that this stack has no other route
  to. They add spread, not detail. **UKMO carries a CC BY-SA upstream licence
  and must not be stored until that share-alike question is answered.**
- **MOSMIX station 71801 via Bright Sky.** The best value-per-declaration here.
  It is the only new source in this ticket that carries **visibility** and
  **dew point** at a St. John's point out to ten days, and issue #9 found the
  in-situ fog evidence gap is the hardest one in the box. Producer = DWD;
  intermediary = Bright Sky; transformations = KMZ parse and nearest-station
  selection, the latter inspectable per response. Being a station point rather
  than a grid, it does not compete with HRDPS for the map surface, which makes
  the "never the display primary" fence cheap to honour.

**Refuse:**

- **WeatherNext 2 cloud via Open-Meteo.** §5. No producer value exists; the
  class does not. Licence-blocked independently.
- **KMA GDPS.** Five months stale, all-null over the box, no staleness signal
  in the response.
- **GraphCast 0.25°.** All-null over the box, no run metadata.
- **CMA GRAPES.** Flat 0 % cloud for 24 hours is not a usable field until
  someone explains it.
- **Meteosource** and every commercial reseller. Producer unnameable, so the
  `reprocessed` declaration cannot be written truthfully.

**Do not route through any aggregator:** HRDPS, RDPS, GDPS, REPS, GEPS, GFS,
GEFS, ECMWF IFS, IFS ENS, AIFS single, AIFS-ENS. All native today (§2).

**ICON global and ICON-EPS: fix the native adapter, do not take the
aggregator.** §6. The CLAT/CLON nearest-cell sample turns
`dwd-icon-global` from a permanently-`implementing` record into `retrieved`
evidence, and ICON is the earliest-published global model over this box
(T+3 h 32 m to T+3 h 48 m by two independent measurements). Going through
Open-Meteo instead would take the fastest global feed available and
permanently bar it from being the display primary — a bad trade made to avoid
about 1.2 MB of coordinate file.

**If any Open-Meteo source is admitted, three client rules follow:**

1. Read `data/<domain>/static/meta.json` beside every data call and store
   `last_run_initialisation_time` as the run reference; a value with no run
   stamp is not admissible.
2. Send `&elevation=nan` and an explicit `cell_selection` on every request, so
   the stored value is the model grid cell and not Open-Meteo's DEM
   downscaling of it. Record both settings in provenance.
3. Prefer `single-runs-api` with an explicit `&run=` where the run is known, so
   provenance is asserted by the caller rather than inferred.
4. Budget against 10 000 calls/day and re-read the non-commercial term before
   this experiment ever grows advertising or a subscription.

---

## 8. What this leaves open

- **The UKMO CC BY-SA share-alike question.** Whether storing and displaying a
  UKMO value alongside other sources triggers a share-alike obligation on
  anything of this deployment's was not researched. It blocks UKMO admission.
- **Open-Meteo's regrid method for ICON.** The 0.125° output spacing was
  inferred from two returned cell centres; the interpolation used to get there
  (nearest, bilinear, conservative) is not stated per model, so a
  `reprocessed` record can name *that a regrid happened* but not *which*.
- **CMA GRAPES's flat zero cloud.** Unexplained.
- **MOSMIX element coverage at 71801.** Several fields were null in the one
  record inspected. Which elements DWD actually issues for this station, and
  how often, is unmeasured — and `relative_humidity` being null while
  `dew_point` is present matters for a fog map.
- **MOSMIX update cadence and latency.** Not measured; DWD documents MOSMIX
  cycles but no probe was made here.
- **ICON-EPS cycle set.** Only the 00 run directory was enumerated.
- **Cost of applying the DWD weights to the box.** The archives were sized
  (~48 MB and ~42 MB) but never unpacked or run, so the per-field regrid cost
  is still the open question the horizon matrix left.
- **NBM domain grids.** Coverage was reasoned from the published domain set,
  not decoded from a GRIB.
- **Bright Sky rate limits.** None documented; none measured.

Nothing was computed, published or promoted. No registry state changed.
