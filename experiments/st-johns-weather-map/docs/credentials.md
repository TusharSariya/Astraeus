# Provider credentials — where to get them, and what each one costs you

Every credential is **optional**. Leave one blank and its source stays
non-active with a stated reason; nothing crashes, no other source is affected,
and no substituted value is ever shown in place of evidence that was not
retrieved. That is the whole point of the design — a missing key produces an
honest absence, not a plausible-looking number.

## How to use them

1. `cp .env.example .env` — `.env` is gitignored and must stay that way.
2. Fill in only the keys you actually want. Blank and whitespace-only values are
   treated as absent, so a placeholder you left empty is never sent to a
   provider as if it were a key.
3. Restart the worker.

Credentials are read in exactly one place, `ingest/secrets.py`, so there is one
thing to audit. They are never written to an artifact, a provenance block, a
log line, a fixture, a commit, or the browser bundle. `secrets.redact()` strips
them from any string before it is logged, which matters because at least one
provider (NL 511) puts the key in the query string, and a URL is exactly what
ends up in an exception message.

**Never** paste a real key into a fixture, a test, an issue, or a chat message.

---

## Read this before enabling anything

Four of these have licence terms that are **unresolved or restrictive**. The
registry marks them `pending` or `restricted` for a reason. Having a key does
not by itself make a source safe to use here, because this experiment caches
artifacts and serves them onward — which is precisely what some of these terms
restrict.

| Source | Licence state | The specific problem |
|---|---|---|
| `noaa-madis` | **restricted** | You are assigned a distribution category. Some contributing mesonets forbid redistribution outright. Records from those must not be served on. |
| `nl-511` | **pending** | Road/event data is likely fine. **Camera image display rights are not cleared** — do not cache or re-serve camera imagery until they are. |
| `purpleair` | **pending** | API terms need reading against this project's caching before enabling. |
| `google-weathernext-2` | **pending** | Requires an approved data request; downstream redistribution terms unknown. Registry policy prohibits use until reviewed. |

`copernicus-cams` and `nasa-earthdata-aerosol` have **verified** licences and
are the two safest to enable.

---

## The keys

### 1. Copernicus ADS — `WEATHER_SECRET_COPERNICUS_ADS_TOKEN`
**Get it:** https://ads.atmosphere.copernicus.eu/how-to-api — free ECMWF/Copernicus
account, then copy your personal access token from your profile page.
**Gives you:** CAMS global atmospheric composition — aerosol optical depth,
extinction, dust, sea salt, black carbon, sulphate, PM1/2.5/10, at surface,
model and pressure levels.
**Licence:** Licence to use Copernicus Products — **verified**. Redistribution
permitted with the required notice: *"Contains modified Copernicus Atmosphere
Monitoring Service information [year]"*.
**Worth it?** Yes. It is the independent atmospheric-composition evidence the
registry wants, and the licence is clean. Keep AOD, extinction and PM as
distinct quantities — they are not interchangeable.

### 2. NASA Earthdata — `WEATHER_SECRET_NASA_EARTHDATA_TOKEN`
**Get it:** register at https://urs.earthdata.nasa.gov/users/new, then generate a
bearer token from your profile.
**Gives you:** MODIS / VIIRS / MAIAC aerosol optical depth, quality flags, cloud
mask, observation geometry, pass time.
**Licence:** NASA Earth Science data policy — **verified**. Open with
attribution; preserve DOI and quality flags.
**Worth it?** Yes, with a caveat: these are polar-orbiting swaths, so Avalon
coverage is pass-dependent. Mark it unavailable outside coverage rather than
carrying a stale value forward. AOD is never PM.

### 3. NOAA MADIS — `WEATHER_SECRET_MADIS_TOKEN`
**Get it:** https://madis-data.ncep.noaa.gov/index.html — request an account;
you are assigned a distribution category.
**Gives you:** quality-controlled surface, radiosonde, profiler and
satellite-wind observations with provider and QC flags.
**Licence:** **restricted** — see the warning above.
**Worth it?** Only after you have read your assigned category. The QC flags are
genuinely valuable, but the redistribution constraints are real and
per-provider, not blanket.

### 4. PurpleAir — `WEATHER_SECRET_PURPLEAIR_API_KEY`
**Get it:** https://develop.purpleair.com/keys
**Gives you:** low-cost PM1/2.5/10 sensors with humidity, temperature and
confidence fields.
**Licence:** **pending review.**
**Worth it?** Marginal here. Low-cost sensors need aggressive QC and distinct
symbology, and sensor density around St. John's should be checked before you
bother. Registry role is explicitly "optional".

### 5. OpenAQ — `WEATHER_SECRET_OPENAQ_API_KEY`
**Get it:** https://explore.openaq.org/register
**Gives you:** aggregated PM2.5, PM10, ozone, NO2, SO2, CO from upstream
agencies, with per-location provenance.
**Licence:** **pending** — OpenAQ's own terms plus each upstream source's.
Provenance must be preserved per location, because the terms vary by source.
**Worth it?** Verify first that OpenAQ actually has stations near St. John's —
if it is only re-serving ECCC AQHI data you already ingest directly, it adds
nothing but a licence question.

### 6. NL 511 — `WEATHER_SECRET_NL511_API_KEY`
**Get it:** https://511nl.ca/developers/doc
**Gives you:** road conditions, cameras, ferry status, events, advisories, and
Wreckhouse wind warnings.
**Rate limit:** **10 calls per 60 seconds** — documented, and low. Budget for it.
**Licence:** **pending**, and camera display rights specifically are not cleared.
**Worth it?** The road-condition and Wreckhouse-wind data is genuinely local and
not available elsewhere. Enable the data endpoints; leave cameras alone until
the display rights question is settled.

### 7. Google WeatherNext 2 — `WEATHER_SECRET_GOOGLE_WEATHERNEXT_TOKEN`
**Get it:** https://developers.google.com/weathernext/guides/access-forecast —
requires a reviewed data request, not a self-serve key.
**Gives you:** ML-model global forecasts.
**Licence:** **pending**; registry policy prohibits use until reviewed.
**Worth it?** Research comparison only. Operational latency, field semantics and
downstream licence all need validating before it could count as evidence.

---

## Sources needing no key at all

Most of this experiment is credential-free by design, including everything on
the critical path: ECCC Datamart and GeoMet (HRDPS, RDPS, GDPS, radar,
lightning, alerts, AQHI), AWC METAR/TAF, NOAA GFS/GEFS on S3, ECMWF open data,
DWD ICON, NOAA GOES on S3, DFO IWLS tides, SmartAtlantic buoys and ECCC SWOB.

Three registry entries need no key because **no authoritative machine endpoint
exists** — `nl-511-rwis`, `municipal-hydrometric` and
`nav-canada-weather-cameras`. They are deliberate tombstones that stop anyone
claiming data the project cannot actually get. Do not "fix" them by pointing at
a scraped page.

---

## Still to wire

`compose.yaml` does not yet pass these variables into the worker container.
That file is being edited concurrently; the `env_file` / `environment` entries
land with that work. Until then the variables are read correctly by
`ingest/secrets.py` in a local run but are not visible inside Compose.
