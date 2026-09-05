# Experimental native deterministic acquisition

## Why

Issue 81 requires native-producer evidence for ECMWF IFS and AIFS Single,
DWD ICON Global, and the NOAA RAP and NAM parent grids. The accepted V1 corpus
currently authorizes governance only. Source-specific contracts and the shared
integration contract remain proposed, so this work cannot replace registered
stubs, schedule acquisition, or enter a production response.

## What

- Add directly instantiated, unregistered HTTPS candidates with bounded index,
  message, discovery, and transfer limits.
- Retain exact selected upstream bytes and indexes/coordinate objects, native
  units, pressure axes, masks, grids, source URLs, ranges, hashes, and a
  test-only HTTP harness around the real artifact reader.
- Record regional exclusions rather than substituting another grid.
- Keep every result `operational: false` pending owner acceptance.

## Evidence and limits

An offline raw-to-artifact-to-reader replay proves one complete selected lead
(not a cycle or horizon). It does not prove an existing production HTTP route.
Cadence, later-lead accumulation semantics, scheduler/storage behavior,
production admission, and stub replacement remain unverified and unauthorized.
