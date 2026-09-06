# Missing-only acquisition representation audit

## Current shapes

The worker cannot infer completeness from time keys alone because registered
adapters publish several incompatible artifact shapes:

| Shape | Representative path | Published unit | Selection available upstream | Partial publication today |
| --- | --- | --- | --- | --- |
| Indexed GRIB | NOAA GFS | `surface` and `upper_air` Zarr files, each spanning many valid times and fields | Byte ranges by field within one lead; URLs by lead | Unsafe: a selected-time Zarr has a new digest under an existing logical name |
| JSON/time series | SWPC products | One Zarr spanning the response's times and fields | Usually only client-side row filtering; discovery currently retrieves the bounded response | Unsafe: selected rows replace an aggregate logical artifact; full-hit discovery already transferred payload |
| Ensemble container | GEFS, REPS and GEPS | One `members` Zarr spanning required members, fields and times | Requests can select member/field/time units | Unsafe: selected units replace the whole-member container and `complete` describes only the selection |
| Multi-grid statistics | WeatherNext statistics | One Zarr per native grid, each spanning selected fields/times | Request manifest can select fields and leads | Unsafe without an expected grid/field matrix and merge validation |
| Granule or scan | GOES ABI/GLM and observations | Usually one logical artifact for a candidate scan or bounded interval | Per-object selection | A one-time candidate is all-or-nothing; interval candidates still aggregate granules |
| Per-field WCS utility | GeoMet WCS helpers | One logical artifact per field plus optional raw companion | Field, time and run are explicit in each request | Structurally mergeable by adding an absent logical name, but this helper is not a registered worker adapter and its experimental run contract is not publishable |

## Why the existing key is insufficient

`artifact-ingestion` identifies a frame by `(source_id, provider_run_id,
valid_time)`. `present_keys` unions every published revision's declared times.
That correctly handles independent time-partitioned artifacts, but it calls a
time present when an expected logical artifact is wholly absent. Intersecting
all artifact times fixes that example while falsely declaring every disjoint
time partition missing. Neither operation can discover an absent row because
the expected artifact/field/member shape is not stored.

The immutable identity check is at `(source_id, provider_run_id,
logical_name)` and compares the whole artifact digest. A selected subset of an
aggregate therefore conflicts with retained bytes even when its individual
frame did not overlap them. Marking that subset `complete` would also weaken
run completeness to mean only "complete for this request," which the current
publication function does not distinguish from a complete provider run.

## Required owner decision

Choose the durable publication unit before aggregate repair proceeds:

1. **Frame-fragment revisions (recommended):** register the expected artifact
   shape per adapter and store immutable fragments keyed by source, provider
   run, logical artifact, valid time, field group and member group. A manifest
   revision atomically points to a complete set of fragments; readers assemble
   only through that manifest. Missing-only fetch adds absent fragments and
   publishes a new manifest without changing retained fragment bytes.
2. **Copy-on-write aggregate merge:** register expected logical artifacts,
   fields and members; read and integrity-check the current aggregate, merge
   newly fetched units locally, validate the entire provider run, then publish
   a new aggregate revision. This preserves old revisions but necessarily
   re-uploads retained bytes and therefore conflicts with the accepted wording
   that retained frames are not re-uploaded.
3. **All-or-nothing aggregate cache:** keep current artifacts and declare a
   partially present provider run unrecoverable until it ages out. This is the
   barrier implemented by this change, but it does not satisfy the accepted
   partly-filled-window repair scenario.

Option 1 matches the requirement that retained frames are neither re-fetched
nor re-uploaded. It requires an accepted clarification because it adds identity
dimensions and a manifest/read contract absent from the current OpenSpec and
database schema. Until that choice is accepted and implemented, no current
aggregate adapter should set `partial_fetch_supported = True`.
