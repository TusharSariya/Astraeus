# Free Open-Meteo access, provenance and request budgets

Research date and anonymous samples: **2026-09-05 UTC**. Resolves investigation
[#72](https://github.com/TusharSariya/Astraeus/issues/72) in map
[#70](https://github.com/TusharSariya/Astraeus/issues/70).

**Spec-Impact: none**: evidence and implementation recommendations only; no code,
provider admission, scientific rule, deployment or normative status changes.
All candidate integrations remain `operational: false`.

## Finding

Open-Meteo supplies several missing sources without a paid subscription for a
qualifying noncommercial experiment. Anonymous responses here demonstrate point
retrieval, not operational readiness, native fidelity, or permission to publish
any derivative product. WeatherNext available through this route is **WeatherNext
2**, not WeatherNext 3. Provider delivery routes must remain separate from the
producer identity, and derived products need separate scientific authority.

## Free service and licences are separate

The free hosted API is limited to noncommercial uses; examples include private
apps without advertising/subscriptions, personal automation and public research.
Commercial products, promotion and undisclosed commercial research are excluded.
Free access supplies no accuracy, completeness or uptime guarantee. These are
service conditions, not a restriction inferred from the data's Creative Commons
label. [Official terms](https://open-meteo.com/en/terms).

The pricing table includes weather, ensemble, marine, air quality, satellite,
archive, single-run, seasonal, climate, elevation, geocoding and flood products in
Free/Open-Access. The paid Standard plan's omission of some products does **not**
mean those products require payment for noncommercial evaluation. Published
ceilings are 600 weighted calls/minute, 5,000/hour, 10,000/day and 300,000/month;
terms say *less than* the short-period limits. Maintain headroom even where monthly
metering is not enforced. [Pricing](https://open-meteo.com/en/pricing).

API data attribution is CC BY 4.0, with an adjacent Open-Meteo link and disclosure
of modifications. Upstream entries are not homogeneous: **UKMO is listed CC
BY-SA**, while ECCC, NOAA, Météo-France and Copernicus have individual linked
licences. Preserve upstream attribution and licence references per source; do
not flatten the catalogue to a single CC BY label. The server's AGPL licence is a
third, software-specific matter. [Licence catalogue](https://open-meteo.com/en/licence).

The user's Google approval email distinguishes historical CC BY 4.0 from GDM
real-time experimental terms. It does not establish which Open-Meteo redistribution
rights apply to this particular derivative stream. Open-Meteo's WeatherNext page
does not settle that issue. Retain a separate owner decision for real-time
redistribution; the email is not evidence of WeatherNext 3 availability here.

## Endpoint and candidate matrix

Hostnames below use HTTPS. All rows are documented Free/Open-Access, subject to
the common budget above; no separate per-endpoint quota entitlement was found.
Documentation availability is distinguished from the samples below.

| Route | Missing-source pathway and identity | Constraints and provenance |
|---|---|---|
| `api.open-meteo.com/v1/forecast` | Named ECMWF IFS/AIFS Single, DWD ICON, NOAA GFS/NAM/AIGFS/HGEFS mean, ECCC GEM, JMA GSM, CMA GRAPES, UKMO Global, ARPEGE World, BOM ACCESS | Point series; model-dependent coverage/fields. `best_match` and seamless aliases may combine models or resolutions. Use named models for evidence. Regional UK/Europe/Asia products do not imply Avalon coverage. [Forecast docs](https://open-meteo.com/en/docs) |
| `ensemble-api.open-meteo.com/v1/ensemble` | Global ICON-EPS (40), GEFS (31), AIGEFS (31), IFS/AIFS (51), GEM (21), MOGREPS-G (18), WeatherNext 2 (64) | Counts are documented, not all sampled. Regional native-grid ECMWF ensembles cover Europe. Default hourly output is interpolated; member archives have only three past days. Per-member completeness matters. [Ensemble docs](https://open-meteo.com/en/docs/ensemble-api) |
| `api.open-meteo.com/v1/forecast` via ensemble-mean selection | Means/spreads, including HGEFS and WeatherNext 2 | Potentially much smaller than members, with longer retention. A mean/spread is a derived summary, not a complete ensemble or new independent source. [Mean API](https://open-meteo.com/en/docs/ensemble-mean-api) |
| `marine-api.open-meteo.com/v1/marine` | MFWAM, SMOC currents/tides/SST, ECMWF WAM, GFS Wave, GWAM, ERA5-Ocean | Global wave forecasts differ in cadence/horizon; MFWAM is 3-hourly, SMOC currents hourly and SST 6-hourly. ERA5-Ocean is delayed reanalysis. Sea-level datum and coastal cell must be retained; not IWLS station observations or CIOPS/RIOPS. [Marine docs](https://open-meteo.com/en/docs/marine-weather-api) |
| `air-quality-api.open-meteo.com/v1/air-quality` | CAMS global AOD, PM, gases; global greenhouse gases; CAMS Europe forecasts/reanalysis | Pin `domains=cams_global` for Avalon composition. Global atmospheric composition is 0.4°, three-hourly; Europe is separate, not coupled. Pollen is not a Newfoundland pathway. Model concentrations/AOD are not AERONET, VIIRS or MAIAC observations. [Air-quality docs](https://open-meteo.com/en/docs/air-quality-api) |
| `satellite-api.open-meteo.com/v1/archive` | MTG, MSG/IODC, SARAH3, Himawari radiation | GOES-East/West explicitly not yet available; no demonstrated Avalon satellite-radiation replacement. Scan-time correction and backward averaging occur; Himawari direct/diffuse radiation is derived. Native time option avoids default hourly resampling. [Satellite docs](https://open-meteo.com/en/docs/satellite-radiation-api) |
| `archive-api.open-meteo.com/v1/archive` | ERA5, ERA5-Land, ERA5 ensemble, IFS and regional CERRA | Select exact dataset; reanalysis differs from a forecast issued at a past date. Dates/fields vary by model. Useful bounded historical/site evidence, not an observational ground-truth claim. [Historical weather](https://open-meteo.com/en/docs/historical-weather-api) |
| `historical-forecast-api.open-meteo.com/v1/forecast` | Historical rolling forecast series | Valid-date history is not an immutable forecast vintage. [Historical forecast](https://open-meteo.com/en/docs/historical-forecast-api) |
| `previous-runs-api.open-meteo.com/v1/forecast` | Fixed previous-day lead offsets | Offsets are not a single shared initialization. Preserve offset and valid time. [Previous runs](https://open-meteo.com/en/docs/previous-runs-api) |
| `single-runs-api.open-meteo.com/v1/forecast` | Exact named initialization using `run=` | Strongest point API for reproducible run selection. Most models from 2026-04-02; IFS HRES 9 km from March 2024. Still intermediary processing. [Single runs](https://open-meteo.com/en/docs/single-runs-api) |
| `seasonal-api.open-meteo.com/v1/seasonal` | EC46 and SEAS5, members/means/spreads | 51 members; 46-day and seven-month products; individual members retained one month. Additional no-charge context pathway, not short-term precision. [Seasonal docs](https://open-meteo.com/en/docs/seasonal-forecast-api) |
| `climate-api.open-meteo.com/v1/climate` | HighResMIP climate projections | Daily products; ERA5-Land bias correction/downscaling defaults on. Record `disable_bias_correction`; projections are not future weather forecasts. [Climate docs](https://open-meteo.com/en/docs/climate-api) |
| `flood-api.open-meteo.com/v1/flood` | GloFAS river discharge | Hydrological context; not road-flood safety authority. [Flood docs](https://open-meteo.com/en/docs/flood-api) |
| `api.open-meteo.com/v1/elevation`; `geocoding-api.open-meteo.com/v1/search` | Copernicus DEM elevation; GeoNames place lookup | Site metadata candidates, not LiDAR horizons or authoritative access records. [Elevation](https://open-meteo.com/en/docs/elevation-api), [Geocoding](https://open-meteo.com/en/docs/geocoding-api) |

Open-Meteo is not a demonstrated route for Earth-2 checkpoints/inference, RAP,
NUCAPS, VIIRS cloud imagery, GOES ABI products, NL511 cameras, PWS/aviation reports,
SmartAtlantic observations, geomagnetic/solar products, night lights or celestial
catalogues. These need their own source investigations. Equivalent weather
variables from another model do not implement those sources.

## Provenance controls and correction to previous research

The older [aggregator note](aggregator-models.md) correctly identified anonymous
UKMO, AIFS and WeatherNext 2 access, upstream share-alike terms, and cloud
derivation. Preserve its restricted/research admissions until the owner resolves
them; access is not newly blocked by payment. The [endpoint note](open-meteo-endpoints.md)
should be read with the current marine attribution table, which explicitly links
SMOC currents/tides and SST to Copernicus Marine products.

The old suggestion to stamp forecast values using adjacent `meta.json` is too
strong. A domain's latest initialization is **not** proof that every sample in a
rolling, stitched time series belongs to that run. Even unchanged metadata around
a retrieval does not establish per-value lineage. Prefer Single Runs where
supported; otherwise retain metadata as domain context and mark value-level run
identity unknown. `generationtime_ms` is response computation time, not model age.

A candidate artifact should capture producer, intermediary, exact request and
model selector, requested and returned coordinates/elevation, cell-selection
policy, units, valid/accumulation intervals, retrieval time, content hash,
initialization evidence and its certainty, member IDs, source licences and
transformation version. Default elevation correction uses a 90 m DEM;
`elevation=nan` disables that correction. `cell_selection=nearest` controls cell
choice independently. Regridding, temporal interpolation, accumulation
redistribution, unit conversion and derived variables remain separate processes.
[Forecast documentation](https://open-meteo.com/en/docs).

WeatherNext uses selector `google_weathernext2_ensemble`. Its six-hour native
output can be requested with `temporal_resolution=native`. Cloud layers are
estimated from pressure-level relative humidity, itself derived from specific
humidity; total cloud combines those layers. Rain/snow/weather codes are also
derived. Native sampling does not make these native producer cloud fractions.
[WeatherNext API](https://open-meteo.com/en/docs/google-weathernext-api).

## Bounded anonymous samples

Seven HTTP requests succeeded with status 200 on 2026-09-05. Each weather call
used `latitude=47.56&longitude=-52.71&forecast_days=1&timezone=GMT`; model selectors
below are exact. These summaries are inline evidence, not stored live artifacts.

| Endpoint above; additional parameters | Observed output |
|---|---|
| Forecast: `models=ukmo_global_deterministic_10km&hourly=temperature_2m,cloud_cover&elevation=nan&cell_selection=nearest` | First temperature 15.3 °C, cloud 94%; returned cell 47.53125, -52.734375, elevation 0 m |
| Forecast: `models=ecmwf_aifs025_single&hourly=temperature_2m&elevation=nan&cell_selection=nearest` | First four temperatures 14.0, 13.6, 13.3, 13.0 °C |
| Ensemble: `models=google_weathernext2_ensemble&hourly=temperature_2m,cloud_cover&temporal_resolution=native` | 128 series, 64 per variable; times 00/06/12/18 UTC; base temperature 15.1, 12.3, 15.4, 15.1 °C |
| Air quality: `domains=cams_global&hourly=aerosol_optical_depth,pm2_5` | First AOD 0.16; PM2.5 5.7 µg/m³ |
| Marine: `models=meteofrance_wave&hourly=wave_height` | First wave height 0.58 m |
| Single Runs: `models=icon_global&hourly=cloud_cover&run=2026-09-04T00:00` | Returned 2026-09-04 00–23 UTC; first cloud 36% |
| `https://api.open-meteo.com/data/ukmo_global_deterministic_10km/static/meta.json` | Initialization 2026-09-04 18:00 UTC; availability 2026-09-05 01:25:16 UTC; domain timestep 3600 seconds |

All six weather bodies lacked a run-reference field. The explicitly requested
ICON initialization is the only exact requested run in these samples; the UKMO
metadata is contextual. Other selectors were documentation-reviewed, not probed.

Reproduce any row with `curl -sS --max-time 25 -w '\n%{http_code}' 'https://HOST/PATH?COMMON&ADDITIONAL'`, substituting the literal endpoint and parameters
above; changing dates or retrieval time changes live results. No accounts,
subscriptions, credentials or billing operations were used.

## Weighted calls and conservative experiment budget

Pinned upstream source: commit
[`6c45053fb1ef0c049de931292a0f5cb35f14c0ba`](https://github.com/open-meteo/open-meteo/commit/6c45053fb1ef0c049de931292a0f5cb35f14c0ba).
The forecast controller multiplies selected weather variables by ensemble-member
counts across selected models. Thus a two-variable, 64-member request represents
128 variable slots, not two.
[Controller](https://github.com/open-meteo/open-meteo/blob/6c45053fb1ef0c049de931292a0f5cb35f14c0ba/Sources/App/Controllers/ForecastapiController.swift#L309).

The result writer computes, per location,
`max(1, V/10, (V/10)*(days/14))`, then sums locations. Example: 128 slots for one
location and one day costs 12.8 weighted calls; 15 variables over 28 days cost 3.
Shorter periods do not remove the variable/member multiplier. Seasonal weighting
has special adjustments; use its documented calculator, not this unmodified
formula. Public source is implementation evidence, not proof of hosted deployment
configuration.
[Weight calculation](https://github.com/open-meteo/open-meteo/blob/6c45053fb1ef0c049de931292a0f5cb35f14c0ba/Sources/App/Helper/Writer/ForecastApiResult.swift#L238).

Proposed local ceiling: **40 weighted/minute, 400/hour, 2,000/day and
50,000/month across all Open-Meteo routes**, one HTTP request at a time. Count
metadata and failed/retried requests conservatively too. Do not rotate IPs or
hosts to evade ceilings. Published server code maintains per-IP weighted counters
and returns 429 for limits/concurrency; actual production configuration may
vary. Stop a throttled batch and retry only after bounded backoff.
[Rate limiter](https://github.com/open-meteo/open-meteo/blob/6c45053fb1ef0c049de931292a0f5cb35f14c0ba/Sources/App/Helper/Vapor/RateLimiter.swift).

Illustrative one-location daily allocation: 10 deterministic models × 4 cycles
× 1 call = 40; four ensemble models × 4 cycles × 2 variables × 64 members / 10
= 204.8 (conservative 64-member bound); four marine/AQ products × 4 = 16;
metadata reserve 200; archive/testing reserve 400. Total **860.8/day**, approximately
26,685/month at 31 days. Ten locations would already make the ensemble portion
2,048/day: spatial batching is not free. Cache by request/run and expand only
inside the local budget. No workload was deployed.

## Decisions before implementation

Owner specification decisions remain for source admissions, UKMO share-alike
handling, WeatherNext real-time downstream rights, derived cloud acceptability,
run-unknown records, interpolation semantics, and archive retention/storage
allocation. A regional product's absent/null coverage stays missing; an
intermediary alias cannot silently become another source. Implementations must
map accepted contracts and test fixture decoding, live artifact capture, API
readback, member completeness, null/stale handling and provenance before claiming
readiness. This investigation settles access routes and identifies those gates;
it does not grant approval or mark sources operational.

Verification: `uv run --project tools/specs python tools/specs/specctl.py validate`.
