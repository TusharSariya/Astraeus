# Source contract authority matrix

Generated from the exhaustive free-source roster on September 5, 2026. This is a
traceability and implementation-gate artifact, not normative authority. The complete
288-row result is in `source-contract-authority-matrix.json`.

## Result

| Authority class | Rows | What may happen now |
| --- | ---: | --- |
| `access-or-licence-gate` | 33 | Resolve access, terms, geography and zero-charge gates, then obtain the same source contract acceptance. |
| `experiment-verification-candidate` | 14 | Run isolated bounded fixture/live/artifact/API/failure verification; production conformance still waits for accepted behavior authority. |
| `owner-source-contract-required` | 165 | Prepare the exact product/access/field contract while isolated adapter work proceeds; owner acceptance gates production registration and scheduling. |
| `recorded-disposition` | 76 | Preserve the rejection, deferral, unavailability or non-source disposition; no fabricated live proof is required. |

Accepted authority is governance only: GOV-SPEC-001/002/004/005/006. EVD-PROV-001,
EVD-MASK-001 and EVD-API-001 are proposed target shape, not authority. The current
experiment contracts describe shared adapter,
manifest, bounded transport, publication, scheduler and truth-boundary behavior. They
do not choose a new producer product, access path or field mapping. The draft
`shared-source-integration-contract` change makes that per-source decision record and
five-part proof gate explicit for owner review.

## Experiment verification candidates

No production integration is a conforming candidate because no behavior-bearing V1
source contract is accepted. These rows already have a registered schedulable adapter,
so bounded isolated experiment verification can start while the owner reviews the contract:

| Source | Product | Target task |
| --- | --- | --- |
| `eccc-hrdps` | HRDPS raw | [Implement deterministic GeoMet WCS fields and WEonG diagnostics](https://github.com/TusharSariya/Astraeus/issues/79) |
| `eccc-rdps` | RDPS | [Implement deterministic GeoMet WCS fields and WEonG diagnostics](https://github.com/TusharSariya/Astraeus/issues/79) |
| `eccc-gdps` | GDPS | [Implement deterministic GeoMet WCS fields and WEonG diagnostics](https://github.com/TusharSariya/Astraeus/issues/79) |
| `eccc-swob` | SWOB-ML surface and marine observations | [Verify complete source coverage and hand off integrated evidence](https://github.com/TusharSariya/Astraeus/issues/97) |
| `eccc-radar` | Weather radar composite and extrapolation | [Verify complete source coverage and hand off integrated evidence](https://github.com/TusharSariya/Astraeus/issues/97) |
| `eccc-lightning` | Lightning flash density | [Verify complete source coverage and hand off integrated evidence](https://github.com/TusharSariya/Astraeus/issues/97) |
| `eccc-cap-alerts` | Common Alerting Protocol weather alerts | [Verify complete source coverage and hand off integrated evidence](https://github.com/TusharSariya/Astraeus/issues/97) |
| `eccc-aqhi` | Air Quality Health Index observations and forecasts | [Implement free aerosol, radiation and fire observations](https://github.com/TusharSariya/Astraeus/issues/86) |
| `noaa-gfs` | Global Forecast System | [Verify complete source coverage and hand off integrated evidence](https://github.com/TusharSariya/Astraeus/issues/97) |
| `noaa-goes-east` | GOES-19 ABI L2+ Enterprise Cloud Mask, five-layer cloud fraction and cloud-top products | [Implement the remaining free cloud and atmospheric satellite products](https://github.com/TusharSariya/Astraeus/issues/85) |
| `noaa-swpc-kp` | Planetary K index (observed series and 3-day forecast) | [Implement missing free space-weather measurements and forecasts](https://github.com/TusharSariya/Astraeus/issues/89) |
| `noaa-swpc-ovation` | OVATION aurora probability nowcast grid | [Implement missing free space-weather measurements and forecasts](https://github.com/TusharSariya/Astraeus/issues/89) |
| `awc-metar-speci` | METAR/SPECI | [Implement additional free local and aviation observations](https://github.com/TusharSariya/Astraeus/issues/88) |
| `awc-taf` | TAF | [Implement additional free local and aviation observations](https://github.com/TusharSariya/Astraeus/issues/88) |

A live success alone does not authorize `operational`. Each candidate still needs a
representative fixture, bounded upstream retrieval, immutable artifact validation,
Astraeus API readback, and absence/failure/provenance evidence for every selected field.

## Owner decision requested

Accept, revise or reject the draft `shared-source-integration-contract` change. If
accepted through the GOV-SPEC-002 status workflow, each missing integration can supply
one source contract instance with exact product/access identity, fields, mappings,
units, masks, runs, members, leads, cadence, limits, charge surfaces, API shape,
failure semantics and rollback. No blanket acceptance of all roster rows is requested.

Spec-Impact: none; generated traceability evidence only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
