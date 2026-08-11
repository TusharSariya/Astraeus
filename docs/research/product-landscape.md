# Product landscape

Last reviewed: 2026-08-10

## Research caveat

Apps often disclose their source organizations or available forecast layers,
but not their production blend, post-processing, bias correction, or ranking
logic. The statements below distinguish published claims from unknown internal
implementation.

Source labels used below:

- **Official product page/listing:** describes user-visible features, but is not
  evidence of the internal forecast pipeline.
- **Official vendor API/SDK:** a supported integration surface with its own
  authentication, pricing, attribution, and storage terms.
- **Official upstream data/model:** raw or near-raw scientific input published
  by the responsible agency.
- **Community SDK:** an unofficial client wrapper; convenience does not make it
  an authoritative data source or transfer the upstream licence.

## Apple Weather and WeatherKit

Apple identifies weather inputs from organizations including NOAA/NWS, ECCC,
DWD, the Met Office/ECMWF, JMA, and Météo-France. Apple does not publish enough
of its model blending and post-processing to reproduce Apple Weather.

WeatherKit exposes current, hourly, and daily forecasts, visibility, humidity,
wind, Sun and Moon information, severe-weather alerts, and supported cloud
cover broken down by altitude.

Strengths:

- simple normalized API;
- broad geographic coverage;
- polished consumer output;
- cloud-by-altitude fields are relevant to observing.

Limitations for Astraeus:

- model-level provenance and disagreement are not sufficiently transparent;
- raw blending and correction methods are proprietary;
- attribution requirements apply;
- difficult to diagnose which source or model failed;
- does not solve travel-constrained astronomical optimization.

Recommendation: consider WeatherKit later as a comparison source or secondary
consumer forecast, not the scientific foundation.

Sources:

- [WeatherKit data-source attribution](https://developer.apple.com/weatherkit/data-source-attribution/)
- [WeatherKit overview](https://developer.apple.com/weatherkit/)
- [WeatherKit REST API](https://developer.apple.com/documentation/weatherkitrestapi)

Access classification: **official vendor API/SDK**, not raw NWP. Apple provides
a native Swift framework and authenticated REST API. WeatherKit requires
Apple Weather attribution; transformed/value-added output has separate
wording requirements. No official bulk-download or self-hosted SDK is offered.

## Astrospheric

Published features include:

- an 84-hour hourly forecast;
- cloud, transparency, and seeing;
- wind, temperature, and humidity;
- Sun and Moon timing;
- smoke integrated into transparency;
- Kp and aurora alerts;
- eclipse information;
- ensemble cloud-model comparison for Pro users.

Strength: astronomy-specific presentation and a compact view of conditions
astronomers already care about.

Gap: the user still interprets layers, chooses a destination, determines when
to leave, and evaluates whether travel is worthwhile.

Sources:

- [Astrospheric on the Canadian App Store](https://apps.apple.com/ca/app/astrospheric/id1166046863)
  (**official product listing**)
- [Astrospheric's approach and source description](https://www.astrospheric.com/dynamiccontent/astrospheric.html)
  (**official vendor documentation**)
- [Astrospheric data domain](https://www.astrospheric.com/DynamicContent/datadomain.html)
  (**official vendor documentation**)

Astrospheric states that RDPS supplies its primary variables, with GFS, RAP,
NAM, and NBM used for selected fields or its cloud ensemble. Its presentation,
tiles, and derived astronomy forecast remain a vendor product rather than a
redistributable raw-data feed. An embed/API link on the site should not be
treated as a general scientific-data SDK without reviewing its current terms.

### Astrospheric and Astraeus feature boundary

The products have substantial input and presentation overlap but different
primary jobs:

```text
Astrospheric:
    inspect astronomy-specific forecast layers at chosen locations

Astraeus:
    choose the best reachable location and window for a stated event,
    then decide whether moving is worth it
```

| Astrospheric strength | Shared territory | Intended Astraeus differentiation |
| --- | --- | --- |
| Hourly seeing and transparency forecast | Cloud and transparency | Automated candidate-location search |
| RDPS astronomy forecast | Wind, temperature and dew point | HRDPS/REPS/GOES observation fusion |
| Pro NBM/ICON/GFS cloud comparison | Smoke/aerosol awareness | Explicit fog onset/clearance and directional ray |
| Visible satellite and light-pollution layers | Moon, twilight and events | Terrain/tree/building horizon in event direction |
| Astronomy calendar, planetarium and ISS information | Aurora and eclipse awareness | Travel time, leave-by time and ranked alternatives |
| Community favourites and society/Subspace tools | Saved locations and notifications | Legal-access, gate, parking and safety evidence |
| Existing mobile apps and Pro raw-weather API | Forecast freshness | Naked-eye/camera success model and value of moving |

Astrospheric already performs much of the layer synthesis that distinguishes
it from an ordinary weather application. A generic Astraeus forecast grid with
an observation score would therefore be a weaker duplicate. The defensible
wedge is an explainable `stay / go / move` recommendation subject to travel,
access, event direction, observer/equipment, and uncertainty.

### Astrospheric concepts Astraeus should retain

- Astronomy-specific transparency rather than humidity or AQI alone.
- Seeing and jet-stream information for future high-resolution imaging modules.
- Dew point for both fog context and equipment-dew risk.
- Smoke as an explicit transparency component.
- Multiple-model agreement in a form understandable to non-specialists.
- Model publication time, availability at the location, and expected update.
- Raw layers as supporting evidence behind the recommendation.
- Community observing sites as candidate evidence, subject to licence and
  independent access verification.

Astrospheric's public description does not establish that Astraeus can produce
more accurate weather. Higher-resolution HRDPS and richer observations create
a testable opportunity, not proof of superiority.

## Windy.com

Windy exposes multiple global and regional model layers, with availability
depending on location. Its product commonly includes ECMWF, GFS, ICON, and
regional models such as HRDPS or HRRR, along with radar, satellite, METAR, wind,
and cloud layers.

Strengths:

- excellent spatial visualization;
- explicit model comparison;
- broad professional-grade data access;
- strong wind and maritime experience.

Gap: it remains primarily a forecast exploration tool. Users must translate
maps into a travel and observing decision.

Sources:

- [Windy.com on the App Store](https://apps.apple.com/xk/app/windy-com-weather-radar/id1161387262)
  (**official product listing**)
- [Windy Point Forecast API](https://api.windy.com/point-forecast/docs)
  (**official paid vendor API**)
- [Windy Map Forecast API](https://api.windy.com/map-forecast/docs)
  (**official visualization SDK/API**)

The Point Forecast API currently documents `canHrdps` among selectable models,
including high-cloud and pressure-level fields. It is normalized point data,
not a replacement for archived GRIB ingestion, and API availability/licensing
must be checked before storing results or using them for model verification.

## Acme Weather

Acme Weather is from creators of Dark Sky and advertises:

- homegrown forecasts;
- alternate predictions and ranges instead of one deterministic answer;
- community weather reports;
- radar, snow, air-quality, and storm maps;
- customizable condition notifications.

Its precise upstream models and blending are not publicly disclosed in the App
Store listing.

The important lesson is product-level uncertainty. Astraeus can make
disagreement actionable, for example:

> Cape North ranks first in 16 of 21 weather scenarios; Meat Cove ranks first
> in the remaining five.

Source: [Acme Weather on the Canadian App Store](https://apps.apple.com/ca/app/acme-weather/id6742032583)

## Sheerr Weather

The relevant Atlantic Canadian product is **Sheerr Weather**, created by
Newfoundland meteorologist Eddie Sheerr.

Its differentiation is regional expertise, explanations, alerts, and forecasts
written for Newfoundland and Labrador. Its precise operational model blend is
not publicly documented in enough detail to reproduce.

Lessons for Astraeus:

- local interpretation creates trust;
- Atlantic coastal regimes need regional bias awareness;
- explanations are part of the product, not decoration;
- “why tonight's forecast is fragile” can be more valuable than another map.

Source: [About Sheerr Weather](https://sheerr-weather.squarespace.com/about)

Access classification: **official product/editorial site**. No public raw-data
API, SDK, reproducible model recipe, or redistribution licence was located.

## SpaceWeatherLive

Published features include:

- current solar and auroral activity;
- solar-wind and geomagnetic graphs;
- alerts for flares, CMEs, coronal holes, Kp, and storms;
- historical space-weather archives;
- written reports during significant activity;
- beginner help and configurable notifications.

Strength: detailed monitoring of solar and geomagnetic conditions.

Gap: it does not primarily combine terrestrial cloud, darkness, terrain, light
pollution, and travel into a destination recommendation.

Source: [SpaceWeatherLive on the App Store](https://apps.apple.com/us/app/spaceweatherlive/id1435501021)

Access classification: **official product listing**. Treat charts and alerts as
a monitoring product. For machine ingestion, use the original NOAA/NASA feeds
documented in `data-sources.md`; no supported general-purpose SpaceWeatherLive
data SDK was established in this review.

## Competitive gap

The current expert workflow is approximately:

```text
SpaceWeatherLive
    -> Is solar/geomagnetic activity favorable?

Astrospheric or Windy
    -> Will terrestrial weather permit viewing?

Light-pollution and terrain maps
    -> Where might the horizon be usable?

Google Maps or another router
    -> Can I reach the location in time?

Human judgment
    -> Is the trip worth making?
```

Astraeus should replace the manual synthesis:

```text
I want to observe an aurora
    -> Go here
    -> Leave by this time
    -> Observe during this window
    -> Look in this direction
    -> This is the dominant risk
    -> These are the best fallbacks
```

The differentiation is optimization and explanation, not another collection of
weather or space-weather layers.

The decisive competitive test is:

> Does Astraeus make a materially better stay/go/move decision than an
> experienced user manually comparing reachable locations in Astrospheric?

Where terms permit, Astrospheric should be archived as an independent benchmark
in the feasibility study. It should not become a critical upstream dependency
without confirming automated use, archival, commercial-derived-output, and
redistribution rights.

## Product principles learned from competitors

1. Preserve expert detail, but make the primary output a decision.
2. Show alternate outcomes and disagreement instead of false certainty.
3. Provide dark-adapted, glanceable live monitoring later, but do not let UI
   polish delay pipeline correctness.
4. Make freshness and update cadence obvious.
5. Support notifications for user-defined observing constraints, not only Kp.
6. Explain the dominant limiting factor.
7. Keep raw layers available as evidence behind the recommendation.
