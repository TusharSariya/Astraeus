# VIIRS JRR cloud-phase native evidence checkpoint

Issue [#102](https://github.com/TusharSariya/Astraeus/issues/102), under
[#85](https://github.com/TusharSariya/Astraeus/issues/85) and the current
[#70 source-map Notes](https://github.com/TusharSariya/Astraeus/issues/70).
Classification: isolated experiment. No VIIRS cloud source is registered or
served; this is a native-index inspection seam and real bounded value proof,
not a completed timestamp-driven Avalon point integration.

## Concrete product and capture

The [official JPSS registry](https://registry.opendata.aws/noaa-jpss/) identifies
anonymous NOAA-20, NOAA-21 and SNPP buckets. The
[NOAA product notice](https://www.ospo.noaa.gov/data/messages/2023/03/MSG_20230314_2104.html)
identifies JRR-CloudPhase v3r2. At September 8 00:16:11–12 UTC, one bounded
listing (max-keys=2, 256 KiB ceiling, 1,396 actual bytes) and one native granule
GET (24 MiB ceiling, 7,743,597 actual bytes) captured:

`https://noaa-nesdis-n20-pds.s3.amazonaws.com/VIIRS-JRR-CloudPhase/2026/09/07/JRR-CloudPhase_v3r2_j01_s202609072202258_e202609072203503_c202609072257324.nc`

SHA-256: `44c69949f27ca071cf168c5ddb38ae9414159879b5131fe07d3f2b389a3e3c83`.
Receipts, script, raw NetCDF, metadata and native-cell output are outside Git at
`/private/tmp/astraeus-viirs-cloud-proof/`. There were two provider requests,
no redirects, credentials or full-global payload. Listing was deliberately
partial; it does not establish newest scan, cadence or current coverage.

The file identifies NOAA-20/VIIRS, `cdm_data_type=swath`, package v3r2,
**algorithm history v2.2.0**, and night mode. Do not equate packaging and
algorithm versions. File scan interval is 2026-09-07T22:02:25Z–22:03:50Z;
filename stamps additionally retain tenths (22:02:25.8–22:03:50.3). Neither
is a per-pixel time. The file's generic global latitude/longitude extrema
(-90..90/-180..180) are not its swath coverage.

## Actual native values and source-local software

`ingest/experimental/viirs_phase_native.py` accepts one exact NOAA-20 v3r2
object key, body length and SHA-256 plus an explicit native row/column.
The existing bounded-process seam supplies 768 MiB address-space, 24 MiB
per-file/stdin, 1 KiB stdout, 8 KiB stderr and its 60-second timeout. The
worker limits rows to 1,024 and columns to 3,200 and produces at most 64 KiB
JSON. It opens NetCDF with automatic masking/scaling disabled, preserves raw
signed bytes and explicit fill markers, checks product/field units/shapes,
and retains all original variable names and granule attributes. No category,
quality-bit, spatial interpolation or fog interpretation is performed.

The retained bytes replayed through the actual Linux leaf at row 384,
column 1600 of the 768×3200 swath:

| Native field | Actual raw value | Native units |
| --- | --- | --- |
| Latitude / Longitude | 46.822933197021484 / 61.28934860229492 | degrees_north / degrees_east |
| CloudPhase / CloudType | 0 / 0 | 1 / 1 |
| CloudPhaseFlag | `[0]` | 1 |
| CloudTypePacked | `[2,0,0,0,0,0]` | 1 |
| granule_level_quality_flag | 0 | 1 |

These are raw observations, not claims that code 0 is clear or QC-passing.
The file declares CloudPhase range 0..5, CloudType 0..8, phase-quality 0..1,
and six signed int8 diagnostic bytes. Fill is -128 for those arrays.
`quality_state=unknown`, `operational=false` always.

Actual latitude/longitude arrays span 40.006431579589844..50.708133697509766 N
and 41.01498794555664..80.9638900756836 E. **This granule does not cover Avalon.**
It establishes format and native values only. No geographic point request,
nearest-time substitution, cache freshness, API readback or cloud scoring is
claimed. The diagnostic helper cannot acquire provider bytes on its own.

## Exact remaining authority and implementation gaps

No accepted VIIRS/JPSS cloud product mapping was found in `docs/specv1` or the
experiment OpenSpec corpus. Before point delivery, settle source identity,
CloudPhase/CloudType meanings, all six CloudTypePacked diagnostic bytes,
CloudPhaseFlag readability and granule-degradation interaction, fill/null
semantics, swath overlap/bow-tie handling, exact scan applicability and maximum
cell distance. GOES DQF-zero rules do not authorize VIIRS quality decisions.
A geographic discovery strategy must find a relevant pass without downloading
an unbounded daily collection. Preserve actual coordinates and declare that
per-pixel times are unavailable when the product supplies only a scan interval.

This selected pass accounts for phase, type, quality, diagnostics and geolocation
as raw retrieved evidence. Granule summary scalars are inventoried but their
numerical mappings are deferred. CloudBase, Height, Mask, CoverLayers, DCOMP,
NCOMP; NOAA-21/SNPP variants; and JPSS blended TPW/rain remain explicitly
unimplemented in this checkpoint. No family or issue completion is claimed.

Verification: eight focused offline Linux tests passed, including the actual
bounded leaf, signed flags/fills, unknown QC, field/product refusal and
pre-decode digest/index limits. `specctl validate`: 0 errors, 0 warnings;
`git diff --check`: passed. Actual retained-granule leaf replay used zero
additional provider requests. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-005, GOV-SPEC-006. No normative status or source admission changed.
