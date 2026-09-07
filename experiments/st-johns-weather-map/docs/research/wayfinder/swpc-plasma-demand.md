# SWPC plasma selected-time demand DQC (#242)

This is non-normative implementation evidence. It does not change a source or
specification status and does not make the result operational.

## Native contract

The admitted `noaa-swpc-plasma` source uses NOAA SWPC's current
`https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json` document. The
repository's representative native fixture contains 31 keys per row: the
provider's `time_tag` and `source` identity plus all 29 fields declared by
`RTSW_WIND_FIELDS`. Those include proton/alpha moments, GSE/GSM components,
sample sizes, the feed active flag and every native quality value.

Selection keeps one row intact. It chooses the newest minute at or before the
aware selected instant, requires an age below the registry's 900-second limit,
and prefers the sole active spacecraft. With zero or multiple active rows it
uses the first provider source token alphabetically and discloses that choice.
No quantity is copied from another minute or spacecraft.

## Bounded delivery

One canonical request fills a one-entry current-document cache for at most the
provider-declared finite freshness. Identical misses coalesce. Request headers
are limited to a small allowlist and 4 KiB total; retained response headers are
limited to an allowlist and 8 KiB total. The response body and worker input are
bounded by the existing SWPC large-feed ceiling. The isolated worker has finite
address-space, output and stdio limits. The acquisition records the final-byte
completion before decode, exact byte count/digest and expiry.

Expired content is removed from eligibility before refresh. If refresh fails,
the API returns null plasma values and may disclose the bounded expired
acquisition with `values_withheld: true`; it never serves the expired row.
The scheduled plasma adapter registration is removed so this mutable current
document is not also treated as an archival artifact path.

## Fixed evidence

Deterministic tests use the repository's 7,245-byte representative native
document. Its newest `2026-09-05T17:57:00Z` active `SOLAR1` row carries proton
density `3.63 cm-3`, speed `339.2 km s-1`, temperature `86894 K` and overall
quality `0`. Tests bind those values through the cache and public API, preserve
an all-null newest row without fallback, and prove one request across
concurrent cache misses. No provider request is part of ordinary verification.
