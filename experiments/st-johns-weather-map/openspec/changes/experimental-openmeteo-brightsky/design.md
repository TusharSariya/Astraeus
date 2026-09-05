# Design

One parser handles exact named Open-Meteo model selectors and either the
complete unsuffixed single-model response or the complete matching-suffix
response. Mixed shapes and every non-selected suffix fail closed, including
suffixes outside the three model contracts. A separate parser
enforces Bright Sky source 1228, exact WMO station 71801, station name,
forecast observation type and row/source correlation. Both use
the existing manifest validator and deterministic zipped-Zarr artifact seam.
Rolling model-cycle identity is explicitly unknown. Missing, unsupported and
deferred fields are recorded instead of substituted. Every selected field is
required; raw fields without accepted canonical semantics are retained in
provenance with response-derived status. An all-null required field is a
completeness failure and quality is suspect while QC may remain passed; the
existing publish seam still requires both `complete` and `qc_passed`. The
modules remain outside the adapter loader until an owner accepts production
contracts.
