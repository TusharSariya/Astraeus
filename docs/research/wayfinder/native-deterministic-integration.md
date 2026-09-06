# Native deterministic acquisition evidence

Captured 2026-09-05 for issue 81. This is non-normative experimental evidence.
All candidates are unregistered, unscheduled, and `operational: false`.

| Candidate | Exact public product path | Selected lead-0 inventory | Result |
|---|---|---|---|
| IFS | ECMWF Open Data `ifs/0p25/oper/*-0h-oper-fc.grib2` plus `.index` | 2t, 2d, 10u, 10v, msl, tp (raw initialization), tcwv, tcc; r/q/t/u/v/w/gh on all 14 published pressure levels | Full box, 1,127 retained 0.25-degree cells |
| AIFS Single | ECMWF Open Data `aifs-single/0p25/oper/*-0h-oper-fc.grib2` plus `.index` | 2t, 2d, 10u, 10v, msl, tp (raw initialization), tcc/lcc/mcc/hcc; q/t/u/v/w/gh on published levels | Full box, 1,127 cells; no r or tcwv and no q at 10 hPa |
| ICON Global | DWD `icon/grib/{cycle}/{field}/icon_global_icosahedral_*` plus run-matched CLAT/CLON | Ten surface objects; r/t/u/v at 850/700/500/300 hPa | Full box, 3,107 native R03B07 cells; qv/w model-coordinate gap explicit |
| RAP parent | NOAA `noaa-rap-pds/rap.YYYYMMDD/rap.tHHz.awp130pgrbf00.grib2` plus `.idx` | MASSDEN 8 m and AOTK column, raw only | Excluded: zero native cells in box; eastern grid bound -57.381 degrees is not a coverage claim and the actual cell mask is empty |
| NAM parent | NOAA `noaa-nam-pds/nam.YYYYMMDD/nam.tHHz.awphys00.tm00.grib2` plus `.idx` | TCDC entire atmosphere | Excluded: incomplete box; native east bound -49.416 degrees and no reader-eligible St. John's cell |

## Capture receipts

No provider payload is stored in Git (owner decision of 2026-09-05, issue 70).
What follows is the receipt for the verified live capture: the exact object
URLs, the request parameters, the retrieved byte count and SHA-256 of each
upstream object, the capture time, and the revision (bytes and SHA-256) of the
artifact that was built from it. Request parameters were identical for every
source: evidence box south 45.0, west -58.0, north 50.5, east -46.0; lead 0 h;
anonymous HTTP GET, whole-object for DWD and HTTP `Range` byte requests driven
by the published `.index`/`.idx` for the indexed sources. Capture time for the
whole run was `2026-09-05T17:09:39.242369+00:00`.

| Source | Upstream object URL | Provider run | Retrieved bytes | Upstream SHA-256 | Artifact revision (bytes / SHA-256) |
|---|---|---|---|---|---|
| IFS | `https://data.ecmwf.int/forecasts/20260905/06z/ifs/0p25/oper/20260905060000-0h-oper-fc.grib2` (+ `.index`) | 2026090506, `2026-09-05T06:00:00+00:00` | 68,808,296 | `e529a2732750ce4387f7de10b4ce197323635e471143a1f31c3db66c5fefc288` (index `28546b14ffc61adc4a5e26d674d9c335478c7ced5d2de0204952ebb9fb19798f`) | 230,071 / `bcaf29bccdd7d7c3720ee64dbfb30bec9b92f0a31a7be0a8e7dc052b695109a8` |
| AIFS Single | `https://data.ecmwf.int/forecasts/20260905/06z/aifs-single/0p25/oper/20260905060000-0h-oper-fc.grib2` (+ `.index`) | 2026090506, `2026-09-05T06:00:00+00:00` | 66,626,102 | `b77b8c7273d95fa84aa3461a563c4ecb130076640bcc3732bc2faf5a89c4d5a6` (index `76ea15d8904edb080469c53e42b7f7559f4f2ded57e6168d16f39a71a04d58d0`) | 222,073 / `cf8409980e8aca9a31105b4a9d52955cadb158dde22527e0776b53c17fde67d1` |
| ICON Global | 28 objects under `https://opendata.dwd.de/weather/nwp/icon/grib/12/`, each with its own URL, byte count and SHA-256 in `evidence/native-deterministic-20260905/dwd-icon-global-native/upstream-objects.json` | 2026090512, `2026-09-05T12:00:00+00:00` | 92,109,503 across 28 objects | per object, see `upstream-objects.json` | 239,033 / `ddbc76bf732787b76f7dbedd8f55a72ab4486a49b8633d68eb5fcc7909eefcfe` |
| RAP parent | `https://noaa-rap-pds.s3.amazonaws.com/rap.20260905/rap.t16z.awp130pgrbf00.grib2` (+ `.idx`) | 2026090516, `2026-09-05T16:00:00+00:00` | 133,310 | `2ab82e2c2f14600e368ab8405cd593d48a722b997ee39a18f6e9e6668a07d328` (index `9acbcc04c82b2c7b3016f3ee905b828f9de5db2d214568cf1e51dba1f02b9298`) | none, excluded before build |
| NAM parent | `https://noaa-nam-pds.s3.amazonaws.com/nam.20260905/nam.t12z.awphys00.tm00.grib2` (+ `.idx`) | 2026090512, `2026-09-05T12:00:00+00:00` | 126,157 | `9d165320e0c84943b46a3b6040ea031ee18d984a2be65d31c38e61e60909f075` (index `9695220cd86d9c380fcaefd1ceb71bc9f952a2ae80ed7bfa57f5a4e9c5d857da`) | none, excluded before build |

The machine-readable form of the same receipt is retained per source as
`discovery.json` under `evidence/native-deterministic-20260905/`, plus
`upstream-objects.json` for the ICON per-object manifest. Those files carry
URLs, byte counts and digests only; they contain no retrieved values. The
retrieved GRIB objects, the `.index`/`.idx` files and the rebuilt Zarr
artifacts are not stored in this repository. Re-verification is a fresh live
capture with `scripts/native_deterministic_live_evidence.py`, which writes the
bundle to a working directory outside Git; the receipts above pin what the
2026-09-05 run retrieved.

The build retained 106 IFS messages, 93 AIFS Single messages and 26 ICON
messages for the selected lead, with full-box coverage at 1,127 quarter-degree
cells for both ECMWF sources and 3,107 native R03B07 cells for ICON.
This is one complete selected lead, not evidence for all forecast leads or a
complete cycle. IFS short/long-cycle reach remains a registry declaration, not
something this single-lead capture re-proves.

## Notes

The HTTP harness is a test-only endpoint around the production `LiveStore`
reader; it does not prove an existing production route's response contract. It
reads every selected pressure level and compares each canonical HTTP number or
null, native unit, and sampled cell with the witness decoded directly from the
corresponding upstream GRIB message at capture time. The run recorded 105 IFS
comparisons, 92 AIFS Single comparisons, and 25 ICON comparisons, all matching. The
lead-0 precipitation messages are separately reported with their decoded zero,
units, and `startStep=endStep=0`; no canonical precipitation value or nonzero
accumulation interval is claimed.

RAP and NAM were checked on the parent products named above. Their actual
two-dimensional native footprints, rather than rectangular extrema alone,
drive exclusion. RRFS remains conditional: no concrete anonymous free feed
covering the complete box was established in this work.

Replay preserves the original source retrieval time in artifact and reader
provenance; its separate `replayed_at` summary is not a new provider
acquisition. Replay now runs against a locally captured bundle, since the
payloads are deliberately absent from Git.
