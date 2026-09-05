# Design

One parser handles exact named Open-Meteo model selectors and either the
complete unsuffixed single-model response or the complete matching-suffix
response. Mixed and foreign model shapes fail closed. A separate parser
enforces Bright Sky source 1228, exact WMO station 71801, station name,
forecast observation type and row/source correlation. Both use
the existing manifest validator and deterministic zipped-Zarr artifact seam.
Rolling model-cycle identity is explicitly unknown. Missing, unsupported and
deferred fields are recorded instead of substituted. Every selected field is
required; raw fields without accepted canonical semantics are retained in
provenance with response-derived status. The modules remain outside the adapter
loader until an owner accepts production contracts.
