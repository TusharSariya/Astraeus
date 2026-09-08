# Published GraphCast bounded native point proof

Classification: isolated experiment; #267/#96. Source-specific OpenSpec remains
draft in `openspec/changes/graphcast-native-point-experiment/`. No source/API
registration, latest-run discovery, finite query cache, scheduler, inferred
clouds, operational promotion or GenCast substitution is included.

## Exact source and actual reading

NOAA/CIRA AIWP GraphCast Operational, namespace `GRAP_v100_GFS`, native publisher
version `3_2025-02-20`, GFS initializer. Namespace and native version do not prove
a model-weight hash. `GRAP_v100_IFS` remains a separate initializer identity.

The exact object is
`https://noaa-oar-mlwp-data.s3.amazonaws.com/GRAP_v100_GFS/2026/0906/GRAP_v100_GFS_2026090612_f000_f240_06.nc`,
size 5,739,811,492 bytes, ETag `"e2e291aac15788fa81f5b56e68e11d15-685"`.
The retained September 7 discovery identity was reused; no listing was repeated.

An anonymous live proof on 2026-09-08 from 00:27:32.568047 to
00:27:38.231041 UTC used **48 exact HTTP 206 requests, 3,145,728 received bytes**.
All requests pinned If-Match and verified ETag, Content-Range and Content-Length.
No entire file, weights or inference inputs were downloaded.

Requested 47.5 N, -52.7 E and native valid time 2026-09-06 18:00 UTC; selected
native cell 47.5 N, -52.75 E on the verified 721×1440 global 0.25-degree grid.
Initialization was 2026-09-06 12:00 UTC, native lead +6 hours.

| Native field | Native value | Unit |
| --- | ---: | --- |
| `t2` | 287.88671875 | K |
| `msl` | 100213.4140625 | Pa |

Object identity SHA-256:
`a12bf0a68c75d792f90c9b5550b1760d3b1cc673f739d2c96457fc8ad07cf883`.
Full range/hash receipts and temporary live launcher remain outside Git at
`/private/tmp/graphcast-linux-proof/graphcast-point-receipt.json` and `live.py`.
The completed-at timestamp brackets the whole decode; it is not labelled a
per-range final-byte receipt. Native data quality remains unknown.

## Reused mechanics and bounded experiment

`graphcast_native.py` subclasses the immutable object identity with a strict
GRAP namespace check and reuses unchanged `aiwp_delivery.RangeReader`. It opens
h5py over this capped seekable stream and closes HDF5 first. h5py supports
[file-like objects](https://docs.h5py.org/en/stable/high/file.html#python-file-like-objects),
so no custom NetCDF parser or uncapped remote xarray opening was needed.

Limits: 8 MiB received/attempt reservation, 128 requests, 90-second cooperative
deadline, maximum two float32 planes of 4,152,960 decoded bytes each. Native
identity, all 41 timestamps, exact axes, dimension scales, units, chunk layout,
packing and link restrictions are checked. Native finite sentinels and nonfinite
cells become individual nulls; unallocated chunks fail. No time/space
interpolation, initializer fallback or derived scientific conversion occurs.

This is an explicit synchronous experiment. A production adapter still needs
owner-accepted source and freshness contracts, bounded-process isolation,
per-range final-byte receipts, discovery, finite query-cache/coalescing/expiry,
API/UI mapping and operational acceptance. Current normal API environments do
not include h5py; only the isolated proof image installs pinned `h5py==3.14.0`.

## Verification

Linux image `astraeus-graphcast-proof:h5py314`, image manifest-list digest
`sha256:0acefd276cf55ad64e55affdc643a65379cec1feec0991459de4125caab9c88e`,
is prepared from `astraeus-lightning-proof:c88ff83` by installing h5py into
`/app/api/.venv`. Its API dependencies otherwise remain unchanged.

The mounted working-tree tests run with `--network none --memory 4g`:

```text
python -m pytest api/tests/test_graphcast_native.py api/tests/test_aiwp_delivery.py -o addopts= -q -p no:cacheprovider --tb=short
```

Synthetic real HDF5 bytes exercise the default reader: native values/coordinates,
GFS versus IFS, drift, masks, unallocated/multiplane chunks, ignored ranges and
changed ETags. Shared reader tests cover caps and object-bound cache reuse.
Result: **46 passed**. `openspec validate graphcast-native-point-experiment --strict`
passed; `specctl validate` reported 0 errors and 0 warnings.
These fixture tests make zero provider requests. Live acquisition above is
separate. The first local/image preparations failed because h5py was absent
from the active interpreter; no provider bytes were fetched by those attempts.

## Published output terms and distinct GenCast prerequisite

[NOAA/CIRA's source documentation](https://noaa-oar-mlwp-data.s3.amazonaws.com/README.txt)
names GraphCast Operational, native fields, GFS/IFS variants and near-real-time
publishing. [The official public-data registry](https://registry.opendata.aws/aiwp/)
states output use is unrestricted, account-free access is available, and data
can be missing. This does not guarantee a complete or newest run.

[Google's deprecation notice](https://developers.google.com/weathernext/guides/deprecation),
updated September 2, states Graph/Gen Earth Engine and BigQuery datasets were
deprecated effective July 29, 2026. This proof establishes no continuing GenCast
output endpoint or rights for one. GenCast needs a concrete published endpoint
with access/terms or a separately authorized self-hosted inference proposal.
WeatherNext 2/3, NOAA AI-GFS and GraphCast are distinct identities.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

Temporary live receipt SHA-256: `a3956105c74dbc158d88e5ab6de17c9d94dc4fd549f59547f2d933b38ac1c177`.
