# State-of-the-art environmental and aurora models

Last reviewed: 2026-08-10

## Executive conclusion

The practical state of the art for Astraeus is not one large simulation. It is
an observation-aware fusion system:

```text
regional convection-permitting NWP
    + ensemble uncertainty
    + geostationary satellite observations
    + surface observations
    + atmospheric-composition models
    + radiative-transfer approximations
    + auroral precipitation and solar-wind models
    + observer geometry
    + local statistical calibration
```

Global AI weather models are increasingly state of the art for medium-range
synoptic forecasting. Most do not directly solve the product's hardest
question: whether a specific Atlantic Canadian site will have thin cirrus, low
cloud, fog, or a usable northern line of sight during a narrow time window.

The highest-leverage proprietary model is therefore likely to be a calibrated
decision model such as:

```text
P(clear usable line of sight |
  site,
  time,
  viewing azimuth and elevation,
  HRDPS,
  REPS,
  GOES history,
  surface observations,
  aerosols,
  terrain,
  season)
```

That output can then be combined with an equipment-specific aurora visibility
model. Do not present the result as a probability until it has been calibrated
against representative outcomes.

## What “state of the art” means

Three different questions are often conflated:

1. **What is the best operational output Astraeus can consume?** National
   centers provide assimilation, ensembles, satellites, quality control, and
   supercomputer operations that a startup should reuse.
2. **What is the most capable model Astraeus could technically run?** WRF,
   MPAS, SILAM, libRadtran, Illumina, SWMF, and multiple AI models are runnable,
   but require very different inputs and expertise.
3. **What is the best model for the actual product decision?** Usually a much
   smaller fusion and calibration model over authoritative upstream products.

Running pretrained inference is not the same as operating a forecasting
system. Production operation also requires current analysis-quality initial
conditions, field transformations, boundary conditions, missing-run handling,
ensembles, storage, monitoring, version management, verification, and failover.

## Recommended source hierarchy

| Requirement | Primary | Secondary or research |
| --- | --- | --- |
| Short-range weather | ECCC HRDPS | NOAA RRFS, ECCC RDPS |
| Weather uncertainty | ECCC REPS | ECMWF ENS/AIFS ENS |
| Longer-range weather | GDPS/GEPS | IFS/AIFS, WeatherNext 2, GFS/GEFS |
| Current cloud | GOES-East ABI | Surface observations |
| Fog and visibility | HRDPS + GOES FLS + METAR/ECCC stations | Local calibrated model |
| Canadian particulates | ECCC RAQDPS | CAMS, GEOS-CF |
| Wildfire smoke | ECCC FireWork | RRFS-Smoke/Dust |
| Aerosol optical depth | CAMS + GOES AOD | GEOS-CF |
| Atmospheric transmission | Offline libRadtran lookup tables | SCIATRAN |
| Emitted artificial light | VIIRS Black Marble | Municipal inventories |
| Directional skyglow | Precomputed heuristic | Illumina research |
| Immediate aurora | NOAA OVATION + SWPC real-time solar wind | Regional magnetometers |
| One-to-four-day aurora context | WSA–Enlil + SWPC forecasts | CME ensembles |
| Aurora confirmation | All-sky cameras + magnetometers | Quality-controlled reports |

# Weather, clouds, and fog

The focused treatment of directional transmission, marine fog, curved ray
tracing, provider options, locally runnable models, and validation is in
[Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md).
The commercial-provider and procurement analysis is in
[Paid cloud, fog, aerosol, and air-quality APIs](paid-environmental-apis.md).

## ECCC HRDPS

**Status:** operational output; consume rather than self-run.

Published characteristics:

- approximately 2.5 km Canadian regional grid;
- forecast horizon around 48 hours;
- up to four runs daily;
- hourly forecast output;
- surface and vertical atmospheric fields in GRIB2.

Sources:

- [HRDPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/)
- [HRDPS GRIB2 specification](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/)

### Benefits

- Best open operational starting point for Atlantic Canada.
- Better coastline, terrain, sea-breeze, and mesoscale representation than
  global models.
- Supplies a consistent state across cloud, humidity, temperature, wind,
  visibility, and precipitation.
- Operational assimilation and maintenance are handled by ECCC.
- Public GRIB2 distribution through HTTPS and AMQP-oriented workflows.

### Drawbacks

- Deterministic: only one atmospheric realization.
- A 2.5 km cell cannot resolve every coastal fog bank or small cloud opening.
- Model cloud fraction is not optical transmission.
- Distributed fields may be a subset of internal model variables.
- Low cloud and fog remain difficult even at convection-permitting resolution.

### Recommendation

Use as the primary zero-to-48-hour weather model. Verify the live inventory for
total/low/middle/high cloud, visibility, RH, dew point, cloud base, liquid/ice
water, and relevant vertical fields before freezing the normalized schema.

## ECCC REPS

**Status:** operational regional ensemble output.

Published characteristics include:

- approximately 10 km;
- 20 perturbed members plus a control member;
- four runs daily;
- individual-member and statistical GRIB2 products.

Source: [REPS GRIB2 documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_reps/readme_reps-datamart_en/)

### Benefits

- Represents cloud and timing uncertainty.
- Supports member-by-member location scoring.
- Reveals whether the preferred location is stable across plausible outcomes.
- More defensible than deriving confidence from deterministic HRDPS alone.

### Drawbacks

- Too coarse for small coastal openings and fog tongues.
- The ensemble mean blurs cloud boundaries and is not a synthetic best
  forecast.
- Full-member ingestion increases network, storage, and compute requirements.
- Exact public cloud fields need a feasibility check.

### Recommendation

Add after deterministic HRDPS works. Preserve member identity and score every
member rather than scoring only the ensemble mean.

## ECCC RDPS, GDPS, and GEPS

Use:

- RDPS for intermediate regional guidance;
- GDPS for global guidance to roughly ten days;
- GEPS for broad uncertainty and “worth monitoring” alerts.

Sources:

- [RDPS](https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps-datamart_en/)
- [GDPS](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps_en/)
- [GEPS](https://eccc-msc.github.io/open-data/msc-data/nwp_geps/readme_geps_en/)

GDPS 10.0 is notable because its physical forecast is spectrally nudged at
large scales toward ECCC's GEML AI forecast. This hybrid retains physical-model
diagnostics while improving broad medium-range guidance. See the [GDPS
changelog](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/changelog_gdps_en/).

These models are valuable for synoptic context but too coarse for a precise
site/window decision.

## ECMWF IFS and ENS

**Status:** operational physical global forecast and ensemble benchmark.

### Benefits

- Among the strongest global medium-range systems.
- Sophisticated data assimilation and ensemble construction.
- Rich cloud, radiation, surface, and vertical diagnostics.
- Independent model family for disagreement detection.

### Drawbacks

- Complete or full-resolution access may carry cost/licensing constraints.
- Global resolution cannot resolve individual coastal fog banks.
- Large data volume.
- Running IFS independently is not a practical startup path.

### Recommendation

Ingest selected output later if access and value justify the expense. Do not
attempt to reproduce the operational IFS.

## ECMWF AIFS Single and AIFS ENS

**Status:** operational deterministic and ensemble AI forecast systems.

AIFS Single became operational in 2025. AIFS ENS is an operational 51-member AI
ensemble. Open output is distributed on approximately a 0.25° grid with
six-hour steps to 15 days. ECMWF also publishes weights and Anemoi tooling.

Sources:

- [AIFS datasets](https://www.ecmwf.int/en/forecasts/datasets/aifs-machine-learning-data)
- [Operational AIFS ensemble](https://www.ecmwf.int/en/about/media-centre/news/2025/ecmwfs-ensemble-ai-forecasts-become-operational)
- [Anemoi documentation](https://anemoi.readthedocs.io/en/latest/index.html)

### Benefits

- Operationally maintained rather than only a research model.
- Fast and relatively inexpensive inference.
- Strong medium-range large-scale skill.
- Ensemble scenarios.
- Open output and weights.

### Drawbacks

- Too coarse spatially and temporally for narrow local observation windows.
- Physics-based ENS still provides important high-resolution and coupled
  diagnostics.
- Broad wind/temperature/geopotential skill does not establish low-cloud or fog
  skill.
- Self-running still requires current analyses, exact transformations,
  monitoring, and validation.

### Recommendation

This is one of the first global AI families to evaluate and remains distinct
from research systems because it is operated by a meteorological center.
Consume the open operational output before attempting self-hosted inference.

## NOAA HRRR and RRFS

RRFS is NOAA's next-generation approximately 3 km North American regional
system, transitioning operationally during 2026.

Source: [NOAA RRFS](https://gsl.noaa.gov/rrfs/)

### Benefits

- High resolution and frequent updates.
- Independent physical-model family.
- Potential broad North American coverage.
- Future coupled smoke and dust products.

### Drawbacks

- Operational transition and changing products during 2026.
- Exact Atlantic Canada coverage and edge quality need testing.
- NOAA assimilation and tuning are strongest over the United States.
- Should not replace HRDPS without local verification.

### Recommendation

Benchmark RRFS against HRDPS when production feeds stabilize.

# Global AI weather models that can be run

## WeatherNext 2

**Status:** public research code, pretrained weights, daily forecast feeds, and
experimental managed inference. Repository support was added in release
`v0.3.0` on 2026-08-06.

WeatherNext 2, previously described as the Functional Generative Network
(FGN), is Google's current global probabilistic medium-range model and succeeds
WeatherNext Gen/GenCast for new projects.

Published characteristics:

- 64-member ensemble forecast;
- 0.25° global grid, approximately 30 km at the equator;
- six-hour standard output and initialization cadence;
- 15-day forecast horizon;
- experimental one-hour output through Vertex AI;
- initialization from ECMWF HRES initial conditions;
- graph-transformer architecture with learned/noisy weight perturbations;
- four independently trained operational-model checkpoints;
- operational checkpoint trained through 2024 and fine-tuned on HRES;
- Apache 2.0 code, with other released materials under CC BY 4.0.

Sources:

- [WeatherNext repository](https://github.com/google-deepmind/weathernext)
- [WeatherNext v0.3.0 release](https://github.com/google-deepmind/weathernext/releases/tag/v0.3.0)
- [WeatherNext model guide](https://developers.google.com/weathernext/guides/models)
- [FGN technical report](https://arxiv.org/abs/2506.10772)
- [WeatherNext 2 announcement](https://blog.google/innovation-and-ai/models-and-research/google-deepmind/weathernext-2/)

### Released artifacts and access

The repository provides four independently trained WN2 checkpoints:

```text
WeatherNext2_<2025_model1.npz
WeatherNext2_<2025_model2.npz
WeatherNext2_<2025_model3.npz
WeatherNext2_<2025_model4.npz
```

It also provides:

- WeatherNext Cyclones checkpoints corresponding to multiple training years;
- a one-degree Mini checkpoint for lower-memory testing;
- a Colab workflow that loads weights and HRES sample inputs, runs rollouts,
  visualizes output, and performs cyclone tracking;
- pretrained weights and samples in a public Google Cloud bucket;
- daily forecasts through Google Cloud, Earth Engine, BigQuery, WeatherLab,
  Open-Meteo, and related Google services;
- experimental custom inference through Vertex AI.

The full models are optimized for TPU. Google documents `v5p`-class TPU use or
an H100-class GPU for sufficient memory. The one-degree Mini model can run on a
P100-class GPU but is explicitly lower skill and resolution. The repository is
research code supplied without API-stability guarantees, so production
experiments should pin `v0.3.0` or another reviewed release.

### Output variables

WeatherNext 2 predicts the following at 13 pressure levels from 50 to 1000 hPa:

- geopotential;
- specific humidity;
- temperature;
- U and V wind;
- vertical velocity.

Surface fields include:

- 2 m temperature;
- 10 m and 100 m wind;
- mean sea-level pressure;
- total precipitation;
- sea-surface temperature.

It does **not** currently expose the variables most directly needed for
astronomical visibility:

- total, low, middle, or high cloud fraction;
- cloud base or cloud-top height;
- cloud liquid or ice water;
- cloud optical depth;
- fog probability or surface visibility;
- aerosol optical depth, smoke, or PM2.5.

Pressure-level humidity can support broad regime and derived-risk features, but
it is not equivalent to an operational cloud, fog, or transmission forecast.

### Benefits

- Current leading Google global AI ensemble, replacing GenCast for new work.
- Six-hour standard output versus GenCast's twelve-hour output.
- 64 coherent ensemble scenarios through 15 days.
- Released code, weights, examples, and daily precomputed feeds.
- Operational HRES initialization rather than an ERA5-only research setup.
- Google reports improvement over WeatherNext Gen on 99.9% of evaluated
  variables and lead times.
- Fast inference relative to physics-based global ensembles.
- Potentially useful for three-to-ten-day regime, humidity, precipitation, and
  storm-timing disagreement.

The 99.9% claim is a comparison with Google's prior WeatherNext Gen model over
its evaluated variables and lead times. It is not evidence that WN2 beats every
operational model for every location or that it predicts local cloud/fog skill.

### Drawbacks

- Approximately 30 km is far too coarse for coastal fog tongues, broken-cloud
  edges, or individual observing sites.
- Standard six-hour output remains too coarse for a ten-minute observation
  optimizer; the one-hour path is experimental and platform-dependent.
- Released variables omit explicit clouds, visibility, fog, optical depth, and
  aerosols.
- Self-hosting the full model requires TPU or H100-class hardware plus timely
  HRES initialization and exact preprocessing.
- Research code is supplied as-is without API-stability guarantees.
- HRES inputs, training data, managed services, and third-party feeds can have
  separate access, licensing, attribution, or cost terms.
- Broad probabilistic benchmark skill does not establish Atlantic Canadian
  astronomy-specific skill.

### Recommended Astraeus use

Start with a small subset of precomputed daily WN2 output rather than
self-hosting:

1. Archive WN2 members over Atlantic Canada.
2. Compare humidity, precipitation, and synoptic evolution against GDPS/GEPS,
   AIFS ENS, and observed outcomes.
3. Test whether WN2 improves three-to-ten-day `watch` notifications.
4. Derive supporting features such as humidity-profile spread, precipitation
   member fraction, regime confidence, and storm-timing disagreement.
5. Self-host only if feed latency, missing fields, custom inference, or cost
   provides a measured reason.

WeatherNext 2 does not replace HRDPS, REPS, GOES, or surface observations:

```text
WeatherNext 2
    -> global medium-range regime and ensemble uncertainty

HRDPS + REPS
    -> regional Atlantic Canadian cloud and fog evolution

GOES + stations/METAR
    -> current cloud, ceiling, visibility, and forecast verification
```

**Verdict:** highest-priority Google AI model for later evaluation through its
precomputed feeds; not a direct cloud/fog source or an MVP dependency.

## GraphCast

Characteristics:

- Apache-2.0 code and public weights;
- 0.25° global grid;
- 37 pressure levels in the full model;
- six-hour steps;
- ten-day deterministic forecast.

Sources:

- [Official repository](https://github.com/google-deepmind/graphcast)
- [DeepMind overview](https://deepmind.google/blog/graphcast-ai-model-for-faster-and-more-accurate-global-weather-forecasting/)

### Benefits

- Mature reproducible implementation.
- Very fast global inference.
- Strong medium-range benchmark performance.
- Useful for architecture and research experiments.

### Drawbacks

- Approximately 25–28 km, far too coarse for coastal fog.
- Does not directly model site visibility, detailed cloud microphysics, or
  cloud optical depth.
- Deterministic.
- Requires two compatible global atmospheric states and exact preprocessing.
- Operational initialization is much harder than downloading weights.

**Verdict:** legacy research baseline, not the product's cloud model. Use WN2
for new Google-model evaluations unless GraphCast comparability is required.

## GenCast

Characteristics:

- stochastic global ensemble;
- 0.25° grid;
- twelve-hour steps in the published system;
- up to 15 days;
- public research implementation and weights.

Sources:

- [GenCast announcement](https://deepmind.google/blog/gencast-predicts-weather-and-the-risks-of-extreme-conditions-with-sota-accuracy/)
- [Original paper](https://arxiv.org/abs/2312.15796)

### Benefits

- Strong probabilistic medium-range performance.
- Ensemble structure aligns with decision-making.
- Fast relative to physical ensembles.

### Drawbacks

- Full-resolution reference inference can require substantial accelerator
  memory.
- Twelve-hour steps cannot support a ten-minute local window.
- Same direct cloud/fog limitations as GraphCast.
- Significant initialization and operational burden.

**Verdict:** legacy research comparison. WN2 supersedes it for new Google-model
work; consuming WN2 or AIFS ENS output is more practical than self-hosting
GenCast.

## Microsoft Aurora

Characteristics:

- approximately 1.3 billion parameters;
- PyTorch code and public checkpoints;
- weather, air-pollution, ocean-wave, and tropical-cyclone specializations;
- surface and pressure-level inputs.

Sources:

- [Official repository](https://github.com/microsoft/aurora)
- [Nature paper](https://www.nature.com/articles/s41586-025-09005-y)
- [API documentation](https://microsoft.github.io/aurora/api.html)

### Benefits

- Earth-system foundation model rather than weather only.
- Includes an air-pollution specialization.
- Public Python/PyTorch implementation.
- Potentially fine-tunable for Atlantic Canada.
- Interesting basis for future coupled weather/composition experiments.

### Drawbacks

- Commercial use requires legal/licensing review; the repository directs
  commercial users to contact Microsoft.
- Fine-tuning needs representative data, expertise, and substantial compute.
- Published broad skill does not establish local fog/cloud-transmission skill.
- “High resolution” in global AI literature is not site scale.
- Operational preprocessing remains substantial.

**Verdict:** best AI research candidate for Astraeus, but not an MVP dependency.

## Pangu-Weather

Characteristics:

- 0.25° global grid;
- 13 pressure levels;
- public inference code and weights;
- ERA5/ECMWF-compatible initialization;
- non-commercial weight licence.

Source: [Official repository](https://github.com/198808xc/Pangu-Weather)

### Benefits

- Fast and historically important.
- Relatively straightforward inference.

### Drawbacks

- Non-commercial licence is disqualifying for a normal product.
- Coarse and sparse vertically for local cloud work.
- Deterministic.
- Older than operational AIFS.

**Verdict:** academic comparison only.

## FourCastNet

Source: [Official repository](https://github.com/NVlabs/FourCastNet)

### Benefits

- Open artifacts and NVIDIA ecosystem.
- Fast inference.
- Useful educational baseline.

### Drawbacks

- Superseded by newer systems.
- Limited variables for cloud/fog work.
- Original-scale training requires major HPC.
- No compelling product advantage.

**Verdict:** skip for product work.

## NeuralGCM

Characteristics:

- hybrid differentiable physics and learned parameterizations;
- open code and weights;
- checkpoints around 0.7°, 1.4°, and 2.8°;
- deterministic and stochastic configurations.

Source: [Official repository](https://github.com/neuralgcm/neuralgcm)

### Benefits

- Scientifically interesting hybrid approach.
- Differentiable.
- Useful for weather and climate research.

### Drawbacks

- Far too coarse for local observing weather.
- Not an operational regional nowcast.
- No established local fog advantage.

**Verdict:** not relevant to the near-term product.

# Multilayer cloud observations

Useful astronomical cloud state should eventually include:

- total, low, middle, and high cloud fractions;
- cloud base and top;
- cloud-top pressure, height, and temperature;
- liquid and ice water;
- cloud phase;
- cloud optical depth;
- overlapping layers;
- temporal persistence and motion;
- model/observation disagreement.

## GOES ABI

GOES-East observes current cloud state at high cadence. Relevant products
include:

- four-level cloud mask and pixel cloud probability;
- cloud-top height, pressure, and temperature;
- cloud-layer classification;
- cloud phase and particle size;
- cloud optical depth;
- derived motion winds;
- fog and low-stratus products;
- aerosol detection and optical depth.

Sources:

- [GOES-R product catalogue](https://www.nesdis.noaa.gov/our-satellites/currently-flying/goes-east-west/goes-r-series-data-products)
- [Algorithm documentation](https://www.star.nesdis.noaa.gov/goesr/documentation_ATBDs.php)
- [NOAA cloud products](https://www.ospo.noaa.gov/products/atmosphere/clouds.html)

### Benefits

- Observes actual clouds rather than the expected state.
- High update frequency.
- Public data.
- Detects forecast errors and moving boundaries.
- Atlantic Canada is covered by GOES-East.

### Drawbacks

- Sees cloud tops more directly than cloud bases.
- High layers can obscure low cloud.
- Thin cirrus and broken cloud are difficult.
- Nighttime optical-depth retrieval is less capable.
- Coastal pixels, snow/ice, parallax, and oblique viewing cause errors.
- Some derived full-disk products are coarser than raw imagery.

### Recommended cloud nowcast

1. Use the latest three to six cloud masks or infrared frames.
2. Estimate motion with derived motion winds or optical flow.
3. Advect cloud probability for approximately 15–120 minutes.
4. Blend progressively toward HRDPS with increasing lead time.
5. Increase uncertainty near boundaries and where frames disagree.

Measure this simple baseline before considering neural satellite nowcasting.

# Fog and visibility

There is no single fog model sufficiently reliable for this use. Fuse:

```text
HRDPS visibility
    + low-cloud fraction and cloud base
    + temperature/dew-point spread
    + relative humidity
    + low-level wind and stability
    + GOES Fog/Low Stratus
    + METAR visibility and ceiling
    + ECCC stations
    + coastal regime and season
```

NOAA's Fog and Low Stratus product supplies aviation-oriented categories and
geometric cloud-thickness information at high cadence. See [NOAA cloud
products](https://www.ospo.noaa.gov/products/atmosphere/clouds.html).

### Benefits

- Combines predicted and observed evidence.
- Detects model failure.
- Can be calibrated locally.

### Drawbacks

- Fog under high cloud can be hidden from satellite.
- Ground fog may be below satellite detection limits.
- Station visibility is local.
- Model fog is sensitive to SST, soil moisture, turbulence, aerosols, and
  subgrid terrain.

### Recommendation

After collecting history, train a calibrated tabular model against METAR and
station outcomes, stratified by coast, season, lead time, and model run. Do not
start with a bespoke neural fog simulator.

# Aerosols, smoke, and particulates

## ECCC RAQDPS

**Status:** operational 72-hour, approximately 10 km North American air-quality
output.

Source: [RAQDPS Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps-datamart_en/)

### Benefits

- Best regionally relevant Canadian source.
- PM2.5, ozone, NO₂, and related pollutants.
- Operational and public.
- Useful conservative transparency penalty.

### Drawbacks

- Surface PM2.5 is not column optical depth.
- PM mass does not fully describe wavelength-dependent scattering.
- Approximately 10 km.
- Not designed for astronomical extinction.

## ECCC FireWork

**Status:** operational wildfire-smoke forecast, roughly 10 km, twice daily,
about 72 hours.

Source: [FireWork Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps-fw/readme_raqdps-fw-datamart_en/)

### Benefits

- Explicit wildfire emission sources.
- Surface and column smoke products.
- Best Canadian smoke input.
- Supports explanations identifying smoke as the primary risk.

### Drawbacks

- Sensitive to fire detection, future fire behavior, emissions, and plume
  rise.
- Fine plume edges are unresolved.
- Twice-daily fire ingestion can miss rapid changes.
- PM still needs optical conversion.

## CAMS global composition

**Status:** operational global composition forecast, twice daily, approximately
five days.

CAMS supplies more than 50 chemical species and aerosol families including
dust, sea salt, organic matter, black carbon, sulphate, nitrate, and ammonium.
Public output is approximately 0.4°.

Sources:

- [CAMS forecast dataset](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview)
- [Copernicus licence](https://ads.atmosphere.copernicus.eu/licences/licence-to-use-copernicus-products)

### Benefits

- Direct total and species-resolved aerosol optical depth.
- Vertical aerosol distributions.
- Long-range smoke and dust context.
- Assimilated, physically and chemically consistent forecast.

### Drawbacks

- Too coarse for a local site decision.
- Large requests and possible queue latency.
- Total-column AOD does not by itself locate the aerosol vertically.
- Global emission errors can misplace plumes.

### Recommendation

Use as the primary secondary source for AOD and aerosol species.

## NASA GEOS-CF version 2

**Status:** experimental/research global composition analysis and five-day
forecast at approximately 25 km.

Sources:

- [GEOS-CF overview](https://gmao.gsfc.nasa.gov/science-snapshots/improved-atmospheric-composition-forecasting-in-geos-cf-version-2/)
- [GEOS-CF data access](https://gmao.gsfc.nasa.gov/gmao-products/geos-cf/data-access_geos-cf/)

### Benefits

- Rich chemistry and aerosol fields.
- Developer-friendly public Zarr access.
- Independent composition family.
- Useful for replay and validation.

### Drawbacks

- One daily cycle.
- No operational continuity guarantee.
- Too coarse locally.
- Self-running GEOS-CF is an HPC research program.

**Recommendation:** phase-two comparison source.

## NOAA RRFS-Smoke/Dust

RRFS-Smoke/Dust may become the most useful independent high-resolution aerosol
model for Atlantic Canada because it combines an approximately 3 km North
American domain, high cadence, smoke, and dust.

Source: [NOAA RRFS](https://gsl.noaa.gov/rrfs/)

Its main drawback is operational maturity: exact fields, cadence, retention,
coverage, and product stability should be rechecked after transition.

# Atmospheric transmission

Do not equate AQI or surface PM2.5 with astronomical transparency. Useful
optical inputs include:

- spectral or 550 nm aerosol optical depth;
- aerosol type and vertical distribution;
- relative humidity and hygroscopic growth;
- molecular/Rayleigh optical depth;
- water vapor;
- cloud optical depth;
- viewing zenith angle and airmass;
- Moon and artificial-light geometry;
- camera or eye spectral response.

A first-order direct-beam conversion is:

```text
extinction_magnitudes ≈ 1.086 × optical_depth × airmass
```

This does not capture multiple scattering or increased sky background.

## libRadtran

**Status:** mature open-source GPL radiative-transfer package.

Sources:

- [libRadtran project](https://libradtran.org/doku.php?id=start)
- [libRadtran manual](https://www.libradtran.org/doc/libRadtran.pdf)

### Benefits

- Multiple validated radiative-transfer solvers.
- Supports molecules, aerosols, clouds, albedo, geometry, and spectra.
- Suitable for camera-passband and naked-eye lookup-table generation.
- Reproducible and scriptable.

### Drawbacks

- Inputs require significant scientific care.
- Standard workflows are solar/thermal, not city-light geometry.
- Plane-parallel calculations do not model 3-D light domes.
- Monte Carlo calculations can be expensive.
- Full execution per candidate/time request is unnecessary.
- GPL integration should receive architectural/legal review.

### Recommendation

Run offline to create versioned lookup tables and validate heuristics. Do not
run the full solver for each API request.

## RTTOV

RTTOV is fast and operationally proven for satellite-channel radiance
simulation.

Source: [NWP SAF RTTOV](https://nwp-saf.eumetsat.int/site/software/rttov/)

It is excellent for assimilation and retrieval research but poorly matched to
ground-to-sky astronomical visibility. Prefer NOAA's derived GOES products.

## MODTRAN

Source: [MODTRAN licensing](https://modtran.spectral.com/modtran_order)

### Benefits

- Mature detailed spectral transmission.
- Strong sensor/passband tooling.

### Drawbacks

- Commercial licence and production-use fees.
- Redistribution restrictions.
- Little MVP advantage over libRadtran.

**Recommendation:** avoid unless a later requirement justifies the licence.

## SCIATRAN

SCIATRAN is an open/LGPL spherical and plane-parallel alternative.

Source: [SCIATRAN downloads](https://www.iup.uni-bremen.de/sciatran/download/index.html)

It offers strong spectral, spherical-geometry, and polarization capability but
is larger and harder to operationalize. Treat it as a research alternative.

# Light pollution

## VIIRS Black Marble Collection 2

**Status:** authoritative daily, monthly, and yearly nighttime-light products
at approximately 500 m.

Sources:

- [Black Marble catalogue](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/science-domain/nighttime-lights/)
- [Collection 2 guide](https://landweb.modaps.eosdis.nasa.gov/data/userguide/BlackMarbleUserGuide_Collection2.0_20241203.pdf)

### Benefits

- Best open emitted-light raster for the MVP.
- Corrected products account for lunar effects, atmosphere, terrain, thermal
  effects, and stray light.
- Quality flags and multiple temporal composites.

### Drawbacks

- Measures upward radiance, not ground-observed sky brightness.
- Spectral response underrepresents some blue-rich LED effects.
- Does not reveal complete luminaire angular emission.
- Cannot resolve individual fixtures.
- Composites hide curfews, outages, and temporary lights.

### Recommendation

Use a stable corrected monthly/yearly composite first. Add daily data only when
temporary lighting and outages have demonstrated product value.

## World Atlas of Artificial Night Sky Brightness

Source: [Science Advances paper](https://doi.org/10.1126/sciadv.1600377)

### Benefits

- Estimates zenith sky brightness rather than raw upward radiance.
- Empirically calibrated and widely recognized.
- Useful benchmark.

### Drawbacks

- Based on older lighting conditions.
- Zenith-only rather than directional.
- Assumes a climatological atmospheric state.
- Commercial reuse requires legal review.

**Recommendation:** benchmark and validation only.

## Illumina

Illumina is the closest fit to physically modeling directional artificial sky
radiance. Published versions support emitted-light spectra and angular
distributions, terrain, obstacles, ground reflection, aerosols, molecular
scattering, multiple scattering, and cloud effects.

Sources:

- [Physical model paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4375359/)
- [Illumina v2 application](https://arxiv.org/abs/2005.14160)
- [Legacy source distribution](https://sourceforge.net/projects/illumina/)

### Benefits

- Directional and potentially hyperspectral skyglow.
- Can attribute source regions contributing to a viewing sector.
- Supports terrain and atmospheric effects.
- Scientifically close to the final light-dome problem.

### Drawbacks

- Requires spectral and angular light inventories that VIIRS cannot supply
  alone.
- Significant computational and data burden.
- Public source appears dated.
- Current v2 source availability and licensing are not fully clear.
- Inappropriate for live per-request use.

### Recommendation

Potential future offline research tool for precomputed directional kernels.
Do not use in the MVP runtime.

## Practical directional heuristic

Precompute per candidate and azimuth bin:

```text
directional_light_penalty =
  sum over emitting pixels:
    emitted_radiance
    × distance_kernel
    × azimuth_kernel
    × terrain_visibility
    × aerosol_and_RH_scattering_factor
```

Include a separate local-light penalty and explicitly label the result as a
heuristic rather than calibrated sky brightness.

# Aurora and space weather

No operational model directly predicts whether a person or camera at a given
site will see aurora. The physical chain is:

```text
solar eruption
    -> heliospheric propagation
    -> upstream solar-wind measurement
    -> magnetospheric response
    -> auroral precipitation
    -> line-of-sight geometry
    -> terrestrial visibility
    -> naked-eye or camera response
```

## NOAA OVATION 2020

**Status:** operational 30–90-minute auroral precipitation/intensity product.

Sources:

- [Current OVATION JSON](https://services.swpc.noaa.gov/json/ovation_aurora_latest.json)
- [NOAA product description](https://www.spaceweather.gov/products/aurora-30-minute-forecast)
- [CCMC OVATION Prime record](https://ccmc.gsfc.nasa.gov/models/Ovation-Prime~1.0/)
- [Historical OVATION Prime IDL release](https://sourceforge.net/projects/ovation-prime/) — archival research code, not the current NOAA operational implementation
- [OvationPyme](https://github.com/lkilcommons/OvationPyme) — community Python implementation, not an official NOAA SDK

The NOAA JSON URL is an official mutable raw endpoint, not a versioned client
SDK or complete archive. No maintained official NOAA OVATION SDK was identified.

### Benefits

- Best turnkey operational global auroral grid.
- Driven by measured upstream solar wind.
- Spatially much more useful than Kp.
- Public machine-readable output.
- Inexpensive older implementations are available for research.

### Drawbacks

- Predicts particle precipitation/intensity aloft, not observed brightness.
- Displayed viewing probability is not calibrated for cloud, Moon, terrain,
  camera response, or horizon distance.
- Empirical training smooths mesoscale arcs and substorms.
- NOAA can fall back to Kp when L1 data are unavailable, changing the product's
  semantics and forecast lead.
- The mutable latest endpoint requires archival and freshness monitoring.

### Recommendation

Use as the primary tactical aurora grid while exposing its driver, age, and
fallback status.

## SWPC real-time solar wind and SOLAR-1

NOAA's SWFO-L1 spacecraft was renamed **SOLAR-1**, entered its L1 orbit in
January 2026, and became operational on 2026-06-10. Do not hard-code a
DSCOVR-specific provider; use a source-agnostic `SwpcRealtimeSolarWindProvider`.

Sources:

- [SOLAR-1 designation](https://www.spaceweather.gov/news/solar-1-now-new-designation-swfo-l1)
- [Operational transition](https://www.ospo.noaa.gov/data/messages/2026/06/MSG_20260610_2105.html)
- [SWPC real-time solar wind](https://www.swpc.noaa.gov/index.php/products/real-time-solar-wind)
- [SWPC raw JSON directory](https://services.swpc.noaa.gov/json/) — official rolling machine-readable endpoints
- [NCEI DSCOVR archive](https://www.ncei.noaa.gov/products/deep-space-climate-observatory-dscovr) — official mission archive, not an exact replay of every operational screen value

Inputs should include:

- IMF Bx, By, Bz, and Bt;
- solar-wind speed, density, and temperature;
- derived dynamic pressure;
- source spacecraft and quality coverage.

### Benefits

- Most actionable immediate precursor.
- Sustained Bz, field strength, speed, density, and pressure are more useful
  than Kp alone.
- Supports rolling coupling and trend features.

### Drawbacks

- Measures one point upstream.
- Propagation time is uncertain.
- Missing or contaminated samples occur.
- A Bz reversal can quickly invalidate expectations.
- Strong coupling does not determine where a substorm arc brightens.

Compute rolling features over approximately 1, 5, 15, 30, and 60 minutes.
Never score from only the latest sample.

## WSA–Enlil

**Status:** operational heliospheric propagation model.

Sources:

- [SWPC WSA–Enlil product](https://www.spaceweather.gov/products/wsa-enlil-solar-wind-prediction) — official operational product
- [NCEP WSA–Enlil output tree](https://www.nco.ncep.noaa.gov/pmb/products/wsa_enlil/) — official raw output, with operational retention rather than an SDK guarantee
- [CCMC WSA–Enlil record](https://ccmc.gsfc.nasa.gov/models/WSA-Enlil-at-SWPC~3/) and [Runs on Request](https://ccmc.gsfc.nasa.gov/tools/runs-on-request/) — official NASA research metadata/hosted execution, not NOAA forecast-vintage APIs

### Benefits

- Best operational context for possible CME arrival over roughly one to four
  days.
- Useful for trip preparation and staged notifications.
- Physics-based propagation.

### Drawbacks

- Cone CMEs do not resolve the internal magnetic field.
- Cannot reliably forecast Bz sign and duration at Earth.
- CME geometry and launch inputs are uncertain.
- Arrival errors can be hours.
- Arrival does not imply visible aurora.

### Recommendation

Use only as a planning prior. Do not derive precise observation windows from
it.

## NOAA Geospace and SWMF

**Status:** operational global magnetosphere-ionosphere MHD modeling.

Sources:

- [SWMF overview](https://clasp.engin.umich.edu/research/theory-computational-methods/space-weather-modeling-framework/)
- [CCMC SWMF](https://ccmc.gsfc.nasa.gov/news/swmf/)
- [SWPC Geospace JSON directory](https://services.swpc.noaa.gov/json/geospace/) — official operational raw output; schema and retention must be monitored

### Benefits

- Physics-based magnetospheric response.
- Regional geomagnetic guidance.
- More informative than one planetary index.

### Drawbacks

- Expensive and operationally complex to self-host.
- Public outputs target geomagnetic hazards rather than optical visibility.
- Too coarse for individual arcs.
- Does not replace OVATION, magnetometers, or cameras.

**Recommendation:** consume selected NOAA outputs if useful; do not self-run.

## Kp and Hp30/Hp60

Kp is a global three-hour planetary magnetic index. It is not auroral
brightness, a local Atlantic Canada index, a substorm clock, a viewing
direction, solar-wind state, or a cloud-adjusted probability.

Use Kp for broad storm context. Higher-cadence Hp30/Hp60 indices are useful
research features for boundary estimation but remain planetary rather than
local.

Official access:

- [GFZ Kp DOI archive](https://datapub.gfz-potsdam.de/download/10.5880.Kp.0001/) — publisher archive; preserve definitive/provisional semantics
- [GFZ Hp30/Hp60 data and API documentation](https://kp.gfz.de/en/hp30-hp60/data) — official higher-cadence downloads/web interface
- [Kyoto WDC geomagnetic indices](https://wdcvmweb.kugi.kyoto-u.ac.jp/wdc/Sec3.html) — official Dst/AE-family service; distinguish quicklook, provisional, and final products

## NRCan and SuperMAG magnetometers

Sources:

- [NRCan observatories](https://www.geomag.nrcan.gc.ca/obs/default-en.php)
- [NRCan space-weather data](https://spaceweather.gc.ca/data-donnee/index-en.php)
- [NRCan data access and FDSN terms](https://www.geomag.nrcan.gc.ca/data-donnee/sd-en.php) — official access; redistribution/commercial use requires explicit terms review
- [SuperMAG hosted service](https://supermag.jhuapl.edu/) — official project portal, but a governed research service rather than an unrestricted raw API
- [SuperMAG processing paper](https://doi.org/10.1029/2012JA017683)

### Benefits

- Regional electrojet and substorm evidence.
- Minute-scale measurements.
- More locally relevant than Kp.
- Strong historical features for validation.

### Drawbacks

- Sparse spatial network.
- Magnetic activity is correlated with aurora, not proof of optical visibility.
- Licensing, caching, and redistribution need review.
- SuperMAG registration and contributor conditions apply.

### Recommendation

Begin licensing discussions early and support magnetometers as optional
tactical evidence.

## THEMIS and Canadian all-sky cameras

Sources:

- [THEMIS all-sky imager documentation](https://themis.igpp.ucla.edu/instrument_asi.shtml) and [download service](https://themis.igpp.ucla.edu/data_download.shtml) — official project documentation/archive
- [CSA THEMIS open-data mirror](https://donnees-data.asc-csa.gc.ca/en/dataset/d700c863-8622-4ec2-a4ee-a1c377880e2e) — official Canadian agency archive
- [AuroraX metadata documentation](https://docs.aurorax.space/about_the_data/metadata_in_aurorax/) — maintained discovery/query layer; underlying data remain governed by their providers

### Benefits

- Measures actual optical aurora.
- High cadence.
- Excellent for substorm onset and validation.
- Canada-focused network.

### Drawbacks

- Cameras suffer cloud, Moon, and local-light interference.
- Coverage is concentrated at auroral latitudes.
- Atlantic Canadian candidates may be far from useful cameras.
- Near-real-time output can be lower resolution.
- Reuse terms need review.

**Recommendation:** future confirmation and calibration input.

## PrecipNet

PrecipNet is a research neural model of auroral electron energy flux trained
from DMSP particle measurements and solar-wind/geomagnetic histories.

Sources:

- [PrecipNet paper](https://doi.org/10.1029/2020SW002684)
- [NOAA Institutional Repository copy and associated research artefacts](https://repository.library.noaa.gov/view/noaa/44545/noaa_44545_DS1.pdf) — archival research material, not a maintained operational package or service

### Benefits

- Uses temporal driver histories.
- Improved mesoscale reconstruction over OVATION Prime in its evaluation.
- Relatively inexpensive inference.

### Drawbacks

- Research model without NOAA-level operational maintenance.
- Predicts energy flux, not visible intensity.
- Does not cover every precipitation population.
- Real-time preprocessing, missing data, drift, and extremes become Astraeus's
  responsibility.

**Recommendation:** offline benchmark after a replay archive exists.

# Practical aurora fusion

## Plan-ahead: one to four days

Use:

- SWPC watches, warnings, and forecaster discussion;
- WSA–Enlil;
- forecast Kp;
- terrestrial weather ensembles.

Return broad states such as `background`, `watch`, `promising`, or `strong
setup`, with wide timing ranges and explicit CME/Bz uncertainty. Do not return a
precise twenty-minute auroral peak.

## Tactical: 30–90 minutes

Use:

- OVATION grid;
- SOLAR-1 real-time solar wind propagated toward Earth;
- rolling coupling history;
- regional magnetometers;
- optical cameras where available;
- terrestrial cloud and visibility nowcast.

## Observer-centric geometry

For each relevant OVATION cell:

1. Convert its position into time-dependent geomagnetic geometry.
2. Assign an emission-altitude distribution rather than one exact altitude.
3. Ray-trace visibility from each candidate site.
4. Calculate azimuth, elevation, and Earth-curvature obstruction.
5. Apply terrain horizon.
6. Convert precipitation to mode-specific apparent brightness using a labelled
   heuristic.
7. Integrate contributions across the visible sector.
8. Apply darkness, Moon, clouds, aerosols, and directional light pollution.
9. Keep naked-eye and camera response curves separate.

Return direction ranges, for example `NNW, 325–350°, 5–20°`, rather than false
single-degree precision.

# What Astraeus should run

## Consume operationally

- HRDPS and REPS.
- GOES ABI.
- ECCC/METAR observations.
- RAQDPS and FireWork.
- CAMS.
- VIIRS Black Marble.
- NOAA OVATION.
- SWPC real-time solar wind.
- WSA–Enlil context.

## Run locally now

- Data normalization and interpolation.
- Astronomy and line-of-sight geometry.
- Fog-risk fusion.
- Simple cloud-motion extrapolation.
- Directional light heuristic.
- Scoring and optimization.
- Offline libRadtran lookup-table generation.
- Historical validation and local calibration.

## Evaluate later

- WeatherNext 2 precomputed feeds, followed by pinned `v0.3.0` inference only
  if feed limitations justify it.
- AIFS/Anemoi inference.
- Microsoft Aurora air-pollution specialization.
- RRFS and RRFS-Smoke/Dust.
- PrecipNet.
- Local ML cloud/fog calibration.
- Neural satellite nowcasting.
- Illumina-like offline skyglow modeling.

## Do not run initially

- Full WRF, MPAS, or ICON forecasts.
- WRF-Chem, GEOS-Chem, CMAQ, or SILAM operationally.
- SWMF.
- WSA–Enlil.
- Full 3-D Monte Carlo radiative transfer.
- A global AI weather model merely because inference is fast.

# Final recommended architecture

```text
HRDPS + REPS
    |
    +-- GOES cloud/fog observations
    +-- METAR/ECCC visibility
    +-- RAQDPS/FireWork/CAMS aerosols
    +-- VIIRS directional light model
    +-- OVATION/SOLAR-1/magnetometers
    +-- astronomy/terrain geometry
    |
    v
locally calibrated clear-line-of-sight model
    |
    v
naked-eye/camera observation score
    |
    v
travel-constrained recommendation
```

The differentiating technology should be the observation-aware fusion and
calibration layer. Running a foundational weather or magnetosphere model would
cost substantially more while initially solving less of the user's decision.

# Open questions requiring feasibility tests

1. Which HRDPS multilayer cloud, visibility, condensate, and cloud-base fields
   are consistently published?
2. How reliable are GOES fog/low-stratus and optical-depth products at night
   over Atlantic Canadian coastlines?
3. Does RRFS cover the full target domain with stable cloud/smoke products?
4. Which WN2 feed has acceptable latency, retention, attribution, cost, and
   commercial terms, and does it add skill beyond GDPS/GEPS or AIFS ENS?
5. What is the practical latency and request volume for CAMS subsets?
6. Which aerosol-to-transparency mappings agree with SQM/all-sky observations?
7. What current licence applies to commercial Microsoft Aurora use?
8. Can NRCan/SuperMAG data be cached and used in derived commercial outputs?
9. What licensing and maintained code path exists for Illumina v2?
10. How often does OVATION use L1 input versus Kp fallback, and how should that
   change confidence?
11. What minimum historical archive is required before training local cloud,
    fog, and visibility calibration?
