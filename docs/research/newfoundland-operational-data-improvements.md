# Newfoundland operational-data coverage audit

Last reviewed: 2026-09-01

Status: non-normative research and implementation backlog. It does not make a
provider operational or alter an accepted V1 contract.

## Audit result

The St. John's weather-map experiment catalogues 63 sources and has registered
adapters for 17; 46 entries remain unwired. At audit time the registry declared
50 `implementing`, 7 `credential_required`, 3 `licence_review`, 2
`unavailable`, 1 `retired`, and no `active` source.

The useful live core is HRDPS, RDPS, GFS, CYYT METAR/SPECI, ECCC radar,
lightning, CAP and AQHI, GOES, NOAA SWPC, and DE442. GDPS, ECMWF, and DWD
adapters existed without a current published artifact in the audited run.
There was no complete live vertical-profile, ensemble, road, harbour, ship, or
local met-ocean experience.

“Everything” means every relevant, lawful, documented observation or forecast
with provenance. It does not mean scraping restricted systems, inventing
public offshore or military feeds, or presenting a camera estimate as an
instrument observation.

## Required source states and truth boundary

Use these states consistently: `operational` (validated and owner-approved),
`implemented-unverified`, `catalogued`, `credential-blocked`,
`licence-blocked`, `link-only`, `partnership-only`, `unavailable`, `rejected`,
and `superseded`.

A registry entry is not an adapter. Refresh must require an eligible registry
state, resolvable freshness contract, **and** registered adapter. A source is
live only after successful, complete, schema-valid artifact publication; a
failed/incomplete latest attempt cannot make it live. WMS and image proxies
need the same artifact, provenance, and freshness boundary as file adapters.

## Complete Newfoundland acquisition backlog

### Local meteorology, aviation, climate, and air quality

- Discover all relevant MSC Datamart SWOB partners, especially `nl-firewx`,
  `nl-water`, `dfo-moored-buoys`, and `dnd-ccg-lighthouse`. Preserve owner,
  instrument height, flags, and observation time.
- Make CYYT the aviation anchor: raw and decoded METAR/SPECI, ceiling,
  visibility, wind/gust, weather groups, pressure, and age. Add TAF and
  SIGMET/AIRMET where documented rights permit; retain IWXXM beside text.
- Add radiosonde/model soundings, inversions, freezing level, low-level wind
  shear, precipitable water, cloud layers, and boundary-layer depth.
- Add ECCC climate observations, AHCCD and MetNotes for calibration and event
  context; add St. John's NAPS PM2.5/ozone and CWFIS fire/smoke context.

Official starting points: [SWOB partners](https://dd.weather.gc.ca/today/observations/swob-ml/partners/),
[climate observations](https://eccc-msc.github.io/open-data/msc-data/climate_obs/readme_climateobs-datamart_en/),
[AHCCD](https://eccc-msc.github.io/open-data/msc-data/climate_ahccd/readme_ahccd_en/),
[IWXXM](https://dd.weather.gc.ca/today/aviation/iwxxm/),
[MetNotes](https://eccc-msc.github.io/open-data/msc-data/metnotes/readme_metnotes-datamart_en/),
[NAPS St. John's](https://www.gov.nl.ca/mca/airmon/naps/stjohns/), and
[CWFIS](https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/cwfif/cwfis-data-placemat.pdf).

### NL 511, roads, ferries, and travel

NL 511 does **not** document raw RWIS/weather-station measurements. Its useful
documented products are:

| Product | Endpoint |
| --- | --- |
| winter roads | `https://511nl.ca/api/v3/get/winterroads` |
| cameras | `https://511nl.ca/api/v2/get/cameras` |
| ferry terminals | `https://511nl.ca/api/v2/get/ferryterminals` |
| events | `https://511nl.ca/api/v2/get/event` |
| alerts | `https://511nl.ca/api/v2/get/alerts` |
| wind warnings | `https://511nl.ca/api/v2/get/windwarnings` |

Use the documented developer-key query parameter, resolve it only at runtime,
never log prepared URLs, and enforce 10 calls per 60 seconds. Cache endpoints
independently and expose age/failure. See [developer documentation](https://511nl.ca/developers/doc)
and [winter-road help](https://511nl.ca/help/endpoint/winterroads).

Derived products can include route closure/hazard overlays, ferry disruption,
crosswind alerts, camera health, and weather-aware alternatives. An unreported
road is never silently certified safe.

### Harbour, ocean, ice, ships, and offshore

- Validate actual variables and latest timestamp in the
  [SmartAtlantic St. John's ERDDAP table](https://www.smartatlantic.ca/erddap/tabledap/SMA_st_johns.html)
  before calling it real-time.
- Add CHS water level, RIOPS/CIOPS, waves, SST, currents, surge, Canadian Ice
  Service, and International Ice Patrol products.
- Add CCG NAVWARN WFS and the StJohnsBase, Sir Humphrey Gilbert Building and
  Fort Amherst viewpoints, subject to camera terms. Start with the
  [CCG camera catalogue](https://e-navigation.canada.ca/topics/cameras/index-en)
  and [NAVWARN GeoJSON](https://e-nav.ccg-gcc.gc.ca/geoserver/nis/nw_en/ows?outputFormat=application%2Fjson&request=GetFeature&service=WFS&typeName=nw_en&version=2.0.0).
- Historical [DFO AIS vessel density](https://open.canada.ca/data/en/dataset/27b450d8-3a9a-460a-8f71-587737b2cdf4)
  supports traffic climatology, not live positions. Live AIS requires a lawful
  receiver or licensed feed, privacy controls, and redistribution review.
- C-NLOPB/C-NLOER provides regulatory installation/safety context. No reliable
  public per-installation live meteorological feed was confirmed for Hibernia,
  Hebron, Terra Nova or SeaRose. Mark observations `partnership-only` until a
  documented WMO/VOS identity and redistributable endpoint are verified; do
  not promise an assumed 3–6-hour fog sentinel.

References: [CHS services](https://www.tides.gc.ca/en/web-services-offered-canadian-hydrographic-service),
[RIOPS](https://eccc-msc.github.io/open-data/msc-data/nwp_riops/readme_riops_en/),
[Ice Patrol](https://navcen.uscg.gov/north-american-ice-service-products), and
[C-NLOPB offshore information](https://www.cnlopb.ca/offshore/).

### Photography, stargazing, Signal Hill, aircraft, and military limits

Combine local STJ geomagnetic evidence and the official
[Space Weather Canada regional forecast](https://www.spaceweather.gc.ca/forecast-prevision/short-court/regional/sr-en.php)
with SWPC. Add VIIRS night lights/fire, GOES cloud top/phase, astronomical
twilight, Moon geometry, seeing proxies, precipitable water, wind, dew/frost
risk and directional obstruction horizons. Present cloud by layer,
transparency/aerosol, Moon separation, gust, dew margin, precipitation,
freshness, and disagreement instead of one opaque score.

Signal Hill is a destination/validation site, not a confirmed unique weather
station. Use CYYT/local networks, terrain, [Parks Canada notices](https://www.parks.canada.ca/lhn-nhs/nl/signalhill),
and nearby harbour cameras with distance/representativeness disclosed.
Aircraft positions require lawful ADS-B or a licensed feed and are context, not
meteorological truth. For military facilities use only intentionally public
weather, aviation, and safety products: no restricted-camera scraping,
operations inference, or military-aircraft tracking.

## Camera computer vision

Useful derived signals are stale/duplicate-frame, blur, darkness, exposure,
obstruction, lens water/snow and camera-movement health; calibrated landmark
visibility and coarse fog classes; daytime cloud fraction and horizon/fog-bank
segmentation; coarse dry/wet/snow/slush/standing-water road classes; and
relative whitecap/sea-spray activity.

Reject face/plate recognition, person tracking, military inference, image-based
vessel identification, “black ice detected,” and camera-only safe wave-height
or visibility claims. Confirm terms, mask private regions, minimize retention,
and publish camera/capture/retrieval IDs and times, crop/mask, model version,
quality flags, confidence, limits, and `operational: false` until validated.

Validate for at least 30–60 days across day/night, fog, rain, snow,
freeze/thaw, and lens contamination. Compare cloud/visibility with METAR/SPECI,
radar and human labels; compare road classes with NL 511 labels; publish
held-out calibration and false-negative performance.

## Prioritized implementation

### P0: make existing claims honest

- Adapter-aware scheduling; complete-artifact live status; evidence-bound WMS.
- Remove hard-coded local-station UI entries without retrieved evidence.
- Reconcile catalogue count, adapter count, states, owners and source IDs in CI.

### P1: maximum local decision value

- NL 511 adapter with secret-safe auth, rate limiting and fixtures.
- CYYT/IWXXM/TAF, all SWOB partners, NAPS, SmartAtlantic, CHS, CCG NAVWARN,
  harbour-camera health, a real vertical profile, and ensemble uncertainty.
- Run, photography, stargazing and travel cards exposing exact evidence,
  freshness and disagreement.

### P2: marine and remote-sensing depth

- RIOPS/CIOPS/waves/icebergs, historical AIS density, CWFIS/VIIRS, and
  calibrated camera visibility/cloud/road-state signals.
- Evaluate licensed live AIS/ADS-B only after necessity, rights, privacy, cost,
  retention and redistribution reviews; pursue offshore data through confirmed
  WMO feeds or explicit partnerships.

For every source require official documentation, licence/access record,
fixture, opt-in live smoke, schema/quality validation, raw checksum where
allowed, normalized artifact, API readback, freshness/failure observability,
attribution, redistribution decision, and missing/stale/conflict UI states.
