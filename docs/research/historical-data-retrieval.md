# Historical environmental-data retrieval

Last reviewed: 2026-08-10

## Purpose

This document is the retrieval and fact-checking runbook for historical cloud,
fog, weather-model, satellite, station, radar, aerosol, smoke, and air-quality
data relevant to Astraeus in Atlantic Canada.

Historical Sun, Moon, eclipse, aurora, meteor, comet, and transient-event data
are covered in
[Historical celestial events and visibility reconstruction](historical-celestial-events.md).

It distinguishes data that are often misleadingly grouped under the word
`historical`:

```text
observation
satellite retrieval
operational analysis
archived operational forecast vintage
reanalysis
hindcast or reforecast
commercial reconstruction or blend
```

Only an **archived operational forecast vintage** answers:

> What could Astraeus actually have predicted at the time the recommendation
> was issued?

A reanalysis answers:

> What is the best retrospective atmospheric estimate after additional
> observations and a consistent assimilation system have been applied?

Using reanalysis or reconstructed history as though it were an old forecast
introduces look-ahead leakage and produces falsely optimistic verification.

## Retrieval tools and repositories

These are the supported or widely used clients behind the retrieval examples
in this runbook. They do not make different datasets scientifically
interchangeable.

| Archive or format | Official documentation | Official client / repository | Community tooling and caveat |
| --- | --- | --- | --- |
| ECCC Datamart and GeoMet | [MSC Open Data](https://eccc-msc.github.io/open-data/), [Datamart AMQP](https://eccc-msc.github.io/open-data/usage/readme_en/), [GeoMet](https://eccc-msc.github.io/open-data/msc-geomet/readme_en/) | No model-archive SDK. Access is HTTP/AMQP, OGC API, WMS/WCS and raw GRIB/XML files. | [ecCodes](https://github.com/ecmwf/eccodes), [cfgrib](https://github.com/ecmwf/cfgrib), and [xarray](https://docs.xarray.dev/) decode/process delivered GRIB. They do not locate unavailable ECCC forecast vintages. |
| ECMWF MARS / Open Data | [MARS user docs](https://confluence.ecmwf.int/display/UDOC/MARS+user+documentation), [Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data) | [ecmwf-api-client](https://github.com/ecmwf/ecmwf-api-client) for legacy Web API/MARS access and [ecmwf-opendata](https://github.com/ecmwf/ecmwf-opendata) for open operational data. | Access rights and licence determine which requests work; a client package does not grant archive entitlement. |
| CDS / ADS: ERA5 and CAMS | [CDS API](https://cds.climate.copernicus.eu/how-to-api), [ADS](https://ads.atmosphere.copernicus.eu/) | Official [cdsapi](https://github.com/ecmwf/cdsapi); [earthkit-data](https://github.com/ecmwf/earthkit-data) is ECMWF's broader data access toolkit. | Pin the catalogue dataset ID and request JSON; catalogue migrations can change valid parameter names. |
| TIGGE | [TIGGE archive](https://confluence.ecmwf.int/display/TIGGE) | MARS/CDS access according to the catalogue; no TIGGE-specific SDK. | Preserve centre, member, cycle and lead time. |
| NOAA NCEI / NOMADS / cloud archives | [NCEI model data](https://www.ncei.noaa.gov/products/weather-climate-models), [NOMADS](https://nomads.ncep.noaa.gov/), [NOAA cloud access](https://www.ncei.noaa.gov/access/cloud-access) | Official access is HTTPS/THREDDS/HAS and cloud object stores, not one universal SDK. | [Herbie](https://github.com/blaylockbk/Herbie) supports many forecast stores; [s3fs](https://s3fs.readthedocs.io/) supports S3. Confirm that the selected backend retains the required dates. |
| GOES-R ABI | [NOAA AWS record](https://registry.opendata.aws/noaa-goes/), [CLASS](https://www.class.noaa.gov/) | Official access is S3/CLASS; no official language SDK identified. | Community [goes2go](https://github.com/blaylockbk/goes2go) provides Python discovery/download and [Satpy](https://satpy.readthedocs.io/) reads/resamples files. Product acronyms and DQF definitions still require official product guides. |
| Aviation Weather METAR | [API docs](https://aviationweather.gov/data/api/) | Official OpenAPI schema and bulk caches; no maintained official Python SDK identified. | Generate a pinned client or use HTTP directly; [python-metar](https://github.com/python-metar/python-metar) parses reports but is not NOAA software. |
| NASA Earthdata: MODIS/VIIRS/MAIAC | [Earthdata Search](https://search.earthdata.nasa.gov/), [Earthdata developer resources](https://www.earthdata.nasa.gov/learn/use-data/tools/developer-resources) | Official [earthaccess](https://github.com/nsidc/earthaccess) Python client and [Harmony](https://harmony.earthdata.nasa.gov/) services; LAADS has its own file API. | [pystac-client](https://github.com/stac-utils/pystac-client) applies only when the collection is exposed through STAC. |
| AERONET | [Web-service documentation](https://aeronet.gsfc.nasa.gov/print_web_data_help_v3.html) | CGI web service; no official language SDK identified. | Direct HTTP plus archived raw response is simplest. |
| OpenAQ | [API docs](https://docs.openaq.org/) | Official [openaq-api](https://github.com/openaq/openaq-api) server repository; consumers normally call the REST API. | Community clients can lag API versions; record source owner and sensor provenance, not only OpenAQ IDs. |
| NREL NSRDB | [NSRDB docs](https://nsrdb.nrel.gov/), [API docs](https://developer.nrel.gov/docs/solar/nsrdb/), [AWS Open Data](https://registry.opendata.aws/nrel-pds-nsrdb/) | Developer REST API (CSV) and AWS S3 HDF5 (.h5) archives; no official dedicated SDK. | Use `h5py`/`xarray` for S3 access or `requests`/`pandas` for API extracts. Historical/calibration only—not for operational event-day forecasts. |
| SmartAtlantic ERDDAP | [SmartAtlantic Portal](https://www.smartatlantic.ca), [ERDDAP server](https://www.smartatlantic.ca/erddap/index.html) | ERDDAP REST API (CSV, JSON, NetCDF); official client is direct HTTP or `erddapy`. | Real-time and historical coastal buoy feeds (St. John's, Holyrood, Placentia Bay); CC-BY 4.0. |
| Grand Banks installations / VOS candidates | [MSC Datamart SWOB partners](https://dd.weather.gc.ca/today/observations/swob-ml/partners/), [C-NLOPB offshore information](https://www.cnlopb.ca/offshore/) | Search documented WMO/SWOB identities; partnership or licensed access may be required. | No dependable public per-installation live feed is confirmed for Hibernia, Terra Nova, Hebron, or SeaRose; do not assume identifiers, cadence, or variables. |
| ECCC CIOPS-East / WW3 | [MSC Open Data](https://eccc-msc.github.io/open-data/msc-data/nwp_ciops/readme_ciops-east_en/) | GeoMet OGC API / NetCDF / GRIB2 on Datamart. | 2 km coupled hydrodynamic ocean model (SST, currents) and 1 km coastal wave grid. |
| NL 511 API | [Developer documentation](https://511nl.ca/developers/doc) | REST JSON API using a developer-key query parameter. | Winter roads, cameras, ferry terminals, events, alerts, and wind warnings; no documented raw RWIS feed. |
| Space Weather Canada / STJ | [Space Weather Canada](https://www.spaceweather.gc.ca), [NRCan Geomagnetism](https://geomag.nrcan.gc.ca) | Space Weather REST API / HTTP data services. | Real-time 1-sec/1-min magnetometer fluxgate data from St. John's Magnetic Observatory (`STJ`). |
| CWOP / PWS Networks | [CWOP Info](http://www.findu.com/citizenweather.html), [Weather Underground API](https://www.wunderground.com/weather/api) | APRS-IS TCP stream / REST JSON. | High-density 5-min personal weather station feeds across Avalon; requires IQR outlier rejection. |
| PurpleAir | [PurpleAir API](https://api.purpleair.com/) | REST JSON API. | Real-time optical laser particle counter PM2.5 measurements in St. John's metro. |
| Generic scientific formats | [ecCodes docs](https://confluence.ecmwf.int/display/ECC), [xarray docs](https://docs.xarray.dev/), [netCDF4 docs](https://unidata.github.io/netcdf4-python/) | [ecCodes](https://github.com/ecmwf/eccodes), [cfgrib](https://github.com/ecmwf/cfgrib), [xarray](https://github.com/pydata/xarray), [netCDF4-python](https://github.com/Unidata/netcdf4-python) | [kerchunk](https://github.com/fsspec/kerchunk) can virtualize archival files, but references must be regenerated if objects move. |

“Official client” here means maintained by the producing institution or the
software project; it does not imply support for every dataset or historical
period.

## Executive recommendation

For Atlantic Canada, use:

```text
forecast truth at issuance:
    self-archived HRDPS + REPS
    requested ECCC five-year archive extract
    archived CAMS operational forecast cycles
    optional ECMWF/NOAA operational forecast vintages

observed cloud and fog outcome:
    GOES ABI NetCDF
    METAR/SPECI and NCEI Global Hourly
    ECCC Historical Climate and prospectively mirrored SWOB

aerosol and smoke outcome:
    AERONET where available
    MAIAC/MODIS/VIIRS/GOES AOD
    ECCC/OpenAQ surface stations

retrospective context:
    ERA5
    CAMS EAC4

astronomy-specific truth:
    Astraeus all-sky cameras and star photometry
```

The most urgent engineering action is to begin immutable self-archiving of
selected HRDPS, REPS, GOES, SWOB, METAR, RAQDPS/FireWork, and CAMS cycles.
Historical observations and reanalysis are generally recoverable later;
forecast vintages are much harder to reconstruct.

## Historical-data taxonomy

| Type | What it represents | Suitable for forecast verification? |
| --- | --- | ---: |
| Observation | Instrument or human report at a point/footprint | Outcome evidence, with representativeness limits |
| Satellite retrieval | Algorithm-derived property from radiances | Outcome evidence, but not direct ground truth |
| Operational analysis | Best estimate produced during operations | Context; not a forecast at positive lead |
| Archived forecast vintage | Output preserved by initialization, lead, and model version | Yes |
| Reanalysis | Retrospective fixed-system reconstruction using later observations | No; useful for climatology and features |
| Hindcast/reforecast | Model rerun retrospectively under a defined configuration | Bias correction and model comparison, not what users saw |
| Reconstruction/blend | Vendor-generated historical estimate | No unless issuance/run dimensions are explicit |

Never normalize a forecast only by `valid_time`. These records are distinct:

```text
2026-01-10 00Z run +24 h
2026-01-10 12Z run +12 h
```

even if they verify at the same time.

## Source priority matrix

| Source | Semantics | Approximate range | Atlantic Canada role |
| --- | --- | --- | --- |
| ECCC HRDPS/RDPS/GDPS | Archived operational forecasts by paid request | Forecasts retained about 5 years | Primary Canadian forecast truth |
| ECCC REPS/GEPS | Archived ensemble forecasts by request; some GEPS via TIGGE | About 5 years native; TIGGE from 2006 | Forecast uncertainty |
| ECMWF IFS/ENS | Operational analyses and forecast vintages in MARS | Decades, product-dependent | Independent forecast benchmark |
| ECMWF AIFS | Archived AI forecasts | Single from 2024; ENS from 2025 | Recent AI benchmark |
| ERA5 | Reanalysis | 1940–present | Long-term retrospective atmospheric state |
| NOAA HRRR | Public operational forecast archive | 2014–present | Partial-domain high-resolution comparison |
| NOAA RRFS | Prototype/retrospective archive | Selected periods before operations | Research only |
| NOAA GFS/GEFS | Operational forecast archives | GFS to mid-2000s; GEFS modern eras | Global baseline and ensemble |
| GOES ABI | Satellite retrieval/radiance | 2017–present, product-dependent | Spatial cloud/AOD outcome |
| METAR/SPECI | Surface observations | Station-dependent | Visibility, fog, ceiling, cloud bases |
| ECCC Historical Climate | Surface observations | Station-dependent, often decades | Canadian station history |
| ECCC SWOB | Rich current/recent observations | Rolling service; mirror forward | Canadian operational truth |
| CAMS operational | Archived operational analysis/forecast cycles | 2015–present | Aerosol/chemistry forecast truth |
| CAMS EAC4 | Composition reanalysis | 2003–present updates | Retrospective aerosol context |
| AERONET | Ground column AOD observation | 1993–present | Aerosol optical validation where available |
| MODIS MAIAC | Satellite AOD retrieval | Terra/Aqua era | Daily high-resolution historical AOD |
| VIIRS aerosol | Satellite AOD retrieval | 2012/2018–present | Modern aerosol/smoke retrieval |
| OpenAQ/ECCC stations | Surface pollutant observation | Provider/station-dependent | Surface PM/gases |
| Commercial histories | Usually reconstruction/reanalysis | Provider-dependent | Convenience, not forecast truth by default |

# Operational weather-model archives

## ECCC HRDPS, RDPS, and GDPS

### Critical availability finding

ECCC states that numerical forecast data are archived for **five years**, but
does not provide a general public self-service historical forecast bucket.
Historical retrieval is handled under a cost-recovery request. At the time of
review, ECCC documented a charge of CAD 118 per hour with a one-hour minimum;
confirm current pricing before ordering.

Official source:

- [MSC Open Data FAQ: historical NWP forecasts](https://eccc-msc.github.io/open-data/faq/readme_en/)

The live [MSC Datamart](https://eccc-msc.github.io/open-data/msc-datamart/readme_en/)
has a rolling retention period—documented as roughly 30 days at review time—and
is not the five-year archive.

### Archive request contents

ECCC asks for:

```text
model
data type: forecast, analysis, or map
variables
date range
run hours
forecast hours
geographic domain
horizontal resolution
vertical levels
delivery method
contact and billing coordinates
```

The FAQ identifies this archive contact:

```text
ec.dps-client.ec@canada.ca
```

Use the official page to verify the current contact and order form before
sending a request.

### Recommended HRDPS request

Start with a small Atlantic subset rather than the full Canadian grid:

```text
Model:
HRDPS continental

Data type:
raw operational forecast

Dates:
earliest available five-year interval through present

Runs:
00, 06, 12, 18 UTC

Forecast hours:
000–048 hourly

Provisional domain:
north=61, west=-70, south=42, east=-50

Surface and column fields:
total cloud cover
available low/middle/high cloud
visibility / VISIFG
cloud base or ceiling if archived
2 m temperature and dew point/depression
relative humidity
10 m U/V wind
precipitation rate and type
surface pressure
column cloud liquid/ice water
column water vapour
boundary-layer height

Vertical fields:
temperature
specific and relative humidity
cloud fraction
cloud liquid and ice water
rain and snow water
geopotential/height
U/V wind

Priority pressure levels:
1000, 985, 970, 950, 925, 900, 850, 800,
750, 700, 650, 600, 550, 500, 450, 400,
350, 300, 250 hPa

Format:
original GRIB2 where possible
```

Ask explicitly whether native/model-level hydrometeors are archived and
releasable. Public field availability does not guarantee that every internally
archived field is distributed.

### Fact-check an ECCC delivery

For a small sample:

1. Inspect GRIB reference time and forecast step with `grib_ls` or `wgrib2`.
2. Confirm two initialization cycles for the same valid time remain separate.
3. Confirm accumulation intervals are explicit.
4. Confirm ensemble/member identifiers where applicable.
5. Compare field names and units with the current
   [HRDPS documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/).
6. Hash the raw file and never overwrite it.

### Licensing

Live ECCC products are governed by ECCC's open-data terms, but a historical
archive order may add service or redistribution conditions. Confirm commercial
use, storage, derived products, attribution, and redistribution in writing.

## ECCC REPS and GEPS

Request REPS with member identity preserved:

```text
members:
control + all perturbed members

runs:
00, 06, 12, 18 UTC

forecast hours:
all available, prioritizing 0–48 h

fields:
total and layer cloud
visibility
near-surface RH/temp/wind
vertical cloud fraction/humidity

format:
GRIB2 preserving ensemble member
```

If volume or retrieval cost is excessive, prioritize cloud strata, visibility,
near-surface fog predictors, and vertical humidity/cloud fraction through the
lower and middle troposphere.

### GEPS through TIGGE

TIGGE archives standardized global ensemble forecasts from multiple centres,
including ECCC, from October 2006 onward. It is useful for coarse GEPS research
but has a reduced standardized parameter set and is not equivalent to the
native archive.

- [TIGGE overview](https://www.ecmwf.int/en/research/projects/tigge)
- [TIGGE FAQ and Data Store migration](https://confluence.ecmwf.int/spaces/TIGGE/pages/40797492/FAQ)
- [TIGGE model upgrades](https://confluence.ecmwf.int/spaces/TIGGE/pages/53523308/Model%2Bupgrades)
- [TIGGE licence](https://ecds.ecmwf.int/licences/tigge-licence)

Provider-specific licensing may include non-commercial terms. Confirm the
licence for ECCC fields rather than assuming one rule covers every contributor.
TIGGE-LAM was deprecated and does not provide a REPS archive.

## Immediate ECCC self-archive

The five-year recovery window advances every day. Mirror each live run before
Datamart expiry.

Suggested immutable key:

```text
raw/eccc/{model}/{model_version}/{init_utc}/
  {variable}/{level_type}/{level}/lead_{forecast_hour}.grib2
```

Suggested manifest:

```json
{
  "provider": "ECCC",
  "model": "HRDPS",
  "model_version": "...",
  "initialization_time_utc": "...",
  "expected_forecast_hours": [],
  "received_forecast_hours": [],
  "fields": [],
  "source_urls": [],
  "retrieved_at_utc": "...",
  "checksums": {},
  "missing_files": [],
  "grib_inventory": [],
  "licence_url": "...",
  "ingestor_version": "..."
}
```

Use ECCC AMQP notifications for production discovery, then copy raw bytes to
object storage before normalization. Never overwrite a run.

## ECMWF operational IFS and ENS archives

ECMWF's MARS archive stores operational analyses, deterministic forecasts,
ENS control and perturbed members, AIFS output, research experiments, and
reanalysis. It preserves initialization, step, member, level, and model-cycle
dimensions needed for honest forecast verification.

- [MARS archive overview](https://www.ecmwf.int/en/about/media-centre/focus/2026/mars-exabyte-scale-meteorological-data)
- [Accessing ECMWF forecasts](https://www.ecmwf.int/en/forecasts/accessing-forecasts)
- [MARS access restrictions](https://confluence.ecmwf.int/spaces/UDOC/pages/47290687/MARS%2Baccess%2Brestrictions)

The 2025 open-data transition improved real-time access, but historical archive
access still depends on product, era, licence, account, and service. Some
retrievals may come from tape.

Illustrative MARS request:

```text
retrieve,
  class=od,
  stream=enfo,
  type=pf,
  date=2026-01-01/to/2026-01-31,
  time=00/12,
  step=0/to/48/by/3,
  number=1/to/50,
  levtype=sfc,
  param=164/186/187/188,
  area=61/-70/42/-50,
  grid=0.1/0.1,
  format=grib,
  target="ecmwf_ens_cloud.grib"
```

This is illustrative. Generate the final request from the live MARS catalogue
because stream, parameter, field, and access availability change across eras.

### AIFS

ECMWF documents archived AIFS Single output from February 2024 and AIFS ENS
from July 2025:

- [AIFS output access](https://confluence.ecmwf.int/spaces/UDOC/pages/599165903/AIFS%2BHow%2BTo%2BAccess%2BAIFS%2Bmodel%2Boutput%2Bdata)
- [AIFS forecast generation and reproducibility](https://confluence.ecmwf.int/spaces/UDOC/pages/599165906/AIFS%2BHow%2BTo%2BGenerate%2Ba%2Bforecast%2Bwith%2Bthe%2BAIFS)

Prefer archived operational output. Regenerated AIFS forecasts are not
necessarily bit-identical because of hardware and interpolation differences.

## ERA5 reanalysis

ERA5 provides a global hourly retrospective state from 1940 onward, commonly
on 0.25-degree output grids, with rich vertical fields:

- [ERA5 pressure levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels)
- [ERA5 single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)
- [ERA5 complete/model levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-complete)
- [ERA5 download guide](https://confluence.ecmwf.int/spaces/CKB/pages/129135000/How%2Bto%2Bdownload%2BERA5)

Cloud-relevant fields include cloud fraction, liquid/ice/rain/snow water,
humidity, temperature, winds, geopotential, and surface pressure.

Illustrative CDS request:

```python
import cdsapi

client = cdsapi.Client()
client.retrieve(
    "reanalysis-era5-pressure-levels",
    {
        "product_type": ["reanalysis"],
        "variable": [
            "fraction_of_cloud_cover",
            "relative_humidity",
            "specific_cloud_ice_water_content",
            "specific_cloud_liquid_water_content",
            "specific_humidity",
            "temperature",
            "u_component_of_wind",
            "v_component_of_wind",
        ],
        "pressure_level": [
            "1000", "975", "950", "925", "900", "850",
            "800", "750", "700", "650", "600", "550",
            "500", "450", "400", "350", "300", "250"
        ],
        "year": "2025",
        "month": "01",
        "day": ["01", "02"],
        "time": [
            "00:00", "03:00", "06:00", "09:00",
            "12:00", "15:00", "18:00", "21:00"
        ],
        "area": [61, -70, 42, -50],
        "data_format": "grib"
    },
    "era5_atlantic_cloud.grib"
)
```

Generate code from the current dataset form because request keys can change.

ERA5 is useful for climatology, historical atmospheric features, regime
discovery, and selected model-level reconstruction. It is too coarse for many
coastal fog banks and cannot verify operational lead-time skill.

## NOAA HRRR

NOAA publishes HRRR forecast archives from 2014 in public object storage:

- [NOAA HRRR archive links](https://rapidrefresh.noaa.gov/hrrr/)
- [HRRR AWS open-data record](https://registry.opendata.aws/noaa-hrrr-pds/)

Bucket:

```text
s3://noaa-hrrr-bdp-pds/
```

Example:

```bash
aws s3 ls --no-sign-request \
  s3://noaa-hrrr-bdp-pds/hrrr.20240101/

aws s3 cp --no-sign-request \
  s3://noaa-hrrr-bdp-pds/hrrr.20240101/conus/hrrr.t00z.wrfsfcf12.grib2 \
  .
```

Use the accompanying `.idx` files for byte-range retrieval of cloud, ceiling,
visibility, humidity, and hydrometeor fields.

The CONUS domain does not cover all Atlantic Canada or Labrador equally well.
Verify domain inclusion and distance from the lateral boundary before using it
as a benchmark.

## NOAA RRFS

As of the review date, the RRFS object store contained prototype output and
selected retrospective periods rather than a homogeneous operational archive:

- [RRFS AWS open-data record](https://registry.opendata.aws/noaa-rrfs/)

```bash
aws s3 ls --no-sign-request s3://noaa-rrfs-pds/
```

Keep configuration/version labels for every period. Do not merge prototypes,
retrospectives, and later operational output into one model era.

## NOAA GFS and GEFS

### GFS

NCEI offers historical GFS analysis/forecast products across multiple model
eras and grids, with THREDDS, HTTPS, HAS staging, and limited recent cloud
storage:

- [NCEI GFS archive](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast)
- [Example GFS THREDDS catalogue](https://www.ncei.noaa.gov/thredds/catalog/model-gfs-004-files-old/202004/20200412/catalog.html)

Recent AWS pattern:

```bash
aws s3 ls --no-sign-request \
  s3://noaa-gfs-bdp-pds/gfs.20260101/00/atmos/
```

The AWS GFS store may be only a trailing operational window. Use NCEI/HAS for
older periods. Inspect `.idx` files rather than assuming stable field contents
across model upgrades.

### GEFS

- [NCEI GEFS archive](https://www.ncei.noaa.gov/index.php/products/weather-climate-models/global-ensemble-forecast)

```bash
aws s3 ls --no-sign-request \
  s3://noaa-gefs-pds/gefs.20260101/
```

NODD object availability should not automatically be treated as guaranteed
archival permanence. Mirror the exact members/fields needed for reproducible
research.

# Historical cloud and fog observations

## GOES-East ABI archive

### Satellite eras

Retain platform identity rather than using only `GOES-East`. GOES-16 and
GOES-19 have different operational and product eras. Record:

```text
platform
product and algorithm version
processing mode and maturity
scan mode and sector
```

Use the [NCEI GOES-R product table](https://www.ncei.noaa.gov/products/satellite/goes-r-series)
to verify first-public dates and maturity for each product.

### NOAA AWS access

- [NOAA GOES AWS open-data record](https://registry.opendata.aws/noaa-goes/)
- [NOAA GOES-R beginner's guide](https://goes-r.noaa.gov/downloads/resources/documents/Beginners_Guide_to_GOES-R_Series_Data.pdf)

Buckets:

```text
s3://noaa-goes16/
s3://noaa-goes18/
s3://noaa-goes19/
```

Typical hierarchy:

```text
PRODUCT/YYYY/DDD/HH/
```

Examples:

```bash
aws s3 ls --no-sign-request \
  s3://noaa-goes16/ABI-L2-ACMF/2024/100/03/

aws s3 cp --no-sign-request --recursive \
  s3://noaa-goes16/ABI-L2-ACMF/2024/100/03/ \
  ./goes/ABI-L2-ACMF/2024/100/03/

aws s3 ls --no-sign-request \
  s3://noaa-goes16/ABI-L1b-RadF/2024/100/03/
```

No AWS account is required for unsigned reads. Enumerate real keys because not
every product exists from the platform's first date or in every sector.

### NOAA CLASS

[NOAA CLASS](https://www.class.noaa.gov/) is the authoritative search/order
system for long-term satellite products and is useful when AWS lacks a product,
reprocessed data are needed, or enterprise Fog/Low Stratus data are required.
CLASS may stage asynchronous orders and is less convenient than S3 for routine
bulk processing.

### Products to retrieve

| Product | Typical prefix/access | What it supports | Main caveat |
| --- | --- | --- | --- |
| ABI L1b radiance | `ABI-L1b-RadF/C/M` | Reprocessing, IR/visible features, motion | Not cloud base or fog truth |
| Cloud mask/probability | `ABI-L2-ACMF/C/M` | Spatial cloud state | Algorithm/DQF era changes; parallax |
| Cloud top | Product-specific ABI L2 | Height/pressure/temp of dominant top | Not base; upper cloud hides lower layers |
| Cloud phase | `ABI-L2-ACTP*` | Retrieved top phase | Not a vertical phase profile |
| Cloud optical depth | Product/version-specific | Vertical retrieved opacity | Not slant opacity; day/night differences |
| Fog/Low Stratus | CLASS `GRABINDE`, `ABI-L2-GFLS*` | MVFR/IFR/LIFR probability and thickness | Model-assisted, not surface visibility truth |
| Aerosol optical depth | ABI L2 AOD | Intraday clear-sky aerosol evolution | Daylight/cloud-free pixels only |

Official references:

- [ABI spectral attributes](https://www.star.nesdis.noaa.gov/goes/abispectralattributes.php)
- [Cloud-top height and layer](https://goes-r.noaa.gov/products/baseline-cloud-top-height-cloud-layer.html)
- [Cloud top phase](https://catalog.data.gov/dataset/noaa-goes-r-series-advanced-baseline-imager-abi-level-2-cloud-top-phase-actp)
- [Cloud optical depth](https://goes-r.noaa.gov/products/baseline-cloud-opt-depth.html)
- [Fog/Low Stratus metadata](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc%3AC01572)
- [FLS CLASS search](https://www.class.noaa.gov/saa/products/search?datatype_family=GRABINDE)
- [GOES AOD](https://www.goes-r.gov/products/baseline-aerosol-opt-depth.html)

### DQF and algorithm-era warning

The GOES cloud mask transitioned to an enterprise algorithm in November 2021,
changing cloud probability and DQF semantics while retaining related product
names. See the
[Enterprise Cloud Mask transition README](https://www.noaasis.noaa.gov/pdf/ps-pvr/goes-16/ABI/Clear%20Sky%20Mask/Provisional/GOES-16_17_ABI_L2_CloudMask_Provisional_ReadMe_ECMupgrade.pdf).

Do not use one DQF decoder across all years. Preserve:

```text
platform_ID
scene_id
time coverage
algorithm/product version
processing parameters
DQF and fill values
satellite and solar zenith angles
day/night regime
```

Apply `scale_factor` and `add_offset`, never bilinearly interpolate categorical
flags, and parallax-correct cloud-top-dependent locations before station
collocation.

### GOES fact-check

For one hour:

1. List the actual AWS prefix.
2. Open one NetCDF and inspect platform, product version, time bounds, grid,
   DQF, fill, scale, and offset.
3. Compare file time with a known Atlantic station observation.
4. Verify fill/missing values remain missing rather than becoming clear/zero.
5. Confirm product availability on both sides of algorithm/platform cutovers.

## METAR and SPECI

### Recent API

The [Aviation Weather API](https://www.connect.aviationweather.gov/data/api/)
provides worldwide METAR in JSON, GeoJSON, CSV, XML, IWXXM, and raw formats,
but retains only a short recent window, documented as about 15 days.

Example:

```bash
curl -A 'Astraeus research contact@example.com' \
  'https://aviationweather.gov/api/data/metar?ids=CYHZ,CYQM,CYYT,CYFC&format=json&hours=24'
```

Use its current OpenAPI schema to verify query names and limits. For broad
current ingest, prefer the minutely cache:

```bash
curl -O https://aviationweather.gov/data/cache/metars.cache.csv.gz
```

This is for operational mirroring and recent backfill, not long-term history.

### NCEI Global Hourly

NCEI Global Hourly contains global hourly/subhourly station data with records
extending back more than a century depending on station:

- [Global Hourly access](https://www.ncei.noaa.gov/data/global-hourly/access/)
- [NCEI Search API](https://www.ncei.noaa.gov/access/search/documentation/search-service/)
- [ISD/Global Hourly format](https://www.ncei.noaa.gov/data/global-hourly/doc/isd-format-document.pdf)

Pattern:

```text
https://www.ncei.noaa.gov/data/global-hourly/access/YYYY/USAF-WBAN.csv
```

First discover the station's USAF/WBAN identifier; do not assume the ICAO code
is the filename.

Useful content includes visibility, temperature/dew point, wind, present
weather, sky-condition groups, report type, raw/additional data, and QC flags.
An hourly row may be a merged/selected report rather than every original
SPECI. Retain raw groups and report/source identifiers.

### IEM convenience access

The [Iowa Environmental Mesonet ASOS/METAR downloader](https://mesonet.agron.iastate.edu/request/download.phtml)
offers convenient CSV access, including Canadian networks where available.
Use it for development and independent cross-checking, not as the sole
authoritative archive. Verify live network/station identifiers before
automating.

### What METAR can establish

- Surface horizontal visibility.
- Fog/mist and other present-weather codes.
- Reported cloud amount/base layers and vertical visibility.
- Temperature, dew point, and wind.

It cannot establish spatial cloud between stations, cloud top, layers hidden
above opaque cloud, or directional astronomical transmission. Interpret
Canadian `CLR` and cloud reporting using
[ECCC MANOBS](https://www.canada.ca/en/environment-climate-change/services/weather-manuals-documentation/manobs-surface-observations.html).

## ECCC SWOB

ECCC SWOB provides rich Canadian observation XML with station/provider
metadata and quality information:

- [SWOB Datamart documentation](https://eccc-msc.github.io/open-data/msc-data/obs_station/readme_obs_insitu_swobdatamart_en/)
- [SWOB station collection](https://api.weather.gc.ca/collections/swob-stations?f=html)
- [SWOB-ML Product User Guide](https://dd4.weather.gc.ca/observations/doc/SWOB-ML_Product_User_Guide_v8.14_e.pdf)

The GeoMet station collection is a recent rolling service, approximately 30
days at review time, not a permanent raw SWOB archive. Mirror prospectively
using AMQP and retain raw XML, original URL, retrieval time, station metadata,
normalized record, and normalizer version.

Not every station reports visibility, cloud, or present weather. Treat
availability and observation method per field, not per station as a whole.

## ECCC Historical Climate Data

The official [Historical Climate Data portal](https://www.climate.weather.gc.ca/)
provides hourly, daily, and monthly station observations depending on period
and station.

Common hourly bulk pattern:

```text
https://climate.weather.gc.ca/climate_data/bulk_data_e.html
  ?format=csv
  &stationID=STATION_ID
  &Year=2024
  &Month=1
  &Day=1
  &timeframe=1
  &submit=Download+Data
```

Example:

```bash
curl -L \
  'https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=STATION_ID&Year=2024&Month=1&Day=1&timeframe=1&submit=Download+Data' \
  -o station_2024_01.csv
```

Discover station IDs through the official search. IDs and record series can
change after station moves or instrumentation changes.

Possible historical fields include visibility, weather, pressure,
temperature/dew point/RH, wind, precipitation, and cloud fields in selected
eras. Modern automated sites may omit cloud/visibility. Retain flags,
provisional status, station history, and missingness.

## Radar

Use [ECCC radar documentation](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_en/)
for current products. The ordinary public ECCC services are not documented as
a complete long-term raw-volume archive; contact ECCC for older scientific
products and mirror selected output prospectively.

NOAA's NEXRAD archive is fully accessible for US sites and can help where
coverage reaches toward Atlantic Canada:

- [NEXRAD archive](https://www.ncei.noaa.gov/products/radar/next-generation-weather-radar)
- [NCEI cloud access](https://www.ncei.noaa.gov/access/cloud-access)

Radar establishes precipitation/hydrometeor structure, not ordinary cloud
clearance:

```text
radar echo present -> likely poor/blocked
no radar echo -> cloud state unknown
```

## Marine observations

Use DFO/ECCC marine archives for upstream wind, air temperature, pressure,
sea-surface temperature, and waves:

- [DFO Marine Environmental Data Section](https://www.meds-sdmm.dfo-mpo.gc.ca/isdm-gdsi/index-eng.html)
- [Canadian marine buoy observations](https://www.canada.ca/en/environment-climate-change/services/general-marine-weather-information/observations/buoy.html)
- [NDBC historical data](https://www.ndbc.noaa.gov/historical_data.shtml)

NDBC example:

```bash
curl -O \
  'https://www.ndbc.noaa.gov/data/historical/stdmet/44027h2024.txt.gz'
```

Verify station ownership and completeness. Canadian platforms may be more
complete in MEDS/ECCC. Most buoys do not directly measure cloud base or
visibility, but they provide crucial marine-fog forcing variables.

### SmartAtlantic ERDDAP coastal buoy retrieval (St. John's, Holyrood, Placentia Bay)

The SmartAtlantic Alliance (Memorial University Marine Institute) hosts an ERDDAP
server with near-real-time and archived met-ocean buoy observations:

- **Server URL**: `https://www.smartatlantic.ca/erddap/index.html`
- **Key dataset IDs**:
  - `smartatlantic_st_johns`: St. John's Harbour Approach (Station 44140, 47.545° N, 52.613° W)
  - `smartatlantic_holyrood`: Holyrood, Conception Bay (47.459° N, 53.134° W)
  - `smartatlantic_placentia_bay`: Mouth of Placentia Bay (Station 44137, 47.017° N, 54.917° W)

#### Python retrieval example (ERDDAP REST API via pandas / requests)

```python
import pandas as pd

# Fetch last 24 hours of 10-minute meteorological data for St. John's buoy
dataset_id = "smartatlantic_st_johns"
base_url = f"https://www.smartatlantic.ca/erddap/tabledap/{dataset_id}.csv"

params = {
    "time>=": "2026-08-11T00:00:00Z",
    "time<=": "2026-08-12T23:59:59Z",
}
columns = "time,latitude,longitude,air_temperature,dew_point,relative_humidity,sea_surface_temperature,wind_speed,wind_direction,gust,air_pressure"
query_url = f"{base_url}?{columns}&time%3E={params['time>=']}&time%3C={params['time<=']}"

# Read directly into DataFrame (skipping units row in header)
df = pd.read_csv(query_url, skiprows=[1], parse_dates=["time"])

# Compute marine advection fog trigger: air dew point >= sea surface temperature
df["marine_fog_risk"] = df["dew_point"] >= df["sea_surface_temperature"]
```

### Newfoundland & Labrador 511 road and camera API

The NL Department of Transportation and Infrastructure exposes road-information
products and camera metadata/images for major Avalon highway routes:

- **Winter roads**: `https://511nl.ca/api/v3/get/winterroads`.
- **Other products**: v2 `cameras`, `ferryterminals`, `event`, `alerts`, and `windwarnings`.
- **Authentication**: documented developer-key query parameter, resolved only at runtime.
- **Throttling**: Maximum 10 requests per 60 seconds.
- **Limitation**: the public documentation does not expose raw RWIS or `weatherstations`.

#### Secret-safe request-shape example

```python
import os
import requests

api_key = os.environ["NL511_API_KEY"]
response = requests.get(
    "https://511nl.ca/api/v2/get/cameras",
    params={"key": api_key},  # Confirm the current parameter name in provider docs.
    timeout=10,
)
response.raise_for_status()
cameras = response.json()
```

Keep the authentication parameter name configuration-driven. Do not log the
prepared URL because query authentication puts the credential in that URL.

### NRCan St. John's Geomagnetic Observatory (`STJ`) space weather retrieval

Natural Resources Canada (CANMOS) operates the geomagnetic observatory in
St. John's (`STJ`). Real-time fluxgate magnetometer data indicates local
auroral electrojet disturbances in real time:

- **Portal**: [Space Weather Canada](https://www.spaceweather.gc.ca)
- **Data service**: `https://spaceweather.gc.ca/api/` and HTTP summary tables.

#### Python STJ magnetometer query example

```python
import requests
import pandas as pd

# Query provisional 1-minute magnetic field vectors for STJ
url = "https://spaceweather.gc.ca/api/geomag/data"
params = {
    "station": "STJ",
    "format": "json",
    "start": "2026-08-12T00:00:00Z",
    "end": "2026-08-12T23:59:59Z",
}
res = requests.get(url, params=params, timeout=15)
if res.ok:
    data = res.json()
    # Extracts X (North), Y (East), Z (Vertical) in nanoteslas (nT)
    # Rapid rate of change (dH/dt > 50 nT/min) signals active local auroral substorm
```

### Grand Banks offshore platform marine synoptic data extraction

Fixed oil platforms (Hibernia `VEP717`, Terra Nova `VCXF`, Hebron, SeaRose)
transmit hourly surface observations to ECCC and WMO. These are available in real
time via MSC Datamart and NDBC archives.

#### Python example: Fetching offshore platform marine XML from MSC Datamart

```python
import xml.etree.ElementTree as ET
import requests

# Example: Read latest marine surface observation from MSC Datamart for Hibernia
url = "https://dd.weather.gc.ca/observations/xml/SWOB-ML/latest/SWOB_VEP717_latest.xml"
res = requests.get(url, timeout=10)
if res.ok:
    root = ET.fromstring(res.content)
    # Extract temperature, dew point, air pressure, and wind speed/direction
    obs = {}
    for elem in root.findall(".//identification-elements/"):
        obs[elem.tag] = elem.attrib.get("value")
    # Upstream marine dew point and wind indicate incoming air masses 3-6h in advance
```

### ECCC CIOPS-East 2 km coastal SST and currents NetCDF extraction

The Coastal Integrated Ocean-atmosphere Prediction System (CIOPS-East) produces
daily 2 km hydrodynamic forecasts in NetCDF format on MSC Datamart and GeoMet.

#### Python example: Subsetting Avalon SST grid via xarray

```python
import xarray as xr

# Open CIOPS-East 2km NetCDF analysis directly or via OPeNDAP/HTTP
ds = xr.open_dataset("https://dd.weather.gc.ca/model_ciops/east/2km/latest/ciops_east_sst.nc")

# Crop to Avalon Peninsula bounding box [46.5°N–48.2°N, 54.5°W–52.5°W]
avalon_sst = ds["votemper"].sel(
    depth=0,
    latitude=slice(46.5, 48.2),
    longitude=slice(-54.5, -52.5),
)

# avalon_sst provides the 2 km skin temperature grid for high-res fog triggering
```

### CWOP & Personal Weather Station (PWS) consensus extraction with IQR filtering

To ingest crowdsourced observations across St. John's and Avalon communities
without being deceived by uncalibrated or sun-heated backyard sensors:

#### Python example: Outlier rejection on local PWS clusters

```python
import pandas as pd
import numpy as np

def compute_filtered_neighborhood_temperature(pws_readings: pd.Series) -> float:
    """Filter PWS readings using Interquartile Range (IQR) outlier rejection."""
    q25 = pws_readings.quantile(0.25)
    q75 = pws_readings.quantile(0.75)
    iqr = q75 - q25
    lower_bound = q25 - 1.5 * iqr
    upper_bound = q75 + 1.5 * iqr
    
    valid_readings = pws_readings[(pws_readings >= lower_bound) & (pws_readings <= upper_bound)]
    return float(valid_readings.median())
```

## Ceilometers and all-sky cameras

A uniform public archive of raw Atlantic Canadian airport ceilometer profiles
was not identified. Use METAR cloud bases now and pursue data agreements with
NAV CANADA, ECCC, airports, universities, or research campaigns later.

No authoritative continuous Atlantic Canada all-sky archive was identified.
Astraeus should create a standardized network with UTC-synchronized,
plate-solvable images and calibrated lens/orientation metadata. This is the
best practical source of directional astronomical transmission labels.

# Aerosol, smoke, and air-quality history

## CAMS global operational forecasts

The CAMS global atmospheric-composition forecast dataset is a genuine archive
of operational analyses and forecast cycles:

- [CAMS global atmospheric-composition forecasts](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts)

At review time it documented:

- 2015–present coverage;
- global 0.4-degree distribution;
- twice-daily five-day forecasts;
- hourly single-level and three-hourly multi-level fields;
- 60 model levels before 2019-07-07 and 137 afterward;
- GRIB with optional NetCDF conversion;
- many chemical species, aerosol types, AOD, and extinction products.

Conceptual ADS request:

```python
import cdsapi

client = cdsapi.Client(url="https://ads.atmosphere.copernicus.eu/api")
client.retrieve(
    "cams-global-atmospheric-composition-forecasts",
    {
        "date": ["2025-06-01/2025-06-02"],
        "type": ["forecast"],
        "data_format": "grib",
        "time": ["00:00"],
        "leadtime_hour": ["0", "3", "6", "12", "24", "48"],
        "variable": [
            "total_aerosol_optical_depth_550nm",
            "particulate_matter_2.5um",
            "black_carbon_aerosol_optical_depth_550nm"
        ],
        "area": [61, -70, 42, -50]
    },
    "cams.grib"
)
```

Generate a request from the live form before implementation because schema
keys evolve. CAMS upgrades create model-era discontinuities; preserve the
operational version.

## CAMS EAC4 reanalysis

EAC4 is a retrospective 4D-Var atmospheric-composition reanalysis beginning in
2003, with three-dimensional aerosols and reactive gases:

- [CAMS reanalysis documentation](https://confluence.ecmwf.int/display/CKB/CAMS%3A+Reanalysis+data+documentation)
- [Atmosphere Data Store](https://ads.atmosphere.copernicus.eu/)

Use for climatology, regime identification, historical features, and
gap-filled context. Do not use it as an archived forecast; it assimilates
observations and uses a consistent later system.

## ECCC RAQDPS and FireWork

ECCC's RAQDPS/GEM-MACH system forecasts PM2.5, PM10, ozone, NO2, SO2, CO,
aerosol components, clouds, meteorology, and related fields. FireWork adds
near-real-time wildfire emissions. Useful references:

- [2026 RAQDPS system description](https://gmd.copernicus.org/articles/19/4137/2026/)
- [RAQDPS-FireWork Datamart documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps-fw/readme_raqdps-fw-datamart_en/)

The difference between FireWork and standard RAQDPS PM2.5 can isolate the
modelled wildfire contribution in compatible model eras. RDAQA is an analysis,
not a forecast vintage.

Public operational retention is short/rolling unless ECCC explicitly states
otherwise. Mirror cycles now and ask ECCC whether five-year forecast retrieval
also covers the desired RAQDPS/FireWork products.

## AERONET

AERONET provides high-quality ground-based column aerosol optical depth:

- [AERONET](https://aeronet.gsfc.nasa.gov/)
- [Version 3 web-service help](https://aeronet.gsfc.nasa.gov/print_web_data_help_v3.html)

Example:

```bash
curl -G \
  'https://aeronet.gsfc.nasa.gov/cgi-bin/print_web_data_v3' \
  --data-urlencode 'site=SITE_NAME' \
  --data-urlencode 'year=2024' \
  --data-urlencode 'month=1' \
  --data-urlencode 'day=1' \
  --data-urlencode 'year2=2024' \
  --data-urlencode 'month2=12' \
  --data-urlencode 'day2=31' \
  --data-urlencode 'AOD20=1' \
  --data-urlencode 'AVG=10' \
  --data-urlencode 'if_no_html=1' \
  -o aeronet.csv
```

Verify the exact station name and period first. Atlantic Canada coverage is
sparse and intermittent.

Quality levels:

- Level 1.0: unscreened.
- Level 1.5: cloud-screened/quality controlled.
- Level 2.0: quality assured after calibration review.

Use Level 2 for final retrospective science and Level 1.5 cautiously for
broader coverage. Standard direct-Sun AOD is unavailable through opaque cloud
and normally at night; missing retrieval is not zero aerosol or an independent
cloud label.

## MODIS MAIAC

MCD19A2 supplies daily 1 km land AOD from combined Terra/Aqua processing:

- [NASA MAIAC dataset record](https://data.nasa.gov/dataset/modis-terraaqua-land-aerosol-optical-depth-daily-l2g-global-1km-sin-grid-v061-c3a26)
- [Earth Engine MCD19A2 catalogue](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD19A2_GRANULES)

Relevant fields include AOD at 0.47 and 0.55 micrometres, uncertainty, QA,
aerosol model, water vapour, and viewing geometry. Apply QA and never convert a
cloud-screened missing pixel to clean air.

## VIIRS aerosol

Relevant VIIRS aerosol archives begin in 2012 for SNPP and 2018 for NOAA-20,
depending on algorithm/product:

- [MODAPS VIIRS products](https://modaps.modaps.eosdis.nasa.gov/services/about/products/viirs-c1/index.html)
- [MODIS-to-VIIRS transition table](https://ladsweb.modaps.eosdis.nasa.gov/learn/modis-to-viirs-transition/MODIS-VIIRS_Transition.pdf)

Level-2 aerosol products are commonly around 6 km even though native imagery
is finer. Preserve collection, algorithm, QA, view geometry, and orbital
sampling information.

## GOES ABI aerosol optical depth

GOES ABI AOD provides frequent daytime clear-sky aerosol retrievals at roughly
2 km product resolution:

- [GOES AOD product](https://www.goes-r.gov/products/baseline-aerosol-opt-depth.html)
- [GOES AOD catalogue](https://catalog.data.gov/dataset/noaa-goes-r-series-advanced-baseline-imager-abi-level-2-aerosol-optical-depth-aod3)

It is useful for intraday smoke evolution but requires daylight and cloud-free
pixels and can be contaminated near cloud edges. Treat no retrieval as missing.

## NREL NSRDB: historical solar radiation and physical cloud property database

The National Renewable Energy Laboratory (NREL) [National Solar Radiation Database (NSRDB)](https://nsrdb.nrel.gov/)
provides serially complete 4 km $\times$ 4 km gridded half-hourly and hourly
solar radiation and atmospheric property records over the Americas (including
Newfoundland and Atlantic Canada) from 1998 to near-present.

It uses the Physical Solar Model (PSM v3 / v4) to retrieve solar irradiance and
cloud optical/physical properties from geostationary satellites (GOES-East).

### Key variables for Astraeus

```text
Solar Irradiance:
  DNI (Direct Normal Irradiance, W/m²)
  GHI (Global Horizontal Irradiance, W/m²)
  DHI (Diffuse Horizontal Irradiance, W/m²)
  Clearsky DNI, GHI, DHI (empirical baseline models)

Cloud & Atmospheric State:
  Cloud Optical Depth (COD, dimensionless)
  Cloud Top Height / Pressure (CTH, m / hPa)
  Cloud Type (e.g. Clear, Cirrus, Stratocumulus, Stratus, Deep Convection)
  Cloud Fill Flag (retrieval quality)
  Aerosol Optical Depth (AOD at 550 nm)
  Precipitable Water (PWAT, cm)
  Solar Zenith Angle (degrees)
  Surface Albedo
```

### Research and calibration role

1. **Direct-sun visibility calibration ([ECL26-CLOUD-002](../specv1/features/eclipse-2026-08-12/SCIENCE_SPEC.md#ecl26-cloud-002--restrict-quantitative-optical-claims))**:
   Correlate satellite-retrieved COD and DNI values across historical August
   afternoons to validate the threshold where direct solar disk visibility is
   extinguished ($DNI \to 0$), supporting the $1 - \exp(-\text{COD}/\mu)$ proxy.
2. **August afternoon cloud climatology**:
   Extract 25+ years of August 10–14 (17:00–19:30 UTC) records across Avalon
   Peninsula candidate coordinates to quantify empirical microclimate variance
   (e.g., probability of marine fog at Cape Spear vs. Conception Bay South).
3. **Aerosol baseline calibration**:
   Establish empirical AOD distributions for coastal Newfoundland air masses.

### Access mechanisms

- **NREL Developer REST API**: Extract point CSV time-series (1,000 requests/day free tier):
  `GET https://developer.nrel.gov/api/nsrdb/v2/solar/psm3-download.csv?lat=47.609&lon=-52.692&names=2023&api_key=DEMO_KEY`
- **AWS Open Data (S3)**: Bulk access to HDF5 (`.h5`) datasets at `s3://nrel-pds-nsrdb/` without API rate limits.

### Minimal retrieval example (HDF5 via Python)

```python
import h5py

# Open NSRDB PSM v3/v4 HDF5 file from local mount or S3
with h5py.File("nsrdb_2023.h5", "r") as f:
    # Coordinates array: (N_points, 2) -> [latitude, longitude]
    coords = f["coordinates"][:]
    # Find nearest index to Avalon seed origin (47.609, -52.692)
    # Extract DNI, COD, solar zenith angle, and cloud type time-series
    dni = f["dni"][:, site_idx]
    cod = f["cld_opd_dcomp"][:, site_idx]
    zenith = f["solar_zenith_angle"][:, site_idx]
    cloud_type = f["cloud_type"][:, site_idx]
```

### Critical caveats

- **Historical/Reanalysis only**: NSRDB is published retrospectively with a multi-month lag; it cannot be used for operational event-day forecasting.
- **4 km spatial grid**: Coarser than native GOES-16 ABI visible channels (0.5–1 km) and HRDPS (2.5 km).
- **Coastal boundary artifacts**: Satellite-derived coastal stratus and advection fog can have boundary retrieval artifacts near cold sea-surface margins.

## Surface air-quality observations

Use ECCC/provincial stations and [OpenAQ](https://docs.openaq.org/docs) for
surface PM2.5, PM10, ozone, NO2, SO2, and CO where available. OpenAQ normalizes
upstream networks but does not erase provider-specific QA or licensing.

Preserve:

```text
original provider and station
instrument/parameter
averaging interval and unit
raw and normalized value
quality flag
ingestion and revision time
licence/source metadata
```

Surface PM may miss elevated smoke and is not column optical depth.

## Fire detections

Potential historical inputs include NASA FIRMS MODIS/VIIRS active fires, the
Canadian Wildland Fire Information System, ECCC FireWork, and CAMS GFAS.

A fire detection is not an emission measurement:

```text
fire detection/radiative power
  -> fuel consumption and emission factors
  -> plume rise/injection height
  -> transport, chemistry, and deposition
```

Store algorithm and inventory versions because historical fire emissions may
be reprocessed.

# Commercial historical APIs

## Tomorrow.io

Tomorrow documents its historical product as a reanalysis blending past
short-range forecasts and final observations, with production delay. Premium
coverage extends back to 2000 depending on plan:

- [Tomorrow historical overview](https://docs.tomorrow.io/reference/historical-overview)
- [Historical and forecast coverage](https://support.tomorrow.io/hc/en-us/articles/5188370662932-Weather-Timeline-Historical-and-Forecast-Coverage)

It is not an archive of the exact forecast shown to users. Ask sales whether an
endpoint can return explicit `forecastInitializationTime`, `validTime`, lead,
and model version. Without those dimensions, it cannot validate old Tomorrow
forecasts.

## Meteomatics

Meteomatics provides observations, reanalysis, model data, and historical
products:

- [API getting started](https://www.meteomatics.com/en/api/getting-started/)
- [Response semantics](https://www.meteomatics.com/en/api/response/)
- [Historical weather API](https://www.meteomatics.com/en/weather-api/historical-data-weather-api/)

A generic valid-time query may change when a newer model run becomes available.
For true vintages, require explicit source, initialization, lead, version, and
contractual retention. Otherwise `historical` may mean reanalysis, observation,
or latest-model reconstruction for that valid time.

## Google Air Quality

Google offers current, forecast, history, and heatmap endpoints:

- [Google Air Quality REST API](https://developers.google.com/maps/documentation/air-quality/reference/rest)
- [Air-quality forecast](https://developers.google.com/maps/documentation/air-quality/forecast)

Google does not document its history as archived forecast vintages. Treat it
as a retrospective proprietary blend unless a contract says otherwise. Review
Google caching, storage, training, attribution, and derivative restrictions
before using it as a permanent research archive.

## Ambee, IQAir, Visual Crossing, and similar services

These providers offer combinations of station observation, gridded current
conditions, forecasts, reanalysis, and history. Do not infer forecast-vintage
semantics from the word `historical`.

Request a schema containing:

```text
issued_at
model_run or initialization_time
valid_at
lead_time
model_version
```

If only one timestamp exists, the result is probably an observation or
reconstruction. Also confirm station versus modelled value, revisions,
Canadian coverage, AOD availability, archival rights, and derived-output use.

# Fact-check test suite

## Forecast-vintage identity

Request:

- two issuance times for one valid time;
- one issuance time at multiple leads;
- the same request again after a week.

Pass only when initialization is explicit, both vintages remain available,
values are immutable, and model/version is identifiable.

## Revision detection

Hash historical responses daily for 30 days. If old records change, determine
whether QA updates, final observations, or reanalysis caused the revision.
Store first-seen, last-seen, revision identity, and both raw values.

## Observation-versus-model test

Query a location far from a station. A smooth hourly series is modelled or
interpolated, not a direct observation.

## Spatial-resolution test

Query a tight grid around one station and across terrain/coast boundaries.
Nearly identical adjacent fine-grid cells may indicate resampling of a coarser
model. Output grid spacing is not independent forecast resolution.

## Elevated-smoke test

Find an event with high satellite/AERONET AOD but low surface PM2.5. A provider
that reports uniformly clean air is surface-centric and inadequate for optical
transparency.

## Cloud-screening test

For satellite AOD and optical products, confirm that QA-rejected or cloudy
pixels stay missing. Never turn no retrieval into zero aerosol or clear sky.

## Model-era test

Retrieve dates before and after documented upgrades. Verify that model,
algorithm, grid, levels, field definitions, and DQFs are versioned and not
silently treated as one homogeneous series.

# Atlantic Canada validation design

## Initial period

Start with 2018 to present because it provides modern GOES-East coverage and a
manageable number of satellite/product eras. Split at least:

```text
2018 to 2021-11-29:
baseline GOES cloud-mask era

2021-11-29 onward:
enterprise cloud-mask era

GOES-19 transition:
separate platform/algorithm era
```

Use file metadata and NOAA notices for exact cutovers.

## Candidate airport anchors

Verify actual coverage before final selection:

```text
CYHZ Halifax
CYAW Shearwater
CYQM Moncton
CYFC Fredericton
CYSJ Saint John
CYYG Charlottetown
CYQY Sydney
CYQI Yarmouth
CYYT St. John's
CYDF Deer Lake
CYJT Stephenville
CYQX Gander
CYYR Goose Bay
```

Build field-by-field coverage statistics; not every site has complete cloud and
visibility reporting for the full period.

## Per-observation collocation

```text
station report
nearest GOES scan and time difference
parallax-corrected native pixel
3x3 and 5x5 neighborhood statistics
distance to observed cloud edge
upwind GOES transect
radar echo presence
marine upstream observations
forecast model/run/member/lead fields
```

## Labels

Fog positive:

```text
FG code
and/or visibility below threshold
and/or vertical visibility or very low ceiling
```

Fog negative requires valid good visibility, no fog/mist, and no confounding
obscuration. Missing or ambiguous observations are `unknown`.

For cloud base, retain all layer amounts. Lowest BKN/OVC can define aviation
ceiling, but vertical visibility is not a conventional cloud base. For GOES,
retain the four-class mask/probability, DQF, neighborhood, view geometry, and
algorithm era.

## Metrics

- Brier score and reliability.
- CRPS for continuous distributions.
- POD, FAR, CSI, ROC, and precision-recall.
- Fog onset and dissipation timing.
- Cloud-base MAE/bias and ceiling-category accuracy.
- Cloud-boundary displacement.
- AOD bias and missing/retrieval rate.
- False-clear rate.
- Recommendation rank regret.
- Performance by elevation angle, season, lead, coast/inland, day/night,
  model era, and source combination.

# Data model and storage

## Required normalized provenance

```json
{
  "source": "cams",
  "product": "global-atmospheric-composition-forecast",
  "data_semantics": "archived_operational_forecast",
  "model_version": "...",
  "initialization_time_utc": "...",
  "valid_time_utc": "...",
  "lead_hours": 24,
  "member": null,
  "retrieved_at_utc": "...",
  "parameter": "aod_550nm",
  "vertical_reference": "total_column",
  "value": 0.18,
  "unit": "1",
  "native_resolution": "0.4_degree",
  "quality_flags": [],
  "raw_checksum": "...",
  "licence": "...",
  "normalization_version": "..."
}
```

Observation records additionally require sensor/station, averaging period,
detection/censoring, and QA. Satellite retrievals require platform, collection,
viewing geometry, cloud/DQF flags, and algorithm version.

## Data lake layout

```text
raw/
  eccc/hrdps/{version}/{init}/...
  eccc/reps/{version}/{init}/{member}/...
  eccc/raqdps-firework/{version}/{init}/...
  ecmwf/ifs/{cycle}/{init}/{type}/{member}/...
  cams/forecast/{version}/{init}/...
  noaa/goes/{platform}/{product}/{year}/{day_of_year}/...
  noaa/gfs/{version}/{init}/...
  noaa/gefs/{version}/{init}/{member}/...

normalized/
  forecast_states/...
  reanalysis_states/...
  observations/goes/...
  observations/stations/...
  observations/aerosol/...

manifests/
  runs/
  field_catalogues/
  product_versions/
  licences/
  missing_data/
```

Keep raw immutable files in object storage and analysis-ready Atlantic subsets
in a chunked format such as Zarr. Preserve raw GRIB/NetCDF before
normalization.

# Acquisition plan

## Phase 1: start forward archival immediately

Archive every new selected:

- HRDPS run.
- REPS run/member.
- RAQDPS/FireWork run.
- CAMS forecast cycle.
- GOES cloud/AOD product.
- SWOB and METAR/SPECI report.
- Product manifest, field inventory, and checksum.

## Phase 2: request ECCC history

Priority:

1. HRDPS selected cloud/fog fields for five years.
2. REPS selected members/fields.
3. RAQDPS/FireWork.
4. RDPS.
5. GDPS.
6. GEPS only where TIGGE is insufficient.

Request an Atlantic subset and a validation sample before approving the full
order.

## Phase 3: build retrospective truth

- GOES ABI from NOAA AWS/CLASS.
- NCEI Global Hourly and METAR/SPECI.
- ECCC Historical Climate.
- ERA5 pressure/model levels.
- CAMS EAC4.
- AERONET/MAIAC/VIIRS/GOES AOD.
- Marine observations and radar context.

## Phase 4: add independent forecast baselines

- GFS and GEFS historical forecasts.
- ECMWF IFS/ENS MARS subsets.
- AIFS recent archive.
- HRRR where its domain is suitable.
- RRFS only as explicitly labelled prototype or retrospective data.

## Phase 5: evaluate commercial archives

Only treat a commercial endpoint as forecast history after it passes the
vintage-identity and immutability tests. Obtain contractual storage, training,
and derived-output rights before building a permanent dataset from it.

# Key guardrails

- Datamart is not ECCC's five-year historical archive.
- ERA5 and CAMS EAC4 are not operational forecast vintages.
- `Historical` does not imply `forecast as issued`.
- Valid time alone cannot identify a forecast.
- AWS object availability does not always guarantee archival permanence.
- GOES cloud top is not cloud base.
- GOES/FLS is model-assisted retrieval evidence, not independent truth.
- Radar absence does not mean clear sky.
- AERONET missing data during cloud does not mean clean air.
- Surface PM2.5 is not column AOD.
- `CLR` is observation-system-censored, not proof of an entirely cloudless sky.
- Model, product, grid, level, and DQF semantics change over time.
- Analysis forecast hour zero is not a direct observation.
- Hydrometeors interpolated to pressure levels may differ from native model
  levels.
- Never discard accumulation intervals, ensemble members, or raw checksums.

## Final recommendation

The durable historical system should combine:

```text
immutable self-archived Canadian forecasts
    + requested ECCC five-year forecast extracts
    + NOAA/ECMWF/CAMS archived forecast vintages
    + GOES spatial observations
    + independent ground visibility/cloud-base observations
    + aerosol column and surface observations
    + all-sky astronomy-specific labels
```

Start archiving live forecast runs now. That decision has greater long-term
value than choosing any single reanalysis or commercial historical API.
