# Unimplemented source audit: geospatial and celestial inputs

Audited September 5, 2026 against `execution/activity-profiles` at `9af2aaf`.
Non-normative repository audit, not fresh provider availability or licence verification.
Companion to [the source audit](unimplemented-data-sources.md).

## Evidence and interpretation

The research names a much wider product than the current weather experiment.
The rows below preserve those candidates without making them immediate weather
implementation requirements. Items within a row are related acquisition products,
not interchangeable feeds or independent forecast centres.

There is a real DE442 download/checksum path in
`experiments/st-johns-weather-map/api/scripts/fetch_ephemeris.py:40` and
`api/weather_api/ephemeris.py:20`; `api/weather_api/astronomy.py:104` loads it
and computes Sun/Moon/darkness geometry. DE442 is **implemented**, not a missing
source. The latter uses `loader.timescale(builtin=True)` at line 114, rather
than an explicitly archived external IERS Earth-orientation ingestion path.
The earlier `v1/services/api/main.py` also loads the pinned ephemeris, but does
not contain the additional catalogue acquisitions below.

The site registry is not a DEM ingestion pipeline:
`experiments/st-johns-weather-map/registry/sites/signal-hill.yaml:7` describes
hand-registered angles, and its `terrain_check` at line 62 is `not_run`, with
`dem: null`. `api/weather_api/sites.py:210` looks up registered horizons; it
does not acquire terrain, canopy, access permissions or closures.

No acquisition implementation for the research-only rows below was located
in the current Python/TypeScript source. Registry-only exceptions are named.
Specifications, fixtures and prototype capture JSON are not retrieval code.

## Terrain, obstructions, light and site access

| Researched source/product | Current implementation gap | Research evidence |
| --- | --- | --- |
| NRCan HRDEM DTM/DSM and LiDAR; NRCan CDEM / GeoGratis | No raster acquisition or DEM-derived site horizon | `docs/research/data-sources.md:296`; `site-obstructions-and-access.md:158` |
| GeoNB DEM, DSM, canopy height and LiDAR | No provincial terrain/canopy ingestion; broader Atlantic Canada scope | `site-obstructions-and-access.md:133` |
| GeoNova Elevation Explorer LAZ/DEM/DSM/canopy; older NS Digital Terrain Model | No acquisition or derivative pipeline; broader Atlantic Canada scope | `site-obstructions-and-access.md:144` |
| Copernicus DEM GLO-30 | No native DEM raster ingestion. The separate Open-Meteo GLO-90 elevation catalogue record is not this source or a terrain horizon implementation | `data-sources.md:296`; `site-obstructions-and-access.md:180` |
| OpenStreetMap building heights/footprints, access tags, roads, parking, barriers and trails | No evidence ingestion/versioning for horizon or access decisions found; a rendered basemap is not this pipeline | `site-obstructions-and-access.md:106,180,281` |
| Microsoft Global Building Footprints; municipal 3-D building data | No footprint acquisition or height integration; footprints alone do not supply heights | `site-obstructions-and-access.md:106,180` |
| NASA Black Marble VIIRS products; NOAA/EOG monthly and annual night-light composites | `viirs-dnb-night-lights` is credential-required with no adapter; exact Black Marble/EOG product acquisition absent | `data-sources.md:328`; `registry/source_data.py:1031` |
| Falchi World Atlas of Artificial Night Sky Brightness | `falchi-night-sky-atlas` is catalogued, no adapter. Research treats it as a restricted benchmark, not an automatic commercial input | `wayfinder/astronomy-tool-needs.md:223`; `sota-models.md:937` |
| Globe at Night; site SQM/photometer/all-sky observations | `globe-at-night` is catalogued, no adapter. No calibrated local photometry acquisition found | `wayfinder/astronomy-tool-needs.md:225`; `wayfinder/transparency-seeing-sources.md:256` |
| Canadian Protected and Conserved Areas Database | No GIS acquisition/versioning; management status would not prove night access | `site-obstructions-and-access.md:312` |
| NS Crown Land; NB Crown Lands and provincial parks; NL Crown Lands and Land Use Atlas | No authoritative land/access evidence pipeline; broader regional scope where appropriate | `site-obstructions-and-access.md:312` |
| St. John's MapCentre parks; Parks Canada Signal Hill/Cape Spear; Grand Concourse site information | Site seeds and human-curated records exist; no refreshable acquisition of hours, closures and legal entrances found | `site-obstructions-and-access.md:361` |
| New Brunswick 511 and PEI 511 | No integrations found; NL 511 is covered separately in the environmental audit | `site-obstructions-and-access.md:368` |
| Mapillary and KartaView | Researched reviewer QA imagery, no integration; not measurements of lawful access | `site-obstructions-and-access.md:349` |
| Google Routes, Google Places, Mapbox routing, HERE | Optional commercial routing/place inputs, no integrations found. Routing engines themselves are software, not forecast sources | `site-obstructions-and-access.md:426` |
| Google Solar data layers; Esri elevation; Nearmap DSM; Maxar Vivid Terrain; Vexcel; Ecopia | Research-only commercial elevation/building alternatives; coverage and permitted derivative uses remain candidate gates | `site-obstructions-and-access.md:426` |
| Cesium ion | Researched visualization/data delivery service; no acquisition integration found and supplier-specific datasets must remain distinct | `site-obstructions-and-access.md:426` |
| Phone panorama/depth and crowd-sourced horizon/access reports | Proposed acquisition workflow, not an existing external provider | `site-obstructions-and-access.md:475` |

GEDI is explicitly unsuitable as the main local canopy source in this research.
Google Street View and Photorealistic 3D Tiles are not proposed unrestricted
automated horizon inputs. Illumina is a future offline modelling tool, not a
retrieved sky-brightness feed (`sota-models.md:958`). None should be counted as
a ready adapter simply because it appears in the dossier.

## Celestial catalogues and historical observations

All references in this table are to `docs/research/historical-celestial-events.md`
unless another path is given. Sources can serve future event modules or
validation without belonging to the current weather-map scope.

| Source/product | Gap or distinction | Research location |
| --- | --- | --- |
| IERS Earth-orientation and versioned time inputs | Explicit external archival pipeline absent; built-in Skyfield timescales already used | lines 89–121 |
| JPL Horizons and USNO data services | No automated independent validation/catalogue adapters found; DE442 computation is already implemented | lines 89–101, 274 |
| NASA solar eclipse catalogue / Besselian elements / paths; NASA lunar eclipse catalogue and Canon | No general event-catalogue ingestion found | lines 274–324 |
| NAIF supplementary SPICE kernels | No general kernel acquisition beyond the pinned DE442 artifact | lines 89–101, 466 |
| NCEI DSCOVR mission archive; NASA SPDF/CDAWeb ACE MAG/SWEPAM | Historical measurement retrieval missing; current SWPC paths are separate products | lines 340–357, 384 |
| NASA OMNIWeb | No retrospective Earth-shifted solar-wind acquisition; never an issued forecast archive | lines 340–357 |
| GFZ definitive/provisional Kp and Hp30/Hp60 archives | No historical index ingestion; current SWPC Kp is a different source | lines 340–357 |
| Kyoto Dst, AE/AL/AO, SYM/ASY | No version-aware historical index acquisition found | lines 340–357 |
| WSA-Enlil operational run archive; NASA DONKI events | No forecast-vintage/event-catalogue ingestion; CCMC Runs on Request is a reconstruction service, not that archive | lines 340–357, 384 |
| NRCan historical magnetometers; SuperMAG | Historical measurement paths missing; the current STJ catalogue entry is not an archive implementation | lines 340–357 |
| THEMIS ASI / CSA archive; AuroraX metadata; AuroraMAX images; DMSP/SSUSI | Optical/particle history and discovery paths absent; camera footprint and processing level matter | lines 340–357, 405 |
| Aurorasaurus released citizen reports | No acquisition; human visibility evidence is separate from geomagnetic activity | lines 340–357 |
| International Meteor Organization calendar/observations; Global Meteor Network; NASA CNEOS fireballs; American Meteor Society reports | No meteor activity/fireball adapters found | lines 437–462 |
| JPL Small-Body Database; Minor Planet Center | No orbital-element/observation catalogue acquisition | lines 464–487 |
| AAVSO observations / International Database | No brightness/light-curve ingestion | lines 479–486, 508 |
| Gaia astrometry; IOTA and regional occultation networks | No star-catalogue or prediction/chord-report ingestion | lines 488–506 |
| Transient Name Server; NASA HEASARC; SIMBAD; VizieR; ZTF; ASAS-SN | No transient/discovery/photometry catalogue ingestion; object identity is not observed light-curve truth | lines 508–527 |
| AstronomyAPI; timeanddate astronomy APIs | Research-only optional convenience APIs, no implementation | lines 529–566 |
| CelesTrak GP element sets | Catalogued as `celestrak-gp`; no retrieval adapter or pass propagation implementation found | `wayfinder/astronomy-tool-needs.md:220`; `registry/source_data.py:1486` |

Space-Track is explicitly rejected in `registry/source_data.py:1517`; do not
turn its historical mention into an open implementation task. DE440/DE441
references are historical alternatives to the selected DE442, not three
unimplemented providers. Skyfield, Astropy, SGP4 and SPICE toolkits are software,
not additional independent evidence sources.

## Verification

Read research and compared current registry, ingestion, API and site source
files, excluding tests/capture files as proof of implementation. Broad searches
covered `v1/` as well as the weather experiment. No live retrieval performed.
Final specification validation is recorded in the parent audit.

Spec-Impact: none; documentation of existing code and research only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005.
