# Astronomy forecast tools: what they ingest and what astronomers ask for

Non-normative research, 2026-09-02. Wayfinder ticket
[#7](https://github.com/TusharSariya/Astraeus/issues/7) for the evidence-layer
charter [#5](https://github.com/TusharSariya/Astraeus/issues/5). Nothing here is
an admission decision or a spec.

## How to read this

Vendor pages describe features, not skill. Every claim below is what a tool says
it does, not evidence it does it well. Where a tool publishes no method, that
absence is recorded as an absence rather than filled in by inference. No tool
surveyed publishes a verification score, a reference period, or an uncertainty
range for its seeing or transparency output.

Terms follow `CONTEXT.md`. In the evidence-class vocabulary, a **producer
output** here means a field the upstream numerical weather prediction centre
publishes (retrieved if we fetched it as issued); a **tool derivation** is the
tool's own post-processing of that output, which for Astraeus would be
`derived-here` only if we computed it ourselves from retrieved inputs with a
cited method, and is otherwise `reprocessed` when an intermediary transformed it
before delivery. Several tools deliver a derivation with no published method,
which means the derivation could only be catalogued as reprocessed with an
undeclared method - the weakest possible provenance.

Builds on `docs/research/product-landscape.md` (Astrospheric feature boundary,
competitive gap), `docs/research/community-findings.md` (repeated unmet needs)
and `docs/research/observation-variables.md` (sections 6 and 7 on seeing and
wavelength-dependent transmission). It does not repeat those.

## The tools surveyed

| Tool | Operator | Upstream models it cites | Nature |
| --- | --- | --- | --- |
| Clear Sky Chart | Attilla Danko (d. 2024), maintained by his widow; forecast by Allan Rahill, Canadian Meteorological Centre | CMC GEM; ECCC wildfire smoke prediction system for the smoke row | Static per-site chart, 96 h, ~6,200 sites, Canada/USA/northern Mexico |
| ECCC Astronomy pages (`weather.gc.ca/astro`) | Environment and Climate Change Canada | "Regional model" (RDPS), four runs at 00/06/12/18 UTC, to T+84 h | The upstream of the Clear Sky Chart, published directly as imagery |
| Astrospheric | Astrospheric LLC | RDPS primary; GFS, RAP (smoke, aerosol optical depth), NAM, NBM, ICON for selected fields and the Pro cloud ensemble; seeing from Rahill's CMC model | Consumer app plus a Pro raw-weather API |
| Clear Outside | First Light Optics | Currently "Powered by Meteosource Weather API"; historically 7Timer/GFS, with an experimental third cloud source | Web and mobile, hourly, global |
| 7Timer! | Community project (Chinese Academy of Sciences origin) | NCEP GFS, presented at ~10 km grid spacing | Free public API, ASTRO product 72 h, other products to 10 days |
| meteoblue Astronomy Seeing | meteoblue AG | Not stated on the English help page; meteoblue's own multi-model chain | Web product, layered cloud plus two seeing indices and a jet-stream panel |
| Good To Stargaze | Good To Forecast | Proprietary engine, hourly in the US and 6-hourly elsewhere; Dark Sky retained as an optional source | Mobile app with an integrated light-pollution map |

## Tools versus fields

`P` = producer output passed through. `D` = the tool's own derivation. `-` =
absent. A cell may be both where the tool re-derives a field the producer also
publishes.

| Field | Clear Sky Chart | ECCC astro | Astrospheric | Clear Outside | 7Timer | meteoblue seeing | Good To Stargaze |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Darkness / twilight | D (astronomical, not weather) | - | D | D (civil, nautical, astronomical hours) | - | - | D |
| Cloud, total | P (CMC) | P | P (RDPS) | P | P | P | P |
| Cloud by layer (low/mid/high) | - (total only) | - | - in the free view; Pro compares whole-model cloud, not layers | P (low, medium, high, % sky obscured) | P (high, mid, low) | P (0-4, 4-8, 8-15 km asl) | not published |
| Transparency | D (from total column water vapour) | D | D (RDPS plus RAP, adds smoke, elevation, surface pressure) | - | D (mag per air mass, 8 classes) | - | D (method unpublished) |
| Seeing | D (Rahill CMC model, 3 h blocks) | D (zenith seeing, 3 h, T+84) | D (Rahill's model, imported) | experimental only | D (arcsec, 8 classes) | D (two indices 1-5, plus arcsec) | D (method unpublished) |
| Dew point / dew risk | ground relative humidity only, with an explicit caveat that it correlates imperfectly with dew | P (humidity) | P | P (dew point, relative humidity, chance of frost) | P (RH at 2 m) | - | P |
| Wind | P (tree-top level) | P | P | P (speed and direction) | P (10 m) | jet stream aloft, not surface | P |
| Smoke | P (ECCC wildfire smoke prediction system, ug/m3, with a caveat it runs optimistic) | - | P from RAP, folded into transparency | - | - | - | - |
| Moon geometry | D (phase, position, in the darkness row) | - | D (Sun and Moon timing, eclipse info) | D (rise/set, illumination %) | - | - | D |
| Satellite passes | - | - | D (ISS and visible satellites) | D (ISS passover row) | - | - | - |
| Jet stream | folded into seeing | folded into seeing | folded into seeing | - | folded into seeing | P, shown explicitly with speed and "bad layers" | - |
| Sky brightness / light pollution | assumes zero light pollution by design | - | D (light-pollution layer) | D (magnitude, Bortle class, mcd/m2) | - | - | D (integrated map) |
| Space weather (Kp, aurora) | - | - | P (Kp, aurora alerts) | - | - | - | - |

## How each tool derives seeing

Every published method reduces to the same two physical inputs: turbulence
strength and vertical temperature structure. The differences are in vertical
integration and in presentation.

- **Rahill / CMC (Clear Sky Chart, ECCC astro, Astrospheric).** A
  post-processing step over CMC GEM output that "uses forecast data of
  turbulence and temperature gradients in the atmosphere to forecast its optical
  steadiness", attempting to predict turbulence and temperature differences at
  all altitudes. Published on three-hour blocks, calibrated - explicitly - for
  11 to 14 inch instruments, which makes the scale aperture-dependent rather
  than a physical arcsecond. Not computed when cloud exceeds about 80%, which
  leaves gaps exactly where a user most wants a fallback. ECCC labels its own
  version "zenith seeing forecast" from the Regional model at 3-hourly steps to
  T+84 h.
- **meteoblue.** Two independent integrations of turbulent layers, "Seeing Index
  1" and "Seeing Index 2" on a 1 (poor) to 5 (excellent) scale, where index 2
  gives more weight to density fluctuations and so to visible flicker. It is the
  only tool surveyed that exposes its intermediate reasoning: it names **bad
  layers** as atmospheric layers with a temperature gradient above 0.5 K/100 m,
  reports the gradient in K/100 m, and states that jet-stream speeds above
  35 m/s or below 5 m/s usually correspond to bad seeing. It also converts to an
  arcsecond value. The English help page does not name the upstream model,
  resolution, horizon, or the conversion formula.
- **7Timer.** Publishes seeing in eight arcsecond bands from below 0.5" to above
  2.5", derived from GFS. The public wiki documents the output bands and the API
  but not the derivation. It offers an altitude-correction parameter (0, 2 or
  7 km), which implies a boundary-layer term in the calculation.
- **Astrospheric** imports Rahill's model rather than deriving its own, so its
  seeing inherits CMC's method and CMC's grid.
- **Clear Outside** and **Good To Stargaze** present a seeing value with no
  published method. Clear Outside's seeing appeared as an experimental feature
  alongside additional cloud sources rather than as a documented product.

The common weakness: none of these separates the boundary-layer (local, dome and
ground) contribution from the free-atmosphere contribution, and none reports a
`Cn2` profile. `docs/research/observation-variables.md` section 6 already lists
`Cn2` and seeing-monitor observations as the inputs that would make a seeing
field verifiable; nothing in this survey supplies them.

## How each tool derives transparency

Transparency is where the tools diverge most, and where the words hide different
physical quantities.

- **Clear Sky Chart / CMC.** Transparency is forecast "based on the total amount
  of water vapour in the air" - a column-integrated moisture proxy, not an
  extinction coefficient. It is deliberately independent of cloud, so poor
  transparency under a clear sky is the expected haze case. It is not computed
  when cloud exceeds about 30%, again leaving a hole. ECCC's own page states the
  transparency forecast is expressed as "the magnitude of the faintest star
  visible to the unaided eye", i.e. a naked-eye limiting magnitude, which is a
  different unit from a per-air-mass extinction.
- **Astrospheric.** RDPS is the primary model with augmentation from NOAA's RAP,
  and the vendor states its transparency model takes smoke, elevation and
  surface pressure into account. Smoke and aerosol optical depth come from RAP.
  This is the only surveyed transparency that explicitly carries an aerosol term
  rather than treating water vapour as the whole story.
- **7Timer.** Reports transparency in magnitudes per air mass in eight bands
  from below 0.3 to above 1. This is the closest to a physical extinction
  coefficient of any of them, and it is the one unit that can be compared
  against an observed extinction measurement.
- **Clear Outside** publishes no transparency row at all; it publishes sky
  quality (magnitude, Bortle class, mcd/m2), which is a light-pollution
  statement about the site, not an atmospheric transmission statement about the
  night. Conflating the two is a common user error the field names invite.
- **meteoblue** does not publish transparency; it publishes layered cloud and
  seeing only.

Three incompatible units - column water vapour proxy, naked-eye limiting
magnitude, magnitudes per air mass - all called "transparency". That is directly
relevant to the open field-catalogue question in #5 about whether a per-field
comparability rule is needed beyond phase and unit. Transparency is the clearest
case yet found where two sources' fields share a name and are not comparable.

## Darkness, Moon geometry and satellite passes

These are the fields with no meteorological content, and the tools treat them as
deterministic computation rather than forecast.

- Clear Sky Chart's darkness row is explicitly "not a weather forecast": it
  assumes clear sky and no light pollution and reports visual limiting magnitude
  at zenith from Sun and Moon position, Moon phase, solar cycle and an
  atmospheric scattering model, citing Ben Sugerman's limiting-magnitude
  calculations. Including the solar cycle term is unusual and worth noting - it
  accounts for airglow varying with solar activity.
- Clear Outside reports civil, nautical and astronomical darkness hours
  separately, plus Moon rise, set and illumination percentage. Astrospheric adds
  a planetarium, an astronomy calendar and eclipse information.
- Satellite passes: only Astrospheric and Clear Outside surface them, and
  neither cites a source. Pass prediction requires current orbital elements and
  an SGP4 propagator; nothing in the registry supplies either.

Astraeus should treat darkness, Moon geometry and pass prediction as
`derived-here` from an ephemeris and orbital elements with a cited method, not
as retrieved fields. They are cheap, exact and need no provider - which makes
them the wrong thing to depend on a vendor for.

## What astronomers ask for that these tools lack

Drawn from Cloudy Nights and the astronomy-app discussion threads, and
consistent with the repeated unmet needs already recorded in
`docs/research/community-findings.md`, which this does not repeat. New or
sharpened here:

1. **Area cloud, not point cloud.** The most specific complaint found:
   Astrospheric is "too pinpoint" - a user reported 2% cloud at their point
   while clouds surrounded them in every direction and imaging was impossible,
   with Clear Outside showing 57% obscured for the same place and time. What is
   wanted is cloud over the sky dome an observer can actually see, not the
   grid cell they stand in. This is a directional, solid-angle question, not a
   scalar one, and no surveyed tool answers it.
2. **Cirrus specifically.** Thin high cloud that civil forecasts call "clear"
   ruins a night. Layer separation exists in Clear Outside, 7Timer and
   meteoblue; a cirrus-specific signal, with its known detection difficulty,
   does not.
3. **Timing of clearing, not hourly state.** Observers ask when a hole opens and
   how long it lasts. Every tool answers with an hourly grid of state.
4. **Dew, not humidity.** Clear Sky Chart itself admits ground relative humidity
   "correlates imperfectly with actual dew formation". The field observers
   actually need is dew point depression against a radiatively cooled optic,
   which is colder than the air - a surface energy-balance question, not a
   humidity readout. No tool computes it.
5. **Cross-checking is mandatory and manual.** The consistent practitioner
   workflow is Astrospheric first, then Clear Outside, then a general model,
   with the divergence itself read as the uncertainty signal. Tools present
   agreement; users want disagreement made legible.
6. **Satellite confirmation of the current sky.** Users reach for visible and
   infrared imagery to check what the model claims. Only Astraeus's registry has
   a satellite source; no astronomy tool surveyed shows one.
7. **Seeing at a stated aperture and focal length.** A scale calibrated for 11 to
   14 inch instruments is silently wrong for a 60 mm refractor or a 300 mm lens.
8. **Honest gaps.** CMC's refusal to compute transparency above 30% cloud and
   seeing above 80% cloud is scientifically defensible and operationally
   frustrating; a white block reads as missing data rather than as "cloud is the
   binding constraint here".

## Candidate sources the registry does not catalogue

Checked against `experiments/st-johns-weather-map/registry/source_data.py`.
Already catalogued and therefore excluded: HRDPS, RDPS, GDPS, GEPS, REPS, GFS,
GEFS, ICON global, ECMWF IFS/ENS/AIFS, GOES-East, CAMS, NASA Earthdata aerosol,
RAQDPS and its retired FireWork tombstone, CWFIS hotspots, SWPC Kp/OVATION/RTSW,
SWOB, radiosondes, radar. The list below is what these tools cite or would
require and the registry does not hold.

| Candidate | Why it appears here | Endpoint | Licence | Note for the box |
| --- | --- | --- | --- | --- |
| ECCC astronomy seeing forecast | The upstream of Clear Sky Chart and Astrospheric seeing; the only operational seeing product covering Newfoundland | `https://weather.gc.ca/astro/seeing_e.html` (imagery); machine collection not identified | MSC Open Data terms presumed, not verified for these pages | Imagery only as far as could be established. Whether a GeoMet coverage exists for the seeing field is an open probe, and matters: if it does not, seeing must be `derived-here` from RDPS/HRDPS levels |
| ECCC sky transparency forecast | Same origin; unit is naked-eye limiting magnitude | `https://weather.gc.ca/astro/transparence_e.html` | as above | Same open probe. Note the unit is not comparable with 7Timer's mag/air mass |
| NOAA RAP | Astrospheric's cited source for smoke and aerosol optical depth; North American domain reaches Newfoundland, unlike HRRR | `https://nomads.ncep.noaa.gov/`, NODD S3 | US government open data, NOAA attribution requested | Would be a second aerosol opinion alongside CAMS. Domain coverage of the evidence box needs verifying before any admission |
| NOAA NBM | Astrospheric's Pro hourly cloud comparison, and a component of its ensemble | `https://registry.opendata.aws/noaa-nbm/` | US government open data | The NBM CONUS domain is very unlikely to cover the evidence box; the oceanic domain may partly. Verify before spending effort |
| NOAA HRRR | Cited by NBM's blend and widely used by US astronomy tools | `https://registry.opendata.aws/noaa-hrrr-pds/` | US government open data | CONUS domain almost certainly excludes Newfoundland. Recorded so a later reader does not re-chase it |
| NOAA NAM | Named in Astrospheric's cloud ensemble | NOMADS / NODD | US government open data | Domain coverage over the Grand Banks needs checking |
| CelesTrak GP element sets | Required for any ISS or satellite-pass field, in TLE, 2LE, OMM XML/KVN or JSON | `https://celestrak.org/NORAD/elements/gp.php` | Non-profit educational resource with a stated usage policy; the policy text was not retrieved and must be read before any automated fetch | Kilobytes. Propagate locally with SGP4; the pass prediction is `derived-here`, not retrieved |
| Space-Track | The authoritative upstream of CelesTrak's catalogue | `https://www.space-track.org/` | Account required; redistribution restricted | Would be `credential-blocked` unless an account is opened |
| JPL DE440 / DE441 ephemeris | Moon and Sun geometry, planet positions, eclipse circumstances, computed exactly rather than fetched | `https://ssd.jpl.nasa.gov/planets/eph_export.html`, consumed via Skyfield | US government public data | A few tens of MB, downloaded once, never re-fetched. Underpins darkness, Moon illumination and altitude, twilight phases |
| Falchi et al. World Atlas of Artificial Night Sky Brightness (2016) | The basis of the Bortle and mcd/m2 figures Clear Outside and Good To Stargaze show | GFZ Data Services, DOI `10.5880/GFZ.1.4.2016.001` | **CC BY-NC 4.0** - non-commercial only | 30 arcsec grid, ~2.9 GB globally; the evidence box crop is small. The NC clause is a real constraint on any future commercial path and should be recorded as such |
| VIIRS DNB nighttime lights | The observational input behind the atlas, and more current than a 2014-based composite | NASA Earthdata / NOAA NCEI annual and monthly composites | US government open data | An alternative to the NC-encumbered atlas, at the cost of doing the radiative transfer ourselves |
| Sky Quality Meter / Globe at Night observations | Ground truth for any sky-brightness field; the atlas itself was calibrated against >35,000 such observations | Globe at Night database | Varies; unverified | Would be `uncalibrated observation` class - never for verification, per the charter |
| Meteosource | Currently powers Clear Outside | `https://www.meteosource.com/` | Commercial API | Catalogue with a licence decision only, per the charter's paid-provider rule |
| 7Timer! API | Free, global, publishes seeing in arcsec and transparency in mag/air mass - the only free machine-readable astronomy-derived fields found | `http://www.7timer.info/bin/api.pl?lon=..&lat=..&product=astro&output=json` | Not stated on the public wiki; must be established before use | HTTP only in the documented form, derivation unpublished, and it would enter as `reprocessed` with an undeclared method. Useful as a comparison benchmark, unsafe as a data path |

## Open questions this leaves

- Does ECCC publish the astronomy seeing and transparency fields as a machine
  collection anywhere (GeoMet WCS, Datamart), or only as web imagery? Given
  #6's finding that ECCC publishes no layered cloud anywhere, and the ongoing
  Datamart withdrawals recorded in memory, the imagery-only outcome is likely
  and would push seeing onto a `derived-here` path.
- If seeing must be derived here, HRDPS's 28-level relative humidity and the
  temperature and wind on model levels found in #6 are the inputs; the
  meteoblue "bad layer" criterion (temperature gradient above 0.5 K/100 m) plus
  jet-stream speed thresholds is the most fully published method available to
  cite, and is a candidate baseline.
- Transparency has three incompatible published units across tools. The field
  catalogue needs to pick one and state the others are not comparable, which is
  a concrete instance of the per-field comparability question left open in #5.
- Whether "cloud over the visible sky dome in a stated direction" is a field or
  a decision-layer computation. It is the single most-cited practitioner
  complaint and it is not a scalar, so it may not fit the field catalogue at
  all.

## Sources

- [Clear Sky Chart, Tucson chart key (row-by-row method)](https://www.cleardarksky.com/c/TucsonAZkey.html)
- [Clear Sky Chart homepage](https://www.cleardarksky.com/csk/)
- [Clear Sky Chart, Wikipedia (Rahill history)](https://en.wikipedia.org/wiki/Clear_Sky_Chart)
- [ECCC Astronomy products](https://weather.gc.ca/astro/index_e.html)
- [ECCC seeing forecast](https://weather.gc.ca/astro/seeing_e.html)
- [Astrospheric FAQ and education pages](https://www.astrospheric.com/dynamiccontent/faq.html) (site returns 403 to automated fetch; content read via search index)
- [Astrospheric transparency education](https://www.astrospheric.com/DynamicContent/education/ed_transparency_en.html)
- [Astrospheric cloud ensemble](https://www.astrospheric.com/dynamiccontent/ensemble.html)
- [Clear Outside forecast page, St. John's](https://clearoutside.com/forecast/47.56/-52.71)
- [7Timer! wiki](https://github.com/Yeqzids/7timer-issues/wiki/Wiki)
- [meteoblue Astronomy Seeing help](https://content.meteoblue.com/en/private-customers/website-help/outdoor-and-sports/astronomy-seeing)
- [Cloudy Nights: best clear-skies weather apps](https://www.cloudynights.com/forums/topic/782391-for-me-here-are-the-two-best-clear-skies-weather-apps-for-astronomy/)
- [Cloudy Nights: weather apps for observation](https://www.cloudynights.com/forums/topic/973095-weather-apps-for-observation/)
- [Good To Stargaze, App Store listing](https://apps.apple.com/us/app/good-to-stargaze/id1298891559)
- [CelesTrak current GP element sets](https://celestrak.org/NORAD/elements/)
- [Falchi et al., The new world atlas of artificial night sky brightness](https://www.science.org/doi/10.1126/sciadv.1600377)
- [GFZ Data Services supplement (CC BY-NC 4.0)](https://dataservices.gfz-potsdam.de/contact/showshort.php?id=escidoc%3A1541893&contactform=)
- [NOAA HRRR on the AWS Registry of Open Data](https://registry.opendata.aws/noaa-hrrr-pds/)
- [NOAA NBM on the AWS Registry of Open Data](https://registry.opendata.aws/noaa-nbm/)
- [NOAA RAP product page](https://www.ncei.noaa.gov/products/weather-climate-models/rapid-refresh-update)
