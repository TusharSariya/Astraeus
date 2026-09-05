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

The capture proves one current scan or interval per access path. CODF,
COD2KMF and CPSF had no producer-good pixel in the evidence box in this
capture and therefore failed closed; they remain retrieved-but-unreadable for
this scan. Production admission, scheduling and owner verification remain
unapproved.
