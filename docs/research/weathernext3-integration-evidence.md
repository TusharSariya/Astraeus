# WeatherNext 3 experimental integration evidence

Recorded 2026-09-05 for [Implement the verified WeatherNext forecast source](https://github.com/TusharSariya/Astraeus/issues/77).
This evidence is non-normative. The source contract remains draft and the
adapter remains absent from production registration and scheduling.

## Exact source and field scope

The implementation accepts only Google DeepMind WeatherNext 3.0.0 statistics
from `weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr`.
It preserves the Cartesian inventory of 21 base variables and six statistics
(`mean`, `p10`, `p25`, `p50`, `p75`, `p90`), 126 fields total. The selected
cloud candidate is four native cloud-cover variables by six statistics, 24
fields. All 126 are retrieved adapter capability; the other 102 have no
accepted consumer mapping and remain deferred for production exposure. Fog, visibility,
ceiling, cloud base and cloud top are unsupported. Raw members and pressure
levels belong to the excluded requester-paid full-ensemble product.

## Live proofs

`evidence/weathernext-20260801-all-fields-lead6.json` describes the exact
lead-6 chunk for every field. All 126 exist with positive size, generation and
ETag. The 127 metadata operations completed in 81.617 seconds and downloaded
zero forecast bytes. A value read would require 3,150,715,420 compressed bytes.
The owner then authorized the known operation with a 30-minute deadline and
4 GiB cap. `evidence/weathernext-20260801-all-fields-lead6-values.json`
retrieved all 126 lead-6 point values sequentially: 3,150,943,978 bytes, 140
operations, 103,708,800 peak decoded bytes, 122,420 output bytes and 432
seconds. It records 120 numeric values and six explicit unavailable masks, all
six being sea-surface-temperature statistics at the selected land cell. The
114 0.1-degree and 12 station-head 0.05-degree arrays retain distinct grid and
coordinate identity. This is all-field point evidence, not full spatial
coverage. Its SHA-256 is
`f6d853bc65e4deae11ed2ff4137b6ea3bf521edd6a238a6761ed8cdc0ae2940d`.
Roughly 50,067,508 KiB was physically free before the operation. The gate held
a 4 GiB team reservation plus the next compressed chunk, decoded allowance and
output allowance. Every raw chunk was deleted immediately after point
extraction. Only the 122,420-byte evidence JSON is retained in the repository;
the two normalized Zarr artifacts are created in temporary test directories
and are not installed in a shared store.

`evidence/weathernext-20260801-avalon-box.json` is the value proof for the six
previously sampled cloud statistics at leads 6, 12 and 24. It contains every
native cell centre within `[-54.0, 46.5, -52.5, 48.0]`: 16 latitudes by 16
longitudes, 256 cells per lead. The read received 375,407,160 bytes in 78
operations, decoded at most 25,934,400 bytes at once, emitted 220,942 bytes,
and completed in 100 seconds. Source object identity checks all passed. Its
SHA-256 is `d35a5bbb3b92deab515732ae88f92934e605a3697d4fe1aee90374c1c81e4d4c`.

The all-field metadata artifact SHA-256 is
`17fff8135223e867693acb70c0de4635d22587a6d616d08184d501ee14990e46`.

## Adapter, artifact, API and failures

The isolated adapter validates exact product/surface/member/statistic/time and
the complete disposition inventory, preserves nulls as masks, writes a
deterministic immutable Zarr artifacts split by native grid, and carries all
126 dispositions in provenance. Astraeus' real HTTP point endpoint reads the resulting artifact in
a local harness and returns the numeric `total_cloud_cover_mean` value using a
test-local field catalogue. No production catalogue, source registry,
scheduler or deployment configuration is changed.

The all-field sample proves one point at one representative lead. The separate
Avalon artifact proves spatial extraction only for six cloud statistics at
three leads. Neither is described as a 126-field spatial coverage proof or as
an operational cadence/completeness result.

Tests refuse WN2 identity, fabricated member identity, incomplete inventory,
statistic mismatch, invalid cloud fractions, mask-count mismatch, blocked
acquisition and requester-paid bucket state. Invalid inputs create no partial
artifact. Existing transport tests prove request reservation, byte limits,
redacted failures and empty billing/project/auth override variables.
