# RAQDPS and RDAQA native acquisition evidence

This is non-normative evidence for issue #133. Both readers remain isolated, unregistered, unscheduled, and `operational: false`.

## Selected product contract

The current WCS inventory was captured anonymously from `https://geo.weather.gc.ca/geomet/` under a 2 MiB metadata ceiling. It advertised the exact selected paths below. Monthly/yearly climatology layers and the retired standalone RAQDPS-FireWork family are excluded.

- RAQDPS is split into a coherent 12-field hourly group and a coherent two-field 24-hour-statistic group because GeoMet advertises different valid times. RAQDPS fields: PM2.5 and PM10 at surface and entire-atmosphere column; O3, NO, NO2, and SO2 at surface; hourly PM2.5/PM10 wildfire-smoke plume at surface and column; provider-published PM2.5 smoke 24-hour mean and maximum (including the provider's `Wildire` spelling).
- RDAQA: PM2.5, PM10, O3, NO, NO2, and SO2 for both preliminary and final surface analysis; PM2.5 and PM10 FireWork-contribution analysis.

ECCC describes RAQDPS as a 10 km North American deterministic forecast, initialized at 00Z and 12Z, hourly through 72 hours. Its current products include surface gases/particles and wildfire contribution. ECCC describes RDAQA as an hourly objective surface analysis combining RAQDPS and observations: preliminary about one hour after measurement time, final and FireWork about two hours after. The official Datamart nomenclature defines `PT0H` as analysis, so RDAQA receives no invented forecast run or lead.

Primary sources:

- https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps_en/
- https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps-datamart_en/
- https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps-geomet_en/
- https://eccc-msc.github.io/open-data/msc-data/nwp_rdaqa/readme_rdaqa_en/
- https://eccc-msc.github.io/open-data/msc-data/nwp_rdaqa/readme_rdaqa-datamart_en/
- https://eccc-msc.github.io/open-data/msc-data/nwp_rdaqa/readme_rdaqa-geomet_en/

## Field disposition and owner gate

WMS metadata publishes surface particulate and smoke as `kg/m³`, column particulate and smoke as `kg/m²`, and gases as `mol/mol`. The existing canonical catalogue has no PM10-column, nitric-oxide, smoke-attribution, RDAQA phase, or general gas mole-fraction keys; its RAQDPS O3/NO2/SO2 mappings point at mass-concentration keys and therefore cannot validate these live `mol/mol` values. The adapter preserves every such field under a source-scoped `raw__` name with published units rather than convert or mislabel it.

The precise owner gate is acceptance of canonical keys for: PM10 column burden; O3/NO/NO2/SO2 surface mole fraction; wildfire-attributable PM2.5/PM10 surface and column mass; 24-hour smoke mean/maximum; and distinct preliminary, final, and FireWork-contribution RDAQA analysis phases. Until then, a full-product `RunManifest` cannot be constructed and publication remains unavailable. This does not thin the selected acquisition contract or imply missing upstream data.

## Bounded live receipt

Before capture, 38 GiB was free. The complete operation was capped at 64 MiB and executed through the grouped full-product fetch seam, which verifies one selected valid/reference-time pair per group and returns a validator-owned nonpublishable verdict. On 2026-09-06 the client retrieved all 28 selected coverages over the 23 x 45 Avalon proof grid. The retained raw total is 127,624 bytes and the complete operation received 664,819 bytes including bounded metadata. Each receipt row records the exact URL, response headers, raw bytes/hash, actual HTTP completion time measured immediately after the response body, selected valid/reference time, units, finite/null counts, and normalized artifact bytes/hash.

All 1,035 cells in every raw TIFF were decoded and compared with the normalized artifact: 28,980 comparisons, zero mismatches. A test harness serialized each staged artifact through FastAPI with injected catalogue/manifest mappings: 28 HTTP 200 responses and 28 exact selected-cell matches. This proves serialization only, not normal-route admission. A separate test without those mappings proves the normal `/point` route does not expose a source-scoped raw field. At `2026-09-06T05:05:57.262622Z`, a local replay of the retained raw bodies rebuilt the normalized artifacts with explicit product phase, vertical scope, and statistic-window attributes; it preserved every original HTTP completion timestamp and header unchanged and repeated all comparisons. Raw files, headers, replayed artifacts, receipt, capture script, and comparison script remain in `/private/tmp/astraeus-raqdps-rdaqa-capture/final-grouped` for independent review. Only the compact receipt is committed.

## Concrete canonical-contract recommendation

A follow-up draft should add dimensionally exact base keys, then carry product phase and attribution in required variable attributes rather than multiplying every pollutant by every source phase:

| Quantity | Recommended canonical key / units | Required attributes |
|---|---|---|
| PM10 column burden | `pm10_column`, `kg m-2` | `vertical_scope=entire_atmosphere` |
| gas mole fractions | `ozone_surface_mole_fraction`, `nitric_oxide_surface_mole_fraction`, `nitrogen_dioxide_surface_mole_fraction`, `sulphur_dioxide_surface_mole_fraction`, `mol mol-1` | `vertical_scope=surface` |
| smoke particulate mass | `wildfire_smoke_pm2_5_surface`, `wildfire_smoke_pm10_surface`, `kg m-3`; matching `_column`, `kg m-2` | `attribution=producer_wildfire_smoke_plume` |
| smoke daily statistic | `wildfire_smoke_pm2_5_surface_24h_mean` and `_24h_max`, `kg m-3` | exact 24-hour window and provider statistic |
| RDAQA phase | reuse pollutant keys | `analysis_phase` required and enum `preliminary`, `final`, `firework_contribution` |

Recommended storage is one atomic artifact per product phase and valid time. RAQDPS is a forecast with required reference time; each RDAQA phase is a distinct PT0H analysis without an invented run. All selected fields are mandatory within their phase. `validate_run` computes completeness/QC, upstream WCS supplies no producer QC flags, and the artifact therefore retains an `unknown` scientific-quality notice even after structural QC passes.

A field-per-phase key alternative makes API filtering simpler but creates 14 near-duplicate catalogue quantities and weakens cross-phase comparisons. A single generic `air_quality_value` payload would reduce catalogue entries but erase unit/level comparability and is unsuitable. Omitting NO, column PM10, or smoke statistics would reduce scope but contradict the verified selected roster. Owner acceptance of the recommended keys and required attributes would unblock an experimental normal-route publication proof; it would not authorize scheduler registration, operational use, or derived air-quality science.
