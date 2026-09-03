## Context

Four owner resolutions dated 2026-09-02 close the admission tickets for the
St. John's evidence layer. This document reconciles the state vocabulary they
assume with the one the registry actually stores, and records the ledger
itself: every source those resolutions name, with its decided state, its
access path and the reason.

Sources of truth read for this design:

- The resolutions: tickets
  [24](https://github.com/TusharSariya/Astraeus/issues/24) (ECCC and foreign
  models), [25](https://github.com/TusharSariya/Astraeus/issues/25) (astronomy,
  space weather, transparency, with its amendment adding the
  intermediary-derived class and the standing credential rule),
  [26](https://github.com/TusharSariya/Astraeus/issues/26) (local observation,
  fog, marine, air quality, cameras, transport) and
  [28](https://github.com/TusharSariya/Astraeus/issues/28) (Open-Meteo
  endpoints); the charter's Decisions-so-far section is ticket
  [5](https://github.com/TusharSariya/Astraeus/issues/5).
- The glossary at `CONTEXT.md` ("Registry state") and the governing rule and
  hard-won facts in `openspec/config.yaml`.
- `registry/schema.json` (`$defs/status`), `registry/README.md`, and the state
  of the world from `python3 registry/audit.py --summary-json`: 63 records,
  `implementing` 50, `credential_required` 7, `licence_review` 3,
  `unavailable` 2, `retired` 1, `active` 0.
- Non-normative research under `docs/research/wayfinder/`, each file on its own
  `research/*` branch and cited by path below.

## Goals / Non-Goals

Goals: one state vocabulary; a credential rule that fails closed; a
research-use admission that records terms and forbids redistribution; and a
ledger complete enough that no admitted source lacks a state, a path and a
reason.

Non-Goals: writing any adapter, promoting any source, choosing ingestion
order, defining delivery kind (that is
`openspec/changes/ensemble-members-and-source-plurality/`), defining evidence
class (that is `openspec/changes/evidence-classes-and-derived-here/`), or
scoring any source against observations.

## Decision 1: ten states, and how the current enum maps

The glossary's ten states become the registry's `status` enum. The mapping is
exact and mechanical, so the migration can be checked rather than argued:

| Current `status` | Records today | New state | Mapping rule |
| --- | --- | --- | --- |
| `active` | 0 | `operational` | Renamed, still never emitted for any source under any circumstance. No record may declare it; the audit refuses it. |
| `implementing` | 50 | `implemented-unverified` or `catalogued` | Split on an objective test: a registered adapter claims the id AND `integration.kind` is not `link_only` AND `fixture_status` is `passing` gives `implemented-unverified`; anything else is `catalogued`, because a declaration with no adapter is a catalogue entry and calling it "implementing" overstated 50 records at once. |
| `credential_required` | 7 | `credential-required` | Renamed. This is the glossary's "credential-blocked"; the resolutions call it credential-required and that name wins because it says the source is admitted, not refused. |
| `licence_review` | 3 | `licence-blocked` | Renamed, except where a resolution settled the review: see the ledger rows for `raw-cwop-pws`, `nav-canada-weather-cameras` and `provincial-hydrometric`. |
| `unavailable` | 2 | `unavailable` | Unchanged. |
| `retired` | 1 | `superseded` or `unavailable` | `superseded` when the record names its successor, `unavailable` otherwise. The one record here, `eccc-raqdps-firework`, names RAQDPS smoke-plume layers, so it becomes `superseded`. |
| `rejected` | 0 | `rejected` | Unchanged. First member is `eccc-rewps`. |
| `duplicate_evidence` | 0 | `superseded` | Folded in: a duplicate is a source another source has replaced, which is what superseded means. The successor must be named. |
| `unsupported_field` | 0 | `unavailable` | Folded in: unreachable for this deployment, with the reason carried in the status reason rather than in the state name. |
| (none) | 0 | `link-only` | New. A source with no data endpoint, cited for the reader and never fetched. |
| (none) | 0 | `partnership-only` | New. A source whose terms require written permission this deployment does not hold. |

`operational` stays unreachable: the audit refuses the value, and the API
ceiling table maps it to `unavailable` alongside every unknown state, so no
code path can emit it. A live retrieval still measures freshness and still
never promotes a state.

## Decision 2: credential-required fails closed

An admission is a ceiling, not a fetch. A `credential-required` record is
admitted, names the credential and its registration page, carries no
credential value, and is not schedulable. Until the owner supplies the key
through the secrets workflow, no adapter runs for it, no prepared URL is
constructed or logged (a URL with a key placeholder is one substitution away
from a leak, and a logged prepared URL is evidence of an attempt that did not
happen), no fixture stands in for the live value, and the reader sees a stated
absence naming the credential. Supplying the key later makes the source
schedulable; it does not raise the ceiling.

## Decision 3: research use only, terms recorded, never redistributed

This is a research experiment, so a source whose terms forbid redistribution
or commercial use is still admitted, under a declaration. The record carries
the terms text and the URL it was read from, sets `redistribution: false`, and
its values are served only to the owner's own reader. The audit fails a record
that declares restricted terms without terms text, and fails any export or
public catalogue path that would carry such values outward. The first members
are UKMO global (CC BY-SA share-alike), the Falchi atlas (CC BY-NC 4.0), NL
511 (no reuse granted), Google WeatherNext 2 (restricted real-time terms), and
MADIS and CWOP under their owner-accepted research licences.

## Decision 4: absence has one shape

Every state answers the same question the same way. A credential that never
resolves, a licence that blocks, a partnership that is not granted, a
link-only citation, and an endpoint that dies under an admitted record all
produce a stated absence with provenance and the record's own reason. None of
them produces a substituted value, a fixture on a live path, a neighbouring
source's value, or a change of state. An endpoint dying is a retrieval
failure, not a demotion: the state is the owner's declaration and only the
owner moves it.

## The admissions ledger

New = a record this change adds. Change = an existing record whose state
moves. Confirm = an existing record the resolution admitted at its current
declaration, migrated by the Decision 1 rule.

### ECCC models, analyses and nowcasting (ticket 24)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `eccc-hrdps` | Confirm | implemented-unverified | GeoMet WCS, 377 coverages, every field | The spine of the box at 2.5 km; 72 to 74 percent of core storage (`docs/research/wayfinder/size-probe-full-fields.md`) |
| `eccc-rdps` | Confirm | implemented-unverified | GeoMet WCS, every field | Includes the seeing and sky-transparency class indices admitted in ticket 25 |
| `eccc-gdps` | Confirm | implemented-unverified | GeoMet WCS, every field | Reaches 240 h only, so it is a core-tier source (`docs/research/wayfinder/planning-horizon-matrix.md`) |
| `eccc-hrdps-weg-prognos` | Confirm | implemented-unverified | GeoMet WCS | Retrieved producer diagnostics (sky state, UV, fog visibility); the [0.25, 0.5, 0.25] hourly smoothing is recorded as a comparability note, not repaired |
| `eccc-hrdpa`, `eccc-rdpa`, `eccc-hrepa` | Confirm | implemented-unverified | GeoMet WCS, 6, 18 and 27 coverages probed 2026-09-02 | Retrieved truth for the 24 h behind now |
| `eccc-hrdlps` | Confirm | implemented-unverified | GeoMet WCS, 19 coverages | Every field |
| `eccc-caldas` | Confirm | implemented-unverified | GeoMet WCS, 12 coverages | Every field |
| `eccc-integrated-nowcasting` | Confirm | catalogued | None; WMS re-probe required | Zero WCS coverages on 2026-09-02; no adapter until a WMS probe answers |
| `eccc-radiosonde` | Change | unavailable | None | The CYYT sounding is gone from Datamart and absent from GeoMet; the served vertical profile is HRDPS and RDPS pressure levels. Standing re-probe (`docs/research/wayfinder/geomet-wcs-inventory.md`) |

### Foreign models (tickets 24 and 14)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `noaa-gfs` | Confirm | implemented-unverified | NOAA S3 byte range, catalogue-family fields | Instantaneous cloud record only (PDT 4.0); the trailing average is a different quantity |
| `ecmwf-ifs` | Confirm | implemented-unverified | ECMWF open data | Reaches 360 h; drops to 144 h at 06z and 18z |
| `ecmwf-aifs-single` | Confirm | implemented-unverified | ECMWF open data | Same rule; the relative-humidity gap is recorded on the record |
| `dwd-icon-global` | Confirm | implemented-unverified | DWD open data, two paths under one source | Point sampling is retrieved via the published CLAT/CLON mesh with no regrid; rendered rasters are derived-here through a registered CDO-weights regrid method, each value labelled with its class |
| `openmeteo-jma-gsm` | New | implemented-unverified, reprocessed | Open-Meteo forecast API | Reachable here only through an aggregator; the six documented transformations are named on the record (`docs/research/wayfinder/aggregator-models.md`) |
| `openmeteo-arpege` | New | implemented-unverified, reprocessed | Open-Meteo forecast API | As above |
| `openmeteo-ukmo-global` | New | implemented-unverified, reprocessed, research use only | Open-Meteo forecast API | Admitted for research; the CC BY-SA share-alike clause is recorded and redistribution is refused |
| `brightsky-dwd-mosmix-71801` | New | implemented-unverified, reprocessed | Bright Sky, station 71801 | Visibility and dew point to ten days; producer DWD, intermediary Bright Sky |
| `openmeteo-kma-gdps` | New | unavailable | None | Stale since March 2026 behind HTTP 200 |
| `openmeteo-cma-grapes` | New | unavailable | None | Flat values over the box |
| `openmeteo-graphcast` | New | unavailable | None | Null over the box |

### Astronomy geometry (ticket 25)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `nasa-jpl-de442` | Confirm | implemented-unverified | JPL ephemeris kernel, local | Source of every derived-here geometry field (`docs/research/wayfinder/astronomy-tool-needs.md`) |
| `celestrak-gp` | New | implemented-unverified | CelesTrak GP element sets | Admitted after its usage policy is read; passes are derived-here by local propagation, never fetched as passes |
| `space-track` | New | rejected | None | Refused; CelesTrak serves the same elements without the account terms |

### Space weather (tickets 25 and 8)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `noaa-swpc-rtsw` | Change (re-implement) | catalogued until re-implemented | SWPC real-time solar wind | DSCOVR has left the feed, which now interleaves SWFO-L1, ACE and IMAP; every quality flag must be stored, which the current adapter does not do (`docs/research/wayfinder/space-weather-sources.md`) |
| `noaa-swpc-kp` | Confirm | implemented-unverified | SWPC | Admitted |
| `noaa-swpc-ovation` | Confirm | implemented-unverified | SWPC | Admitted |
| `noaa-swpc-plasma` | New | implemented-unverified | SWPC plasma product | Openly licensed, live |
| `noaa-swpc-propagated-solar-wind` | New | implemented-unverified | SWPC propagated solar wind | Openly licensed, live |
| `noaa-swpc-kp-1m` | New | implemented-unverified | SWPC 1-minute Kp | Openly licensed, live |
| `noaa-swpc-alerts` | New | implemented-unverified | SWPC alerts | Text products, retrieved |
| `noaa-swpc-scales` | New | implemented-unverified | SWPC NOAA scales | Retrieved |
| `gfz-hp30` | New | implemented-unverified | GFZ Hp30 | Openly licensed half-hour index |
| `noaa-goes-magnetometer` | New | implemented-unverified | SWPC GOES magnetometer | Openly licensed |
| `noaa-goes-xray` | New | implemented-unverified | SWPC GOES X-ray flux | Openly licensed |
| `noaa-swpc-kyoto-dst` | New | implemented-unverified, reprocessed | SWPC relay of the Kyoto WDC series | Producer Kyoto WDC and intermediary SWPC both named; never the display primary and never a derivation input |
| `noaa-swpc-stereo-a` | New | unavailable | None | Stale behind HTTP 200 |
| `noaa-swpc-kp-hourly-prediction` | New | unavailable | None | Stale behind HTTP 200 |
| `nrcan-stj-magnetometer` | New | partnership-only | None until written permission | Live over NRCan FDSN, but its terms forbid redistribution without written permission; the request goes out with the Fort Amherst camera request |
| `space-weather-canada-regional` | New | link-only | Citation only | No data endpoint exists |
| `nasa-soho-sdo-goes-suvi-imagery` | New | link-only | Citation only | Imagery for the reader, never a data path |

### Transparency, seeing, aerosol, light pollution (tickets 25, 10 and 28)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `eccc-rdps` seeing and sky-transparency indices | Confirm (field-level) | implemented-unverified | GeoMet WCS, RDPS 10 km hourly to about 84 h | Admitted as class-index fields inside their families; unlabelled integer classes, so the family carries the comparability note (a fourth incompatible transparency encoding) |
| `openmeteo-cams-aod` | New | implemented-unverified, reprocessed | Open-Meteo air-quality API | The only AOD reachable here; every direct CAMS path is credential-gated. Total AOD only, no speciation, so sea-salt AOD is not served. Two runs a day at T+10 h 16 m. The record must declare the 0.1 versus 0.4 degree upsampling trap (`docs/research/wayfinder/open-meteo-endpoints.md`) |
| `openmeteo-lsa-saf-radiation` | New | implemented-unverified, reprocessed, conditional | Open-Meteo `satellite_radiation_seamless` (`eumetsat_lsa_saf_msg`) | Direct, diffuse and DNI with a real instantaneous split, the missing wet-bulb globe input; about 1 h latency, archive only. Conditional on the unmeasured Meteosat limb-geometry cost at 52.7 W |
| `eccc-raqdps` | Confirm | implemented-unverified | GeoMet and the dated WXO-DD Datamart path | Primary air quality; 3.8 h latency (`docs/research/wayfinder/transparency-seeing-sources.md`) |
| `eccc-rdaqa` | Confirm | implemented-unverified | GeoMet | Admitted |
| `eccc-wildfire-hotspots` | Confirm | implemented-unverified | GeoMet and dated Datamart | Admitted |
| `eccc-raqdps-firework` | Change | superseded | None | Superseded by the RAQDPS smoke-plume layers, which are named as the successor |
| `copernicus-cams` | Confirm, licence corrected | credential-required | ADS API, credential | Fails closed without the key. Registry licence text corrected to the ADS catalogue's CC BY 4.0, which the current record contradicts |
| `nasa-earthdata-aerosol` | Confirm | credential-required | Earthdata granules | Fails closed without the key |
| `viirs-dnb-night-lights` | New | credential-required | Earthdata VIIRS day-night band | Fails closed without the key |
| `falchi-night-sky-atlas` | New | implemented-unverified, research use only | Published atlas raster, local | CC BY-NC 4.0 recorded as a standing constraint on any commercial path; never redistributed |
| `7timer` | New | link-only | Citation only | Benchmark for comparison, never a data path |
| `meteosource` | New | catalogued | None | Paid provider; catalogued with a licence decision only |
| `noaa-rap` | New | catalogued | None | Domain coverage over the box unverified |
| `noaa-nam` | New | catalogued | None | Domain coverage over the box unverified |
| `globe-at-night` | New | catalogued | None | Uncalibrated observation; catalogued only |

### Satellite and research comparison (tickets 25 and 9)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `noaa-goes-east` | Confirm, re-pointed | implemented-unverified | GOES-19 ABI on S3: Enterprise Cloud Mask, five-layer cloud fraction (ABI-L2-CCLF, about 21 KB over the box), cloud-top height at 2 km, cloud-top phase and temperature | Re-pointed from GOES-16 to GOES-19. No fog product exists, and the record says so (`docs/research/wayfinder/fog-cloud-line-of-sight-sources.md`) |
| `google-weathernext-2` | Confirm | credential-required, research use only | Google credential | Fails closed without the key; forward-looking values sit under restricted real-time terms and are never redistributed |
| `openmeteo-weathernext-2-cloud` | New | implemented-unverified, intermediary-derived | Open-Meteo | Open-Meteo computes cloud for a model that publishes none. Admitted under the intermediary-derived class added by ticket 25's amendment: producer Google, intermediary Open-Meteo, never the display primary, never a derivation input |

### Surface, aviation, hazard and nowcast (ticket 26)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `eccc-swob` | Confirm | implemented-unverified | Datamart SWOB | 51 stations in the box, none marine |
| `awc-metar-speci` | Confirm | implemented-unverified | AWC data API | Admitted; also the 30-day validation set for camera derivations |
| `awc-taf` | Confirm | implemented-unverified | AWC data API | Admitted |
| `awc-sigmet-airmet` | Confirm | implemented-unverified | AWC data API | Admitted |
| `awc-pirep-airep` | Confirm | implemented-unverified | AWC data API | Admitted |
| `eccc-radar` | Confirm | implemented-unverified | GeoMet WMS only | WCS carries no radar; the WMS constraints in the hard-won facts apply (axis order, unadvertised TIME) |
| `eccc-lightning` | Confirm | implemented-unverified | GeoMet | Admitted |
| `eccc-cap-alerts` | Confirm | implemented-unverified | Datamart CAP | Admitted |
| `eccc-thunderstorm-outlooks` | Confirm | implemented-unverified | Datamart | Admitted |
| `eccc-hurricane-products` | Confirm | implemented-unverified | Datamart, when active | Absent out of season is an honest absence, not a failure |

### Fog, marine and ocean (tickets 26, 9 and 28)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `smartatlantic-st-johns` | Confirm | implemented-unverified | SmartAtlantic | The only in-situ marine observation in the box carrying air temperature, dew point and SST together |
| `smartatlantic-other-validated` | Confirm | implemented-unverified for in-box buoys, catalogued otherwise | SmartAtlantic | State is per buoy: inside the box admitted, outside catalogued |
| `eccc-marine-buoys-synop` | Confirm | implemented-unverified | Datamart SYNOP | Admitted with the recorded fact that no ECCC buoy in the box carries dew point or visibility and no ship reports were observed, so fog over water stays unverifiable in situ |
| `ccg-navwarn` | New | implemented-unverified | Canadian Coast Guard NAVWARN | Hazard text feed for the marine sectors |
| `eccc-ciops-east` | Confirm | implemented-unverified | GeoMet, every field | 2 km SST and currents |
| `eccc-riops` | New | implemented-unverified | GeoMet, every field | 5 km SST; the Datamart root path is 404, GeoMet is the path |
| `eccc-rdwps` | Confirm, conditional | implemented-unverified pending an Atlantic-domain check over the box | GeoMet | Admitted subject to the check; if the domain does not cover the box the record moves to rejected the way REWPS did |
| `eccc-gdwps` | New, conditional | implemented-unverified pending the same check | GeoMet | As above |
| `eccc-rewps` | Change | rejected | None | Great Lakes only, verified on GeoMet 2026-09-02; it can never cover the box |
| `eccc-gdsps` | Confirm | implemented-unverified | GeoMet | Surge |
| `eccc-resps` | Confirm | implemented-unverified | GeoMet | Surge ensemble |
| `dfo-iwls` | Confirm | implemented-unverified | DFO IWLS API | Water level |
| `openmeteo-gfs-wave` | New | implemented-unverified, reprocessed | Open-Meteo marine API, model `ncep_gfswave016` | The only wave field reachable; carries the swell partition `ecmwf_wam` lacks; T+5 h 21 m, 16 d, 0.16 degree. `cell_selection=sea` is mandatory and an all-null column is a retrieval failure, not calm |
| `eccc-marine-forecasts-alerts` | Confirm | implemented-unverified | Datamart | Retrieved text products |

### Hydrology and air quality (tickets 26 and 11)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `eccc-hydrometric` | Confirm | implemented-unverified | Datamart hydrometric | Admitted |
| `provincial-hydrometric` | Change | catalogued | None | Licence review closed as catalogued only |
| `municipal-hydrometric` | Confirm | catalogued | None | No feed |
| `nl-air-quality-csv` | New | implemented-unverified, uncalibrated observation | NL provincial hourly CSV | The only timely PM2.5 and ozone in the box; provisional data, so uncalibrated and never used for verification (`docs/research/wayfinder/running-sources.md`) |
| `eccc-aqhi` | Confirm | implemented-unverified | Datamart | Unchanged by these resolutions; migrated by the Decision 1 rule |

### Transport and cameras (tickets 26, 12 and 21)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `nl-511` | Confirm | credential-required, research display only | NL 511 API key | Fails closed without the key; its terms grant no reuse, so research display only and never redistributed |
| `nl-511-rwis` | Confirm | unavailable | None | No reachable feed |
| `nav-canada-weather-cameras` | Change | credential-required | NC-SPACES account held by the owner | Moves off licence review and off the earlier unavailable finding: the public registry endpoint is dead, but the owner holds NC-SPACES credentials. Fails closed until the key resolves. Follow-up: NC-SPACES hosts more than cameras, so a HITL ticket inventories its products |
| `ccg-harbour-cameras` | New | partnership-only | None until permission | Three harbour cameras, 20-minute MP4 sequences under a courtesy notice that is not a licence |
| `city-st-johns-road-cameras` | New | partnership-only | None until permission | Six road JPEGs with no licence |
| `ntv-cameras` | New | partnership-only | None until permission | Eight JPEGs including the only sky-dome camera (`docs/research/wayfinder/camera-inventory.md`) |

### Citizen observations (tickets 26 and 25)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `noaa-madis` | Confirm | credential-required, research use only | MADIS credential | Fails closed without the key; uncalibrated observation; licence accepted by the owner for research |
| `raw-cwop-pws` | Change | implemented-unverified, uncalibrated observation, pending licence text | CWOP feed | Licence review closes as admitted once the licence text is read and recorded; until then the record carries the unread-terms condition |
| `purpleair` | Confirm | credential-required | PurpleAir key | Fails closed; uncalibrated observation |
| `openaq` | Confirm | credential-required | OpenAQ key | Fails closed; uncalibrated observation |
| `netatmo` | New | catalogued | None | Catalogued only |
| `weather-underground` | New | catalogued | None | Catalogued only |

### Open-Meteo endpoints not admitted (ticket 28)

| Record | Action | State | Access path | Reason |
| --- | --- | --- | --- | --- |
| `openmeteo-air-quality-particulates` | New | catalogued | None | RAQDPS stays primary for PM, ozone, NO2, SO2, CO and dust |
| `openmeteo-marine-currents-sealevel` | New | catalogued | None | The producer cannot be declared truthfully: Open-Meteo labels `meteofrance_currents` Météo-France, the field set reads as a Mercator or Copernicus analysis, and `meta.json` carries no producer string |
| `openmeteo-glofas` | New | catalogued | None | Works (Exploits 243, Humber 187 m3/s) but no profile scores it and a 0.05 degree cell does not resolve the Waterford |
| `openmeteo-elevation` | New | catalogued | None | Copernicus GLO-90 DEM; the downscaling switch is what matters, not the DEM as a field |
| `openmeteo-marine-sst` | New | rejected | None | Four native SST paths already exist and they are four different quantities; a fifth is not evidence |
| `openmeteo-uv-index` | New | rejected | None | UV index is producer output on GeoMet |
| `openmeteo-pollen-ammonia` | New | rejected | None | 0 of 216 non-null; `cams_europe` returns HTTP 400 "No data is available for this location" here |
| `openmeteo-aqi-indices` | New | rejected | None | `european_aqi` and `us_aqi` are index constructions, not quantities |
| `openmeteo-beam-split` | New | rejected | None | An intermediary's split of a producer's total with no method named; the WeatherNext 2 cloud reasoning, without the intermediary-derived declaration that saved it |
| `openmeteo-climate-cmip6` | New | rejected | None | CMIP6 projections answer for forecast dates unmarked |
| `openmeteo-seasonal-seas5` | New | rejected | None | Monthly run at T+4.4 d; adds nothing inside 14 days |

Anything reachable only through `best_match` is refused everywhere: it names no
producer, so no record can declare one.

## Risks and open questions

- **The `implementing` split touches 50 records at once.** The test is
  objective, but it will move most of the registry to `catalogued`, which is
  the honest reading and will look like a regression in any dashboard that
  counts `implementing`. The audit's summary counts change accordingly.
- **Conditional admissions.** RDWPS, GDWPS and the LSA SAF radiation are
  admitted with a named condition. A conditional record must state the
  condition and stay unschedulable until it is met, so that a condition never
  quietly lapses into an admission.
- **Unread terms.** CWOP and CelesTrak are admitted after their terms are
  read; the records carry the unread-terms condition until then.
- **Cross-change coupling.** `openspec/changes/ensemble-members-and-source-plurality/`
  removes the requirement "The registry is the only catalogue" and replaces it
  with a delivery-kind-aware version. This change does not touch that
  requirement, and every reprocessed or intermediary-derived row above
  declares its delivery kind under that change's rules, extended by
  `openspec/changes/evidence-classes-and-derived-here/`.
- **CAMS licence.** The correction is to CC BY 4.0 per the ADS catalogue. If
  the ADS licence dispute noted in ticket 10 reaches the Open-Meteo delivery
  as well, `openmeteo-cams-aod` inherits it and the record must be re-read.

## Seam

Pinned by the change lead on 2026-09-02 before any task was dispatched. Every
task agent implements against this section verbatim; a disagreement between a
task's prose and this section is resolved in favour of this section, and any
departure is recorded under Deviations below.

### S1. The ten states

`registry/schema.json` `$defs/status` is exactly this list, in this order:

```
"operational", "implemented-unverified", "catalogued", "credential-required",
"licence-blocked", "link-only", "partnership-only", "unavailable",
"rejected", "superseded"
```

Hyphens, never underscores. The old nine values are gone from the schema; the
audit reports `invalid status 'implementing'` (and so on) for any record still
carrying one. The audit refuses `operational` on any record with the error
text `declares operational, which no source may claim`.

### S2. A dependency-free admission module

`registry/admission.py` is new and imports nothing but the standard library.
It is the single definition the audit, the API and the ingest registry all
read, so no two of them can disagree:

- `STATES: tuple[str, ...]` is the S1 list.
- `SCHEDULABLE_STATES = frozenset({"implemented-unverified"})`.
- `NO_ACCESS_PATH_STATES = frozenset({"link-only", "partnership-only", "rejected"})`:
  `access_endpoints` must be `[]` on these.
- `TERMINAL_STATES = frozenset({"unavailable", "rejected", "superseded", "link-only", "partnership-only"})`:
  `fixture_status` and `live_smoke_test_status` must both be `not_applicable`.
- `CEILING: dict[str, str]` maps each state to itself except
  `"operational" -> "unavailable"`.
- `ceiling_state(status: str) -> str` returns `CEILING.get(status, "unavailable")`.
- `condition_outstanding(record) -> bool` is true when the record carries an
  `admission_condition` block whose `satisfied` is false.
- `implemented_unverified_ok(record, adapter_ids) -> bool` is the objective
  test of Decision 1: `record["id"] in adapter_ids` and
  `record["integration"]["kind"] != "link_only"` and
  `record["fixture_status"] == "passing"`.
- `declaration_schedulable(record, adapter_ids) -> bool` is
  `record["status"] in SCHEDULABLE_STATES and implemented_unverified_ok(record, adapter_ids) and not condition_outstanding(record)`.
  It is the registry half of schedulability; the ingest half (freshness,
  reach, cadence, ensemble flag) stays in `ingest/registry.py`.
- `access_path_of(record) -> str | None` returns the first access endpoint or
  `None`.

### S3. Record blocks

All four are optional keys on `$defs/source` with `additionalProperties: false`.

`credential`, required when and only when status is `credential-required`:

```json
{"name": "WEATHER_SECRET_NC_SPACES_TOKEN", "registration_url": "https://..."}
```

`name` matches `^WEATHER_SECRET_[A-Z0-9_]+$` and is the environment variable
`ingest/secrets.py` `SECRET_ENV_BY_SOURCE` maps for the id; the block has no
other key, so no value can be written into it. `authentication.required` must
be true and `authentication.registration_url` must equal the block's URL.
Names: `copernicus-cams` WEATHER_SECRET_COPERNICUS_ADS_TOKEN,
`nasa-earthdata-aerosol` and `viirs-dnb-night-lights`
WEATHER_SECRET_NASA_EARTHDATA_TOKEN, `noaa-madis` WEATHER_SECRET_MADIS_TOKEN,
`purpleair` WEATHER_SECRET_PURPLEAIR_API_KEY, `openaq`
WEATHER_SECRET_OPENAQ_API_KEY, `nl-511` WEATHER_SECRET_NL511_API_KEY,
`google-weathernext-2` and `open-meteo-weathernext-2`
WEATHER_SECRET_GOOGLE_WEATHERNEXT_TOKEN, `nav-canada-weather-cameras`
WEATHER_SECRET_NC_SPACES_TOKEN.

`restricted_terms`, optional on any non-terminal state:

```json
{"terms_text": "...verbatim clause...", "terms_source_url": "https://...",
 "redistribution": false, "read_date": "2026-09-02"}
```

`redistribution` is `const false`. The audit refuses a block whose
`terms_text` is empty or whitespace, and requires `licence.review_state` to
be `restricted` and `consensus.eligible` to be false on the record. The
top-level prose `redistribution` string stays as it is.

`admission_condition`, optional on any state:

```json
{"condition": "what is outstanding", "satisfied_by": "what would satisfy it",
 "satisfied": false, "recorded_on": "2026-09-02"}
```

`satisfied: false` makes the record unschedulable (S2). Nothing in the running
system flips it.

`superseded_by`, required when and only when status is `superseded`:

```json
{"source_id": "eccc-raqdps", "detail": "RAQDPS smoke-plume layers"}
```

`source_id` must be an existing record id; the audit refuses `superseded`
without it.

`access_endpoints` becomes `minItems: 0`. On `NO_ACCESS_PATH_STATES` it must
be `[]`; `documentation_urls` carries the citation. The API keeps emitting the
literal `"unavailable"` for `access_endpoint` when the list is empty.

### S4. Audit functions and summary

New functions in `registry/audit.py`, each `(source) -> list[str]` unless
stated, all called from `semantic_errors`:

- `state_errors(source, adapter_ids)`: S1 membership, `operational`
  refused, `implemented-unverified` requires `implemented_unverified_ok`
  (error text `claims implemented-unverified with no registered adapter,
  a link_only integration or a fixture that is not passing`), terminal
  states require `not_applicable` fixture and smoke, `NO_ACCESS_PATH_STATES`
  require empty endpoints, `credential-required` requires the `credential`
  block and vice versa, `superseded` requires `superseded_by` and vice versa.
- `credential_errors(source)`: block shape, name pattern, no key material,
  `authentication` agreement.
- `restricted_terms_errors(source)`: S3 rules.
- `condition_errors(source)`: `condition` and `satisfied_by` non-blank.
- `no_endpoint_errors(source)`: `link-only` and `partnership-only` carry no
  endpoint and `integration.kind == "link_only"`.
- `glossary_state_errors(path=None) -> list[str]`: reads the repo-root
  `CONTEXT.md` (`HERE.parents[2] / "CONTEXT.md"`), extracts the ten names
  from the "Registry state" entry, maps `credential-blocked` to
  `credential-required`, and compares the set against `admission.STATES`.
  A missing file is an error.
- `ledger_errors(data) -> list[str]`: every id in `LEDGER_SOURCE_IDS`
  (a frozenset in `audit.py` transcribed from the ledger table, minus
  `openmeteo-weathernext-2-cloud`, see Deviations) has a record; every record
  has a non-blank `reason`. Added by task 2.3, which runs after section 7.

`--summary-json` keeps every existing key. `status_counts` is keyed by the
S1 states. New keys, each a sorted list of ids unless stated:
`schedulable_by_registry` (S2 `declaration_schedulable` against
`adapter_source_ids()`), `admission_conditions_outstanding`,
`research_use_only` (records carrying `restricted_terms`),
`credential_required`, `no_access_path` (empty endpoints), and
`migration_split: {"implemented-unverified": n, "catalogued": n}`.

### S5. The migration of the 65 existing records

The registry holds 65 records today, not 63: `dwd-icon-eps` (`unavailable`)
and `open-meteo-weathernext-2` (`credential_required`) were added by steps 3
and 7. All 50 `implementing` records carry `fixture_status: "planned"`. The
21 ids `adapter_source_ids()` returns all have passing fixture suites under
`api/tests/test_adapter_*.py` (207 passed on 2026-09-02), so task 3.1 sets
`fixture_status: "passing"` on exactly those 21 and applies the Decision 1
rule: those 21 become `implemented-unverified`, the other 29 become
`catalogued`. `live_smoke_test_status` is untouched. A record the ledger
marks "Confirm implemented-unverified" that has no registered adapter lands
on `catalogued` with its reason prose extended by one sentence saying it is
admitted by its ticket and catalogued until an adapter claims the id. New
records the ledger marks `implemented-unverified` follow the same rule: with
no adapter they are written `catalogued`, and their reason says so.

### S6. API ceiling and schedulability

`api/weather_api/sources.py` does not exist. The ceiling table is
`_REGISTRY_STATE_CEILING` in `api/weather_api/store.py`; task 9.1 replaces it
with `admission.ceiling_state`. The emitted enum `SourceState` in
`api/weather_api/models.py` is replaced by the ten S1 values
(`OPERATIONAL`, `IMPLEMENTED_UNVERIFIED`, `CATALOGUED`,
`CREDENTIAL_REQUIRED = "credential-required"`, `LICENCE_BLOCKED`,
`LINK_ONLY`, `PARTNERSHIP_ONLY`, `UNAVAILABLE`, `REJECTED`, `SUPERSEDED`);
this is the one edit to `models.py` and it is recorded under Deviations.
`api/weather_api/fixtures.py` moves its six fixture records to
`IMPLEMENTED_UNVERIFIED`. `ingest/registry.py` `IngestConfig` gains
`admission_condition_outstanding: bool` (read through
`admission.condition_outstanding`) and `ingestible` tests
`registry_status == "implemented-unverified"` and
`not admission_condition_outstanding`. `ingest/secrets.py` gains the two rows
S3 names for `nav-canada-weather-cameras` and `viirs-dnb-night-lights`.
`POST /refresh` keeps the detail prefix `source ids are not schedulable:` and
appends each id as `id (state)` or `id (state; condition outstanding: ...)`.
Tests for 9.x live in new files `registry/tests/test_ceiling.py` and
`registry/tests/test_schedulable.py`, which exercise `registry/admission.py`
under plain `python3`, plus pytest cases in `api/tests/test_api.py` and
`api/tests/test_astronomy.py` updated to the new strings.

### S7. Verification commands

From `experiments/st-johns-weather-map/`: `python3 registry/audit.py`,
`python3 registry/audit.py --summary-json`,
`python3 -m unittest discover -s registry/tests -v`. API tests run from
`api/` with `uv sync` once, then bare `uv run pytest` (`addopts = "-q"`).
Between the schema landing (section 1) and the migration landing (task 3.1)
the audit is expected red on the old status values; the unit tests named in
each task are the verify signal for sections 1 and 2. Every new record must
also be listed under a candidate in `registry/catalogue_coverage.json`, or
the audit reports it absent from catalogue coverage.
