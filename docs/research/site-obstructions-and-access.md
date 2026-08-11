# Observation-site obstructions and public access

Last reviewed: 2026-08-10

## Executive conclusion

Astraeus should not represent a site with a single `visible` or `public`
Boolean. A trustworthy recommendation requires three independent evaluations:

1. **Optical visibility:** terrain, trees, buildings, and event geometry.
2. **Legal access:** whether the public can enter at the required time.
3. **Operational safety:** parking, roads, gates, tides, closures, and walking
   conditions.

A location should become a firm recommendation only when all three pass. A
park polygon, viewpoint marker, or Crown-land designation is not evidence that
the site is accessible at night.

The recommended MVP is a curated catalogue of approximately 50–150 candidate
sites rather than arbitrary points on a geographic grid. Precompute a
directional horizon profile for each site, preserve the source and confidence
of every obstruction, and recheck volatile access and safety information at
recommendation time.

```text
Candidate point
    +-- regional terrain horizon
    |     mountains, ridges, Earth curvature
    +-- local obstruction horizon
    |     trees, buildings, structures
    +-- event geometry
    |     auroral volume or eclipse track
    +-- access evidence
    |     ownership, hours, gates, parking, route
    +-- operational checks
          closures, road conditions, tides, coastal hazards
                   |
                   v
        site suitability + confidence
```

## Directional horizon model

Represent the visible horizon from each observation point as a function of
azimuth. Keep terrain and surface obstructions separate even when the combined
horizon is their maximum:

```json
{
  "azimuth_degrees": 335,
  "terrain_horizon_degrees": 2.4,
  "surface_horizon_degrees": 8.1,
  "combined_horizon_degrees": 8.1,
  "primary_obstruction": "tree_canopy",
  "distance_to_obstruction_m": 146,
  "confidence": 0.84
}
```

For each azimuth, trace outward through the elevation surfaces and calculate:

```text
horizon_angle = max atan2(
    corrected_obstacle_elevation - observer_elevation,
    horizontal_distance
)
```

Normally:

```text
combined_horizon = max(terrain_horizon, surface_horizon)
```

The individual layers must remain available because mountains are stable,
buildings change occasionally, and tree lines can change through storms,
forestry, growth, and season. Temporary structures and vehicles may only be
captured by a recent field observation.

Suggested initial sampling:

- regional terrain rays every 1–2 degrees;
- local high-resolution rays every 0.25–1 degree;
- approximately 1.6 m default standing observer height, configurable for a
  tripod or camera;
- 1 m DTM/DSM from 0–2 km where available;
- 2–10 m elevation data from 2–20 km;
- 20–30 m terrain data from 20–100 km.

Precompute profiles for curated sites. A 360-degree horizon profile is very
small compared with repeatedly reading the underlying rasters.

## DTM, DSM, and canopy data

The elevation products have distinct meanings:

| Product | Represents | Primary use |
| --- | --- | --- |
| DTM | Bare Earth | Hills, ridges, and mountains |
| DSM | Highest visible surface | Buildings and tree canopy |
| CHM | DSM minus DTM | Approximate canopy height |

Do not use a DSM as though it were ground elevation. That can place the
observer on top of a tree or building.

### Building height hierarchy

Use the strongest available source and record which source was selected:

1. Classified LiDAR.
2. DSM minus DTM within a building footprint.
3. Municipal 3-D building data.
4. Explicit OpenStreetMap `height`.
5. OpenStreetMap `building:levels` times a regional storey-height prior.
6. Conservative default height with low confidence.

### Tree height hierarchy

1. Classified LiDAR.
2. Provincial canopy-height model.
3. DSM minus DTM after masking buildings.
4. Satellite canopy products.
5. Land-cover-based height prior.
6. Unknown obstruction state.

Store at least p50 and p95 height, canopy density, acquisition date, and
confidence. A thin isolated tree should not be treated identically to a dense
forest wall. The MVP can conservatively treat canopy as opaque, while clearly
acknowledging season and source staleness.

## Free and open Atlantic Canada data

### New Brunswick

New Brunswick is the best initial province for the obstruction-model
prototype. It publishes 1 m bare-earth DEM, DSM, canopy-height products, raw
LiDAR, and data services under an open licence:

- [GeoNB raster data catalogue](https://www2.gnb.ca/content/gnb/en/departments/erd/open-data/raster-data.html)
- [Government of Canada dataset record](https://open.canada.ca/data/en/dataset/213fbdff-93dd-b7df-7bcd-8239fca8fce8)
- [GeoNB data catalogue](https://www.gnb.ca/en/campaign/geonb/data-catalogue.html)
- [GeoNB Open Data Licence](https://geonb.snb.ca/documents/license/geonb-odl_en.pdf)

### Nova Scotia

Where coverage exists, Nova Scotia's Elevation Explorer supplies LAZ point
clouds and LiDAR-derived DEM, DSM, canopy-height, and intensity products,
generally at 1 m resolution:

- [GeoNova Elevation Explorer](https://nsgi.novascotia.ca/datalocator/elevation/)
- [Elevation Explorer user guide](https://nsgi.novascotia.ca/datalocator/elevation/docs/DataLocator%20Elevation%20Explorer%20User%27s%20Guide.pdf)
- [Nova Scotia Open Government Licence](https://support.novascotia.ca/services/open-data-portal-licence)

The older [Nova Scotia Digital Terrain Model](https://data.novascotia.ca/Lands-Forests-and-Wildlife/Nova-Scotia-Topographic-Database-Digital-Terrain-M/5vns-2bw2)
can fill some terrain gaps but is not adequate for dependable local tree and
building visibility.

### National fallbacks

NRCan's HRDEM is the preferred Canadian fallback. Its coverage is
project-based and commonly provides 1–2 m DTM and DSM products:

- [HRDEM product description](https://natural-resources.canada.ca/science-data/science-research/geomatics/high-resolution-digital-elevation-model-product-changing)
- [NRCan download documentation](https://prod-natural-resources.azure.cloud.nrcan-rncan.gc.ca/science-data/science-research/geomatics/download-directory-documentation)

CDEM, available through [GeoGratis](https://geogratis.gc.ca/site/eng/download),
is appropriate for distant terrain and mountain horizons.

For Prince Edward Island and Newfoundland and Labrador, start with HRDEM where
available and CDEM elsewhere. Until local high-resolution DSM or LiDAR
coverage is verified, return an explicit result such as:

```text
Terrain horizon: evaluated
Local trees and buildings: unverified
```

Do not silently classify such a location as clear.

### Other open sources

- [Copernicus DEM GLO-30](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM)
  is a useful 30 m international fallback but is too coarse and old for
  dependable local trees and buildings.
- [OpenStreetMap](https://www.openstreetmap.org/copyright) provides building
  footprints, parking, viewpoints, trails, barriers, access tags, and roads.
  Most objects lack trustworthy heights.
- [Microsoft Global Building Footprints](https://github.com/microsoft/globalmlbuildingfootprints)
  can fill footprint gaps but does not supply heights.
- GEDI is unsuitable as the main local canopy source because sampling is
  sparse, its orbital coverage ends around 52 degrees latitude, and its
  gridded products are too coarse for site horizon masks.

## Earth curvature and atmospheric refraction

Distant ridges and low-altitude aurora require curvature correction. Evaluate
at least two scenarios:

- no atmospheric refraction as a conservative case;
- standard terrestrial refraction using an effective Earth radius of roughly
  7/6 of the physical radius.

GDAL documents curvature and refraction handling in
[`gdal_viewshed`](https://gdal.org/en/stable/programs/gdal_raster_viewshed.html).
Near-horizon refraction varies with atmospheric structure, so Astraeus should
not claim sub-degree certainty from geometry alone.

Suggested initial uncertainty margins:

- recent LiDAR terrain: 0.25–0.5 degrees;
- recent DSM including surface obstructions: 0.5–1 degree;
- coarse or stale surface data: 2–5 degrees or `unverified`;
- critical low-altitude eclipse phases: a larger conservative margin.

Normalize all sources to compatible horizontal and vertical datums before
computing sight lines.

## Aurora-specific visibility

Aurora is a three-dimensional luminous region rather than a point target. The
visibility calculation should:

1. obtain predicted auroral intensity cells or an oval;
2. assign plausible emission altitude ranges;
3. transform relevant cells into observer-local azimuth and elevation;
4. compare each cell with the combined horizon at that azimuth;
5. integrate the predicted intensity that remains visible.

A useful metric is:

```text
visible_auroral_energy_fraction =
    predicted auroral intensity above the horizon
    ------------------------------------------------
    total predicted intensity potentially visible
```

Indicative altitude bands are roughly 90–120 km for lower emissions,
approximately 100–150 km for much of the green emission region, and higher for
red emissions. These should be distributions or scenarios rather than one
fixed shell.

For weak or distant aurora, a clean northern horizon is critical. When the
oval expands overhead, the score should become less sensitive to the northern
horizon and more sensitive to broad sky openness.

Example output:

```text
Visible auroral forecast fraction: 76%
Best direction: NNW, 325–350 degrees
Expected elevation: 7–24 degrees
Terrain clears forecast by: 4.2 degrees
Tree-line clearance: uncertain below 10 degrees
```

## Eclipse-specific visibility

Eclipse geometry is deterministic enough for precise evaluation. For every
candidate site:

1. compute the solar disc's azimuth and elevation throughout the eclipse;
2. sample densely around first contact, maximum eclipse, and final contact;
3. compare the upper and lower edges of the disc, not only its centre, with
   the horizon;
4. apply terrain and surface uncertainty margins;
5. reject the site if an obstruction intersects a critical phase.

Example output:

```text
First contact: clear by 6.3 degrees
Maximum eclipse: clear by 3.8 degrees
Final contact: potentially blocked by tree line
```

For a sunrise or sunset eclipse, calculate refracted and unrefracted tracks and
communicate the uncertainty. False-clear recommendations are more damaging
than conservative exclusions.

## Public-access evidence model

Access is not one Boolean. Record independent evidence:

```json
{
  "ownership": "provincial_park",
  "public_entry": "yes",
  "night_access": "unknown",
  "vehicle_access": "yes",
  "parking": "verified",
  "walking_route": "verified",
  "seasonal_access": "open",
  "gate_status": "unknown",
  "current_closure": "none_reported",
  "coastal_hazard": "low",
  "verified_at": "2026-08-08T18:00:00Z"
}
```

Use a weakest-link rule: excellent ownership evidence must not compensate for
unknown nighttime access or a locked gate.

Suggested evidence grades:

- **A:** officially verified and recently checked;
- **B:** strong evidence with no known operational issue;
- **C:** plausible but unverified; show only as exploratory;
- **D:** unsuitable or materially uncertain;
- **X:** hard rejection because it is private, closed, unsafe, or inaccessible.

Useful official starting sources include:

- [Canadian Protected and Conserved Areas Database](https://open.canada.ca/data/en/dataset/6c343726-1e92-451a-876a-76e17d398a1c)
- [Nova Scotia Crown Land](https://data.novascotia.ca/Lands-Forests-and-Wildlife/Crown-Land/3nka-59nz)
- [New Brunswick Crown Lands](https://www2.gnb.ca/content/gnb/en/departments/erd/open-data/crown-lands.html)
- [New Brunswick provincial parks](https://www.gnb.ca/en/campaign/geonb/data-catalogue/provincial-parks.html)
- [Newfoundland and Labrador Crown Lands](https://www.gov.nl.ca/crownlands/)
- [Newfoundland and Labrador Land Use Atlas](https://www.gov.nl.ca/crownlands/land-use-atlas/),
  which warns that its information may not always be current.

Classify these as **official GIS ownership/management evidence**, not as an
access permission API. Preserve the dataset version, feature identifier,
licence, retrieved time, and original geometry. Nova Scotia exposes Crown Land
as downloadable GeoJSON/shapefile under its open-government licence; GeoNB
publishes its own catalogue and licence. The national protected-areas database
identifies conservation/management status, not gate hours or permission to be
present after dark.

Public cadastral viewers are especially easy to overinterpret. A parcel
boundary can help reject obvious private-land ambiguity, but cadastral records
may omit current interests, easements, lease conditions, or a lawful route to
the parcel. Do not publish owner names or infer public access from missing
ownership data. When authoritative ownership cannot be established, set
`ownership=unknown` and cap the access grade at C.

Useful OpenStreetMap features include parking, viewpoints, trailheads,
beaches, parks, roads, barriers, gates, and access restrictions. Missing
access tags mean `unknown`, not `permitted`; see the
[OSM access-tag reference](https://wiki.openstreetmap.org/wiki/Access_tags).
OSM is **community raw geodata**, licensed under the
[ODbL with attribution requirements](https://www.openstreetmap.org/copyright).
Store the OSM object ID/version and extraction timestamp. A community mapper's
`access=yes` remains weaker than a current official closure or park rule, and
the absence of a gate or restriction tag is not positive evidence.

## Runtime operational checks

Recheck volatile facts before issuing a recommendation:

- park hours and seasonal opening;
- gates and current closures;
- every road segment against provincial 511 information;
- ferry schedules and outages;
- parking evidence, walking distance, and walking surface;
- tide, water level, and coastal hazards.

Road sources include [New Brunswick 511](https://511.gnb.ca/),
[Newfoundland and Labrador 511](https://511nl.ca/), and the
[PEI 511 condition definitions](https://511.gov.pe.ca/about/definitions).
`No report` must not be interpreted as `normal`.

For coastal sites, use the Canadian Hydrographic Service
[web services](https://www.tides.gc.ca/en/web-services-offered-canadian-hydrographic-service)
and [tide, current, and water-level products](https://www.tides.gc.ca/en/tides-currents-and-water-levels).
Tide alone is insufficient: waves, surge, cliffs, route elevation, and
single-exit beaches also matter.

Reject a route when it requires a private or prohibited road, an unknown
non-public motor road, a seasonally closed road, an unresolved gate, a 511
closure, or unsafe and unverified parking or walking access.

## Free, locally hosted implementation

Recommended components:

- [PDAL](https://pdal.org/en/2.7.2/stages/filters.hag_nn.html) for LAZ/LiDAR
  processing and height-above-ground calculations;
- Rasterio and GDAL for raster processing;
- GRASS GIS [`r.horizon`](https://grass.osgeo.org/grass-stable/manuals/r.horizon.html)
  as a reference implementation;
- GDAL viewshed for selected calculations and validation;
- NumPy and Numba for an optimized production ray profiler;
- PostGIS for candidates, evidence, provenance, and profile metadata;
- Cloud Optimized GeoTIFFs for DTM, DSM, and CHM storage;
- LAZ source files outside the database;
- Valhalla or OSRM for routing;
- QGIS for manual scientific QA rather than runtime computation.

Validate any custom profiler against GRASS and GDAL before relying on it for
recommendations.

Use local OSM extracts with the
[official OSRM engine](https://github.com/Project-OSRM/osrm-backend) or the
[official Valhalla engine](https://github.com/valhalla/valhalla). Their code
licences do not replace the ODbL obligations on OSM-derived databases. Public
demo servers are for evaluation/fair use, not an availability dependency for
safety-relevant recommendations.

At 1 m resolution, one uncompressed 32-bit raster band is approximately 4 MB
per square kilometre. Province-scale DTM, DSM, and CHM storage therefore grows
quickly. Use tiled Cloud Optimized GeoTIFFs, download or derive only required
areas of interest, and retain compact precomputed horizon profiles.

## Paid and commercial options

Paid products are best used to fill selected high-value coverage gaps rather
than as the foundation of Atlantic Canada coverage.

| Provider | Useful for | Main limitation |
| --- | --- | --- |
| Google Routes | Routing and travel times | Does not prove access or parking |
| Google Places | Hours, names, and photos | Not authoritative access evidence |
| Google Solar API | Machine-readable surface layers in covered areas | Coverage and derivative-storage rights require verification |
| Mapbox | Maps, routing, and isochrones | Not a scientific tree/building-height source |
| HERE | Routing and isolines | No obstruction DSM |
| Esri | Hosted viewshed and elevation analysis | Credit cost and source-dependent accuracy |
| Cesium ion | 3-D visualization | Supplier restrictions carry through |
| Nearmap | High-resolution local DSM and aerial data | Cost, coverage, and contract restrictions |
| Maxar Vivid Terrain | Downloadable DSM, DTM, and 3-D products | Enterprise pricing and licence |
| Vexcel | High-resolution aerial and elevation data | Coverage and enterprise contract |
| Ecopia | Building vectors and some 3-D structures | Not a tree or canopy solution |

Google Photorealistic 3D Tiles and Street View should not power automated
horizon extraction under standard terms. Google's
[Map Tiles policies](https://developers.google.com/maps/documentation/tile/policies)
restrict image analysis, machine interpretation, object detection, geodata
extraction, and offline use. They may support human inspection subject to the
applicable terms.

The Solar API is more promising because it exposes machine-readable data
layers, but it is roof- and solar-oriented. Coverage and rights to store
derived horizon masks require verification before use; see the
[data-layer reference](https://developers.google.com/maps/documentation/solar/reference/rest/v1/dataLayers)
and [data-layer guide](https://developers.google.com/maps/documentation/solar/data-layers).

Nearmap exposes DSM and true-ortho products for local areas; see its
[DSM API documentation](https://developer.nearmap.com/docs/dsm-and-true-ortho-api)
and [coverage map](https://www.nearmap.com/coverage). Maxar documents terrain
and 3-D ordering in its
[3-D ordering guide](https://developers.maxar.com/docs/ordering/guides/3d-ordering).

Before adopting commercial data, obtain explicit answers to:

- Is automated analysis permitted?
- May source tiles be cached?
- May derived horizon profiles be stored permanently?
- May derived outputs be shown in a consumer SaaS product?
- Must derivatives be deleted when the subscription ends?
- Is mixing with other datasets permitted?
- What attribution is required?
- What are the update frequency and vertical-accuracy guarantees?

## Phone-based horizon scanning

A phone panorama is probably the best scalable source of truth for exact local
conditions. It can capture current trees, individual buildings, temporary
structures, and the precise position within a parking or viewing area.

A future workflow could:

1. ask the user to stand at the observation position;
2. record a 360-degree panorama or slow video;
3. use IMU/GNSS and ARKit or ARCore depth where available;
4. segment sky from non-sky;
5. allow manual correction;
6. calibrate azimuth against the Sun, Moon, or stars because magnetometers are
   unreliable near vehicles and tripods;
7. store the derived mask, timestamp, observer height, and confidence.

Retaining the derived mask rather than raw imagery reduces privacy and storage
concerns. Crowd-sourced gate, access, and horizon reports should decay in
confidence with age and become stronger through independent confirmations.

The optimizer should also test micro-relocation. Moving 20–100 m within a
legal parking or viewing area can materially improve the horizon.

## Validation

Create synthetic test landscapes containing:

- flat terrain;
- one ridge or hill;
- a building;
- a tree wall;
- raster seams;
- no-data gaps;
- a curvature-sensitive distant ridge.

Compare the production profiler with GRASS and GDAL, then validate real sites
against surveyed or phone-panorama horizons.

Measure:

- angular mean absolute error;
- maximum horizon error;
- false-clear rate;
- false-blocked rate;
- accuracy by obstruction distance and data age.

Suggested initial targets are less than 0.25-degree mean error for a LiDAR
terrain horizon and approximately 0.5–1 degree for a recent combined DSM
horizon. Do not label a direction `verified clear` without a safety margin and
recent provenance. Optimize especially against false-clear errors for
eclipses.

## Recommended delivery sequence

1. Prototype in New Brunswick using its 1 m DTM, DSM, and canopy data.
2. Curate ten real observation sites with documented access evidence.
3. Generate separate terrain and surface horizon profiles.
4. Validate profiles against GRASS, GDAL, and field panoramas.
5. Add auroral-volume visibility and directional visible-intensity metrics.
6. Add eclipse solar-disc clearance for every critical phase.
7. Expand into Nova Scotia LiDAR coverage.
8. Add HRDEM/CDEM fallbacks for PEI and Newfoundland and Labrador.
9. Add user scans, evidence freshness, and micro-relocation.
10. Use paid DSM products only where coverage is valuable and derivative
    rights are contractually clear.

The governing product rule is:

> Unknown local obstruction or nighttime access is a first-class result,
> never a silent assumption.
