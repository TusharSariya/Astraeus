# ECCC SWOB exact-time demand observations

## Why

Issue #251 moves admitted `eccc-swob` surface readings from a sparse scheduled
station artifact to exact selected-time, selected-location demand evidence. A
station is a native point report, so an outer-product grid could create a
coordinate pair that MSC did not publish.

## What changes

- Make one bounded GeoMet OGC API Features `swob-realtime` request for the
  exact selected UTC report instant and a bounded station neighbourhood.
- Admit a response feature only when its native `data_pvdr-value` is exactly
  `MSC` and its `dataset` starts
  `msc-observation-atmospheric-surface_weather-`; no hostname or partner
  inference is used.
- Retain the nearest exact-time native MSC station inside the accepted
  latitude-corrected 0.75-degree ceiling. Preserve its report/station identity,
  coordinates, field quality tokens, native units, final-byte receipt, and
  bounded request/response metadata.
- Compose the six native station fields into the default point response and
  advertise a cache-only demand layer. Fields absent or failed by provider QC
  remain null; a failed refresh after expiry exposes typed metadata only.
- Replace the legacy scheduler after the completed cache-to-API, Linux default
  worker, and fixed-live browser checks.

The experiment remains `operational: false`. This adds no archive, stale
fallback, interpolation, synthetic station grid, partner record, forecast
meaning, or consensus contribution.
