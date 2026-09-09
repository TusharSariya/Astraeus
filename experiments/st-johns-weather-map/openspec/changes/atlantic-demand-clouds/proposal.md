# Atlantic demand clouds

Classification: experiment. Owner authorization: the 2026-09-08 implementation
request approves the supplied GOES cloud mask, RDPS white-opacity clouds and
wider WN3 plan. No production status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

## Why
Expose selected native clouds across 40-55 N, 70-40 W including water without
scheduled ingestion or forecast-sequence acquisition.

## What Changes
Add two distinct optional demand layers and metadata-only time inventories;
extend WN3 with named Atlantic geography while keeping Avalon the API default.

## Impact
Experimental API, bounded native readers, map rendering and timeline only.
