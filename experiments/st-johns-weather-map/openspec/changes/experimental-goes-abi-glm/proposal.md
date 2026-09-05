# Experimental GOES-19 ABI expansion and GLM acquisition

## Why

Issue 101 asks for bounded acquisition of the named current GOES-19 ABI L2+
products and GLM. Source-specific production contracts remain unaccepted, so
the work may prove retrieval and reader behavior but cannot promote or schedule
these products.

## What

- Add bounded, directly instantiated acquisition adapters for the selected ABI
  fixed grids, DMW point vectors and GLM event/group/flash detections.
- Preserve producer identity, scan times, native units, pressure axes,
  geolocation, masks and quality flags; only producer-readable gridded pixels
  enter point reads.
- Add canonical catalogue mappings and a non-operational GLM source record.
- Record live immutable receipts and actual reader results without committing
  provider payloads or rebuilt artifacts.

## Limits

The completion capture proves complete selected DMWF and DMWVF scans and one
complete ten-minute GLM interval. A bounded suitable-daylight capture produced
readable CODF and COD2KMF cells. Fifteen daylight CPSF scans across three days
contained no finite particle-size value whose producer good-quality bit was
clear, so CPSF remains explicitly retrieved but unavailable under the native
quality rule. Production admission, scheduling and owner verification remain
unapproved.
