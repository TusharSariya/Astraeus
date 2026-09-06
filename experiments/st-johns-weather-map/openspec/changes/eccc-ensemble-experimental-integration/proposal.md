# ECCC ensemble experimental integration

## Classification

Experiment, Spec-Impact: none. The source-specific product/access/field
contracts remain proposed. This change cannot register GEPS, enable REPS or
GEPS scheduling, promote a registry state, or claim V1 conformance.

## Outcome

Complete bounded live evidence for issue 83: decode selected REPS fields for
all 21 published member identifiers through GeoMet WCS, and retain selected
GEPS producer reductions under their issued mean, standard deviation,
percentile and threshold-probability identities. Preserve missing member,
level and reduction failures and keep the REPS control identifier unresolved.

## Authority

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005,
GOV-SPEC-006.


## Evidence

No raw provider payload is stored in Git (owner decision of 2026-09-05, issue
70). The completion evidence is the receipt below plus the API readback, and
the capture is reproducible with `scripts/eccc_ensemble_live_evidence.py`. A
hand-trimmed receipt — endpoint, request parameters, decoded byte counts,
checksums, capture times and artifact revision — is committed at
`api/tests/fixtures/eccc_ensemble/eccc-ensemble-2026-09-05.receipt.json` and is
asserted by `api/tests/test_adapter_ensemble.py`.

### Live capture receipt, 2026-09-05T18:11:57.687500+00:00

Endpoint `https://geo.weather.gc.ca/geomet/`; every coverage request
`SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&FORMAT=image/tiff` with
`SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326`,
`SUBSET=long(-58.0,-46.0)&SUBSET=lat(45.0,50.5)`,
`SCALESIZE=long(133),lat(61)`, an advertised `TIME` and an advertised
`DIM_REFERENCE_TIME`. Artifact revision for every row is `requested_unverified`
run identity, non-operational, `pixel_is_area_cell_centres` geometry,
`server_resampled_method_unknown`. Bytes are decoded response bodies, not
compressed wire bytes, under a 4,194,304-byte hard ceiling per response.

| Response | Decoded bytes | sha256 | Retrieved at |
| --- | --- | --- | --- |
| `GetCapabilities` | 1090094 | `73c26c280d0bcb31…` | 2026-09-05T18:11:34.578972+00:00 |
| `REPS.MEM.ETA_NT.01` | 32900 | `a54d288bdfb7af22…` | 2026-09-05T18:11:34.682251+00:00 |
| `REPS.MEM.ETA_NT.21` | 32900 | `a61afcfd7ebf0c1b…` | 2026-09-05T18:11:44.785128+00:00 |
| `REPS.MEM.ETA_WSPD.01` | 32900 | `14cd4ca1de6807b0…` | 2026-09-05T18:11:45.240438+00:00 |
| `REPS.MEM.ETA_WSPD.21` | 32900 | `76c109ea243d7a07…` | 2026-09-05T18:11:55.258022+00:00 |
| `GEPS.DIAG.3_TT.ERMEAN` | 1474 | `c1a20d3cf3a8fac4…` | 2026-09-05T18:11:55.679246+00:00 |
| `GEPS.DIAG.3_TT.ERSSTD` | 1474 | `2cf45aa771cc4223…` | 2026-09-05T18:11:56.194052+00:00 |
| `GEPS.DIAG.3_TT.ERC50` | 1474 | `6e6f67cad0551dd3…` | 2026-09-05T18:11:56.710282+00:00 |
| `GEPS.DIAG.3_NT.ERC50` | 1474 | `8988b868bcacfbf5…` | 2026-09-05T18:11:57.192111+00:00 |
| `GEPS.DIAG.12_GUST-15MS.PROB` | 1474 | `24dd1c7372bc3581…` | 2026-09-05T18:11:57.687177+00:00 |

Full-run totals: 48 responses, 2,479,264 decoded bytes — one 1,090,094-byte
capability inventory, 42 REPS coverages totalling 1,381,800 bytes, and 5 GEPS
reductions totalling 7,370 bytes — captured between 18:11:34.578972 and
18:11:57.687177 UTC with no field failures.

| Rebuilt artifact | Bytes | sha256 | Run time | Valid time | Shape |
| --- | --- | --- | --- | --- | --- |
| `eccc_reps_members.zarr.zip` | 504100 | `b9110ef16bd5fad5…` | 2026-09-05T12:00:00+00:00 | 2026-09-05T18:00:00+00:00 | member 21 × valid_time 1 × lat 61 × lon 133 |
| `eccc_geps_reductions.zarr.zip` | 13636 | `c4ddefac471549d2…` | 2026-09-05T00:00:00+00:00 | 2026-09-05T12:00:00+00:00 | valid_time 1 × lat 11 × lon 24 |

Neither rebuilt artifact is retained in Git; their checksums are. The core
reader and the test-only HTTP readback passed at 2026-09-05T18:20:53.756390+00:00
with `operational=false`.

The bounded selection is not whole-family completion: 42 of 1,239 advertised
REPS coverages (two catalogued surface fields for 21 members, the other five
surface fields and 1,092 further coverages deferred to issue 147) and 5 of 532
advertised GEPS reductions (527 deferred to issue 148). GEPS advertises zero
`GEPS.MEM.*` coverages, so no members were created and no statistics were
computed here.
