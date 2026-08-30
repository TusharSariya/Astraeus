## Why

`noaa-gfs` never published: every lead hour tripped the 25 MB per-lead byte
ceiling and failed closed. The `.idx` selection matched on parameter name
alone, and GFS pgrb2 publishes TMP, RH, UGRD, VGRD and TCDC at every isobaric
level, so hundreds of messages were selected and the 1 MiB gap-merge coalesced
them into near-whole-file spans (a correct selection measures ~8.4 MB of
messages, ~10.5 MB after merging, against a 450+ MB file). A second, latent
defect sat behind the first: the decode opened the whole heterogeneous subset
(mean sea level + 2 m + 10 m + surface + cloud layers) in a single cfgrib
call, which cannot build one dataset from disagreeing scalar level
coordinates, so even correctly bounded ranges could never have decoded.

Separately, the reader has no cloud strata at all. GFS itself declares
low/middle/high cloud cover (`LCDC`/`MCDC`/`HCDC` at the provider's own
low/middle/high cloud layers) as retrievable fields. Serving them is not the
derivation the owner has gated (deriving strata from METAR layer reports,
`api/weather_api/store.py:51-55`, owner gate 2 in `cloud-and-fog-evidence`):
these are provider-declared quantities, published as retrieved with GFS
provenance. That gate stays open and untouched.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **GFS `.idx` selection:** select messages by exact (parameter, level) pair
  — eleven pairs — plus an instantaneous-forecast filter (`anl` /
  `N hour fcst`), so the time-averaged cloud duplicates and APCP
  accumulations are never fetched. The 25 MB per-lead ceiling is kept
  unchanged; measured requests are ~10.5 MB.
- **GFS decode:** one cfgrib open per shortName over the subset file; each
  message's scalar level coordinates move into variable attrs
  (`strip_message_scalars`), then the fields assemble into one flat step
  dataset. A fetched message that fails to decode is a decode error and
  lowers the verdict; an optional message the inventory did not publish is
  not.
- **Provider-declared strata:** `LCDC`/`MCDC`/`HCDC` are retrieved, renamed
  to `cloud_low`/`cloud_middle`/`cloud_high` (percent), declared optional in
  the GFS manifest, and mapped in `FIELD_BY_VARIABLE` so `/point` serves them
  with `source_id: noaa-gfs`. `UNAVAILABLE_POINT_FIELDS` is unchanged:
  wherever no provider stratum was retrieved the fields stay null with
  unavailable provenance. Nothing is derived from METAR layers.
- Precipitation (`APCP`) is no longer fetched at all: its accumulation
  semantics remain unpinned for GFS, and bytes nothing may publish should not
  be requested.
- `noaa-gfs` registry status stays `implementing`; `data_mode` becomes `live`
  only through real retrievals.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `artifact-ingestion`: byte-range subsetting selects only declared
  (parameter, level) messages; heterogeneous-level GRIB subsets decode per
  message, never as one forced merge.
- `point-evidence-sampling`: provider-declared cloud strata are served as
  retrieved provider fields; the prohibition on deriving strata from
  observation layers is unchanged.
