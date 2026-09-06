# Design

OSTIA discovery reads consolidated metadata and the latest time coordinate,
then downloads only coordinate arrays and the three native chunks intersecting
45.0 to 50.5 N, 58.0 to 46.0 W from the time-chunked ARCO Zarr. It keeps
`analysed_sst`, `analysis_error` and `mask`; Kelvin SST is normalized to degC
and land cells are null according to the native water bit.

OISST discovery reads the current NCEI monthly listing and accepts either the
plain final filename or the provider's `_preliminary` filename. It downloads
one bounded daily NetCDF file, crops the native 0.25 degree grid, and keeps
`sst` and `err`. `anom` and `ice` are explicitly outside this ticket.

Both outputs remain producer-specific Level-4 analyses. Their provenance names
product, analysis identity, source URLs, retrieval time, native resolution,
units, quality and artifact revision. Neither adapter computes or implies fog.

Per operation ceilings are 2 MiB metadata, 16 MiB per OSTIA chunk and 32 MiB
per OISST file, below the ticket's 4 GiB scratch bound and the existing 64 GiB
hot-cache policy.
