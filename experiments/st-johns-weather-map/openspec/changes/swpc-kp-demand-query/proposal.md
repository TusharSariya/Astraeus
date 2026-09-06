# NOAA SWPC Kp selected-time demand query

## Why

Issue #218 migrates the existing bounded `noaa-swpc-kp` experiment from
scheduled artifact publication to the owner-selected timestamp-demand cache.
Closed issue #200 and PR #177 remain historical ingestion evidence.

## What changes

- Add an aware selected instant to `/space-weather` and the existing client.
- Fetch the canonical observed and forecast documents once per fresh cache
  generation, then select native rows locally without nearest or future
  substitution.
- Keep forecast failure independent from observed Kp and keep solar wind's
  unmigrated retained read independent from both.
- Remove stale retained Kp from the broader product inventory when scheduler
  cutover is complete; unrelated space-weather products remain unchanged.

The source remains `operational: false`. This creates no archive, scientific
promotion, interpolation, or stale fallback.
