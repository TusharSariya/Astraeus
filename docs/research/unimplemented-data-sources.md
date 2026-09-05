# Researched data sources that are not yet implemented

Audited September 5, 2026. Repository baseline: `execution/activity-profiles`
at `9af2aaf`, with the current source registry and ingestion code inspected.
This is non-normative research, not a source-admission decision.

## Result

**WeatherNext 3 and NVIDIA FourCastNet 1/3 are researched and proposed, but
neither has an ingestion/inference implementation or a source-registry entry.**
They are part of a much larger unfinished source backlog.

The existing [Optional North Atlantic forecast-centre evidence proposal](../../experiments/st-johns-weather-map/openspec/changes/optional-north-atlantic-models/proposal.md)
already covers WeatherNext 3, Earth-2/FourCastNet, RAP/NAM and additional native
forecast centres. All of its [implementation tasks](../../experiments/st-johns-weather-map/openspec/changes/optional-north-atlantic-models/tasks.md)
are unchecked. This planning work should be reconciled and reused, rather
than recreated or mistaken for implemented integrations.

Three subagents audited AI/commercial research, environmental research, and
the complete registry/dispatch path. The parent checked geospatial and
celestial research and reconciled exceptions. This audit covers the research
in `docs/research/` and the weather experiment's `docs/research/`, against
current implementation rather than the older inventory snapshots. No existing
`graphify-out/graph.json` was found; findings were traced directly to files.

## What the 118 registry records actually represent

| Implementation state from code inspection | Source IDs | Meaning |
| --- | ---: | --- |
| Ordinary discovery/retrieval path | 14 | Code exists; this audit does not establish deployment or fresh live success |
| No registered ingestion adapter | 95 | Includes catalogued, credential-gated, partnership, rejected, unavailable and retired entries |
| Partial ensemble implementation | 4 | Member assembly exists, but discovery is unfinished and scheduling disabled |
| Nonpublishing placeholder | 2 | Registered classes whose discovery/retrieval always fail |
| Disabled adapter awaiting reimplementation | 1 | SWPC real-time solar wind |
| Image-only proxy | 1 | HRDPS WEonG liquid/ice fog images; numeric ingestion absent |
| Static artifact and calculation path | 1 | JPL DE442 is implemented outside the scheduler |
| **Total** | **118** | Research-only candidates outside the registry are additional |

The 95 adapter-absent records split into **59 catalogued, 10
credential-required, 4 partnership-only, 3 link-only, 9 unavailable, 9 rejected,
and 1 superseded**. They are not 95 ready-to-build tasks. A credential-required
entry without an adapter needs engineering as well as access.

The 14 ordinary paths are HRDPS, RDPS, GDPS, SWOB, radar, lightning, CAP alerts,
AQHI observations, GFS, GOES-East, SWPC Kp, SWPC OVATION, AWC METAR/SPECI and
TAF. A working family does not imply every researched product in that family
is implemented. DE442 is separately implemented; it must not be counted as
missing just because the registry calls it `catalogued`.

## Principal unfinished families

| Family | Named missing or partial integrations | State and consequence |
| --- | --- | --- |
| Google AI weather | WeatherNext 3; native WeatherNext 2; Open-Meteo WeatherNext 2 | WN3 is research/proposal-only. WN2 has catalogue records but no adapters. Direct WN3 clouds and reseller-generated WN2 clouds are different evidence |
| NVIDIA and other AI weather | FourCastNet 1/3 local; hosted FourCastNet/NIM; NOAA AI-GFS/AI-GEFS; NOAA AIWP archive; Aurora, GraphCast, Pangu, GenCast, NeuralGCM, FuXi, FengWu, ArchesWeather | No integration found. Self-run checkpoints produce generated-here evidence; NOAA-hosted outputs are distinct retrieval paths. Earth2Studio is a framework, not a forecast source |
| Native forecast centres and ensembles | ECMWF IFS, IFS ENS, AIFS Single/ENS; DWD ICON Global/EPS; ECCC REPS/GEPS; NOAA GEFS, RAP, NAM; conditional RRFS-NA | IFS/ICON Global are nonpublishing stubs. REPS/IFS ENS/AIFS ENS/GEFS have incomplete discovery. Remaining named families lack adapters; RRFS remains conditional |
| Intermediary forecast/model products | Open-Meteo JMA GSM, ARPEGE World, UKMO Global; Bright Sky DWD MOSMIX 71801; CAMS AOD, GFS-Wave, LSA SAF radiation | Probed and catalogued, but no ingestion adapters. Preserve upstream source, transformations, issue times and product-specific restrictions |
| Local weather and air quality | RAQDPS, RDAQA, HRDPA, RDPA, HREPA, HRDLPS, CaLDAS; radiosondes; NL air-quality CSV; PIREP/AIREP and SIGMET/AIRMET; additional GOES products | Catalogue/research gaps; nine-level GRIB profiles and METAR/TAF exist, but expanded deterministic WCS and RDPS seeing/transparency ingestion remain missing |
| Ocean, coastal and hydrology | CIOPS-East, RIOPS, wave/surge products; SmartAtlantic buoys; IWLS tides/water levels; marine reports, NAVWARN; hydrometric feeds; OSTIA and other researched SST products | No adapters for the catalogue entries; several researched native access routes are not separately registered |
| Satellite, aerosols and retrospective truth | GOES CCL/phase/temperature and other missing ABI products; native CAMS; NASA MAIAC/VIIRS aerosol; AERONET; NSRDB; historical model/reanalysis and observation archives | Existing GOES ingestion covers ACMF mask and ACHAF height, not the entire umbrella record. Archive acquisition is separate from rolling live ingestion |
| Space weather and optical aurora | SWPC plasma/propagated wind/alerts/scales; higher-cadence Kp, GFZ Hp30; GOES magnetic/X-ray; NRCan STJ; regional forecasts; historical indices, spacecraft and optical archives | Mostly no adapter. RTSW has disabled code needing source/quality preservation. Latest Kp/OVATION do not implement the researched historical archive |
| Cameras, roads and local partnerships | NL 511/RWIS; NAV CANADA, harbour, municipal and NTV camera families; MADIS/CWOP/PWS, PurpleAir, OpenAQ, Netatmo/Wunderground; academic/offshore observations | Camera schemas, calibration/privacy helpers and hand-entered geometry are not provider retrieval. Some families are intentionally link-only or partnership-only |
| Terrain, light pollution and access | HRDEM/CDEM, provincial LiDAR, GLO-30, OSM/footprints, Black Marble/EOG, Falchi, SQM/Globe at Night, land/parks/closures | Mostly research-only or catalogue-only. Existing site horizons are hand-registered and do not prove DEM acquisition |
| Celestial catalogues and observations | CelesTrak; NASA/USNO event catalogues; Horizons/MPC/SBDB; IMO/GMN/CNEOS/AMS; AAVSO; Gaia/IOTA; TNS/HEASARC/SIMBAD/VizieR/ZTF/ASAS-SN | Additional future-module/validation inputs, not dependencies of every weather view. DE442 geometry already works as code |
| Paid providers | Meteomatics, Tomorrow.io, Google AQ, Ambee, IQAir, Vaisala/Xweather, Visual Crossing, Weatherbit, OpenWeather, Windy, Spire, DTN, Meteoblue, Stormglass, Meteosource, and the researched commercial AI providers | No ingestion integration found. A named vendor, consumer benchmark or paid option is not an approved purchase or source admission |

## Complete inventories and evidence

- [Every registry entry with implementation and evidence references](unimplemented-sources-registry.md), including all absent and intentionally excluded entries.
- [Machine-readable registry inventory](unimplemented-sources-registry.json), 118 unique source IDs, exact registry states and code categories.
- [AI, commercial and global-model candidates](unimplemented-sources-ai-commercial.md), including researched sources absent from the registry.
- [Environmental, marine, satellite and archive candidates](unimplemented-sources-environmental.md), including product-level gaps inside partially implemented families.
- [Geospatial, light-pollution, access and celestial candidates](unimplemented-sources-geospatial-celestial.md), including broader Atlantic Canada and future event-module inputs.

Provider aliases and access surfaces remain grouped where appropriate: 64
WeatherNext members are one Google family; multiple AIWP model runs must retain
their model/initializer identity; GCS/BigQuery/Earth Engine are access surfaces,
not three independent WeatherNext forecasts. For this reason there is no
single defensible grand total combining every research mention with registry
IDs. The registry count is exact; the companion tables inventory the named
research candidates and preserve the grouping.

## Corrections to older research and planning text

1. “Adapter-backed” IFS/ICON does not mean working retrieval: both are stubs.
   Four ensemble families need discovery code, not only a configuration switch.
2. “Admitted” Open-Meteo sources are still catalogued without ingestion.
   Research HTTP probes are not the deployment's retrieval pipeline.
3. Nine-level HRDPS/RDPS GRIB profiles now have code. Expanded deterministic
   WCS, 40/80/120 m fields and RDPS seeing/transparency ingestion remain
   missing despite field-catalogue entries marked `stored`. The alternative
   GeoMet model classes are unregistered WMS point samplers, not WCS ingestion.
4. GOES cloud mask/top-height code does not implement CCL, cloud phase,
   cloud-top temperature, arbitrary ABI bands or every SST/aerosol product.
5. Retired FireWork, rejected Space-Track and excluded/non-covering regional
   models must not be silently reopened as ordinary implementation backlog.
6. The owner-selected UI design does not imply its sources have been built.
   The source inventory must inform API and implementation planning first.

## Evidence limits and validation

This is a static repository audit, supplemented by the AI agent's check of
[Google's official model guide](https://developers.google.com/weathernext/guides/models)
and [NVIDIA's Earth2Studio repository](https://github.com/NVIDIA/earth2studio).
No production/deployment inventory, authenticated provider read or live
source smoke was performed. Access, terms and stale/dead endpoint statements
in the appendices are dated research/registry findings unless explicitly
identified as checked today. They require fresh verification when selected.

No source registry, adapter, specification status, issue, or runtime was
changed. The audit is saved in an isolated worktree to preserve unrelated
root changes.

Spec-Impact: none; research/implementation inventory only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005.
Verification: registry inventory uniqueness/count checks, document-link checks,
and `uv run --project tools/specs python tools/specs/specctl.py validate`: all passed;
`specctl` reported 0 errors and 0 warnings.
