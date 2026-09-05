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

The artifact bundle under `evidence/native-deterministic-20260905/` records exact
run URLs, object/range sizes, SHA-256 digests, decoded native units and grid
templates, field/level dispositions, selected-cell extents, and HTTP readback.
The Zarr files contain the retrieved numerical values and null masks. The run
is a complete selected lead, not evidence for all forecast leads or a complete
cycle. IFS short/long-cycle reach remains a registry declaration, not something
this single-lead capture re-proves.

The HTTP harness reads every selected pressure level, not only one sample. It
compares each canonical HTTP number or null, native unit, and sampled cell with
the witness decoded directly from the corresponding retained upstream GRIB
message. The summary contains 105 IFS comparisons, 92 AIFS Single comparisons,
and 25 ICON comparisons; raw-only lead-0 precipitation is intentionally absent
from the canonical comparison set.

RAP and NAM were checked on the parent products named above. Their actual
two-dimensional native footprints, rather than rectangular extrema alone,
drive exclusion. RRFS remains conditional: no concrete anonymous free feed
covering the complete box was established in this work.
