# Timestamp-driven source query cache

## Why

On September 6 the owner corrected the delivery architecture: the application
selects a timestamp, reads a simple anti-hammering cache, and performs one
bounded provider query on a miss. Background full-run ingestion, mandatory
ArtifactStore publication and two-run retention are not the desired source
path. This proposal records that latest direction without changing accepted,
verified, superseded or operational status.

## What changes

- Resolve an aware selected timestamp to one provider-native request.
- Cache the bounded raw and normalized result under provider-native identity and
  validators for a source-specific freshness interval.
- Coalesce concurrent identical misses and revalidations.
- Return explicit unsupported, unavailable and expired outcomes without stale
  or neighbouring-time substitution.
- Migrate existing HRDPS, METAR/SPECI and Kp routes as bounded follow-ups; revise
  CYYT TAF and GFS before their current persistent-publication branches merge.

## What stays

Complete eligible-field dispositions, bounded acquisition and decoding, native
units/times/masks/QC/provenance, actual API/client proof, `operational: false`,
and independent verification remain required. Existing persistence safeguards
remain in main but are not a mandatory route for this cache.
