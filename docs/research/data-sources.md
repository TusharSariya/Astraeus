# Data-source recommendations

Last reviewed: 2026-08-10

## Strategy by forecast horizon

No single source should drive every decision horizon.

| Time before observing | Primary inputs | Supporting inputs | Purpose |
| --- | --- | --- | --- |
| 3–10 days | GDPS/GEPS; possibly ECMWF later | Official ECCC forecast | Early trip awareness only |
| 48–84 hours | RDPS and REPS | GDPS/GEPS | Regional trend and uncertainty |
| 0–48 hours | HRDPS | REPS/RDPS comparison | Primary Atlantic Canada forecast |
| 0–6 hours | HRDPS plus GOES observations | Stations, METAR, radar | Refine the decision |
| 0–90 minutes | GOES cloud state and motion | Latest HRDPS and observations | Leave, stay, or reroute |
| Aurora arrival | OVATION and real-time solar wind | Magnetometers, Kp, SWPC alerts | Actual auroral opportunity |

Preserve every source and model run independently. A consensus may be derived,
but model disagreement, source freshness, and missing data must remain visible.

## Weather forecasts

For the detailed source matrix, oblique viewing geometry, cloud/fog nowcasting,
commercial-provider comparison, and self-hosted options, see
[Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md).
For paid-versus-open differentiation, environmental API licensing, and the
recommended commercial bake-off, see
[Paid cloud, fog, aerosol, and air-quality APIs](paid-environmental-apis.md).
For historical forecast and observation archives, exact retrieval examples,
and forecast-versus-reanalysis semantics, see
[Historical environmental-data retrieval](historical-data-retrieval.md).
For reproducible Sun/Moon and eclipse calculations plus aurora, meteor, comet,
and transient-event archives, see
[Historical celestial events and visibility reconstruction](historical-celestial-events.md).

### Weather integration quick links

| Source | Official docs/access | SDK or practical reader |
| --- | --- | --- |
| ECCC operational models | [MSC Open Data](https://eccc-msc.github.io/open-data/) and [GeoMet OGC APIs](https://eccc-msc.github.io/open-data/msc-geomet/readme_en/) | There is no ECCC model SDK. Read GRIB with ECMWF's official [ecCodes](https://github.com/ecmwf/eccodes) or [cfgrib](https://github.com/ecmwf/cfgrib). |
| GOES-East | [NOAA GOES cloud archive](https://registry.opendata.aws/noaa-goes/) | No official SDK; community [goes2go](https://github.com/blaylockbk/goes2go) for discovery/download and [Satpy](https://satpy.readthedocs.io/) for reading/resampling. |
| ECMWF / Copernicus | [Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), [CDS API](https://cds.climate.copernicus.eu/how-to-api), [ADS](https://ads.atmosphere.copernicus.eu/) | Official [ecmwf-opendata](https://github.com/ecmwf/ecmwf-opendata), [cdsapi](https://github.com/ecmwf/cdsapi), [earthkit-data](https://github.com/ecmwf/earthkit-data). |
| NOAA operational models | [NOMADS](https://nomads.ncep.noaa.gov/) and [NOAA Open Data](https://www.noaa.gov/information-technology/open-data-dissemination) | No universal NOAA SDK; community [Herbie](https://github.com/blaylockbk/Herbie) is useful for supported stores. |
| Meteorological observations | [Aviation Weather API](https://aviationweather.gov/data/api/) and [ECCC SWOB](https://eccc-msc.github.io/open-data/msc-data/obs_station/readme_obs_insitu_swobdatamart_en/) | OpenAPI/direct HTTP for METAR; XML/OGC/file access for SWOB. |

The detailed documents above contain model-specific and commercial-provider
links. Keep retrieval adapters separate from GRIB/satellite decoders so an
access endpoint can change without altering scientific normalization.

### ECCC HRDPS: primary deterministic source

Use the High Resolution Deterministic Prediction System as the MVP's primary
short-range weather model.

Why it fits:

- approximately 2.5 km regional resolution;
- designed for Canadian short-range forecasting;
- better aligned with Atlantic Canada's coastlines, terrain, fog, and local
  cloud than a global model alone;
- public GRIB2 distribution;
- short forecast horizon matches actionable travel decisions.

Initial fields to verify and ingest:

- total, low, middle, and high cloud fraction;
- visibility;
- 2 m temperature and dew point;
- 2 m relative humidity, if published directly;
- 10 m wind speed and direction;
- precipitation rate and type;
- cloud base, boundary-layer, and vertical moisture fields where reliable.

Use HTTPS during feasibility work. Evaluate ECCC's AMQP notification service for
production ingestion so new files arrive promptly.

Sources:

- [MSC Open Data](https://eccc-msc.github.io/open-data/)
- [HRDPS documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/)
- [Using GRIB2 data](https://eccc-msc.github.io/open-data/msc-data/readme_grib_en/)

Important limitation: 2.5 km grid spacing does not mean a forecast is accurate
at every 2.5 km point. Small cloud gaps, coastal fog banks, and local terrain
effects can remain unresolved.

### HRDPS advantage over the documented Astrospheric baseline

Astrospheric documents RDPS as its primary weather model. HRDPS offers Astraeus
a potentially stronger tactical input through approximately 2.5 km horizontal
spacing, up to 31 vertical levels, and short-range raw atmospheric fields. This
may improve coastline, terrain, humidity, wind, cloud, and fog-boundary
representation relative to RDPS.

It does not establish superior forecast skill. A higher-resolution model can
place a sharper fog boundary in the wrong location. The feasibility study must
compare HRDPS, RDPS, Astrospheric output where licensed, and observed outcomes
by region, season, lead, cloud type, and event-viewing direction.

### ECCC REPS: uncertainty source

Add the Regional Ensemble Prediction System after the deterministic vertical
slice works.

Published characteristics include:

- 20 perturbed members plus a control member;
- approximately 10 km horizontal resolution;
- four runs per day;
- Canada and United States coverage;
- cloud, humidity, wind, temperature, precipitation, and other variables.

Useful derived features:

- fraction of members below a cloud threshold;
- cloud median, percentiles, and spread;
- disagreement about clearing time;
- fraction of members sustaining a usable observation window;
- stability of the top-ranked location across members.

Sources:

- [REPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps_en/)
- [REPS GRIB2 distribution](https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps-datamart_en/)

### Longer-range models

Use RDPS/GDPS and eventually GEPS for preparation and broad regional choices.
Do not use long-range guidance to issue precise instructions such as “arrive at
23:40.”

ECMWF could later provide valuable multi-model comparison. Before depending on
it, review operational access, licence, cost, caching, and redistribution
rights. It should not block an open-data MVP.

## Current weather observations

### GOES cloud products

Forecasts describe what was expected; GOES describes what clouds are doing.
This is one of the highest-value additions to the handoff plan.

Direct ingestion permits Astraeus to go beyond a displayed satellite layer by
retaining calibrated products, quality flags, timestamps, cloud probability,
cloud-top properties, multispectral nighttime evidence, motion, and
forecast-versus-observation disagreement. Raw access also creates substantially
more processing and validation responsibility.

The GOES ABI Enterprise Cloud Mask provides clear/probably clear/probably
cloudy/cloudy classifications and cloud probability. Full-disk observations
are produced at high cadence and are usable day and night.

Recommended uses:

- compare forecast cloud with observed cloud;
- detect early or late clearing;
- estimate motion from successive masks;
- reduce confidence when forecast and observation disagree;
- rerank candidate sites before departure;
- explain whether conditions are improving or deteriorating.

Known limitations are directly relevant to Atlantic Canada: nighttime low cloud
is difficult to detect, and coastal pixels can be misclassified.

Sources:

- [NOAA GOES Clear Sky Mask](https://vlab.noaa.gov/web/towr-s/goes-csm)
- [NOAA GOES-R data products](https://www.nesdis.noaa.gov/our-satellites/currently-flying/goes-east-west/goes-r-series-data-products)
- [ECCC satellite open data](https://eccc-msc.github.io/open-data/msc-data/obs_satellite/readme_satellite_en/)

Do not build a neural cloud-nowcasting model for V1. First evaluate simple
motion/advection methods against held-out observations.

### Surface stations and METAR

Use nearby observations for:

- visibility and ceiling;
- temperature, dew point, and humidity;
- wind;
- precipitation;
- fog confirmation.

Station reports are point observations. Store station distance, elevation,
observation age, and representativeness rather than applying them uniformly to
an entire region.

### Radar

Use radar for active precipitation, approaching showers, and short-term
precipitation extrapolation. Do not use radar as the primary cloud detector:
non-precipitating stratus and cirrus can prevent observing without producing a
radar return.

Sources:

- [ECCC radar products](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_en/)
- [ECCC GeoMet radar layers](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_geomet_en/)

## Fog and poor visibility

For V1, derive a conservative `visibility_risk` from:

- model visibility;
- relative humidity;
- temperature–dew-point spread;
- wind speed;
- low-cloud fraction;
- nearby surface observations;
- coastal exposure.

Suggested interpretation:

- severe risk when modeled or observed visibility is poor;
- high risk when humidity is very high, dew-point spread is small, wind is
  light, and low cloud is present;
- moderate risk when only some indicators agree;
- unknown, not clear, when essential fields are absent.

Do not build a bespoke fog neural network for the MVP. Regional bias correction
can come after collecting forecast-versus-observation history.

## Aurora and space weather

### NOAA OVATION

Use NOAA's auroral forecast as the initial spatial intensity/oval input. It is
more useful than Kp alone for estimating:

- auroral activity north of a candidate;
- distance to the active oval;
- likely viewing azimuth;
- whether emission may be overhead or near the horizon.

Store product creation time, valid time, input freshness, and data quality.
Stale data must become an explicit degraded or unavailable state, not “no
aurora.”

### NOAA real-time solar wind

Ingest:

- IMF Bz and Bt;
- solar-wind speed;
- density;
- dynamic pressure where available;
- spacecraft/source identity;
- timestamp and quality flags.

Compute rolling summaries over roughly 5, 15, 30, and 60 minutes. Sustained
southward Bz is more informative than one transient negative sample.

Source: [NOAA SWPC real-time solar wind](https://www.swpc.noaa.gov/products/real-time-solar-wind)

### Kp, alerts, and magnetometers

Use Kp for broad storm context, multi-day alerts, and historical comparison,
not as the primary real-time visibility predictor. NASA similarly describes Kp
as a rough intensity guide rather than precise real-time timing.

Source: [NASA guide to finding and photographing auroras](https://science.nasa.gov/feature/nasas-guide-to-finding-and-photographing-auroras/)

Later evaluate Natural Resources Canada or SuperMAG magnetometer data, subject
to API and redistribution terms.

Recommended evidence hierarchy:

1. OVATION spatial intensity and viewline.
2. Current solar-wind coupling indicators.
3. Recent regional geomagnetic observations.
4. SWPC watches, warnings, and forecast discussion.
5. Kp as broad context.

## Astronomy

Use Skyfield with a pinned JPL ephemeris. Compute:

- Sun altitude and azimuth;
- civil, nautical, and astronomical twilight;
- Moon altitude and azimuth;
- Moon illumination;
- Moon separation from the aurora viewing sector;
- darkness at every evaluated timestamp.

Moon interference should be directional. A bright Moon behind the observer is
less damaging than one near the northern viewing sector.

Astropy can be added for generalized event modules and deep-sky calculations,
but it is not required for the first aurora slice.

Historical celestial geometry should be recalculated from versioned ephemeris,
time-scale, observer, refraction, and horizon inputs rather than copied from a
consumer calendar. Preserve issued forecast vintages and optical observations
as separate records for stochastic events such as aurora.

## Terrain

Use Canadian elevation products before the global fallback:

| Source | Classification | Useful role | Access/licence note |
| --- | --- | --- | --- |
| [NRCan HRDEM](https://natural-resources.canada.ca/science-data/science-research/geomatics/high-resolution-digital-elevation-model-product-changing) | **Official raw raster data** | High-resolution DTM/DSM where projects cover the site | Download through NRCan; retain tile, acquisition, horizontal datum, vertical datum, and licence metadata |
| [NRCan CDEM](https://open.canada.ca/data/en/dataset/7f245e4d-76c2-4caa-951a-45d1d2051333) | **Official raw raster data** | Distant terrain and gaps | Open Government Licence – Canada; too coarse for local trees/buildings |
| [GeoNB elevation/LiDAR](https://www2.gnb.ca/content/gnb/en/departments/erd/open-data/raster-data.html) | **Official provincial raw data/services** | Preferred New Brunswick DTM, DSM, canopy height | GeoNB Open Data Licence; verify each layer's vintage |
| [Nova Scotia Elevation Explorer](https://nsgi.novascotia.ca/datalocator/elevation/) | **Official provincial raw data portal** | Preferred Nova Scotia LiDAR derivatives where covered | Open Government Licence – Nova Scotia; coverage and acquisition dates vary |
| [Copernicus DEM GLO-30](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) | **Official mission-derived raw raster data** | Global 30 m fallback | Confirm the applicable Copernicus terms and attribution for the selected product/version |

Precompute a horizon profile for each candidate site:

```text
site_id
azimuth_deg
minimum_visible_elevation_deg
dem_source
dem_version
computed_at_utc
```

Suggested initial calculation:

- azimuth bins every 2–5 degrees;
- terrain samples along rays for 50–100 km;
- Earth-curvature correction for long rays;
- penalties evaluated only in the predicted aurora sector.

Do not calculate full horizon profiles during each user request.

## Directional light pollution

Use a cloud-free VIIRS nighttime-lights composite such as NASA Black Marble or
an appropriate NOAA/EOG product. Confirm licensing and redistribution before
selecting the packaged raster.

Source distinctions matter:

- [NASA Black Marble](https://blackmarble.gsfc.nasa.gov/) is an **official
  satellite-derived product suite**, with daily products distributed through
  [NASA Earthdata](https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp46a2-002).
- [VIIRS nighttime-lights products from the Earth Observation Group](https://eogdata.mines.edu/products/vnl/)
  are **research-institution raw/composite datasets** with separate access and
  use conditions; record the exact annual/monthly product and processing mask.
- Consumer light-pollution maps and mobile apps are **derived visualizations**.
  Their colours, Bortle conversions, tiles, and redistribution rights must not
  be assumed to match the underlying VIIRS licence.

Neither satellite radiance family directly measures zenith sky brightness or
the angular extent of a light dome. Calibration against ground SQM readings
and directional imagery remains a separate scientific task.

V1 algorithm:

1. Define a sector around the viewing azimuth.
2. Sample nighttime-light intensity through the sector.
3. Weight nearer sources more heavily.
4. Weight sources close to the horizon more heavily.
5. Separate local site brightness from the northern light dome.
6. Normalize against the Atlantic Canada domain.

Call the result a directional light-pollution exposure or penalty, not a
physically calibrated sky-brightness measurement.

## Smoke and atmospheric transparency

Defer this provider until after the first operational MVP while preserving a
normalized transparency interface.

Candidate inputs:

- aerosol optical depth;
- smoke column;
- near-surface PM2.5;
- relative humidity;
- precipitable water where available.

ECCC FireWork and related Canadian products are candidates. Aerosol optical
depth is more directly relevant to astronomical transparency than AQI alone.

Source: [Canadian Wildland Fire Information System FAQ](https://cwfis.cfs.nrcan.gc.ca/en/faq)

## NREL NSRDB: solar radiation and physical cloud property database

The National Renewable Energy Laboratory (NREL) [National Solar Radiation Database (NSRDB)](https://nsrdb.nrel.gov/)
provides high-resolution (4 km, half-hourly/hourly) gridded solar irradiance and
physical atmospheric/cloud properties over the Americas (including Newfoundland)
from 1998 to near-present via the Physical Solar Model (PSM).

### Operational role in Astraeus

NSRDB is a **historical and calibration dataset**, not a real-time operational forecast.
Per [PRD-OUT-004](../specv1/product/PRD-001-ASTRAEUS-V1.md#prd-out-004--fail-closed),
it must never be substituted for live NWP or satellite observations on event day.

Primary research and offline utility:

1. **Direct-sun optical depth calibration ([ECL26-CLOUD-002](../specv1/features/eclipse-2026-08-12/SCIENCE_SPEC.md#ecl26-cloud-002--restrict-quantitative-optical-claims))**:
   Time-matched pairs of Direct Normal Irradiance (DNI), Cloud Optical Depth (COD),
   Cloud Type, and solar zenith angle enable empirical validation of the direct solar
   transmission proxy $1 - \exp(-\text{COD} / \mu)$.
2. **August mid-afternoon cloud climatology**:
   25+ years of August 10–14 afternoon (17:00–19:30 UTC) records over Avalon candidate
   sites provide empirical microclimate frequency baselines (marine fog vs. clear sky).
3. **Aerosol optical depth (AOD) baselines**:
   Physical aerosol properties provide empirical clear-sky extinction baselines for
   coastal maritime air masses.

### Key variables

- **Solar Irradiance**: Direct Normal Irradiance (DNI), Global Horizontal Irradiance (GHI), Diffuse Horizontal Irradiance (DHI), and clear-sky models.
- **Cloud Properties**: Cloud Optical Depth (COD), Cloud Top Height/Pressure (CTH), Cloud Type, Cloud Fill Flag, Surface Albedo.
- **Meteorological/Aerosol**: Aerosol Optical Depth (AOD), Precipitable Water (PWAT), Temperature, Relative Humidity, Wind Speed/Direction, Ozone.

Sources:
- [NSRDB Overview and Access](https://nsrdb.nrel.gov/)
- [NREL Developer API](https://developer.nrel.gov/docs/solar/nsrdb/)
- [AWS Open Data Registry: NREL-PDS NSRDB](https://registry.opendata.aws/nrel-pds-nsrdb/)

## Newfoundland and St. John's localized meteorological networks

The Avalon Peninsula of Newfoundland has sharp maritime microclimates, severe
advection fog regimes, and rapid coastal-to-inland transitions. Several local
observation networks provide high-density ground truth to complement regional NWP
and satellite models.

### 1. SmartAtlantic Alliance & MUN Marine Institute met-ocean buoys

The SmartAtlantic Alliance (led by the Fisheries and Marine Institute of Memorial
University of Newfoundland) operates high-rate oceanographic and meteorological
buoy stations in coastal Newfoundland waters:

- **St. John's Harbour Approach Buoy** (Station `44140` / `smartatlantic_st_johns`, 47.545° N, 52.613° W)
- **Holyrood Buoy** (Conception Bay / `smartatlantic_holyrood`, 47.459° N, 53.134° W)
- **Placentia Bay Buoy** (Station `44137` / `smartatlantic_placentia_bay`, 47.017° N, 54.917° W)

**Key parameters**: 10-minute air temperature, dew point, relative humidity,
barometric pressure, 10 m wind speed/direction/gust, sea surface temperature (SST),
significant wave height, and wave spectrum.

**Access protocol**: Programmatic [SmartAtlantic ERDDAP REST API](https://www.smartatlantic.ca/erddap/index.html)
in JSON, CSV, and NetCDF formats under Creative Commons Attribution 4.0 (CC-BY 4.0).

**Operational value for Astraeus**:
- **Marine fog and stratus genesis detection**: Advection fog forms when air dew
  point exceeds sea surface temperature ($T_{\text{dew}} \ge \text{SST}$).
- **Microclimate bay contrast**: Compares exposed open Atlantic conditions (St. John's buoy)
  against sheltered inland marine conditions (Holyrood / Conception Bay).

### 2. Newfoundland & Labrador 511 road information and highway cameras

The NL Department of Transportation and Infrastructure publishes road information
and traffic-camera products for major Avalon corridors:
- Route 1 (Trans-Canada Highway) across the Avalon Isthmus;
- Route 2 (Pitts Memorial Drive);
- Route 100 (Cape Shore / Argentia);
- Route 80 (Trinity Bay).

The documented developer interface exposes winter-road conditions, cameras,
ferry terminals, events, alerts, and wind warnings. It does not document raw
RWIS or weather-station measurements, so those variables must not be promised.

**Access protocol**: the [NL 511 developer API](https://511nl.ca/developers/doc)
uses a developer-key query parameter and allows 10 calls per 60 seconds.

**Operational value for Astraeus**:
- Camera and road-condition context along travel corridors; any CV visibility
  estimate remains derived and requires calibration against instruments.
- Real-time road passability and safety validation during weather events.

### 3. ECCC Holyrood S-band dual-polarization Doppler radar (`CASHR`)

- **Location**: Holyrood, NL (`CASHR`, 47.417° N, 53.117° W).
- Upgraded modern S-band radar with 240 km Doppler velocity range and 300 km conventional
  reflectivity range covering the entire Avalon Peninsula and offshore waters.
- **Capabilities**: Dual-polarization hydrometeor classification (separating drizzle, rain,
  snow, sea spray, and biological clutter) and clear-air boundary-layer wind vectors.
- **Access**: MSC Open Data / GeoMet OGC API.

### 4. ECCC SWOB and aviation surface stations across the Avalon

- **Key stations**:
  - `CYYT` (St. John's International Airport): 1-minute SWOB, hourly METAR/SPECI,
    optical transmissometer, and laser ceilometer cloud base heights.
  - St. John's West (`71804`), Torbay, Cape Spear, Bay Bulls, Argentia (`CWQC`),
    Grates Cove, Bonavista (`CWVA`), Heart's Content.
- **Access**: MSC Datamart XML and GeoMet OGC API.

### 5. NRCan St. John's Geomagnetic Observatory (`STJ`)

- **Location**: St. John's, NL (`STJ`, 47.595° N, 52.677° W; Geomagnetic ~53.2° N),
  operated by Natural Resources Canada (NRCan) under CANMOS.
- **Parameters**: 1-second and 1-minute tri-axial magnetic fluxgate measurements ($X, Y, Z$),
  total magnetic intensity ($F$), and local rate of change ($dH/dt$).
- **Access**: [Space Weather Canada](https://www.spaceweather.gc.ca) REST / tabular feeds.
- **Operational value**: Authoritative local ground truth for future Aurora Observation
  Modules ([RFC-005](../specv1/rfcs/RFC-005-OBSERVATION-SUBJECTS-AND-MODULES.md)).
  Local substorm magnetic deflection directly indicates auroral electrojet activity
  above Newfoundland skies, far more responsive than planetary 3-hour $Kp$.

### 6. Nav Canada Aviation Weather Cameras (WCAM)

- **Stations**: CYYT (St. John's), Argentia, Bonavista, Gander, Marystown.
- **Feeds**: 360° fixed camera horizons updated every 10 minutes with annotated
  horizon reference distances via `plan.navcanada.ca/weather-cameras`.

### 7. Marine fog microphysics: FATIMA-GB campaign insights

The Office of Naval Research FATIMA (Fog and Turbulence Interactions in the Marine
Atmosphere) Grand Banks field campaign (FATIMA-GB) and Memorial University / C-CORE
research established key coastal fog dynamics for the Avalon:
- **The "Fog Shadow" phenomenon**: Clearing of marine stratus/fog in the lee
  (downwind) of headlands and islands under southwesterly summer flows.
- **Terrain stratus lifting**: Higher terrain (e.g. Hawke Hills ~300 m, Butter Pot)
  can lift low marine stratus into broken stratocumulus inland while coastlines remain
  socked in.

### 8. Offshore Grand Banks installations (candidate partnership sources)

Fixed oil platforms and FPSOs on the Grand Banks (~300 km east/southeast of St. John's)
may contribute observations through WMO/VOS or commercial channels. No dependable
public, redistributable, per-installation live meteorological feed was confirmed:
- **Hibernia Platform** (Call Sign: `VEP717`, 46.750° N, 48.783° W)
- **Terra Nova FPSO** (Call Sign: `VCXF`, 46.400° N, 48.400° W)
- **Hebron Platform** (46.544° N, 48.498° W)
- **SeaRose FPSO** (46.800° N, 48.000° W)

Treat coordinates and call signs as unverified until checked against a current
official record. Mark these feeds `partnership-only`; do not infer parameters,
cadence, or warning time from an installation's existence.

### 9. ECCC coupled coastal & ocean models (CIOPS-East & WW3-HRW)

- **CIOPS-East (Coastal Integrated Ocean-atmosphere Prediction System)**:
  2 km high-resolution hydrodynamic ocean model run by ECCC and DFO covering Atlantic Canada.
  Provides gridded hourly Sea Surface Temperature (SST), coastal currents, and mixed-layer
  depth. Essential for computing the high-resolution coastal fog trigger ($T_{\text{dew}} \ge \text{SST}$).
- **WW3-HRW (High-Resolution Wave Model)**:
  1 km coastal wave model providing significant wave height, peak period, and swell
  direction for site safety along rocky oceanfront viewing locations (Cape Spear,
  Ferryland, St. Vincent's beach).

### 10. Local commercial meteorological & aerospace providers

- **PAL Aerospace Weather & Oceanography / Oceans Ltd.** (85 LeMarchant Road, St. John's):
  Operates a 24/7 dedicated commercial forecasting centre specializing in offshore helicopter
  flight routing, low-altitude fog ceilings, vessel motion, and Grand Banks sea-surface
  temperature isotherm tracking.
- **Sheerr Weather (`sheerrweather.ca`)**:
  Independent local platform by Chief Meteorologist Eddie Sheerr, incorporating high-resolution
  250 m radar composites and bay-specific microclimate adjustments for Newfoundland terrain.
- **C-CORE (Memorial University campus, St. John's)**:
  Specialized research institution developing satellite synthetic aperture radar (SAR)
  and marine remote-sensing techniques.

### 11. Provincial hydrometric & municipal networks

- **NL Water Resources Management Division (WRMD)**:
  Operates automated climate and hydrometric stations across Newfoundland watersheds,
  accessible via the [NL Water Resources GeoHub](https://www.gov.nl.ca/ecc/waterres/)
  and [Atlantic DataStream](https://atlanticdatastream.ca).
- **City of St. John's Open Data**:
  Municipal weather and road condition sensors accessible via `map.stjohns.ca`.

### 12. High-density citizen science & personal weather stations (PWS)

- **CWOP / APRS-WX & Weather Underground (50+ Avalon Stations)**:
  High-density 5-minute temperature, humidity, dew point, and pressure stations in
  St. John's, Mount Pearl, Paradise, Conception Bay South, Torbay, Bay Bulls, Carbonear,
  and Spaniard's Bay.
- **Ingestion quality control**: Must apply **Interquartile Range (IQR) outlier rejection**
  to filter uncalibrated or direct-sun-heated consumer sensors before computing
  neighborhood consensus grids.
- **PurpleAir Optical PM2.5 Monitors**:
  Laser particle counters in the St. John's metro reporting continuous optical aerosol
  scattering to verify local atmospheric transparency.

### 13. Academic research observatories

- **Memorial University CTec Holyrood Marine Base**:
  Conception Bay met-ocean observation testbed.
- **MUN Physics & Physical Oceanography Rooftop Observatory**:
  Research-grade multi-spectral solar irradiance, sonic anemometers, and thermal flux
  monitors on the St. John's university campus.

## Astrospheric as a benchmark source

Astrospheric should be treated as an independent astronomy-forecast benchmark,
not assumed to be either ground truth or a production dependency.

Its documented concepts that Astraeus should compare or reproduce include:

- RDPS primary forecast;
- specialized astronomy transparency and seeing;
- smoke incorporated into transparency;
- NBM, ICON, GFS, and other cloud-model comparison;
- dew point and jet-stream context;
- visible satellite and light-pollution layers;
- aurora/Kp context;
- model publication, location availability, and expected-update metadata.

If current Pro API terms allow automated commercial comparison and permanent
archival, store its issued point forecasts alongside Astraeus forecasts during
the feasibility experiment. Confirm:

```text
automated query limits
forecast archival rights
commercial and competing-use restrictions
redistribution and derived-score rights
model and post-processing provenance
historical endpoint semantics
```

Do not use Astrospheric forecast values as observed truth. Compare both systems
against GOES, SWOB/METAR, all-sky imagery, and attempted observations.

The objective is to test whether this richer Astraeus stack:

```text
HRDPS + REPS + GOES + surface observations
+ directional event geometry
+ travel and access constraints
```

produces better stay/go/move decisions than manual location comparison in
Astrospheric. Higher input resolution alone is not a product advantage.

## Candidate locations

Seed candidates from:

- public parks and land;
- public coastal lookoffs;
- trailheads and parking areas;
- known astronomy sites;
- road-accessible high/open points;
- OpenStreetMap parking, viewpoint, and park features;
- the user's current location.

Each candidate should store access provenance, road proximity, known hours or
restrictions, horizon profile, light exposure, parking/access confidence, and
safety caveats.

A coarse grid may supplement this database, but an unknown grid point should
not be presented as a confidently accessible destination.

Use official land layers for ownership/management evidence, including the
[Canadian Protected and Conserved Areas Database](https://open.canada.ca/data/en/dataset/6c343726-1e92-451a-876a-76e17d398a1c),
[Nova Scotia Crown Land](https://data.novascotia.ca/Lands-Forests-and-Wildlife/Crown-Land/3nka-59nz),
[GeoNB Crown Lands](https://www2.gnb.ca/content/gnb/en/departments/erd/open-data/crown-lands.html),
and the [Newfoundland and Labrador Land Use Atlas](https://www.gov.nl.ca/crownlands/land-use-atlas/).
These are **official GIS datasets/viewers**, but a parcel or park polygon does
not prove night entry, parking, an open gate, or a safe walking route.

OpenStreetMap is **community-maintained raw geodata** under the ODbL; review
[copyright and attribution](https://www.openstreetmap.org/copyright) and model
missing `access`, `opening_hours`, and barrier tags as unknown. The public OSM
tile service is not a production bulk-data API; it has a separate
[tile usage policy](https://operations.osmfoundation.org/policies/tiles/).

## Routing

Use straight-line distance only for an internal science prototype. Before a
public recommendation tells someone to drive, use road routing.

Preferred progression:

1. [OSRM](https://github.com/Project-OSRM/osrm-backend) (**official project
   repository; open-source routing engine**) for initial duration and distance
   matrices over a locally hosted OSM extract.
2. [Valhalla](https://github.com/valhalla/valhalla) (**official project
   repository; MIT-licensed engine**) if richer costing, isochrones,
   multimodal routing, or arrive-by semantics become necessary.
3. Cached routes among common candidate sites.

Community clients such as
[`routingpy`](https://github.com/gis-ops/routing-py) are **unofficial/community
SDKs**: useful for prototyping multiple engines, but not an authority on data
quality, service limits, or upstream terms. Do not rely on public demo routing
instances in production. If evaluating Google Routes, treat it as an
**official paid vendor API** and review its
[caching and attribution policy](https://developers.google.com/maps/documentation/routes/policies)
before persisting matrices or mixing results with non-Google maps.
