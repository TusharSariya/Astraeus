# ECMWF native timestamp-demand family delivery

## Why

#270 owns live app delivery for IFS, IFS ENS, AIFS Single v2 and AIFS ENS v2.
#81 proved deterministic native acquisition; #82 proved ensemble acquisition.
#83 is ECCC ensemble work, not ECMWF. Neither experiment authorizes live
registration. The accepted artifact-ingestion scenario still requires IFS
always to refuse discovery using an August 2026 listing failure. The current
adapter and tests encode that refusal. A provider listing now understood by
`discover_experiment` cannot bypass an explicit accepted refusal scenario.

## What Changes

Replace the unconditional IFS refusal scenario with a bounded, verified-demand
exception for these four named products. Preserve refusal on unresolved native
identity, fields, grids, members or availability. Start with native 2t, 2d,
msl and instantaneous tcc point evidence; full wind, profile, precipitation,
cloud-strata and ensemble field scope remains in #270. Family/member identity
is mandatory, with no averaging substituted for deterministic fields.

## Capabilities

### Added Capabilities

- `ecmwf-timestamp-demand`: distinct products, native fields, exact selected time,
  finite cache, receipts and ensemble completeness.

### Modified Capabilities

- `artifact-ingestion`: retain unresolved-provider refusal but replace the
  historical unconditional IFS example with verified timestamp-demand access.

## Impact and authority

Proposed requirement change, not an accepted implementation or registration.
Owner must accept this exception and the explicit IFS control mapping extension
before runtime code changes. The existing #82 permission for six oper:fc control
fields was experiment-only; it is not silently promoted here.

No paid endpoint, credentials, self-hosted model, full-run ingestion, permanent
artifact store, V1 promotion, new forecast-centre vote or public deployment.
