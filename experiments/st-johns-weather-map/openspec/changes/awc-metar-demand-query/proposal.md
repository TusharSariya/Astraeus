# CYYT METAR selected-time demand query

## Why

Issue #214 migrates the already bounded `awc-metar-speci` experiment from scheduled publication to the owner-selected timestamp-demand architecture. PR #185 remains historical acquisition evidence; this change does not relabel it as demand-cache proof.

## What changes

- Resolve each aware selected time to a canonical two-hour AWC request ending at the UTC hour ceiling, using official `date` and `hours` selectors.
- Cache at most 64 complete 64 KiB responses, coalesce identical requests, and revalidate only under provider validators and finite freshness headers.
- Select the latest CYYT observation at or before the requested instant only when its age is strictly less than one hour.
- Serve the observation through the existing `/point`, Brief, and Workbench paths without requiring ArtifactStore health.
- Disable scheduled `awc-metar-speci` acquisition after the demand path is proven.

The experiment remains `operational: false`; no source admission, new derivation, bulk archive, or stale fallback is introduced.
