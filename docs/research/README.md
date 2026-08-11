# Astraeus research dossier

Last reviewed: 2026-08-10

This directory preserves the product, scientific, data-source, competitor, and
implementation research for the Astraeus MVP: an aurora observation optimizer
for Atlantic Canada.

The central product question is:

> Given where I am, how far I can travel, and when I am available, where should
> I go, when should I be there, where should I look, and how good is the
> opportunity?

## Documents

- [Repositories, documentation, APIs, and SDK index](integration-tooling-index.md):
  navigation across official documentation, canonical repositories, APIs,
  producer-maintained clients, community tooling, and raw access protocols.
- [Data sources](data-sources.md): recommended weather, space-weather,
  astronomy, terrain, light-pollution, aerosol, observation, and routing
  sources.
- [Product landscape](product-landscape.md): Apple Weather/WeatherKit,
  Astrospheric, Windy.com, Acme Weather, Sheerr Weather, SpaceWeatherLive, and
  the product gap Astraeus should address.
- [Community findings](community-findings.md): recurring Reddit and
  practitioner workflows, needs, and failure modes.
- [Scientific and scoring design](scientific-design.md): normalized inputs,
  scoring constraints, uncertainty, freshness, and validation principles.
- [Observation variables and success criteria](observation-variables.md):
  target-to-background contrast, observer/equipment response, duration, wind,
  dew, seeing, site operations, event-specific variables, and value of moving.
- [Risks and uncertainties](risks-and-uncertainties.md): ranked scientific,
  operational, safety, data, and product risks; unresolved questions; evidence
  requirements; and the recommended feasibility experiment.
- [Implementation plan](implementation-plan.md): staged delivery plan,
  architecture, tests, decision gates, and MVP acceptance criteria.
- [State-of-the-art models](sota-models.md): operational and runnable weather,
  cloud, fog, aerosol, radiative-transfer, light-pollution, and aurora systems,
  including benefits, drawbacks, licensing, and recommendations.
- [Observation-site obstructions and public access](site-obstructions-and-access.md):
  terrain, trees, buildings, directional horizons, public-access evidence,
  safety checks, free/local tooling, commercial options, and validation.
- [Cloud, fog, and astronomical line-of-sight forecasting](cloud-fog-line-of-sight.md):
  probabilistic 3-D extinction, curved rays, fog and marine stratus,
  operational and commercial feeds, local models, and validation.
- [Paid environmental APIs](paid-environmental-apis.md): cloud, fog, aerosol,
  smoke, and air-quality providers; paid-versus-open differentiation,
  licensing, procurement, and forecast bake-off design.
- [Historical environmental-data retrieval](historical-data-retrieval.md):
  archived forecasts, analyses, reanalysis, satellite and station observations,
  aerosol/smoke history, commercial semantics, retrieval examples, and
  fact-check tests.
- [Historical celestial events and visibility reconstruction](historical-celestial-events.md):
  reproducible Sun/Moon and eclipse calculations, aurora and space-weather
  archives, meteor/comet/transient sources, forecast-vintage semantics, and the
  event-to-weather validation pipeline.

## Current recommendation

Build a decision layer over authoritative public models and observations. Do
not build a weather model and do not present an uncalibrated percentage as a
probability.

The first operational stack should be:

1. ECCC HRDPS deterministic weather.
2. Skyfield astronomy with a pinned JPL ephemeris.
3. NOAA OVATION and real-time solar wind.
4. Curated Atlantic Canada candidate sites.
5. Explainable heuristic scoring evaluated every ten minutes.
6. GOES cloud observations as the first nowcasting enhancement.
7. ECCC REPS for ensemble uncertainty after the deterministic vertical slice.

## Research standards

- Treat official documentation as authoritative for data availability and
  product characteristics.
- Treat App Store and vendor claims as descriptions of published features, not
  proof of forecast skill.
- Mark proprietary blending or post-processing as unknown unless the vendor
  documents it.
- Treat Reddit reports as qualitative product discovery, not accuracy
  validation.
- Recheck model versions, forecast ranges, licences, pricing, and API terms
  before implementation because they change.
- Use `SDK` only for a maintained client library. Label raw GRIB/S3/OGC/REST
  access, generated clients, command-line tools, and community wrappers
  explicitly; see the
  [integration tooling index](integration-tooling-index.md).
