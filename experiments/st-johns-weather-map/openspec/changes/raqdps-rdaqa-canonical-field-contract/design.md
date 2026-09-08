# Design

## Recommended canonical quantities

The recommendation keeps existing keys wherever their dimensions and meaning already match. It adds keys only for quantities the catalogue cannot currently name.

| Provider quantity | Canonical key | Units | Status |
| --- | --- | --- | --- |
| surface PM2.5 | `pm2_5_surface` | `kg m-3` | existing |
| column PM2.5 | `pm2_5_column` | `kg m-2` | existing |
| surface PM10 | `pm10_surface` | `kg m-3` | existing |
| column PM10 | `pm10_column` | `kg m-2` | new |
| surface O3 mole fraction | `ozone_surface_mole_fraction` | `nmol mol-1` | existing |
| surface NO mole fraction | `nitric_oxide_surface_mole_fraction` | `nmol mol-1` | new |
| surface NO2 mole fraction | `nitrogen_dioxide_surface_mole_fraction` | `nmol mol-1` | new |
| surface SO2 mole fraction | `sulphur_dioxide_surface_mole_fraction` | `nmol mol-1` | new |
| wildfire-attributed surface PM2.5 | `wildfire_smoke_pm2_5_surface` | `kg m-3` | new |
| wildfire-attributed column PM2.5 | `wildfire_smoke_pm2_5_column` | `kg m-2` | new |
| wildfire-attributed surface PM10 | `wildfire_smoke_pm10_surface` | `kg m-3` | new |
| wildfire-attributed column PM10 | `wildfire_smoke_pm10_column` | `kg m-2` | new |
| wildfire-attributed surface PM2.5 24-hour mean | `wildfire_smoke_pm2_5_surface_24h_mean` | `kg m-3` | new |
| wildfire-attributed surface PM2.5 24-hour maximum | `wildfire_smoke_pm2_5_surface_24h_max` | `kg m-3` | new |

GeoMet publishes O3, NO, NO2 and SO2 as `mol/mol`. The normalizer multiplies finite values deterministically by exactly 1,000,000,000 to store `nmol mol-1`, retaining `original_units: mol mol-1` and the scale factor in provenance. Missing cells remain missing and non-finite decoded values are refused. Verification compares against the same declared operation with zero relative tolerance and an absolute tolerance of one ULP of the expected binary64 result; it does not claim decimal scaling is bitwise lossless. This dimensionless SI-prefix conversion permits reuse of the existing ozone key and comparison with ppb-class station mole fractions. It does not use temperature, pressure or molecular mass and never converts a mole fraction to a mass concentration. Existing `ozone_surface`, `nitrogen_dioxide_surface`, `sulphur_dioxide_surface` and `carbon_monoxide_surface` mass keys remain distinct and unused by these coverages.

## Exact selected coverage mapping and manifest order

The row order below is the mandatory manifest field order and canonical artifact-digest order within each phase. Identity hashes the ordered sequence of `(coverage_id, canonical_key, artifact_digest)` tuples; map or filesystem iteration cannot change it.

| Phase | Exact GeoMet coverage id | Canonical key |
| --- | --- | --- |
| `forecast` | `RAQDPS.SFC_PM2.5` | `pm2_5_surface` |
| `forecast` | `RAQDPS.EATM_PM2.5` | `pm2_5_column` |
| `forecast` | `RAQDPS.SFC_PM10` | `pm10_surface` |
| `forecast` | `RAQDPS.EATM_PM10` | `pm10_column` |
| `forecast` | `RAQDPS.SFC_O3` | `ozone_surface_mole_fraction` |
| `forecast` | `RAQDPS.SFC_NO` | `nitric_oxide_surface_mole_fraction` |
| `forecast` | `RAQDPS.SFC_NO2` | `nitrogen_dioxide_surface_mole_fraction` |
| `forecast` | `RAQDPS.SFC_SO2` | `sulphur_dioxide_surface_mole_fraction` |
| `forecast` | `RAQDPS.Sfc_PM2.5-WildfireSmokePlume` | `wildfire_smoke_pm2_5_surface` |
| `forecast` | `RAQDPS.EAtm_PM2.5-WildfireSmokePlume` | `wildfire_smoke_pm2_5_column` |
| `forecast` | `RAQDPS.Sfc_PM10-WildfireSmokePlume` | `wildfire_smoke_pm10_surface` |
| `forecast` | `RAQDPS.EAtm_PM10-WildfireSmokePlume` | `wildfire_smoke_pm10_column` |
| `forecast_statistic` | `RAQDPS.Sfc_PM2.5-WildireSmokePlume-DAvg` | `wildfire_smoke_pm2_5_surface_24h_mean` |
| `forecast_statistic` | `RAQDPS.Sfc_PM2.5-WildireSmokePlume-DMax` | `wildfire_smoke_pm2_5_surface_24h_max` |
| `preliminary` | `RDAQA-Prelim_10km_PM2.5` | `pm2_5_surface` |
| `preliminary` | `RDAQA-Prelim_10km_PM10` | `pm10_surface` |
| `preliminary` | `RDAQA-Prelim_10km_O3` | `ozone_surface_mole_fraction` |
| `preliminary` | `RDAQA-Prelim_10km_NO` | `nitric_oxide_surface_mole_fraction` |
| `preliminary` | `RDAQA-Prelim_10km_NO2` | `nitrogen_dioxide_surface_mole_fraction` |
| `preliminary` | `RDAQA-Prelim_10km_SO2` | `sulphur_dioxide_surface_mole_fraction` |
| `final` | `RDAQA_10km_PM2.5` | `pm2_5_surface` |
| `final` | `RDAQA_10km_PM10` | `pm10_surface` |
| `final` | `RDAQA_10km_O3` | `ozone_surface_mole_fraction` |
| `final` | `RDAQA_10km_NO` | `nitric_oxide_surface_mole_fraction` |
| `final` | `RDAQA_10km_NO2` | `nitrogen_dioxide_surface_mole_fraction` |
| `final` | `RDAQA_10km_SO2` | `sulphur_dioxide_surface_mole_fraction` |
| `firework_contribution` | `RDAQA-FW_10km_PM2.5` | `wildfire_smoke_pm2_5_surface` |
| `firework_contribution` | `RDAQA-FW_10km_PM10` | `wildfire_smoke_pm10_surface` |

## Required attributes and phase identity

Every variable declares `vertical_scope` as `surface` or `entire_atmosphere`. Wildfire fields additionally declare `attribution: producer_wildfire_smoke_contribution`; this records ECCC's product attribution and does not claim independent smoke-source verification.

The two daily RAQDPS fields declare `statistic_window_hours: 24` and respectively `cell_methods: time: mean` or `cell_methods: time: maximum`. The provider valid coordinate remains the field's valid time. The contract does not infer an unadvertised interval start or treat the statistic as instantaneous.

Required `product_phase` values are:

- RAQDPS hourly fields: `forecast`;
- RAQDPS daily statistics: `forecast_statistic`;
- RDAQA preliminary analysis: `preliminary`;
- RDAQA final analysis: `final`;
- RDAQA FireWork contribution: `firework_contribution`.

RAQDPS requires the provider reference time and forecast valid time. RDAQA is a PT0H analysis: it carries the provider analysis valid time, `run_time: null`, and no invented forecast lead. Its immutable provider-run identity contains source id, product phase, valid time and artifact digests in the mandatory table order above. Preliminary, final and FireWork contribution can therefore never overwrite or satisfy one another.

## Complete atomic products

The 28 coverages form five independently timed logical streams: RAQDPS hourly (12 mandatory fields), RAQDPS statistics (2), RDAQA preliminary (6), RDAQA final (6), and RDAQA FireWork contribution (2). `RunManifest` validates every field in the selected stream, including units and required attributes, before atomic publication. A missing or mismatched field refuses that stream without thinning and leaves its prior revision current. It does not block a different phase whose complete field set validates.

WCS exposes no producer QC flag for these coverages. Shared validation computes structural completeness and QC; provenance separately states `provider_qc: unknown`. RDAQA preliminary remains labelled preliminary and cannot substitute for final. FireWork contribution remains attributed evidence and cannot substitute for total particulate concentration.

## Consumer and activation boundary

Acceptance of this contract would authorize only a follow-up experimental normal-route proof. Registry registration, scheduling, `operational: true`, display-primary status, AQHI derivation, health advice, source blending, smoke causality and production admission remain separate decisions. Until implementation is reviewed, `raw__` variables remain omitted by normal APIs and `fetch_unresolved_product` remains `complete: false`.

## Alternatives

**Field-per-phase keys** would encode preliminary/final/FireWork in every name. It simplifies callers that cannot filter provenance but creates duplicate physical quantities and makes cross-phase comparison harder. The recommended required phase attribute supplies the distinction without multiplying keys.

**Store upstream `mol mol-1` in new gas keys** avoids scaling but would leave ozone split between two canonical units and prevent reuse of the accepted `ozone_surface_mole_fraction` key. The declared SI-prefix operation keeps one unit per canonical quantity; binary64 rounding is checked with the one-ULP bound above, not claimed to be lossless.

**Keep all fields permanently source-scoped** preserves today's safest nonpublication state but prevents validated RAQDPS/RDAQA evidence from using normal field APIs. It remains the fallback if the owner declines this contract.

Omitting NO, PM10 column, smoke fields or daily statistics is not a valid alternative because it would thin the verified selected product.
