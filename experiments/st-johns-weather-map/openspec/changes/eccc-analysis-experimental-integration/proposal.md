# Change: prove selected ECCC analysis access paths

## Why

Issue 80 groups air-quality forecasts and analyses, precipitation analyses,
land products, hotspots, nowcasting, and public hazards. They do not share one
time or payload model. Treating the group like an RDPS forecast would invent
lead times and quality semantics.

## What changes

- Declare small selected-field contracts for RAQDPS, RDAQA, HRDPA, RDPA,
  HREPA, HRDLPS, and CaLDAS over their exact GeoMet WCS coverage identities.
- Reuse the corrected numeric WCS transport while assigning each product its
  own grid identity, cadence, time meaning, and unknown quality state.
- Retain upstream TIFF bytes beside deterministic Zarr output and record both
  digests plus finite/null counts.
- Define the owner decision needed for HRDPA and HREPA selected-timestamp
  demand reads: exact advertised analysis times, finite request-local caches,
  typed transport receipts, and no stale or neighbouring-time fallback.
- Record hotspots, integrated nowcasting, CAP alerts, thunderstorm outlooks,
  hurricane products, and retired standalone FireWork as unavailable through
  this adapter until separate typed contracts are selected.

No registry or scheduler entry is enabled. Every contract and artifact remains
`operational: false`.

## Review status and bounded work

This is a contract/transport scaffold, not completed source acquisition.
Independent review found only two JSON retrieval summaries without retained
live artifacts or product-specific HTTP proof. The family remains open and
blocked by these acquisition tickets:

- [Native RAQDPS and RDAQA fields](https://github.com/TusharSariya/Astraeus/issues/133).
- [HRDPA and HREPA precipitation analyses](https://github.com/TusharSariya/Astraeus/issues/134).
- [HRDLPS and CaLDAS land analyses](https://github.com/TusharSariya/Astraeus/issues/135).
- [Native RDPA geometry and units](https://github.com/TusharSariya/Astraeus/issues/136).
- [Public alerts, outlooks and nowcasting](https://github.com/TusharSariya/Astraeus/issues/137).

CWFIS/FIRMS and wildfire hotspots remain owned by the existing fire-source
ticket, not duplicated by the public-hazard child. Standalone FireWork stays
superseded. An unsupported path in this scaffold is not proof that the
producer has no public data.

For [issue #134](https://github.com/TusharSariya/Astraeus/issues/134), the
reviewable initial demand scope is deliberately exact:

- HRDPA may expose only `HRDPA_2.5km_Precip-Accum6h` as the provider's final
  six-hour precipitation accumulation ending at the selected advertised time.
  It has no forecast lead or invented model run and is never divided into a
  rate.
- HREPA may initially expose only the provider-published `PCT25` and `PCT75`
  six-hour analysis coverages. They remain two retrieved percentile fields,
  never locally recomputed percentiles, member values, probabilities,
  uncertainty, or confidence.
- The wider HREPA source remains in scope. Public precipitation-analysis,
  uncertainty, confidence-index, probability, and 24-perturbed-member-plus-
  control claims remain unavailable until their exact coverage ids, units,
  statistic definitions, time identity, masks, and quality semantics have
  provider evidence and owner acceptance.

Acceptance of this proposal would authorize a bounded demand implementation;
it does not activate one. Until then, the current experimental WCS reader and
its source declarations remain non-operational and absent from the public point
response.

Spec-Impact: experiment. Accepted governance authority: GOV-SPEC-001,
GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

## Live capture receipt

Per the owner decision of 2026-09-05 (issue #70) the capture is recorded as a
receipt, not a payload. One anonymous WCS 2.0.1 session against
`https://geo.weather.gc.ca/geomet/` at `2026-09-05T15:41:00Z`:
`GetCapabilities` returned HTTP 200, 1,090,094 bytes, 5,589 coverages. Two
`GetCoverage` requests in `EPSG:4326` over the Avalon box produced the raw
GeoTIFFs and zipped-Zarr artifacts below; nothing is registered or scheduled
and the classification is "isolated experiment; source contracts pending owner
acceptance".

| Source | Coverage | Valid time | Run time | Units | Shape | Raw bytes | Raw SHA-256 | Artifact bytes | Artifact SHA-256 | Finite / null cells |
|---|---|---|---|---|---|---:|---|---:|---|---|
| `eccc-raqdps` | `RAQDPS.SFC_PM2.5` | 2026-09-05T15:00Z | 2026-09-05T00:00Z | kg/m³ | 23 x 45 | 4,558 | `77c3e241bde23e5089d5dfc56bd369e9ded74d978779839a79e3119c73c76601` | 6,528 | `b434c9ee2b29b0789fdd81461674ffbefc91cb0fa2aa4edf82d8fe44defe3ae0` | 1,035 / 0 |
| `eccc-hrdpa` | `HRDPA_2.5km_Precip-Accum6h` | 2026-09-05T06:00Z | none published | mm | 89 x 178 | 63,840 | `055c80a29a8199d9f3b43f5ac47c2365ad27e418467a786aec1de6e0e7f34a8b` | 9,377 | `0c62ff484989773e4cf222211bff6bdb312f3b739a1afc34adf8ae68bdbbfec7` | 15,842 / 0 |

Quality is `unknown` for both; `operational: false`.
