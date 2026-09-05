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

The experimental pressure-profile contract is source-specific. JMA declares
16 provider UI surfaces, ARPEGE 29 and UKMO 33; all eight documented upstream
field families are requested at every declared surface. Temperature and wind
speed/direction are stored as canonical profile arrays. RH, dew point,
pressure-level cloud, geometric vertical speed and geopotential metres are
retained raw with their response masks because phase, intermediary derivation,
or catalogue-unit semantics prevent a truthful canonical mapping. No vertical
or temporal interpolation is performed. A documented field-level array that
is all null is recorded as missing with its returned unit; the other profile
fields and levels remain usable. Exact 2026-09-05 availability and the ARPEGE
all-null vertical-velocity exception are recorded in the non-normative research
note and retained evidence bundle.
