# Design

One parser handles exact named Open-Meteo model selectors and model-suffixed
arrays. A separate parser enforces exact Bright Sky WMO station 71801. Both use
the existing manifest validator and deterministic zipped-Zarr artifact seam.
Rolling model-cycle identity is explicitly unknown. Missing, unsupported and
deferred fields are recorded instead of substituted. The modules remain outside
the adapter loader until an owner accepts production contracts.
