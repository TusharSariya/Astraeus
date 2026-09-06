# JMA GSM global pressure-profile contract

Status: draft; owner decision pending.

Affected release profiles: none; this contract remains experimental.

## Why

The existing experiment treats all 16 pressure surfaces shown by Open-Meteo's
JMA UI as mandatory for `jma_gsm`. Current API responses return null at 975,
950, 900 and 800 hPa because those levels belong to JMA's Japan-area product,
not its global product. This leaves the global source permanently incomplete
even when every field the producer publishes is retrieved.

Issue 143 requires an explicit source-specific decision. Required levels must
not be silently removed, interpolated, or filled from another model.

## What Changes

Define a draft global-product pressure contract for `openmeteo-jma-gsm`:

- require canonical temperature and wind at the 12 global levels exposed by
  Open-Meteo from 1000 through 100 hPa;
- retain producer RH and intermediary-derived dew point and cloud only at the
  eight levels where global GSM publishes RH;
- account explicitly for every field at all 16 old selection levels;
- mark 975, 950, 900 and 800 hPa unsupported by the global producer product;
- keep 70, 50, 30, 20 and 10 hPa producer-native but intermediary-unexposed;
- preserve the current 16-level consumer requirement as unsatisfied by a
  complete 12-level global-source artifact; and
- prohibit vertical interpolation and alternate-model substitution.

This proposal does not alter the adapter, registry, scheduler, API, consumer
science, source admission, or any accepted status. Until owner acceptance and
a separate implementation, current partial/deferred behavior remains in
force.

## Alternatives

1. Keep the current experimental contract permanently partial/deferred. Its
   16-level artifact remains incomplete and nonpublishable.
2. Accept this source-specific global contract. Source completeness can then
   describe complete retrieval of native global fields, while any consumer
   requiring all 16 levels still refuses the source.

The proposal recommends option 2 because it separates producer-product
completeness from consumer suitability without manufacturing values.

## Authority and evidence

Status remains draft. Only `@TusharSariya` may authorize acceptance.

Evidence: [`docs/research/wayfinder/jma-pressure-level-disposition.md`](../../../../../docs/research/wayfinder/jma-pressure-level-disposition.md)
and its adjacent live receipt. The retained raw responses, headers, official
JMA sample ZIP, and decoded GRIB are outside Git at the paths named there.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005,
GOV-SPEC-006.
