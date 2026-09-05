# Non-AI research source audit, 2026-09-05

Spec-Impact: none. Read-only audit, no implementation or source admission. Research claims below are dated repository evidence, not fresh live probes. Source families/products are grouped, not counted as independent providers. Code boundary is experiment ingest adapters, not a production Astraeus deployment.

## Key corrections

- The old 59-source registry and old 209-source research gap analysis are not current implementation inventories. `registry/source_data.py` materializes newer records with explicit admission/status policy; many remain catalogued without adapters.
- HRDPS/RDPS **nine-level low-cloud GRIB pressure profiles** are implemented (`ingest/registry.py:94`). Expanded deterministic **GeoMet WCS, 40/80/120m boundary-layer stack, seeing and transparency remain missing** despite `registry/fields.py:1089,1163` marking them stored. `eccc_geomet.py:2603,2617` are WMS GetFeatureInfo point adapters, not WCS, and are NOT registered (`MODEL_SOURCE_OWNER="eccc_datamart"`, :2644). REPS WCS exists only as a gated partial adapter and its default GeoTIFF reader raises unavailable (`eccc_geomet_ensemble.py:216`). The old “no vertical profile” statement is partly obsolete; the expanded WCS gap is real.
- GOES-19 **ACMF cloud mask and ACHAF cloud-top height** are implemented (`ingest/adapters/goes_abi.py:71`, `:464`, `:609`); the richer admitted satellite product list has not landed in the adapter.
- RTSW adapter exists and registers (`ingest/adapters/swpc.py:260`, `:472`), even though registry status says catalogued. It extracts Bt/Bz and aggregate spacecraft identity, but not full vector, per-row spacecraft/QC or plasma. Do not label all RTSW absent.
- The newer September 2 SmartAtlantic probe reports St. John's live with <22-minute latency; registry's old May 2 cutoff is stale (`docs/research/wayfinder/fog-cloud-line-of-sight-sources.md:174`). ECCC/DFO buoy lack is **not** lack of every local buoy. SmartAtlantic ingestion still absent.
- CYYT ProgTephi/ObsTephi direct files withdrawn, standalone FireWork superseded, REWPS Great Lakes-only. These are unavailable/superseded/rejected, not pending implementation tasks.

## Missing / partial research source families beyond current usable adapters

Paths abbreviated: **A** = `experiments/st-johns-weather-map/docs/research/01-atmospheric-nwp-satellite.md`; **M** = `.../02-marine-ocean-ice-hydrology.md`; **L** = `.../03-local-climate-commercial.md`; **H** = `docs/research/historical-data-retrieval.md`; **W** = `docs/research/wayfinder/`; **N** = `docs/research/newfoundland-operational-data-improvements.md`. All IDs in appended registry list are exact.

### Local/surface/aviation/road/hazard

| Source/product | Current gap / caveat | Research |
|---|---|---|
| ECCC SWOB partners `nl-water` (Pippy Park, Conception Bay South), `nl-firewx`, `dfo-moored-buoys`, `dnd-ccg-lighthouse` | Existing SWOB adapter uses OGC station observations; no dedicated Datamart SWOB partner XML discovery/ingestion. Preserve embedded all-rights-reserved attribution; newer admission may allow experimental uncalibrated handling but does not create adapter. | N:41; L:410,445,460,471; M:844 |
| ECCC citypage_weather St. John's official forecast/UV/category | No adapter/record. | L:310; W/running-sources.md:27 |
| ECCC MetNotes | No adapter; research found empty directory. Reconfirm payload before implementation. | L:332; N:41 |
| Raw WMO alphanumeric bulletins including FD winds/temperatures aloft | No distinct adapter; mostly duplicates existing normalized products. | L:322,969 |
| ECCC IWXXM METAR/TAF/SIGMET | Raw XML counterpart absent; AWC METAR/TAF JSON adapters exist. | L:377; N:41 |
| AWC SIGMET/AIRMET and PIREP/AIREP | Catalogued, no adapters. | N:41; registry |
| Mode-S weather via ADSB.lol | No adapter; research verified winds/OAT in aircraft records. Not the same as raw position tracking or a calibrated station. Earlier A research “no network” is superseded. | L:937; A:442 |
| CoCoRaHS including CAN-NL-2 | No adapter; manual precipitation/snow observations, network licence/attribution and QC still required. | L:595 |
| CWOP/APRS, Netatmo, Weather Underground | Catalogued, no adapters; PWS uncalibrated. | L:646–794; registry |
| WeatherFlow/Tempest, AWEKAS, PWSweather, Weathercloud | Research-only optional personal networks; account/owner/access and local station availability unresolved. | L:668,677 |
| NOAA MADIS including aircraft/mesonets | Credential-required, no adapter; distribution tier can prohibit aircraft redistribution. | A:213; L:657 |
| NL 511 winter roads, cameras, ferryterminals, event, alerts, windwarnings | Credential-required no adapter; permissions and independent endpoint freshness/caching needed. Raw RWIS is not available. | N:62; W/running-sources.md:128 |
| ECCC thunderstorm outlook, hurricane products, integrated nowcasting/SCRIBE matrices, HRDPA-watershed | No adapters; exact machine collection and valid availability need confirmation. Radar/flash **extrapolations** also absent although observed radar/lightning adapters exist. | L:360,368; registry source comments:65 |
| ECCC hydrometric real-time + Water Office CSV | Catalogued no adapter; archive is separate below. | M:797,834 |
| Provincial hydrometric/WRMD acquisition | Catalogued no adapter; municipal equivalent unavailable. | M:844; N:41 |

### Satellites, upper air, radar

| Source/product | Current gap / caveat | Research |
|---|---|---|
| VIIRS JRR CloudBase, CloudHeight, CloudMask, CloudPhase, CloudCoverLayers, CloudDCOMP, CloudNCOMP across NOAA20/21/SNPP | No adapter or explicit source registry family. Strong missing near-nadir cloud/fog evidence. Cloud-base retrieval alone must not be treated as validated surface fog truth. | A:163,425 |
| NUCAPS EDR (CrIS+ATMS retrieved profiles), including BUFR variants | No adapter/record. Clear/cloudy retrieval QC and footprint matter. | A:163,425 |
| ATMS SDR/TDR/BUFR, CrIS FS SDR | No adapter; raw radiances high effort and research prefers NUCAPS retrievals. | A:163 |
| VIIRS M/I SDR and Day-Night Band raw radiances | Missing operational satellite input; separate from static night-lights composites handled by root. | A:163 |
| JPSS Blended TPW, Rain Rate, Percent-of-Normal TPW | No adapter/record. | A:163 |
| GOES ABI additional products: CMI bands 2/7/13/14/15; cloud-top temperature ACHTF, phase ACTPF, optical depth CODF/COD2KMF, particle size CPSF, TPWF/TPWC, vertical moisture/temperature LVMPF/LVTPF, stability DSIF, SSTF, derived motion winds DMWF/DMWVF, cloud-cover layers CCLF, rain RRQPEF | Adapter only ACMF+ACHAF; these remain missing even where catalogue fields are admitted. Recent detailed fog research supersedes older broad recommendations (day/night, product/domain availability). | A:141; W/fog-cloud-line-of-sight-sources.md:50 |
| GOES GLM lightning | No adapter; ECCC gridded lightning exists but different observation/product. | A:198 |
| Sentinel-3 SLSTR/OLCI, Sentinel-5P TROPOMI | No adapter; Copernicus downloads/access/QA vary. TROPOMI mainly air-quality, SLSTR SST relevant to fog. | A:163 |
| MODIS Aqua/Terra cloud products via LAADS | Missing, lower priority than VIIRS; aerosol products listed separately. | A:163 |
| GPM IMERG (Early/Late/Final) | Missing; account-gated NRT; open-ocean precipitation use, not superior local radar. | A:163 |
| ASCAT scatterometer ocean winds | Missing; provider/API-key/path verification outstanding. | A:181 |
| Holyrood CASHR per-site radar/DPQPE/dual-pol products | Existing national-composite point adapter does not implement native per-site volume/product path. Raw Canadian Level-II-like open volumes not confirmed. | A:233 |
| Radiosondes via IGRA/UWyoming archives / alternative upper-air providers | Not operational CYYT feed; nearest launch representativeness matters. | A:213 |

### Ocean, marine, ice and coastal hazard

| Source/product | Current gap / caveat | Research |
|---|---|---|
| ECCC CIOPS-East; RIOPS ocean/ice; RDWPS/GDWPS waves; GDSPS/RESPS surge | All catalogued no adapters. RIOPS/CIOPS numeric WCS proven in later research; domain checks remain admission conditions for waves. | M:303,375,685; W/fog-cloud-line-of-sight-sources.md:138 |
| GIOPS global ocean; GEWPS global ensemble waves | Research-only missing. GEWPS differs from rejected Great-Lakes REWPS. | M:338,396 |
| NOAA RTOFS; HYCOM | Missing independent ocean model; HYCOM dataset route only partially verified. | M:360 |
| Copernicus Marine global physics, waves, OSTIA, and marine products | Missing direct integration. **OSTIA anonymous CloudFerro Zarr verified later**, correcting old blanket credential assumption; product-specific access rules. | M:360,934; W/fog-cloud-line-of-sight-sources.md:138 |
| NOAA GFS-Wave native / Open-Meteo GFS-Wave | Missing adapter; aggregator record exists. | M:408; registry |
| SmartAtlantic St. John's + Holyrood/other validated NL buoys | Catalogued no adapter; station-by-station live validation. Tide wharf archive is dormant. | M:450,529; W/fog-cloud-line-of-sight-sources.md:174 |
| CIOOS Atlantic: Station27 CTD, AZMP/NAFC cruise profiles, DFO Sutron shore stations, Bonavista/Trinity gliders, satellite chlorophyll/bloom series, Grand Banks WSP waypoint3 wave buoy archive | No generic ERDDAP adapter; do not count SmartAtlantic mirror as independent observation source. Some are delayed/archived only. | M:450 |
| Argo (including synthetic BGC) | No adapter; freely accessible, sparse float profiles. | M:552 |
| Ocean Networks Canada / OceanSITES | Missing; local applicability/access not established. | M:582,610 |
| DFO IWLS observed/predicted/forecast tides/water levels | Catalogued no adapter; product distinctions important. | M:621 |
| ECCC coastal flooding risk index NLWO_NL | No adapter/explicit registry ID; event-driven empty response legitimate. | M:654 |
| CCG NAVWARN WFS | Catalogued no adapter. | N:85 |
| International Ice Patrol iceberg limits; CIS SIGRID3 ice charts and iceberg charts | No adapters/records; seasonal/no-ice absence legitimate. | M:117 |
| PolarWatch VIIRS/AMSR2 ice concentration and NOAA/NSIDC CDR | Missing; Avalon grid coverage not proved in old research. | M:240 |
| OSI SAF ice drift OSI405 | Missing, coarse Arctic focused low value. | M:240 |
| Sentinel1 SAR/OCN ice/icebergs/ocean wind/waves | Missing; registered downloads/access/processing required. | M:249 |
| JPL MUR SST; NOAA OISST v2.1; Coral Reef Watch SST | Missing analysis/observation alternatives; MUR latency days, not current skin SST. | M:722,758,781 |
| GEBCO / CHS NONNA bathymetry | Missing static environmental input. | M:964 |
| DFO AIS vessel density | Missing historical traffic-context data; no live AIS implied. | N:85 |
| Commercial/local receiver live AIS | Partnership/licence acquisition, no public redistributable feed confirmed. | N:85 |

### Aerosol, air quality, fire, running weather

| Source/product | Current gap / caveat | Research |
|---|---|---|
| RAQDPS surface/column PM2.5, PM10, ozone, wildfire-smoke plume; RDAQA preliminary and FW analysis | Catalogued but no adapter. Standalone FireWork is superseded, not missing. | W/transparency-seeing-sources.md:50 |
| CAMS global atmospheric-composition forecast direct ADS | Credential-required no adapter. | W/transparency-seeing-sources.md:66 |
| Open-Meteo CAMS AOD and particulate/gas feeds | Catalogued no adapter, reprocessed output; aerosol AOD specifically fills keyless gap. Particulates admission does not imply needed duplicate. | registry; W/open-meteo-endpoints.md |
| NASA MAIAC MCD19A2; VIIRS Deep Blue AERDB NOAA20/SNPP regular and NRT; VIIRS JRR AOD/ADP; GOES ABI AOD | No dedicated adapter; broad Earthdata-aerosol record credential-required does not implement all these. | W/transparency-seeing-sources.md:67; H:1113,1124,1136; A:163 |
| AERONET | Missing AOD validation archive/feed, local station availability separate. | H:1074 |
| NL StJohns provisional PM2.5/ozone CSV + validated NAPS annual archive | CSV catalogued no adapter, uncalibrated/provisional; archive no integration. AQHI implemented index is not concentrations. | W/running-sources.md:147 |
| OpenAQ, PurpleAir | Credential-required no adapters, sensor QC and per-provider licence. | L:796 |
| CWFIS WFS hotspots, daily hotspot CSV, CFFEPS emissions; NASA FIRMS MODIS/VIIRS | No adapters. CWFIS umbrella hotspot ID catalogued, not operational; daily CSV/emissions distinct acquisition forms. | W/transparency-seeing-sources.md:74; H:1239 |
| BlueSky Canada/firesmoke.ca | Viewer research, no verified documented machine feed or licence. | W/transparency-seeing-sources.md:78 |
| Expanded deterministic GeoMet WCS: full 28/31-pressure-level profiles; 40/80/120m temperature/RH/dewpoint/specific humidity/winds; BLH, skin/radiative temperature, ice cover; WEonG sky state; RDPS seeing/transparency | Missing deterministic WCS retrieval despite declared `stored` fields; existing nine-level GRIB low-profile and three steering levels do not close this. | A:398; W/geomet-wcs-inventory.md; `eccc_geomet.py:2644` |
| ECCC HRDPS/RDPS/GDPS UV all-sky/clear-sky/daily max; Humidex; wind chill | No named catalogue field or adapter selectors found in current `fields.py` (surface WCS implementation does not mean every coverage implemented). | W/running-sources.md:24 |
| LSA SAF satellite radiation via Open-Meteo | Catalogued no adapter; separate from rejected model beam-split endpoint. | registry; W/open-meteo-endpoints.md |
| Aerobiology Research Laboratories pollen / The Weather Network licensed pollen | Research-only commercial acquisition blocked; open CAMS pollen out-of-region. | W/running-sources.md:109 |

### Historical environmental / verification (all distinct from live provider adapters)

- ARCO-ERA5 anonymous Zarr; CDS ERA5 single-levels/pressure-levels, ERA5-Land and new point time-series collections: no historical acquisition/verification integration. A:110.
- ECCC RDRS v2.1 / CaSR v3 via CaSPAr/hpfx: missing, download endpoint/licence needs confirmation. A:110.
- NASA MERRA2: missing; old goldsmr4 OPeNDAP dead, use current Earthdata path after verification. JRA3Q: missing, NC-SA licence limitation. NCEP R1/R2/20CR research-only century/coarse context, low relevance. A:110.
- ECCC climate station inventory, hourly/daily/monthly records, 1981–2010 and 1991–2020 normals, AHCCD, LTCE, bulk climate CSV and legacy bulk endpoint: no adapter. These access paths overlap datasets, not independent truth. L:55–285.
- CanGRD historical anomalies; SPEI and climate indices; CanSIPS hindcast/seasonal archives: no adapter. CMIP5/6/CanDCSU6/DCS projections explicitly out of operational horizon. L:286–305.
- NOAA NCEI ISD/Global Hourly, GHCN-Daily; Iowa Environmental Mesonet ASOS/AWOS; Meteostat bulk historical: no adapter; overlapping surface observations require provenance/deduplication. L:685–783.
- Open-Meteo Historical Forecast, Previous Runs, Single Runs, Historical Weather ERA5/ERA5-Land: no archival/verification adapters. Distinguish issued forecasts from reanalysis. L:983–1017.
- Retrospective native ECCC HRDPS/RDPS/GDPS/REPS/GEPS archive requests and self-archive expansion, GEPS TIGGE, ECMWF IFS/ENS MARS/TIGGE, NOAA GFS/GEFS historical vintages: current real-time decoders do not implement the documented backfill/verification acquisition workflows. H:154–542.
- Historical GOES16/19 ABI eras and NOAA CLASS, historical SWOB/ECCC radar, NCEI METAR archives: live GOES/SWOB/radar adapters insufficient for historical batch QA and era provenance. H:544–802.
- DFO MEDS/ISDM wave archive; CIOOS historical buoys/profiles; PSMSL station393 monthly/annual mean sea level; hydrometric archives: missing historical integration, several access/licence caveats. M:590,700,797; H:802.
- CAMS EAC4 reanalysis and historical composition forecasts; past RAQDPS/FireWork archives; AERONET/MODIS-MAIAC/VIIRS aerosol; surface air-quality/NAPS and fire archives: missing historical acquisition. H:999–1255.
- NREL NSRDB solar irradiance/cloud optical depth/height/AOD/PWAT historical calibration: missing; research/calibration only, not operational forecast. H:1147.
- WMO LC-DNV and ECMWF forecast-quality scorecards: contextual verification references, not local prediction feeds; no import. L:1018–1034.

### Space weather

Missing catalogued adapters: RTSW plasma, propagated solar wind, one-minute Kp, SWPC alerts/watches/warnings, NOAA scales, GFZ Hp30, GOES magnetometer, GOES X-ray, Kyoto Dst via SWPC. Reference `W/space-weather-sources.md:46`; exact registry IDs below.

Research-only missing: RTSW spacecraft ephemerides, Geospace model Dst; full SWPC 3-day text forecast (Kp JSON overlaps existing adapter), 27-day outlook; direct Kyoto Dst and AE/AU/AL/AO; GFZ Kp and Hp60; NRCan Atom bulletins; GOES instrument-sources metadata; CCOR1 coronagraph index/FITS; ACE hourly fallback; SuperMAG (access terms unresolved, `docs/research/data-sources.md:281`). These are not all equal priorities: imagery/context and >14-day products differ from actionable aurora evidence.

Blocked/intentional: NRCan STJ magnetometer partnership-only (permission pending); Space Weather Canada regional forecast link-only; SOHO/SDO/SUVI imagery link-only; STEREO-A and model hourly Kp unavailable/stale; AuroraWatch UK irrelevant local sector; Aurorasaurus endpoint unavailable and uncalibrated reports. Current Kp/OVATION adapters already exist; do not call these missing.

### Cameras

Three camera provider families are catalogued partnership-only, no ingest adapter: CCG Fort Amherst/StJohnsBase/Sir Humphrey Gilbert Building; City New Gower/Middle Pond/Shea Heights/Thorburn/Windsor Lake/Kenmount; NTV StJohnsSky/QuidiVidi/Downtown/GeorgeStreet/AdmiralsGreen/LogyBay/StPhilipsBellIsland/PortdeGrave. Individual YAML records exist in `registry/cameras/` but no permissioned frame ingestion/CV pipeline. NAV CANADA NC-SPACES and NL511 camera access credential-required. CBC harbour/The Rooms stream has no reuse; Windy/Webcams.travel are credentialed aggregators with unnamed operators, not owned cameras. `W/camera-inventory.md:32`. MUN, Marine Institute, Parks Canada and Port sites supplied no usable camera feed.

## Exclusions / unresolved research leads, not ready implementation backlog

- Dead CYYT sounding paths; standalone RAQDPS FireWork; stale STEREO-A and hourly Kp; nonexistent raw NL RWIS; unavailable municipality hydrometrics/closure API; no public Grand Banks offshore-platform weather; MUN/GEO Centre station display-only/no API; metnotes empty.
- CERRA/CARRA, European convection-permitting models, NOAA HRRR/NAM-CONUS/NBM-CONUS, MRMS, Himawari and Great Lakes REWPS do not cover intended region. RAP/NAM parent domains require checks; NOAA RRFS eventual relevant domain not established.
- CAPS/CAPS-Ocean domain research conflicts (older rejects, newer WCS capabilities observed); no local numeric proof, do not silently admit.
- OpenSky anonymous no data/met schema; ADSB Exchange restricted; EMADDC Europe only (different from working ADSB.lol Mode-S).
- NSIDC hemispheric extent and coarse OSI SAF drift low local value; satellite altimeter SWH Jason3/Sentinel6/SWOT/CryoSat2 research-only validation and unverified local retrieval; SMAP/SMOS soil moisture low local utility.
- C-CORE Ice Chart commercial/registered route not confirmed; Hibernia/TerraNova/WhiteRose/Hebron partnership-only. MEOPAR and OFI fund research, they are not independent feeds.
- Seasonal SEAS5/EC46/CanSIPS and CMIP projections are research-context possibilities, not 14-day forecast substitutes. Existing rejected Open-Meteo routes remain rejected.

## Current registry states for scoped non-AI sources

The table is generated from `registry/source_data.py` at audit time. `catalogued` is not implemented. `implemented-unverified` is adapter-level status, not deployment/live verification. Exact adapter presence must overrule stale registry prose, especially RTSW.

| Source ID | Current registry status |
|---|---|
| `eccc-hrdps` | implemented-unverified |
| `eccc-hrdps-weg-prognos` | catalogued |
| `eccc-rdps` | implemented-unverified |
| `eccc-reps` | implemented-unverified |
| `eccc-gdps` | implemented-unverified |
| `eccc-geps` | catalogued |
| `eccc-integrated-nowcasting` | catalogued |
| `eccc-hrdpa` | catalogued |
| `eccc-rdpa` | catalogued |
| `eccc-hrepa` | catalogued |
| `eccc-hrdlps` | catalogued |
| `eccc-caldas` | catalogued |
| `eccc-ciops-east` | catalogued |
| `eccc-riops` | catalogued |
| `eccc-rdwps` | catalogued |
| `eccc-gdwps` | catalogued |
| `eccc-rewps` | rejected |
| `eccc-gdsps` | catalogued |
| `eccc-resps` | catalogued |
| `eccc-swob` | implemented-unverified |
| `eccc-radiosonde` | unavailable |
| `eccc-radar` | implemented-unverified |
| `eccc-lightning` | implemented-unverified |
| `eccc-cap-alerts` | implemented-unverified |
| `eccc-thunderstorm-outlooks` | catalogued |
| `eccc-hurricane-products` | catalogued |
| `eccc-aqhi` | implemented-unverified |
| `eccc-raqdps` | catalogued |
| `eccc-rdaqa` | catalogued |
| `eccc-wildfire-hotspots` | catalogued |
| `eccc-raqdps-firework` | superseded |
| `eccc-marine-buoys-synop` | catalogued |
| `eccc-marine-forecasts-alerts` | catalogued |
| `ccg-navwarn` | catalogued |
| `eccc-hydrometric` | catalogued |
| `nl-air-quality-csv` | catalogued |
| `ecmwf-ifs` | implemented-unverified |
| `ecmwf-ens` | implemented-unverified |
| `noaa-gfs` | implemented-unverified |
| `noaa-gefs` | implemented-unverified |
| `dwd-icon-global` | implemented-unverified |
| `dwd-icon-eps` | unavailable |
| `noaa-goes-east` | implemented-unverified |
| `copernicus-cams` | credential-required |
| `nasa-earthdata-aerosol` | credential-required |
| `noaa-rap` | catalogued |
| `noaa-nam` | catalogued |
| `noaa-swpc-kp` | implemented-unverified |
| `noaa-swpc-rtsw` | catalogued |
| `noaa-swpc-ovation` | implemented-unverified |
| `noaa-swpc-plasma` | catalogued |
| `noaa-swpc-propagated-solar-wind` | catalogued |
| `noaa-swpc-kp-1m` | catalogued |
| `noaa-swpc-alerts` | catalogued |
| `noaa-swpc-scales` | catalogued |
| `gfz-hp30` | catalogued |
| `noaa-goes-magnetometer` | catalogued |
| `noaa-goes-xray` | catalogued |
| `noaa-swpc-kyoto-dst` | catalogued |
| `noaa-swpc-stereo-a` | unavailable |
| `noaa-swpc-kp-hourly-prediction` | unavailable |
| `nrcan-stj-magnetometer` | partnership-only |
| `space-weather-canada-regional` | link-only |
| `nasa-soho-sdo-goes-suvi-imagery` | link-only |
| `awc-metar-speci` | implemented-unverified |
| `awc-taf` | implemented-unverified |
| `awc-sigmet-airmet` | catalogued |
| `awc-pirep-airep` | catalogued |
| `smartatlantic-st-johns` | catalogued |
| `smartatlantic-other-validated` | catalogued |
| `dfo-iwls` | catalogued |
| `nl-511` | credential-required |
| `nl-511-rwis` | unavailable |
| `nav-canada-weather-cameras` | credential-required |
| `ccg-harbour-cameras` | partnership-only |
| `city-st-johns-road-cameras` | partnership-only |
| `ntv-cameras` | partnership-only |
| `noaa-madis` | credential-required |
| `raw-cwop-pws` | catalogued |
| `purpleair` | credential-required |
| `openaq` | credential-required |
| `netatmo` | catalogued |
| `weather-underground` | catalogued |
| `provincial-hydrometric` | catalogued |
| `municipal-hydrometric` | unavailable |
| `openmeteo-cams-aod` | catalogued |
| `openmeteo-lsa-saf-radiation` | catalogued |
| `openmeteo-gfs-wave` | catalogued |
| `openmeteo-air-quality-particulates` | catalogued |
| `openmeteo-marine-currents-sealevel` | catalogued |
| `openmeteo-glofas` | catalogued |
| `openmeteo-marine-sst` | rejected |
| `openmeteo-uv-index` | rejected |
| `openmeteo-pollen-ammonia` | rejected |
| `openmeteo-aqi-indices` | rejected |
| `openmeteo-beam-split` | rejected |
| `openmeteo-climate-cmip6` | rejected |
| `openmeteo-seasonal-seas5` | rejected |

## Final code verification correction

RTSW uses the current `json/rtsw/rtsw_mag_1m.json` endpoint (`swpc.py:52`), not a dead legacy URL. This is implemented partial magnetometer ingestion; full per-row source/QC/vector preservation is missing. Do not claim endpoint repair is needed based only on old research.

Additional restricted lightning leads: Blitzortung/LightningMaps raw strokes participant-only; WWLLN institution agreement; Vaisala GLD360/NLDN and Earth Networks/Xweather paid. They are research exclusions rather than ready missing integrations (A:198).
