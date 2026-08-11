# Cloud, fog, and astronomical line-of-sight forecasting

Last reviewed: 2026-08-10

## Executive conclusion

Astraeus should not predict only cloud cover at an observation point. The
scientifically relevant target is the distribution of wavelength-dependent
optical transmission along the curved, three-dimensional ray from observer to
astronomical target:

```text
P(direct transmission is adequate |
  observer, time, azimuth, elevation, wavelength, equipment)
```

For Atlantic Canada, the strongest feasible system is:

```text
ECCC HRDPS/REPS 3-D atmospheric forecast
    + GOES-East observed cloud geometry and motion
    + METAR/SWOB fog, visibility, and ceiling
    + stochastic unresolved-cloud geometry
    + spherical line-of-sight ray tracing
    + local calibration from all-sky cameras
```

The right intermediate fidelity is a **probabilistic curved-ray extinction
engine**. Full cloud tomography and Monte Carlo radiative transfer are valuable
research tools, but uncertain cloud inputs would dominate their extra solver
accuracy in the MVP.

## Integration and implementation tooling

The access method matters: ECCC and NOAA model products are files or geospatial
services, not Python SDKs. The following links are the practical starting
points; “community” means useful but not operated or supported by the data
producer.

| Source or tool | Official documentation | Official repository / SDK | Community tooling and access note |
| --- | --- | --- | --- |
| ECCC HRDPS, REPS, RDPS, GDPS, GEPS | [MSC Open Data](https://eccc-msc.github.io/open-data/), [HRDPS](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/), [REPS](https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps_en/), [GRIB guide](https://eccc-msc.github.io/open-data/msc-data/readme_grib_en/) | No model-specific SDK. Official access is Datamart/AMQP and [MSC GeoMet OGC APIs](https://eccc-msc.github.io/open-data/msc-geomet/readme_en/). | Decode GRIB with ECMWF's official [ecCodes](https://github.com/ecmwf/eccodes) and [cfgrib](https://github.com/ecmwf/cfgrib); use [xarray](https://docs.xarray.dev/) for labelled arrays. Do not describe these as ECCC SDKs. |
| GOES-East ABI | [GOES-R products](https://www.goes-r.gov/products/), [NOAA AWS dataset](https://registry.opendata.aws/noaa-goes/) | No product SDK; official access is S3/CLASS. | Community [goes2go](https://github.com/blaylockbk/goes2go) discovers/downloads cloud objects; [Satpy](https://satpy.readthedocs.io/) reads and resamples ABI files; [s3fs](https://s3fs.readthedocs.io/) provides object-store access. |
| METAR/SPECI and ECCC stations | [Aviation Weather API](https://aviationweather.gov/data/api/), [ECCC SWOB](https://eccc-msc.github.io/open-data/msc-data/obs_station/readme_obs_insitu_swobdatamart_en/) | Aviation Weather publishes an OpenAPI description; SWOB is XML/file and OGC API access, with no official language SDK. | Use a generated OpenAPI client only after pinning the current schema; normal HTTP/XML libraries are sufficient. |
| ECMWF IFS/ENS, ERA5 and CAMS | [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data), [CDS API setup](https://cds.climate.copernicus.eu/how-to-api), [ADS](https://ads.atmosphere.copernicus.eu/) | Official [ecmwf-opendata](https://github.com/ecmwf/ecmwf-opendata), [cdsapi](https://github.com/ecmwf/cdsapi), [ecCodes](https://github.com/ecmwf/eccodes), [cfgrib](https://github.com/ecmwf/cfgrib), and [earthkit](https://github.com/ecmwf/earthkit-data). | [Herbie](https://github.com/blaylockbk/Herbie) is a community downloader for several operational-model stores; confirm dataset and licence coverage per model. |
| NOAA GFS/GEFS/HRRR/RRFS | [NOMADS](https://nomads.ncep.noaa.gov/), [NOAA Open Data](https://www.noaa.gov/information-technology/open-data-dissemination) | Official distribution is NOMADS and cloud object storage, not a language SDK. | [Herbie](https://github.com/blaylockbk/Herbie) and [s3fs](https://s3fs.readthedocs.io/) are convenient; retain the original GRIB identifiers and run metadata. |
| WRF / WRF-Chem | [WRF Users Guide](https://www2.mmm.ucar.edu/wrf/users/docs/user_guide_v4/contents.html), [WRF-Chem users page](https://ruc.noaa.gov/wrf/wrf-chem/) | Official/community-model repositories: [WRF](https://github.com/wrf-model/WRF), [WPS](https://github.com/wrf-model/WPS), [Users Guide](https://github.com/wrf-model/Users_Guide). | [wrf-python](https://wrf-python.readthedocs.io/) is NCAR-supported post-processing, not a hosted forecast API. |
| MPAS-Atmosphere | [MPAS documentation](https://www2.mmm.ucar.edu/projects/mpas/) | [MPAS-Model](https://github.com/MPAS-Dev/MPAS-Model) | Compile/run workflow; no remote data SDK. |
| UFS / FV3 | [UFS documentation](https://ufs-community.github.io/ufs-weather-model/), [UFS applications](https://ufs.epic.noaa.gov/) | [ufs-weather-model](https://github.com/ufs-community/ufs-weather-model), [UFS_UTILS](https://github.com/ufs-community/UFS_UTILS) | Full forecasting system, not an SDK. Use published NOAA output unless a controlled experiment justifies operating it. |
| ICON | [DWD Open Data](https://opendata.dwd.de/weather/nwp/), [ICON documentation](https://www.icon-model.org/) | [ICON model](https://gitlab.dkrz.de/icon/icon-model) | Raw GRIB access for DWD operational output; ecCodes/cfgrib are appropriate readers. |
| AI forecast runners | [ECMWF AI models overview](https://www.ecmwf.int/en/forecasts/dataset/aifs-machine-learning-data) | [ECMWF ai-models](https://github.com/ecmwf-lab/ai-models) and model-specific plugins | A runner does not create missing cloud microphysics or prove local fog skill; inspect each checkpoint's output variables and licence. |
| libRadtran | [Official documentation](http://www.libradtran.org/doku.php) | [Official source distribution](http://www.libradtran.org/doku.php?id=download) | Command-line radiative-transfer suite, not a hosted API or maintained official Python SDK. |

For raster reprojection and ray sampling, use the official projects
[PROJ/pyproj](https://pyproj4.github.io/pyproj/stable/),
[GDAL](https://gdal.org/), [Rasterio](https://rasterio.readthedocs.io/), and
[Shapely](https://shapely.readthedocs.io/). Pin versions because GRIB mappings,
coordinate conventions, and satellite product definitions evolve.

## Prediction target

For one atmospheric realization:

```text
tau(lambda) = integral along ray of beta_ext(lambda, x, y, z, t) ds
T_direct(lambda) = exp(-tau(lambda))
```

The extinction coefficient includes molecules, aerosols, fog droplets, cloud
liquid and ice, and precipitation. The result must be a distribution because
cloud location, overlap, timing, and microphysics are uncertain:

```json
{
  "azimuth_deg": 338,
  "elevation_deg": 9,
  "direct_transmission": {"median": 0.72, "p10": 0.08, "p90": 0.94},
  "clear_ray_probability": 0.61,
  "opaque_intersection_probability": 0.29,
  "dominant_risk": "low marine stratus 35–70 km north"
}
```

Until calibrated against observed outcomes, `clear_ray_probability` is
model-derived confidence rather than a calibrated success probability.

## Why ordinary cloud percentages fail

`Total cloud = 40%` does not specify:

- where cloud lies within the grid cell;
- cloud base, top, phase, water content, or optical depth;
- how layers overlap vertically;
- whether the requested oblique ray intersects cloud;
- whether remaining transmission is adequate for a bright eclipse, faint
  aurora, or deep-sky target.

A clear overhead column can coexist with a blocked northern horizon.
Near-horizontal viewing also makes vertically separate clouds overlap and can
make a geometrically thin cloud optically thick. See
[Physical interpretation of gray cloud observed from airplanes](https://pubmed.ncbi.nlm.nih.gov/27463934/).

## Low-elevation geometry

For an initial flat-Earth approximation, a ray at elevation `e` intersects a
cloud height `h` at:

```text
distance approximately h / tan(e)
```

| Cloud height | 5-degree elevation | 10-degree elevation | 20-degree elevation |
| ---: | ---: | ---: | ---: |
| 0.5 km | 5.7 km | 2.8 km | 1.4 km |
| 1 km | 11.4 km | 5.7 km | 2.7 km |
| 3 km | 34 km | 17 km | 8.2 km |
| 8 km | 91 km | 45 km | 22 km |

A 5-degree aurora ray can intersect cirrus nearly 100 km away. Coastal
stratus tens of kilometres north can block an aurora while the observer's
forecast cell remains clear. Sampling only that cell is invalid.

## Curved ray geometry

Use Earth-centred coordinates:

```text
observer = geodetic_to_ECEF(lat, lon, height)
direction = local_azimuth_elevation_to_ECEF(azimuth, elevation)
ray(s) = observer + s * direction
```

At each step:

1. Convert to latitude, longitude, and geometric height.
2. Locate the NWP horizontal cell.
3. Locate the real model layer using geopotential interfaces.
4. Interpolate cloud and extinction variables in space and time.
5. Accumulate optical depth.
6. Stop at the target volume, atmosphere exit, terrain, or opaque threshold.

Use fine adaptive steps near fog, the observer, layer boundaries, and strong
gradients. Do not treat pressure surfaces as flat altitudes.

Even a straight horizontal ray rises relative to Earth's curved surface. Use
an ellipsoidal Earth. Below approximately 5 degrees, evaluate refraction
scenarios from temperature, pressure, and water vapour, and widen uncertainty.
Kasten–Young air mass improves clear-air attenuation near the horizon but does
not solve discrete cloud intersection. See
[Kasten and Young](https://doi.org/10.1364/AO.28.004735) and
[Extinction, refraction, and delay](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2008JD010176).

## Three-dimensional atmospheric state

The normalized cell should eventually support:

```text
cloud fraction
liquid and ice mixing ratios
rain, snow, and graupel mixing ratios
liquid and ice effective radius
temperature, pressure, humidity, and air density
horizontal and vertical wind
```

Convert mixing ratios to water content:

```text
LWC = air_density * liquid_water_mixing_ratio
IWC = air_density * ice_water_mixing_ratio
```

A simplified liquid-cloud relation is:

```text
tau_liquid approximately
    3 * liquid_water_path
    ---------------------
    2 * water_density * effective_radius
```

ECMWF's [ecRad documentation](https://confluence.ecmwf.int/download/attachments/70945505/ecrad_documentation.pdf?api=v2)
describes optical thickness, particle size, phase, asymmetry, and overlap.
Where effective radius is absent, use regime-specific priors and broaden
uncertainty.

Liquid and ice differ in particle size, shape, phase function, and wavelength
response. Optical depth dominates blocked/not-blocked decisions; detailed
phase and spectral behavior matter more for Moonlight, light pollution, thin
cloud, and sunsets.

## Sub-grid cloud fraction and overlap

Cloud fraction does not reveal which sub-cell paths contain cloud. ECMWF and
other operational radiation systems use overlap assumptions and stochastic
subcolumns. See ECMWF's
[atmospheric-physics overview](https://www.ecmwf.int/en/research/modelling-and-prediction/atmospheric-physics)
and [IFS physical-process documentation](https://www.ecmwf.int/sites/default/files/2023-06/Part-IV-Physical-Processes.pdf).

Astraeus should:

1. Sample cloud occupancy from layer cloud fraction.
2. Correlate adjacent layers and nearby horizontal cells.
3. Sample in-cloud condensate or optical depth.
4. Ray-trace the sampled realization.
5. Repeat across ensemble members, stochastic columns, optical assumptions,
   satellite uncertainty, and target geometry.

Return clear and opaque probabilities, median and interval transmission, and
the dominant intersected layer and distance.

Never use `transmission = 1 - total_cloud_fraction`, and never ray-trace an
ensemble-mean cloud field. Clear and overcast ensemble members can average
into an atmosphere that no member predicts.

## Direct transmission versus scattered background

Direct extinction answers whether the target remains visible:

```text
received_target_radiance = intrinsic_radiance * exp(-tau_total)
```

Cloud also scatters Moonlight, twilight, artificial light, and auroral light.
That changes sky background and target contrast and requires source direction,
spectrum, cloud phase function, ground albedo, and possibly multiple
scattering.

Keep direct target transmission, diffuse background, and resulting contrast
as separate outputs. Prioritize direct transmission for the MVP and use
offline radiative-transfer lookup tables for background corrections later.

## Fog and marine stratus

Fog is cloud intersecting the observer or near-surface ray. Visibility depends
on droplet number and size, liquid-water content, aerosols, humidity,
turbulence, radiative cooling, surface state, sea temperature, boundary-layer
depth, and advection.

Recent research continues to find large fog activation and lifecycle
uncertainties. A 2024 WRF study evaluated activation based on local cooling and
water-vapour flux rather than conventional updraft assumptions
([Peterka et al.](https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4704)).
Measurements also show complex and sometimes bimodal fog droplet distributions
([Nelli et al.](https://www.sciencedirect.com/science/article/pii/S0169809524003521)).

Fuse:

```text
model visibility and lowest-layer cloud/LWC
RH and dew-point depression
wind, precipitation, and boundary-layer height
surface temperature tendency and sea-surface temperature
coastal exposure and low-level inversion
GOES fog/low-stratus evidence
METAR/SWOB visibility and ceiling
aerosol concentration
```

Do not reduce fog diagnosis to `RH > 95%`.

A useful initial approximation is:

```text
meteorological_visibility approximately 3.912 / beta_ext
```

Convert visibility to near-surface extinction, diagnose a fog-depth
distribution, taper it vertically, and integrate the oblique path. Increase
uncertainty when fog depth is unknown. Reject a site when the observer is
inside dense fog.

For Atlantic Canada, explicitly include onshore wind, sea/air temperature
contrast, coastal exposure, inversion strength, boundary-layer depth, GOES
low-cloud motion, and upstream coastal stations or buoys. Marine stratus can
clear at the observer while still blocking an offshore line of sight.

## Forecast strategy by horizon

| Horizon | Primary evidence | Role |
| --- | --- | --- |
| 0–2 hours | GOES + METAR/SWOB + HRDPS background + motion | Leave, stay, or reroute |
| 2–12 hours | HRDPS + current model-error correction + station trends | Main short-range decision |
| 12–48 hours | HRDPS + REPS + run and model disagreement | Site/window planning |
| Beyond 48 hours | GDPS/GEPS + ECMWF/ENS | Regional planning only |

## Free operational sources

### ECCC HRDPS

HRDPS is the primary free short-range source for Atlantic Canada: approximately
2.5 km, four runs daily, hourly forecasts to 48 hours, up to 31 pressure
levels, public GRIB2, and AMQP notifications.

Relevant fields include cloud cover, relative and specific humidity,
temperature, dew-point depression, winds, precipitation, column fields, and
the derived `VISIFG` visibility/fog field. Discover and test the live inventory
rather than relying on an old static list.

- [HRDPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/)
- [HRDPS Datamart and fields](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/)

HRDPS supplies a physically consistent background but can displace small fog
banks and broken-cloud boundaries.

### ECCC REPS

REPS supplies uncertainty through 20 perturbed members plus a control at
approximately 10 km. Evaluate members independently to derive clear-member
fraction, timing percentiles, score distribution, and site-rank stability.

- [REPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps_en/)
- [REPS GRIB2 access](https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps-datamart_en/)

### GOES-East ABI

Relevant observed products include:

- Enterprise Cloud Mask and cloud probability;
- cloud-top height, pressure, temperature, layer, and phase;
- cloud optical depth and particle properties;
- fog and low-stratus probabilities;
- Derived Motion Winds and Nighttime Microphysics imagery.

Sources:

- [GOES product inventory](https://www.nesdis.noaa.gov/our-satellites/currently-flying/goes-east-west/goes-r-series-data-products)
- [Cloud-top height and layers](https://goes-r.noaa.gov/products/baseline-cloud-top-height-cloud-layer.html)
- [Cloud optical depth](https://goes-r.noaa.gov/products/baseline-cloud-opt-depth.html)
- [Algorithm documents](https://www.star.nesdis.noaa.gov/goesr/documentation_ATBDs.php)
- [Fog and Low Stratus](https://vlab.noaa.gov/web/towr-s/goes-16-fog-and-low-stratus)
- [Derived Motion Winds](https://goes-r.noaa.gov/products/baseline-derived-motion-winds.html)

GOES sees the radiatively dominant top, not the full column. High cloud can
hide fog; day/night algorithms differ; terminators are difficult; and cloud
top is not cloud base. Correct perspective displacement using cloud height and
satellite geometry; see
[Parallax Shift in GOES ABI Data](https://repository.library.noaa.gov/view/noaa/52613).

### METAR, SPECI, SWOB, and radar

Use stations for visibility, ceiling, layers, fog/mist codes, temperature,
dew point, and wind. Preserve distance, elevation, age, coastal regime, and
representativeness.

- [NOAA Aviation Weather API](https://aviationweather.gov/data/api/)
- [ECCC SWOB Datamart](https://eccc-msc.github.io/open-data/msc-data/obs_station/readme_obs_insitu_swobdatamart_en/)
- [ECCC GeoMet](https://api.weather.gc.ca/)

Use [ECCC radar](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_en/)
for precipitation and shower motion only:

```text
no radar echo != clear sky
```

### ECMWF and NOAA comparisons

ECMWF IFS/ENS is a strong independent source for low/middle/high cloud, cloud
base, ceiling, fog/visibility, and vertical fields. Fog, cloud base, and
ceiling are distinct diagnostics.

- [ECMWF cloud forecast guide](https://confluence.ecmwf.int/spaces/FUG/pages/673550490/Section%2B2A.1.5.2%2BClouds)
- [Open-data transition](https://www.ecmwf.int/en/about/media-centre/news/2025/ecmwf-achieve-fully-open-data-status-2025)
- [IFS 50r1 and AIFS v2](https://www.ecmwf.int/en/about/media-centre/news/2026/ifs-cycle-50r1-aifsv2-live)

NOAA RRFS is a useful independent North American comparison, but its 2026
transition, product maturity, and coverage require monitoring:

- [RRFS overview](https://gsl.noaa.gov/rrfs/)
- [RRFS v1 status](https://gsl.noaa.gov/rrfs/rrfsv1/)

## Short-term nowcasting

For zero to two hours, prioritize GOES cloud probability, optical depth, phase,
layer and fog products; METAR/SPECI and SWOB; and HRDPS as the evolving
background. Use height-aware cloud motion or image optical flow. Radar only
adds evidence for precipitating cloud.

```text
observed state at analysis time
    -> advect cloud constraints
    -> blend toward HRDPS as lead increases
    -> widen uncertainty near cloud boundaries
```

Pure advection misses formation and dissipation, so NWP tendency and
low-level thermodynamics remain necessary.

For two to twelve hours, calculate current state error:

```text
initial_state_error = observed_GOES_station_state - HRDPS_state_now
```

Decay the correction using historical validation, separately for low/fog,
middle, high, coastal/inland, boundary displacement, and day/night regimes.

For twelve to forty-eight hours, use HRDPS, REPS, run-to-run stability, and
independent model disagreement. Return timing and site-rank uncertainty.

## Paid and commercial APIs

The full paid-versus-open provider assessment, including air quality,
commercial differentiation, licensing, and procurement, is in
[Paid cloud, fog, aerosol, and air-quality APIs](paid-environmental-apis.md).

| Provider | Vertical capability | Best role | Main limitation |
| --- | --- | --- | --- |
| Meteomatics | Excellent | Multi-model scientific backend | Cost; downscaled grid is not native resolution |
| Tomorrow.io | Moderate/good operational fields | Point forecast and redundancy | Proprietary blend; limited vertical transparency |
| WeatherKit | Surface/blended | Apple UI and comparison | Opaque blend |
| Google Weather | Surface/blended | Consumer comparison | Total cloud only |
| Aeris/Xweather | Aviation observations | Conditions and alerts | Not a raw 3-D NWP service |
| Windy | Layer visualization | Human QA | App rights do not imply raw extraction rights |
| Visual Crossing/Weatherbit/OpenWeather | Surface aggregate | Cheap UI or backup | Inadequate vertical science |
| Spire | Radio-occultation profiles | Future assimilation research | Expensive; indirect cloud value |
| DTN | Managed operations | Enterprise support | Cost and limited transparency |
| Vaisala | Sensors and aviation truth | Visibility/ceilometer validation | Not a gridded forecast |

### Meteomatics

Meteomatics is the strongest paid technical candidate because it exposes
source models, ensemble members, pressure/height levels, initialization
metadata, many parameters, and point/line/area queries including NetCDF.

- [Weather API](https://www.meteomatics.com/en/weather-api/)
- [Request and model selection](https://www.meteomatics.com/en/api/request/)
- [OpenAPI explorer](https://swagger-ui.meteomatics.com/)

Fine advertised downscaling does not mean cloud microphysics were dynamically
simulated at that resolution. Preserve source model, native grid, returned
grid, and postprocessing version. Before purchase, confirm Canadian regional
models, ensemble members, hydrometeors, archived operational forecasts,
caching, and derived-output redistribution rights.

### Tomorrow.io and consumer APIs

Tomorrow.io exposes cloud cover, cloud base, ceiling, visibility, humidity,
dew point, and plan-dependent probabilistic fields:

- [API documentation](https://docs.tomorrow.io/reference/welcome)
- [Data layers](https://docs.tomorrow.io/reference/weather-data-layers)
- [Probabilistic forecasts](https://docs.tomorrow.io/reference/probabilistic-forecasting)

It is the strongest low-engineering point API but does not expose a complete
transparent hydrometeor atmosphere.

[WeatherKit](https://developer.apple.com/weatherkit/) and
[Google Weather](https://developers.google.com/maps/documentation/weather/reference/rpc/google.maps.weather.v1)
are useful comparisons, not the scientific backbone. Google supplies total
cloud and surface fog predictors but no cloud strata or vertical atmosphere.

## Locally runnable models

| Model | Layered cloud/fog? | Recommendation |
| --- | ---: | --- |
| WRF | Yes | Targeted hindcasts later |
| WRF-LES | Yes, very fine scale | Research-HPC only |
| MPAS-A | Yes | Research platform, not MVP |
| ICON | Yes | Consume output first |
| FV3/UFS/RRFS | Yes | Consume operational output |
| OpenFOAM | Only with bespoke work | Not appropriate |
| Global AI models | Usually incomplete local diagnostics | Synoptic context |
| libRadtran | Optical physics, not forecasting | Offline lookup tables |

### WRF

WRF controls vertical resolution, cloud microphysics, boundary-layer and land
schemes, radiation, nests, and data assimilation. See the
[WRF physics guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

A future experiment might use a 9 km parent, 3 km regional nest, 1 km coastal
nest, 50–80 vertical levels, and multiple fog-relevant physics schemes. This
does not guarantee skill. Assimilation, cycling, sea/land state, ensembles,
bias correction, verification, HPC reliability, and failover are the harder
parts. A fine startup WRF run can be worse than HRDPS.

Only run WRF after archived validation identifies a recurring, valuable HRDPS
failure that a targeted experiment might correct. WRF-LES over a useful region
is a research-HPC project.

### ICON, MPAS, FV3, and AI models

[ICON](https://www.icon-model.org/) and
[MPAS-Atmosphere](https://www2.mmm.ucar.edu/projects/mpas/mpas_website/build/html/)
can represent sophisticated cloud physics, as can FV3/UFS. None removes the
assimilation and operational burden. Consume official output first.

AIFS, GraphCast, GenCast, Pangu-Weather, FourCastNet, Microsoft Aurora, and
WeatherNext are useful for large-scale circulation and model diversity. Their
usual public fields do not establish better local fog, low-stratus, ceiling,
thin-cirrus, or ten-minute clearing skill.

### libRadtran

Use [libRadtran](http://www.libradtran.org/) offline for spectral extinction,
auroral bands, Moonlight, aerosols, idealized thin clouds, camera filters, and
future sunset experiments. It does not predict cloud location.

## Full 3-D research frontier

Research systems combine multi-angle imagery, radar/lidar, neural cloud
reconstruction, and Monte Carlo radiative transfer:

- [AI-derived 3-D cloud tomography](https://amt.copernicus.org/articles/17/961/2024/index.html)
- [Cloud tomography and the veiled core](https://arxiv.org/abs/1910.00077)
- [Open 3-D Monte Carlo path tracing](https://arxiv.org/abs/1902.01137)
- [Large-angle 3-D cloud radiative effects](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1002/2016JD025441)

These are not yet the operational answer because Atlantic Canada lacks dense
multi-angle/radar/lidar coverage, passive satellites cannot recover complete
cloud interiors, and input uncertainty dominates solver precision. Use them
offline for sensitivity analysis and lookup-table generation.

## Event-specific treatment

### Aurora

Trace a bundle across azimuth, elevation, auroral emission altitude, and
forecast intensity. Integrate auroral radiance after atmospheric transmission.
Distant low cloud may block low emission while leaving overhead aurora visible.

### Eclipse

Trace the apparent solar disc throughout contacts and totality. Distinguish
solar-disc visibility, corona-photography viability, thin-cloud risk, and
clearance over the complete critical interval. Thin cirrus can leave the disc
visible while ruining corona imaging.

### Deep sky and meteor showers

For deep sky, calculate transmission across the target field and optimize the
distribution of usable exposure minutes. Thin cirrus affects both attenuation
and background. For meteor showers, evaluate a weighted useful-sky fraction,
not merely the radiant point.

### Sunrise and sunset

Sunset quality is a two-path problem:

```text
Sun -> cloud illumination
cloud -> observer visibility
```

Earth shadow, curvature, refraction, aerosols, cloud shadows, phase function,
and multiple scattering matter. Keep this outside the MVP. A later model can
combine spherical illumination, libRadtran clear-air lookup tables,
single-scattering approximations, observer-path extinction, and learned
correction from calibrated images.

## Uncertainty and validation

Historical source access, exact retrieval examples, forecast-vintage
semantics, and archive fact-checking are documented in
[Historical environmental-data retrieval](historical-data-retrieval.md).

Sample across weather members, stochastic subcolumns, satellite perturbations,
optical-property scenarios, and event geometry. Use a manageable Monte Carlo
or Latin-hypercube sample rather than the full Cartesian product.

Archive operational forecasts before truth arrives; reanalysis is not an
archived forecast. Validate:

- clear versus blocked and low/middle/high presence;
- optical-depth, visibility, and ceiling errors;
- fog onset and clearing time;
- cloud-boundary displacement;
- CRPS, Brier score, reliability, and false-clear rate;
- recommendation rank regret;
- skill by elevation, lead, season, coast/inland, and day/night.

Truth hierarchy:

```text
directional star photometry or user imagery
    > local radar/lidar/ceilometer
    > METAR/SWOB visibility and ceiling
    > GOES probability and optical depth
```

All-sky cameras observe the same geometry as the user. Plate-solved images can
derive star-count deficit, photometric attenuation, directional sky
background, and cloud motion. Relevant work includes
[CLOWN](https://arxiv.org/abs/2409.04245) and
[cloud reconstruction using star photometry](https://doi.org/10.1088/1538-3873/ad2867).
The desired label is directional transmission by time and approximate
wavelength, not station-wide cloud cover.

## Normalized interfaces

```python
class CloudField:
    x
    y
    layer_bottom_m
    layer_top_m
    cloud_fraction
    liquid_water_content_kg_m3
    ice_water_content_kg_m3
    liquid_effective_radius_m | None
    ice_effective_radius_m | None
    extinction_coefficients | None
    phase
    uncertainty
    provenance

class CloudObservation:
    observed_at
    cloud_probability
    apparent_pixel_geometry
    corrected_cloud_geometry
    cloud_top_m
    cloud_top_uncertainty_m
    cloud_optical_depth
    phase
    quality_flags
    satellite_zenith_angle

class AtmosphericRayResult:
    azimuth_deg
    apparent_elevation_deg
    wavelength_band
    direct_transmission_distribution
    clear_probability
    opaque_probability
    fog_optical_depth
    cloud_optical_depth
    aerosol_optical_depth
    dominant_intersection
    uncertainty_sources
    provenance
```

## Provider bake-off

Before buying an API, compare identical archived operational forecasts for
20–50 Atlantic Canadian sites across at least one fog season:

1. Direct HRDPS and REPS.
2. Meteomatics source-selected Canadian model and proprietary mix.
3. Tomorrow.io.
4. ECMWF/ICON.
5. One consumer blend such as WeatherKit or Google.

Measure cloud/fog reliability, visibility and ceiling, onset/clearance timing,
coastal/inland skill, lead dependence, freshness, outages, and directional
site-ranking regret. The likely answer is complementary evidence, not one
universal winner.

## Delivery sequence

### Phase A: directional layered heuristic

1. Discover and ingest the live HRDPS vertical/cloud/visibility inventory.
2. Trace curved rays through nominal low/middle/high slabs and adjacent cells.
3. Add METAR/SWOB fog, visibility, and ceiling.
4. Return intersections and uncertainty without inventing optical depth.

### Phase B: observed correction

5. Add GOES probability, top, layer, phase, and optical depth.
6. Correct GOES parallax and preserve quality flags.
7. Add height-dependent motion for zero-to-two-hour nowcasts.
8. Add REPS member-by-member uncertainty.

### Phase C: probabilistic extinction

9. Replace nominal slabs with reconstructed model layers and hydrometeors.
10. Convert hydrometeors and particle assumptions into extinction.
11. Add correlated stochastic subcolumns.
12. Cache rays by candidate, time, azimuth, elevation, and band.

### Phase D: calibration and research

13. Deploy or partner with representative all-sky cameras.
14. Calibrate directional transmission distributions.
15. Evaluate Meteomatics and Tomorrow.io against the public stack.
16. Consider WRF hindcasts only for a demonstrated recurring deficiency.
17. Keep full 3-D radiative transfer and sunset scoring as later research.

## Scientific guardrails

- Cloud fraction is not transmission.
- Total cloud is not a vertical profile.
- Satellite cloud top is not cloud base.
- Cloud optical depth is not geometric thickness.
- Vertical optical depth cannot use simple secant scaling near the horizon.
- Satellite pixels require parallax correction.
- A clear observer pixel does not imply a clear distant ray.
- Surface visibility does not automatically apply through the boundary layer.
- Aerosol, fog, and cloud extinction remain separate components.
- Beer–Lambert transmission does not predict diffuse sky background.
- Full 3-D transfer cannot compensate for a bad cloud field.
- Daytime retrieval skill cannot be assumed at night.
- Missing vertical information increases uncertainty.
- No observation means unknown, not clear.

## Final recommendation

```text
HRDPS primary forecast
    + REPS uncertainty
    + GOES current-state correction
    + METAR/SWOB fog and ceiling
    + ECMWF/ICON/RRFS disagreement
    + probabilistic curved-ray extinction
    + local all-sky calibration
    + one commercial API for redundancy
```

The defensible product advantage is an observation-specific cloud-transmission
decision layer, not a replacement for a national weather service.
