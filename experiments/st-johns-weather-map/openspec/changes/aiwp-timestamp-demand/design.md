# Design and measured access evidence

## Reuse and missing seam

`ingest/http.py` owns resource accounting, pacing, bounded ranges and final-byte receipts (`get_range_with_headers_completed`). Existing point services and query-cache lifecycle supply integration boundaries. xarray/netCDF4 are existing dependencies; h5py/fsspec are not declared runtime dependencies. The isolated metadata probe used h5py's standard file-like interface. A source-local seekable reader backed by the existing capped client is the proposed missing seam, subject to accepted dependency/decoder implementation review. Never let a library independently fetch a whole URL.

## Measured identities and geometry

All four namespace identities are `GRAP_v100_GFS`, `GRAP_v100_IFS`, `PANG_v100_GFS`, `PANG_v100_IFS`. Native `model_name` is respectively graphcast/panguweather; `initialization_model` is GFS/IFS; native `version=3_2025-02-20` is retained separately from namespace v100 and is not a checkpoint hash. Model naming follows [provider README](https://noaa-oar-mlwp-data.s3.amazonaws.com/README.txt): GraphCast Operational, not an unspecified original GraphCast checkpoint.

The four sampled objects have path `{identity}/2026/0906/{identity}_2026090612_f000_f240_06.nc` under `https://noaa-oar-mlwp-data.s3.amazonaws.com/`. Native initialization is September 6 2026 12Z, 41 valid times through September 16 12Z, six-hour spacing. Grid: float32 latitude 90→−90 (721), longitude0→359.75 (1440), quarter-degree rectilinear global coordinates including Avalon. Surface datasets t2 K and msl Pa are float32 gzip/shuffle chunks `(1,721,1440)`; profile chunks are `(1,1,721,1440)`. One decoded surface plane is 4,152,960 bytes.

| Identity | Object bytes | +6h t2 offset / compressed bytes | +6h msl offset / compressed bytes |
|---|---:|---|---|
| GRAP_v100_GFS | 5739811492 | 619292494 / 1480072 | 620772566 / 1450381 |
| GRAP_v100_IFS | 3909837668 | 1345724746 / 841451 | 1346566197 / 763150 |
| PANG_v100_GFS | 4611286100 | 617404224 / 1476988 | 611663309 / 1435537 |
| PANG_v100_IFS | 2800258215 | 1091316479 / 813153 | 1087379314 / 732156 |

These offsets belong only to the sampled ETag-bound objects; runtime must parse each selected object's own index. They are not fixtures or universal constants. Two-field compressed demand was 1.55–2.94MB in this sample; no meteorological chunk body was fetched. Total bounded listing/header/schema/coordinate/chunk-index proof: 415,149 received bytes, 326 requests across all phases. Raw evidence remains outside Git under `/private/tmp/aiwp-*`; issue checkpoints persist exact identity and results. No full-file, weight or inference acquisition occurred.

## Proposed resource and selection policy

The 8MiB received-byte,128-request and600-second freshness ceilings are owner choices, not measurements or provider guarantees. They include discovery, metadata, failed attempts and payload; decoded planes and HTTP buffers require separate preflight memory reservations. A full plane per field is unavoidable with the measured compression layout, but a full run is forbidden. Use one query-wide budget, not a new allowance per retry. Resolve each requested identity independently; do not multiply one request's allowance implicitly across four models.

## Rights, failure and remaining scope

[NOAA/CIRA output terms](https://registry.opendata.aws/aiwp/) state unrestricted data use. They are distinct from Pangu's noncommercial self-host weights and from Google's code/weight terms. Attribute producer, initializer and model. Native structural checks do not assert provider quality-control approval or consensus eligibility. Existing scientific/QC admission remains unchanged.

Missing data, changed objects, exceeded budgets and stale cache return explicit unavailable. No fallback model, permanent archive, consensus promotion or self-hosting. Wind, pressure-level profiles and GraphCast w/apcp need their own native interval/mapping scenarios before admission; GenCast and FuXi remain separate open objectives.
