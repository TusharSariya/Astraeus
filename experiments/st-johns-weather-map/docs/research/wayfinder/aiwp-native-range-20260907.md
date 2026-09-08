# NOAA/CIRA AIWP AURO_v100 native range experiment

Classification: experiment. This unregistered source-local transport does not
admit fields, add API models, run inference, or claim Aurora 1.5. Publisher
identity remains NOAA/CIRA AIWP `AURO_v100_GFS`; `AURO_v100_IFS` is a distinct
initializer identity. These object names do not establish checkpoint digests.

## Actual bounded acquisition

On 2026-09-08 shortly after 00:02:46 UTC, one anonymous HTTP GET requested
`Range: bytes=0-262143` and pinned `If-Match` to the discovery ETag from:

`https://noaa-oar-mlwp-data.s3.amazonaws.com/AURO_v100_GFS/2026/0907/AURO_v100_GFS_2026090712_f000_f240_06.nc`

- Publisher object size: 4,576,425,283 bytes.
- ETag: `"86ac993b0054e16ac5a343726584c89f-546"`.
- Response: exact HTTP 206, Content-Range and Content-Length validated, ETag matched.
- Actual native response body: **262,144 bytes, one request**, no retries,
  redirects, credentials, or full download. Initial proof ceilings were 4 MiB,
  12 requests and 90 seconds; acquisition completed within that window.
- Header SHA-256: `715089a1937b3df468dccb4b9c169b63eee173462646d5d0ad1d7a00337aed75`.
- Object identity SHA-256: `355f8665c90abc0bd96f1b9af072504884bbe5748b612d7706dfd81fc932284c`.

The [official S3 GetObject API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html)
documents anonymous reads for publicly readable objects, single byte ranges and
If-Match preconditions. No AWS account or SDK credential lookup is used here.

Temporary evidence is under `/private/tmp/astraeus-aiwp-prefix-proof/`:
`aurora-gfs-header.bin`, `aurora-gfs-range-receipt.json`,
`aurora-gfs-selected-attributes.txt`, `aurora-gfs-coordinates.txt`, and
`aurora-gfs-horizontal-coordinates.txt`. Captured bytes are not committed.

## Native metadata recovered offline

The captured header has an HDF5 signature. Existing Homebrew `h5dump` decoded
selected dataset attributes and compressed coordinate arrays from an offline
sparse scratch file containing only the captured first 262,144 bytes and the
publisher's logical file size. No additional ranges were fetched. Sparse holes
are **not source data**; this scratch file must never supply forecast values.
A whole-file netCDF4 metadata open failed with `NetCDF: HDF error`; a whole-file
h5dump also failed on global attributes. Only successful selected dataset reads
below constitute metadata evidence, not a complete native decoder proof.

| Native variables | Shape | Native units |
| --- | --- | --- |
| `t2` (2 metre temperature) | 41 × 721 × 1440 | K |
| `msl` | 41 × 721 × 1440 | Pa |
| `u10`, `v10` | 41 × 721 × 1440 | m s-1 |
| `z` | 41 × 13 × 721 × 1440 | m2 s-2 |
| `q` | 41 × 13 × 721 × 1440 | kg kg-1 |
| `t` | 41 × 13 × 721 × 1440 | K |
| `u`, `v` | 41 × 13 × 721 × 1440 | m s-1 |

`time` has 41 native int32 values from 1788782400 through 1789646400
in 21,600-second increments, with units `seconds since 1970-1-1` and
`calendar=standard`. These correspond to 2026-09-07 12:00 through
2026-09-17 12:00 UTC, matching f000..f240 every six hours.
`level` contains 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200,
150, 100, 50 hPa. Latitude contains 721 values from 90 to -90 degrees, decreasing by 0.25;
longitude contains 1,440 values from 0 through 359.75 degrees, increasing by
0.25. Coordinates alone do not establish field coverage or quality. `t2` declares a compressed native
chunk of one complete 721 × 1440 spatial plane, so a point read may need a
whole compressed plane. Sparse-file storage-size reports are not reliable.

Independent review then located the compressed coordinate chunks using
`H5Dget_chunk_info_by_coord` and decoded zlib/shuffle directly from the captured
header bytes, with zero network requests. This verifies coordinate values
without reading sparse holes: latitude offset 11130 / 808 bytes, longitude
8086 / 948 bytes, time 5878 / 112 bytes, level 26389 / 32 bytes. The temporary
`review-coordinate-proof.json` and `review_coordinates.py` in the same evidence
directory retain the method and per-chunk SHA-256 receipts.

No cloud field was seen in these selected native datasets. This limited
inventory is not an assertion about all versions of Aurora. No actual weather
value, Avalon field subset, operational latency, licence admission, cloud
mapping or scientific comparison was proved. The IFS object's payload was not
read.

## Implemented transport seam and limits

`api/weather_api/aiwp_delivery.py` supplies a finite seek/read/readinto interface
for a future native file-object decoder. It accepts only publisher AURO_v100
GFS/IFS keys with matching date directories and a pinned ETag/size. Cache and
receipts bind URL, size and ETag; cache memory is reader-local and cleared on
close. Every uncached block reserves bytes and a request before transmission.
A failed request consumes that reservation. Unbounded reads are refused.

The default client disables retries, redirects and environment configuration,
requests identity encoding, and checks HTTP 206, exact Content-Range,
Content-Length and ETag before consuming a body. Ignored ranges are closed
without body consumption. The synchronous reader checks its deadline before
requests and during streaming, with per-operation HTTP timeouts up to ten
seconds. A strict hard wall-time guarantee for decoder execution still needs
the existing bounded child-process seam. This is not a production decoder or a
shared public receipt/cache model.

Next bounded proof should feed the same revision-bound reader into a locally
available HDF5 file-object decoder in `ingest/isolation.py`'s bounded process,
recover all required metadata and then request one explicitly sized native
chunk. The current environment has netCDF4 and h5dump but no h5py; no new
package dependency was installed. Field admission remains separate.

Verification: `PYTHONPATH=api /private/tmp/astraeus-api-first-delivery/experiments/st-johns-weather-map/api/.venv/bin/python -m pytest api/tests/test_aiwp_delivery.py -q`
from the experiment directory: **25 passed**. Covers revision/request identity,
seek/readinto/cache reuse, zero-copy refusal of ignored ranges, redirect/status,
cookie suppression, encoding and header rejection, truncated/oversized bodies, failure reservation,
finite integer budgets, byte/request/deadline ceilings and closed/unbounded reads.

Verification: `uv run --project tools/specs python tools/specs/specctl.py validate`
from repository root: **0 errors, 0 warnings**.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005. Experimental isolated
transport and non-normative evidence only; no production conformance claim or
normative status change.
