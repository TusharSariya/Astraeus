# UV, pollen, radiation and road-state sources for running

Non-normative research, 2026-09-02. No registry state changed, nothing published
to the store. Evidence-class vocabulary is `CONTEXT.md` at the repository root:
retrieved, reprocessed, derived-here, generated-display, uncalibrated
observation. Evidence box is 45.0 to 50.5 N, 58.0 to 46.0 W.

Reuses without repeating: the WCS request shape and native `SCALESIZE` from
[`geomet-wcs-inventory.md`](geomet-wcs-inventory.md) (branch
`research/geomet-wcs-inventory`), and the dated WXO-DD Datamart path plus RAQDPS
placement from [`transparency-seeing-sources.md`](transparency-seeing-sources.md)
(branch `research/transparency-seeing-sources`). NL 511 endpoint list is prior
work in [`../newfoundland-operational-data-improvements.md`](../newfoundland-operational-data-improvements.md).

Probe window 2026-09-02 05:40 to 06:20 Z. GeoMet service version at probe time:
GeoMet-Weather 2.40.3.

## Per source

### Ultraviolet

| Field | Class | Endpoint | Cadence | Latency | Licence | Live |
| --- | --- | --- | --- | --- | --- | --- |
| HRDPS UV index, all sky (`HRDPS.CONTINENTAL_IUVA`) and clear sky (`_IUVC`) | retrieved | GeoMet WMS/WCS, `https://geo.weather.gc.ca/geomet` | hourly steps, 4 runs/day, `reference_time` 00/06/12/18Z | run available at probe time was 00Z, time axis `2026-09-02T00Z/2026-09-04T00Z/PT1H` (48 h) | Open Government Licence – Canada | yes, WCS 200, 526 366 B at native `SCALESIZE=long(534),lat(245)` |
| HRDPS daily maximum UV index (`_UVAX_00Z`…`_18Z`, clear sky `_UVCX_*`) | retrieved | same | PT24H steps, per run | 00Z…18Z variants each carry one `reference_time` | OGL – Canada | not individually probed; same collection as `_IUVA` |
| RDPS UV index (`RDPS_10km_UVIndex`, `-ClearSky`, `-Max24h_00Z`…`_18Z`) | retrieved | same | hourly, `2026-09-02T00Z/2026-09-05T12Z/PT1H` (84 h) | 6-hourly runs | OGL – Canada | yes, WCS 200, 526 366 B |
| GDPS UV index (`GDPS_15km_UVIndex`, `-ClearSky`, `-Max24h`) | retrieved | same | enumerated time list, hourly early then 3-hourly; 12-hourly runs | 12-hourly runs | OGL – Canada | capabilities only |
| HRDPS UV index on Datamart | retrieved | `https://dd.weather.gc.ca/YYYYMMDD/WXO-DD/model_hrdps/continental/2.5km/HH/PPP/YYYYMMDDTHHZ_MSC_HRDPS_UVIndex_Sfc_RLatLon0.0225_PT###H.grib2` (and `_UVIndexClearSky_`) | per lead hour, 4 runs/day | file for 00Z run, 012 h present at 05:50 Z | OGL – Canada | yes, HTTP 200, 709 815 B for the whole continental grid — GeoMet subsets, Datamart does not |
| St. John's point UV index with category | retrieved | `https://dd.weather.gc.ca/YYYYMMDD/WXO-DD/citypage_weather/NL/HH/*_MSC_CitypageWeather_s0000280_en.xml` | roughly hourly, city-page issue cycle | file at 00:01 Z read at 06:15 Z | OGL – Canada | yes, `<uv category="moderate"><index>5</index>` |

`GEPS.DIAG.*_UVMX.*` and `REPS.DIAG.*_UVMX.*` are **not** UV. Their titles read
"Wind speed at 10 m above ground - maximum over 12-hour [m/s]"; `UV` is the GEM
wind modulus and the `ERGE20`…`ERGE118` thresholds are km/h. No ensemble UV
index exists on GeoMet.

### Shortwave radiation for wet-bulb globe temperature

WBGT outdoors needs a globe temperature, which needs **instantaneous** global
and ideally direct-beam irradiance in W/m².

| Model | What is published | Class | Instantaneous? |
| --- | --- | --- | --- |
| HRDPS 2.5 km | `HRDPS.CONTINENTAL_N4` downward shortwave **accumulated** [J/m²]; `_AS` net shortwave accumulated; `_AD`/`_AI` longwave accumulated; `_EV`/`_EI` are top-of-atmosphere only | retrieved | no |
| RDPS 10 km | `RDPS_10km_DownwardShortwaveRadiationFlux-Accum` [J/m²], Net/Upward shortwave, downward longwave; hourly `2026-09-02T00Z/2026-09-05T12Z/PT1H` | retrieved | no |
| GDPS 15 km | `GDPS_15km_DownwardShortwaveRadiationFlux-Accum` and the same accumulated family | retrieved | no |
| CAPS 3 km | `CAPS_3km_DownwardShortwaveRadiationFlux-Accum` and family | retrieved | no |
| GFS 0.25 deg | `DSWRF:surface:0-6 hour ave fcst` (and `0-3 hour ave` at f003), `DLWRF`, `USWRF`; `SUNSD:surface` sunshine duration | retrieved | no — period **average**, not instantaneous |

Direct beam and diffuse are absent everywhere probed. A search of every GeoMet
layer title for "direct", "diffuse" or "beam" solar returns nothing; GFS
`pgrb2.0p25` and `pgrb2b.0p25` `.idx` files carry no `VBDSF`/`VDDSF` record at
0.25 deg. So:

- **Global horizontal irradiance is derived-here.** Differencing consecutive
  hourly `J/m²` accumulations and dividing by 3600 s gives a mean W/m² over the
  hour, not an instantaneous value. Method and inputs must be cited; the
  hour-mean assumption is the whole error budget under broken cloud.
- **Direct-beam irradiance is blocked.** Splitting global into beam and diffuse
  needs a separation model (Erbs, DIRINT, DISC) on top of the derived hourly
  mean — a derived-here value stacked on a derived-here value, and none of the
  producers publish the split for verification.
- Therefore **WBGT itself is derived-here at best**, with an explicit
  uncertainty note, and is not producer output from any source in the box.

Confirmed instead as producer output, so a running profile need not derive them:

| Field | Class | Layer | Cadence | Licence | Live |
| --- | --- | --- | --- | --- | --- |
| Humidex at 2 m | retrieved | `HRDPS.CONTINENTAL_HMX` (hourly to 48 h, `reference_time` PT6H), `RDPS_10km_Humidex`, `GDPS_15km_Humidex` | hourly / 3-hourly | OGL – Canada | yes, WCS 200, 524 230 B |
| Wind chill at surface | retrieved | `HRDPS.CONTINENTAL_RE`, `RDPS_10km_WindChill`, `GDPS_15km_WindChill` | hourly / 3-hourly | OGL – Canada | yes, WCS 200, 524 230 B |

Sizes are one field, one time step, at the native box `SCALESIZE`; multiply by
lead count before any admission decision.

### Pollen

| Source | Class if used | Endpoint | Cadence | Licence | Live |
| --- | --- | --- | --- | --- | --- |
| Aerobiology Research Laboratories | would be reprocessed (third-party lab counts and forecast) | no public API; city page `https://aerobiology.ca/st-johns-newfoundland/` is a subscription sign-up, not data | daily during season | **all rights reserved**; data "available for sale in its raw form", partners licensed individually | page 200, no data payload |
| The Weather Network pollen, St. John's | would be reprocessed | `https://www.theweathernetwork.com/en/city/ca/newfoundland-and-labrador/st-johns/pollen` | daily, three-day outlook | "Forecasts Provided by Aerobiology Research Laboratories under license", © 2026 Pelmorex Corp.; no open licence | HTML only, no feed |
| Open-Meteo air-quality pollen (CAMS European) | would be reprocessed | `https://air-quality-api.open-meteo.com/v1/air-quality?...&hourly=alder_pollen,grass_pollen,ragweed_pollen` | hourly | CC BY 4.0 (Open-Meteo), CAMS upstream | yes but **empty over the box**: 0/24 non-null for alder, grass and ragweed at 47.56 N, 52.71 W — the CAMS pollen domain is Europe only |
| ECCC | — | none | — | — | ECCC publishes no pollen product |

**Pollen is blocked.** The only Canadian observing network is a single
commercial laboratory; every route to its numbers is a licence negotiation, and
the one openly licensed pollen API returns nulls at this longitude. Scraping The
Weather Network would be redistribution of licensed third-party data and is not
a candidate.

### Road and trail state

| Source | Class | Endpoint | Cadence | Licence / terms | Live |
| --- | --- | --- | --- | --- | --- |
| NL 511 winter roads | would be retrieved | `https://511nl.ca/api/v3/get/winterroads` | provincial reporting cycle | developer key required; documented throttle "Throttling is enabled. Ten calls every 60 seconds"; site terms are an "AS IS" liability release with **no data-reuse, attribution or redistribution clause at all** | probed keyless: HTTP 200 body `<Error><Message>Invalid Key</Message></Error>` |
| NL 511 cameras, events, alerts, ferry terminals, wind warnings | would be retrieved | `https://511nl.ca/api/v2/get/{cameras,event,alerts,ferryterminals,windwarnings}` | event-driven | same | same gate; no key requested |
| NL 511 raw RWIS telemetry | — | none documented at `https://511nl.ca/developers/doc` | — | — | reconfirmed absent; registry `nl-511-rwis` `unavailable` stands |
| City of St. John's road closures, trail closures, plow tracker, sidewalk snow priority | — | interactive viewers linked from `https://www.stjohns.ca/about-st-johns/maps/`; `https://map.stjohns.ca/mapcentre/` returns 200 but `/arcgis/rest/services` and `/server/rest/services` are both IIS 404 | — | no open data portal, no licence statement; `opendata-stjohns.hub.arcgis.com` resolves to an unregistered generic Esri Hub shell | no machine-readable feed found |

Registry `nl-511` stays `credential_required` and the terms are worse than the
registry note implies: there is no licence granting reuse, only a warranty
disclaimer. Any future key request should be paired with a written permission
question, not just a throttle setting.

### Air quality at St. John's

| Source | Class | Endpoint | Cadence | Latency | Licence | Live |
| --- | --- | --- | --- | --- | --- | --- |
| NL provincial near-real-time station data, St. John's NAPS site | uncalibrated observation | `https://www.mae.gov.nl.ca/wrmd/pp_adrs/Data/StJohns_Line.csv` (XML twin at `StJohns_Line.xml`), page `.../template_airmon.asp?station=stjohns` | hourly, rolling 35 days (890 rows at probe) | last row 2026-09-02 01:00 NDT read at 06:16 Z, about 2.75 h | "copyright, Government of Newfoundland and Labrador, all rights reserved"; data flagged **PROVISIONAL**, "has not undergone quality control checks… may be subject to significant change" | yes, 200, 59 224 B |
| National NAPS continuous archive | retrieved | `https://donnees-data.ec.gc.ca/data/air/monitor/national-air-pollution-surveillance-naps-program/Data-Donnees/`, query tool `https://environmental-maps.canada.ca/naps-snpa/` | posted annually, maintenance "as needed" | about a year | Open Government Licence – Canada | catalogue 200; the `Data-Donnees/` index is a JS shell, so a machine path must be pinned per year before use |
| ECCC AQHI observations | retrieved | `https://api.weather.gc.ca/collections/aqhi-observations-realtime/items` | hourly | 2026-08-31T23:00Z item present | OGL – Canada | yes — already registry `eccc-aqhi`; index only, **no PM2.5 or ozone concentration** |
| RAQDPS surface fields | retrieved | GeoMet `RAQDPS.SFC_O3` [mol/mol], `RAQDPS.SFC_PM2.5` [kg/m³], plus `RAQDPS.Sfc_PM2.5-WildfireSmokePlume` | model run cadence | about 3.8 h (prior research) | OGL – Canada | capabilities confirm layers exist |

The provincial CSV is the only PM2.5 and ozone **measurement** inside the box.
It is an uncalibrated observation by `CONTEXT.md`: the publisher itself says it
is provisional and unvalidated. It must never be presented as producer-quality
air quality; the validated version of the same instrument arrives a year later
through NAPS.

## What a running activity profile can be fed today

Producer output, retrievable now, no derivation:

- UV index and clear-sky UV index at 2.5 km hourly to 48 h (HRDPS), 10 km to
  84 h (RDPS), 15 km beyond that (GDPS), plus a St. John's point value with an
  official category in the city-page XML. Daily-maximum UV is published too, so
  a "worst hour of the day" answer needs no maths.
- Humidex and wind chill as ECCC's own diagnostics at 2.5 km hourly. These are
  the two heat and cold indices the producer stands behind, and between them
  they cover most of what a runner in St. John's actually needs.
- AQHI hourly as an index, and modelled surface PM2.5 and ozone from RAQDPS.

Derived-here, allowed on data paths with inputs, method and citation recorded:

- Mean hourly global horizontal irradiance, from differenced accumulated
  shortwave. Honest label: hour-mean W/m², not instantaneous.
- Any WBGT or heat-stress composite. Inputs would be the derived irradiance, a
  beam/diffuse separation model with no local verification, plus HRDPS
  temperature, dew point and wind. Publish it as derived-here with its
  uncertainty, or prefer humidex, which is producer output.
- Route exposure overlays from NL 511 products, once a key exists.

Blocked, and should be recorded as blocked rather than filled in:

- **Pollen.** No open Canadian source at any price short of a commercial licence
  with Aerobiology; the open API's pollen domain does not reach Newfoundland.
- **Instantaneous or direct-beam solar radiation.** Absent from HRDPS, RDPS,
  GDPS, CAPS and GFS alike. Nothing to retrieve, and no way to verify a
  separation model locally.
- **Municipal trail and road closures.** St. John's publishes viewers, not data;
  no REST root answered and no licence exists to rely on.
- **Raw RWIS telemetry.** Still undocumented, unchanged from prior research.
- **Measured PM2.5 and ozone as producer output.** Only the provincial
  provisional feed is timely, and it is an uncalibrated observation.

## Follow-ups worth their own ticket

- Pin a stable machine path and year folder under the NAPS `Data-Donnees`
  directory, since the HTML index is JS-rendered.
- Decide whether an hour-mean irradiance is useful enough to admit at all, given
  that humidex already answers the heat question with producer authority.
- If NL 511 is ever pursued, get written reuse permission; the published terms
  grant none.
