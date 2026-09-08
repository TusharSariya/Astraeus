# Proposed typed ACTPF provenance

Status: draft. The following is a reviewable wire-shape proposal, not an
existing schema or an implementation instruction until approved.

Add optional `Provenance.native_satellite: NativeSatelliteIdentity | null`.
Its initial supported product is narrowly ACTPF; do not use an arbitrary
metadata dictionary or a fabricated NativeReportIdentity.

| Member | Proposed type and meaning |
| --- | --- |
| `product_id` | Literal `ABI-L2-ACTPF`. |
| `granule_id` | Nonempty producer dataset filename, maximum 256 characters, matching the acquired object. |
| `scan_start`, `scan_end` | Offset-aware native timestamps; end cannot precede start. Neither claims an individual pixel observation time. |
| `phase_code` | Integer 0, 1, 2, 3, 4, 5 or null, exactly as retained at the sampled cell. A QC-masked cell can have null; never reconstruct a masked code. |
| `dqf_code` | Nonnegative native integer or null; preserve unrecognized nonzero values without claiming they pass QC. Native variable is `DQF`. |
| `phase_categories` | At most six ordered `{code: integer, meaning: string}` pairs read directly from this artifact's CF `flag_values`/`flag_meanings`. No duplicate codes, blank meanings or invented local table. |
| `projection` | Typed `NativeGeostationaryProjection`, with the source parameters below. |

`NativeGeostationaryProjection` retains finite native numeric attributes
`perspective_point_height`, `longitude_of_projection_origin`,
`latitude_of_projection_origin`, `semi_major_axis`, `semi_minor_axis`, and
optional `inverse_flattening` only when present. It also carries literal
`grid_mapping_name="geostationary"` and the file's `sweep_angle_axis` (`x` or
`y`). No absent projection parameter is silently supplied. Optional `long_name`
may retain the provider label. Required missing or inconsistent projection
metadata makes the complete ACTPF shared reading unavailable.

Existing Provenance members retain actual sampled latitude/longitude, native
cell distance and `curvilinear_nearest_cell`, native variable `Phase`,
`original_units="1"`, `normalized_units="code"`, actual retrieval time,
artifact digest and source identity. `native_crs` describes the geostationary
source without assigning an invented EPSG code. `valid_time` equals the native
scan start; `run_time` remains null. `SourceAcquisition` separately retains the
bounded transport/cache receipt. These structures do not establish coverage,
freshness, local QC or admission merely by being present.

The public `EvidenceField.value` is the matching producer meaning string when
all existing spatial/readability requirements hold and the retained phase code
has a unique matching category. DQF zero is native readability, not proof of
local scientific QC: quality remains `unknown` with an explicit reason. An
unreadable DQF, missing/masked phase, absent mapping or exceeded cell-distance
ceiling yields a null field with its native context and reason flags. Native
category metadata that is malformed or inconsistent is refused rather than
converted with a local lookup. Never publish the code as a fallback value.

The reader must acquire/return only a granule whose native start equals the
requested instant, comparing timestamps as UTC instants. The existing
source-local helper's one-hour temporal tolerance cannot be reused on this
shared path. Discovery, caching and refresh must preserve this exact selection;
no cached/latest neighboring scan may answer it. An exact scan that cannot be
identified or retrieved is unavailable. Existing byte/request limits, fixed
expiry and identical-miss coalescing remain; expiry is not scan freshness.

Registration after approval: root-owned `source_delivery` adds the point-only
ACTPF descriptor and source-local reader, with `GOES ACTPF` as its proposed
point selector; app dispatch delegates to that reader. Unsupported explicit
product/field/level/run/member selections are refused before acquisition.
This proposal does not add an image endpoint or broaden any Series inventory.
