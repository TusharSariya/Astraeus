# Paid cloud, fog, aerosol, and air-quality APIs

Last reviewed: 2026-08-10

## Executive conclusion

Most paid weather APIs do not own uniquely superior cloud or aerosol physics.
They primarily sell:

- normalized access to many public and proprietary sources;
- bias correction and model blending;
- decision-ready probabilistic outputs;
- spatial and temporal post-processing;
- archived operational forecasts;
- service-level agreements, support, and stable delivery;
- occasionally, unique satellite, drone, or sensor observations.

No evaluated provider delivers Astraeus's actual target:

```text
cloud + fog + aerosol extinction
integrated along the true observer-to-target ray
conditioned on current observations
with travel-aware alternatives
```

The best paid scientific candidate is **Meteomatics**, because it reduces
multi-model ingestion work while retaining model and ensemble selection. The
best decision-ready operational candidate is **Tomorrow.io**, because it
offers probabilistic fields, alerts, route/polygon products, and proprietary
observations. Google Air Quality is strongest for consumer air-quality maps and
health interpretation, not astronomical transparency. Vaisala is valuable as
local validation instrumentation rather than a regional forecast API.

The recommended approach is to establish a public-data baseline first, then
run paid providers as additional evidence in an archived forecast bake-off.

## Provider documentation and SDK map

An example in vendor documentation is not necessarily an SDK. Unless noted
below, these services expose ordinary authenticated REST endpoints and should
be integrated with a generated OpenAPI client or a small internal HTTP adapter.

| Provider | Official documentation | Official SDK / repository | Community SDK status |
| --- | --- | --- | --- |
| Meteomatics | [API guide](https://www.meteomatics.com/en/api/getting-started/), [parameter catalogue](https://www.meteomatics.com/en/api/available-parameters/alphabetic-list/) | Official [Python connector docs](https://www.meteomatics.com/en/api/data-connectors/python/) and [repository](https://github.com/meteomatics/python-connector-api); additional connectors are linked from the vendor's data-connector pages. | Prefer the official connector or direct HTTP. Verify maintenance and licence before adopting third-party wrappers. |
| Tomorrow.io | [API reference](https://docs.tomorrow.io/reference/welcome), [authentication](https://docs.tomorrow.io/reference/api-authentication) | Official [Postman collection](https://github.com/Tomorrow-IO-API/tomorrow-postman) and examples; no general official Python/JavaScript client library identified. | Numerous wrappers exist, but direct REST/OpenAPI integration minimizes abandonment risk. Do not label code snippets as SDKs. |
| Google Air Quality | [Product docs](https://developers.google.com/maps/documentation/air-quality), [REST reference](https://developers.google.com/maps/documentation/air-quality/reference/rest) | Google-generated [Go Air Quality client](https://pkg.go.dev/google.golang.org/api/airquality/v1) is official but maintenance-mode; other languages can call REST. | Google Maps web-service clients do not necessarily implement Air Quality endpoints; verify endpoint coverage. |
| Ambee | [Developer documentation](https://docs.ambeedata.com/) | No official open-source language SDK identified; authenticated REST API. | Treat third-party packages as community wrappers and validate current endpoint coverage. |
| IQAir AirVisual | [API documentation](https://api-docs.iqair.com/) | No official open-source SDK identified; REST API. | Direct HTTP is preferable for the small API surface. |
| Vaisala | [Product documentation portal](https://docs.vaisala.com/) | Instrument protocols, generated files, and vendor software are product-specific; there is no general regional-weather SDK. | Parse only the contracted instrument format/protocol and pin firmware/schema versions. |
| Xweather / AerisWeather | [Weather API docs](https://www.xweather.com/docs/weather-api) | [Official SDK and examples organization](https://github.com/aerisweather) contains product-specific libraries; confirm active support before selection. | Avoid older packages that target retired Aeris endpoints. |
| Visual Crossing | [Weather API docs](https://www.visualcrossing.com/resources/documentation/weather-api/timeline-weather-api/) | No official general language SDK identified; REST and CSV/JSON responses. | Community clients offer convenience only. |
| Weatherbit | [API documentation](https://www.weatherbit.io/api) | No official general SDK identified; REST API and examples. | Use direct HTTP or a generated internal client. |
| OpenWeather | [API documentation](https://openweathermap.org/api) | No official general language SDK identified; REST APIs. | Many community wrappers exist with uneven One Call version support; direct HTTP is safer. |
| Windy | [Map Forecast API docs](https://api.windy.com/map-forecast/docs), [Point Forecast API docs](https://api.windy.com/point-forecast/docs) | JavaScript map library and REST point API are vendor interfaces, not raw-model SDKs; no official server-language SDK identified. | Subscription access does not grant redistribution rights to upstream model files. |
| Spire Weather | [Weather and climate products](https://spire.com/weather-climate/) | Enterprise delivery/API documentation is contract-dependent; no generally available open-source SDK identified. | Require sample payloads and schemas during procurement. |
| DTN | [Weather APIs](https://www.dtn.com/weather/api/) | Enterprise product interfaces are contract-dependent; no generally available open-source SDK identified. | Require contract-specific docs and a data dictionary before estimating integration. |

The absence of a public SDK is not inherently a weakness. A stable REST schema
is often easier to own than a thin vendor wrapper, but Astraeus must archive raw
responses and provider/model metadata before normalization.

## Open baseline for comparison

A paid provider must be compared with the actual authoritative public stack,
not with a generic free weather application.

| Requirement | Free/open source |
| --- | --- |
| Atlantic Canada short-range weather | ECCC HRDPS |
| Regional forecast uncertainty | ECCC REPS |
| Current cloud placement | GOES-East ABI |
| Fog, visibility, and ceiling observations | METAR/SPECI and ECCC SWOB |
| Precipitation | ECCC radar |
| Medium-range deterministic/ensemble weather | ECMWF IFS/ENS and GDPS/GEPS |
| Canadian smoke | ECCC RAQDPS-FireWork |
| Global aerosol composition and optical properties | CAMS |
| Satellite aerosol optical depth | GOES, MODIS, VIIRS, and MAIAC |
| Surface air-quality observations | ECCC, AirNow, OpenAQ, and provincial networks |

### CAMS is a high scientific baseline

The free CAMS global atmospheric-composition forecast includes:

- PM1, PM2.5, and PM10;
- aerosol extinction at 355, 532, and 1064 nm;
- total and species-specific aerosol optical depth;
- black carbon, organic matter, sulphate, nitrate, ammonium, dust, and sea salt;
- aerosol mixing ratios and optical properties;
- asymmetry factors at multiple wavelengths;
- reactive gases and twice-daily five-day forecasts.

See the [CAMS global atmospheric-composition forecast catalogue](https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts?tab=overview).

These fields are more relevant to astronomical transmission than a consumer
AQI value. CAMS is coarse, and its own guidance says global output represents
regional rather than individual-site conditions; see
[CAMS global forecast plots](https://atmosphere.copernicus.eu/global-forecast-plots).

### ECCC smoke forecast

ECCC's RAQDPS-FireWork supplies Canadian smoke and PM2.5 guidance in public
GRIB2 products at approximately 10 km, with forecasts extending to roughly 72
hours. See the
[RAQDPS-FireWork Datamart documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps-fw/readme_raqdps-fw-datamart_en/).

## What paying buys

### 1. Normalized access to many models

Without an aggregator, Astraeus must operate:

```text
GRIB2 and NetCDF ingestion
projection and vertical-coordinate handling
model-run discovery
parameter normalization
ensemble extraction
missing-run and source-version handling
spatial/temporal interpolation
historical archive management
```

A commercial API can collapse this into a stable query interface. This saves
engineering time but does not, by itself, improve forecast skill.

### 2. Proprietary blending and correction

Providers may combine government NWP, radar, satellite, surface stations,
private sensors, terrain adjustment, historical bias correction, and learned
post-processing. This may improve point forecasts, but opaque blends are
difficult to diagnose and reproduce.

For every commercial result, preserve when available:

```text
source model
native resolution
returned resolution
model initialization
forecast lead
post-processing product/version
ensemble or percentile semantics
```

### 3. Decision-ready probability products

Commercial providers may return cloud-base, ceiling, visibility, or threshold
percentiles instead of requiring Astraeus to ingest every ensemble member.
Tomorrow.io, for example, documents probabilistic cloud cover, cloud base,
ceiling, and visibility at supported minute and hourly steps in
[Probabilistic Forecasting](https://docs.tomorrow.io/reference/probabilistic-forecasting).

These are convenient distributions, but their calibration for Atlantic
Canadian astronomy must still be measured.

### 4. Post-processing and query ergonomics

Paid services commonly provide:

- point, route, line, and polygon requests;
- arbitrary time aggregation;
- terrain-aware downscaling;
- fine output grids;
- map tiles and ready-made visual products;
- provider-managed interpolation and source selection.

A response on a 90 m or 500 m output grid does not imply that the atmospheric
model dynamically resolved a 90 m fog bank or 500 m pollution source.

### 5. Operational guarantees

Enterprise contracts can include SLAs, higher quotas, redundancy, dedicated
support, advance change notices, private endpoints, archive retention, custom
fields, and negotiated redistribution rights. These may be more valuable in
production than a small average skill improvement.

### 6. Archived forecasts

An especially valuable paid feature is a true archive of forecasts exactly as
issued:

```text
model name and version
initialization time
forecast lead
valid time
value and uncertainty
```

Many products labelled `historical weather` are observations, reanalysis, or
reconstructed histories. They cannot measure the skill of the forecast a user
would have received at that time.

### 7. Unique observations

The strongest genuine differentiators are observations not present in the
ordinary public feed:

- Tomorrow.io microwave sounders and space-based precipitation radar;
- Meteomatics Meteodrone boundary-layer profiles where deployed;
- Vaisala ceilometers and visibility instruments;
- Spire radio-occultation profiles;
- IQAir and other private/community sensor networks.

Unique data only helps Astraeus where geographic coverage exists and where the
observations improve the forecast or current-state estimate being consumed.

## Provider comparison

| Provider | Best role | Primary advantage | Primary limitation |
| --- | --- | --- | --- |
| Meteomatics | Scientific multi-model backend | Source/member selection, vertical fields, NetCDF | Cost; no proven Atlantic-specific superiority |
| Tomorrow.io | Operational decisions and redundancy | Probabilities, alerts, routes, private observations | Opaque blend and limited vertical transparency |
| Google Air Quality | Consumer AQ maps and health UX | Normalized fine-grid presentation and AQIs | Surface health product, not optical transmission |
| Vaisala | Local validation instrumentation | Direct backscatter, cloud base, fog, visibility | Point-local and hardware-intensive |
| Ambee | Environmental-data aggregation | AQ, pollen, wildfire, weather under one API | Limited optical/vertical atmospheric science |
| IQAir/AirVisual | Current PM and sensor network | Private/community station observations | Surface PM, uneven coverage, limited forecast provenance |
| Aeris/Xweather | Aviation/conditions aggregation | Developer-friendly observations, maps, alerts | Not a raw 3-D NWP service |
| Visual Crossing | Prototype and historical UI | Simplicity and low integration effort | Inadequate vertical cloud science |
| Weatherbit | Low-cost comparison | Easy surface weather and visibility | No meaningful 3-D cloud atmosphere |
| OpenWeather | Consumer UI or backup | Broad developer adoption | Opaque and scientifically shallow |
| Windy | Human model comparison | Excellent visualization | Subscription/API rights are not raw model rights |
| Spire | Future assimilation research | Unique radio-occultation profiles | Enterprise cost and indirect cloud value |
| DTN | Managed weather operations | Support and domain decision services | Cost and limited model transparency |

## Meteomatics

Meteomatics is the strongest paid fit when scientific control matters. It
documents:

- access to many global, regional, ensemble, and AI model families;
- explicit source-model selection;
- ensemble-member selection;
- pressure- and height-level parameters;
- model initialization metadata;
- point, route, polygon, and area requests;
- JSON, CSV, XML, image, and NetCDF output;
- low, middle, high, total, and effective cloud cover;
- cloud base, ceiling, cloud-top temperature, and convective-cloud top;
- visibility, fog, boundary-layer height, and aviation parameters;
- air quality, satellite cloud type, and aerosol optical-depth parameters.

Sources:

- [Meteomatics Weather API](https://www.meteomatics.com/en/weather-api/)
- [API request and source selection](https://www.meteomatics.com/en/api/request/)
- [Cloud parameters](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/clouds/)
- [General weather and visibility parameters](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/general-weather-state/)
- [Alphabetical parameter catalogue](https://www.meteomatics.com/en/api/available-parameters/alphabetic-list/)

### What it adds over direct public feeds

- One interface over multiple model families.
- Easier model and ensemble comparisons.
- Model-level and derived aviation parameters.
- NetCDF area delivery.
- Route and polygon requests.
- Provider-operated model mixes and downscaling.
- Potential archived operational forecasts and contractual support.
- Proprietary high-resolution models in covered regions.

### What it does not add

- Guaranteed better Atlantic Canadian cloud/fog skill.
- Astronomy-specific directional transmission.
- Complete observed 3-D cloud geometry.
- Proof that fine output grids resolve equally fine cloud dynamics.
- A known Meteodrone network covering Atlantic Canada.

Meteomatics publishes Swiss cases in which boundary-layer drone profiles
improved fog and low-cloud initialization. This is geographically specific
vendor evidence, not an Atlantic Canada benchmark; see its
[Meteodrone fog case study](https://www.meteomatics.com/en/meteodrones-weather-drones/swiss-case-meteodrones-greatly-improve-forecast-accuracy/).

### Recommendation

Run the first paid technical trial with Meteomatics. Test its source-selected
Canadian models separately from its proprietary `mix`; its greatest likely
value is reduced engineering, not a universally superior blend.

Before contracting, verify:

- availability of HRDPS or equivalent Canadian regional output;
- REPS or comparable ensemble members;
- vertical cloud liquid/ice, humidity, base, ceiling, and visibility fields;
- AOD and extinction parameters;
- initialization and native-grid metadata;
- archived operational forecasts;
- area limits, caching, retention, and derived-output rights.

## Tomorrow.io

Tomorrow.io is more decision-oriented. Relevant documented products include:

- cloud cover, base, and ceiling;
- visibility and probabilistic percentiles;
- PM2.5, PM10, NO2, CO, ozone, and other air-quality fields;
- Wildfire Smoke Index;
- point, route, polygon, and monitored-location products;
- custom alerts, maps, technical support, and meteorological support;
- enterprise SLAs and advanced historical capabilities.

Sources:

- [Tomorrow.io Weather API](https://www.tomorrow.io/weather-api/)
- [Weather data layers](https://docs.tomorrow.io/reference/weather-data-layers)
- [Air-quality fields](https://docs.tomorrow.io/reference/data-layers-air)
- [Probabilistic forecasting](https://docs.tomorrow.io/reference/probabilistic-forecasting)

### Proprietary observations

Tomorrow.io operates commercial microwave sounders and space-based radar. Its
catalogue includes precipitation radar profiles, passive-microwave brightness
temperatures, and integrated products. See
[Tomorrow.io satellite data](https://www.tomorrow.io/satellite-data/) and its
[space programme](https://www.tomorrow.io/space/).

These observations can add water-vapour and precipitation information,
especially over oceans. They do not directly provide a complete thin-cirrus,
cloud-optical-depth, or local-fog solution. Announced next-generation DeepSky
capabilities should not be treated as fully operational until their actual
products, coverage, latency, and validation are demonstrated.

### What it adds

- Ready-to-use probabilistic cloud, ceiling, and visibility outputs.
- Operational alerting and threshold monitoring.
- Route and polygon evaluation.
- Proprietary observations and model post-processing.
- Lower integration and operational burden.
- Enterprise support and SLA options.

### What it does not add

- Transparent source-model and member selection comparable to Meteomatics.
- Complete cloud liquid/ice profiles.
- Full observed cloud vertical structure.
- Demonstrated astronomy-specific or Atlantic marine-fog skill.

### Recommendation

Use as the second paid trial: a redundant decision provider and potential
short-range feature source, not the sole atmospheric model.

## Google Air Quality

Google's Air Quality API provides current, hourly forecast, short history,
pollutant concentrations, local and Universal AQIs, health recommendations,
and heatmap tiles. Google documents coverage in more than 100 countries and
output resolution as fine as 500 by 500 m:

- [Google Air Quality API](https://developers.google.com/maps/documentation/air-quality)
- [REST reference](https://developers.google.com/maps/documentation/air-quality/reference/rest)
- [History endpoint](https://developers.google.com/maps/documentation/air-quality/history)

Google says its multi-layered product is continuously cross-validated against
government stations using leave-one-out evaluation; see the
[Air Quality FAQ](https://developers.google.com/maps/documentation/air-quality/faq).

### What it adds over CAMS/ECCC

- Simple globally normalized point queries.
- Fine presentation grids and ready-made heatmap tiles.
- Many regional AQI translations.
- Pollutant descriptions and health recommendations.
- Station-informed interpolation and managed scaling.

### What it lacks for astronomy

- Aerosol vertical profiles.
- Wavelength-dependent extinction.
- Aerosol optical depth as the principal product.
- Species-specific optical properties.
- Transparent model provenance.
- Long archived operational forecasts.
- Oblique-path transmission.

The 500 m output grid is not proof that all pollution processes are resolved at
500 m. Google also imposes attribution, mapping, caching, and display
requirements. Review its
[Air Quality policies](https://developers.google.com/maps/documentation/air-quality/policies)
and [usage and billing](https://developers.google.com/maps/documentation/air-quality/usage-and-billing)
before adoption.

### Recommendation

Use only if Astraeus needs polished consumer AQ maps, localized AQI, or health
messaging. Do not use it as the atmospheric-transparency model.

## Ambee

Ambee exposes current, forecast, and historical PM2.5, PM10, NO2, SO2, CO,
ozone, and AQI, along with pollen, wildfire, weather, and other environmental
products:

- [Ambee documentation](https://docs.ambeedata.com/)
- [Air-quality API](https://docs.ambeedata.com/apis/air-quality)
- [Environmental API overview](https://docs.ambeedata.com/apis/overview)

### Added value

- Multiple environmental hazards in one interface.
- Easy coordinate queries.
- Preassembled current, forecast, and historical products.
- Potentially useful pollen and wildfire integration.

### Limitations

- No detailed cloud vertical structure.
- No strong emphasis on spectral AOD or extinction profiles.
- Limited model provenance.
- No astronomy-specific transmission.
- No established superiority for Atlantic Canada.

### Recommendation

Only adopt if one environmental-data contract materially simplifies pollen,
wildfire, and AQ integration. It is not the primary transparency source.

## IQAir/AirVisual

IQAir is primarily a station and sensor ecosystem. Its API exposes nearest
station/city, pollutant concentrations, PM2.5/PM10, AQIs, weather context, and
plan-dependent forecast/history. Its documentation notes uneven station update
cycles and missing pollutants where a station did not publish a measurement:

- [AirVisual API](https://api-docs.iqair.com/)
- [IQAir API access overview](https://www.iqair.com/in-en/support/knowledge-base/access-airvisuals-aqi-air-quality-and-pollution-api)

### Added value

- Private and community sensor observations.
- Useful current surface-PM evidence.
- Hardware plus API ecosystem.

### Limitations

- Uneven coverage and sensor quality.
- Surface PM is not column AOD.
- Low-cost sensors may need humidity correction and calibration.
- Limited forecast and model provenance.
- No cloud/fog vertical atmosphere.

### Recommendation

Consider as an additional real-time PM observation source only where local
coverage is demonstrably useful.

## Vaisala

Vaisala is an observation-system vendor rather than a generic forecast API.
Its ceilometer systems can provide:

- attenuated atmospheric backscatter profiles;
- multiple cloud bases and vertical visibility;
- total and layer-specific sky cover;
- estimated cloud penetration depth/thickness;
- fog and precipitation detection;
- boundary-layer structure;
- one-minute updates and NetCDF output.

See the [CL61 generated-file documentation](https://docs.vaisala.com/r/M212721EN-D/en-US/GUID-8A1950A0-9C67-48AA-BA80-96A0BCB2AF65/GUID-8A62791D-6928-4953-8A28-7FD7553C1A11).

Dense fog and precipitation can attenuate the laser before it reaches upper
layers. Vaisala documents when the system reports vertical visibility instead
of cloud base in its
[CL61 vertical-visibility guide](https://docs.vaisala.com/r/M212475EN-E/en-US/GUID-90753767-46B7-454D-9F90-F5DAC78E3055).

### Added value

- Direct local vertical observations.
- Strong fog, cloud-base, and boundary-layer validation.
- High temporal cadence and controlled instrumentation.
- Valuable calibration labels.

### Limitations

- Point-local rather than regional.
- No horizontal cloud geometry.
- Dense fog can hide higher layers.
- Province-wide coverage would require many installations.

### Recommendation

A partnership or one validation-site ceilometer may ultimately add more
scientific value than another generic weather API. It is not an MVP regional
forecast solution.

## Other aggregators and enterprise services

### Aeris/Xweather

Useful for current conditions, METAR/aviation observations, alerts, maps, and
environmental aggregation. Treat it as an observation/API-ergonomics option,
not a source of raw three-dimensional cloud physics.

### Visual Crossing, Weatherbit, and OpenWeather

These are useful for inexpensive prototypes, surface forecast comparisons,
and simple history. They generally lack model-member selection, hydrometeor
profiles, cloud optical depth, spectral aerosol properties, and detailed
provenance. They should not form the scientific backbone.

### Windy

Windy is excellent for manual comparison of ECMWF, ICON, GFS, and cloud layers.
A consumer subscription or map API does not automatically grant permission to
extract, archive, or redistribute the underlying raw model fields.

### Spire

Spire radio occultation adds proprietary temperature and moisture profiles,
particularly over oceans and observation-sparse regions. Much of this value
may already be present in operational centres that assimilate commercial
occultation data. Direct use becomes compelling only if Astraeus operates or
partners on data assimilation, which is outside the MVP.

### DTN

DTN's value is managed domain-specific weather decision support, operational
reliability, and human/enterprise services. It is more relevant as a future
operations partner than as a transparent raw atmospheric field provider.

## Cloud-specific comparison

| Capability | Open stack | Meteomatics | Tomorrow.io | Consumer APIs |
| --- | ---: | ---: | ---: | ---: |
| Low/middle/high cloud | Yes | Yes | Product-dependent | Often absent |
| Model vertical levels | Yes, engineering-heavy | Strong | Limited | No |
| Liquid/ice hydrometeors | Source-dependent | Source-dependent | Generally opaque | No |
| Cloud base/ceiling | Available/derivable | Strong | Strong | Inconsistent |
| Cloud optical depth | GOES | Source-dependent | Not central | Usually no |
| Ensemble members | REPS/ENS | Strong | Percentile products | No |
| Current cloud geometry | GOES | Aggregated | Proprietary blend | Usually derived |
| Source-model choice | Direct access | Strong | Weak | No |
| Oblique-ray transmission | No | No | No | No |
| Operational simplicity | Low | High | Very high | High |

Meteomatics most meaningfully reduces engineering while retaining scientific
control. Tomorrow.io provides easier decision-ready uncertainty but less
transparent vertical science.

## Particulate-specific comparison

For astronomy:

```text
surface PM2.5/PM10
    != column aerosol optical depth
    != wavelength-dependent slant extinction
```

Surface AQI is a health metric. AOD, spectral extinction, and aerosol vertical
distribution describe optical transmission.

| Capability | CAMS/ECCC open | Google AQ | Tomorrow.io | Ambee/IQAir |
| --- | ---: | ---: | ---: | ---: |
| Surface PM2.5/PM10 | Yes | Yes | Yes | Yes |
| Reactive gases | Yes | Yes | Yes | Yes/variable |
| Total AOD | Yes | Not central | Not central | Usually no |
| Species-specific AOD | Yes | No | No | No |
| Vertical aerosol profiles | Yes | No | Opaque/limited | No |
| Spectral extinction | Yes | No | No | No |
| Fine consumer map | Must build | Excellent | Good | Good |
| Health recommendations | Must build | Excellent | Available | Available |
| Private sensor aggregation | Limited | Blended | Blended | Strong |
| Astronomy suitability | Strongest raw science | Low | Moderate | Low |

CAMS plus ECCC FireWork is scientifically stronger than a generic paid AQI API
for astronomical transparency. A paid source may still improve current
surface interpolation, reliability, and product ergonomics.

## Procurement plan

### MVP: establish the open baseline

Use:

```text
HRDPS + REPS + GOES + METAR/SWOB + CAMS + ECCC FireWork
```

This reveals which costs come from engineering and which errors come from the
underlying forecast.

### First paid trial: Meteomatics

Evaluate model/member access, vertical cloud fields, AOD/extinction, NetCDF
areas, model initialization, archives, uptime, and contractual rights. Treat
its proprietary mix as one candidate, not ground truth.

### Second paid trial: Tomorrow.io

Evaluate probabilistic visibility, base, ceiling, fog timing, smoke, PM2.5,
alerts, freshness, and any measurable Atlantic benefit from private satellite
observations.

### Optional consumer AQ trial: Google

Use only if polished pollutant maps, localized AQIs, or health messaging are
product requirements.

### Long-term observation investment

Several calibrated all-sky cameras and a potential ceilometer partnership may
create more defensible scientific value than additional generic APIs because
they generate directional transmission labels owned by Astraeus.

## Required forecast bake-off

Use the archive semantics, retrieval procedures, and fact-check tests in
[Historical environmental-data retrieval](historical-data-retrieval.md). In
particular, do not accept a vendor's `historical` endpoint as an archive of
forecasts-as-issued without explicit initialization, lead, version, and
immutability.

Request archived operational forecasts—not reconstructed history—over at least
one Atlantic fog and wildfire season for 20–50 coastal and inland sites.

Evaluate:

- low/middle/high cloud Brier score and reliability;
- cloud-base and ceiling error;
- fog onset and clearance timing;
- visibility categories;
- GOES-observed boundary displacement;
- AOD bias against AERONET where possible;
- PM2.5 against independent stations;
- performance by lead, season, coast/inland, and day/night;
- freshness, completeness, outages, and schema stability;
- recommendation rank regret;
- false `drive there; it will be clear` rate.

Compare:

```text
public stack alone
paid provider alone
public stack + paid provider as another ensemble member
```

The combined system is the likely winner.

## Contract and licensing checklist

Before depending on a provider, confirm:

- May raw responses be cached, and for how long?
- May forecasts be archived permanently for validation?
- May normalized fields be stored?
- May derived scores and recommendations be redistributed?
- Must data be deleted when the contract ends?
- Are maps restricted to the provider's mapping platform?
- What attribution is required?
- Are model names, initialization times, and native resolutions exposed?
- Are historical products archived forecasts, observations, or reanalysis?
- Which fields and sources are guaranteed by the SLA?
- How are model changes announced and versioned?
- What are rate limits, area-query limits, and overage charges?
- Is commercial consumer SaaS use explicitly permitted?
- Are route and bulk/offline processing allowed?
- Are machine-learning training and calibration allowed on derived archives?

## Final recommendation

1. Use the public stack as the scientific baseline.
2. Trial Meteomatics first for transparent multi-model/vertical access.
3. Trial Tomorrow.io second for decision-ready probabilities and operational
   redundancy.
4. Use Google Air Quality only for consumer AQ presentation and health context.
5. Treat Ambee/IQAir as optional aggregation or observation sources.
6. Consider Vaisala or equivalent instruments for high-value validation sites.
7. Keep the directional cloud/fog/aerosol fusion and calibration layer
   proprietary.

The paid API should be a replaceable provider behind Astraeus's normalized
interfaces, never the definition of the scientific model.
