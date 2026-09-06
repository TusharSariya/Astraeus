# GEFS selected-member demand experiment

## Why

Issue #84 already defines NOAA GEFS as a 31-member family with provider control `gec00`. This operational-false slice replaces retained full-run acquisition with one selected native run/lead and the seven registered family fields required by existing ensemble evidence consumers.

## What changes

- Resolve one aware selected instant to one canonical NOAA GEFS run and native lead.
- Fetch only indexed ranges for the seven registered fields across `gec00` and `gep01` through `gep30`.
- Cache the validated member family by canonical provider requests, never a full run.
- Preserve incomplete members and the native provider-declared cloud averaging interval (three hours at f003 and the exact labelled window thereafter) without treating it as instantaneous cloud.
