# ECMWF ensemble discovery and bounded retrieval

Verified 2026-09-05 against the anonymous ECMWF Free and Open Data HTTPS
portal. This is experiment evidence, not accepted product authority. Both
registry records remain unschedulable and `operational: false`.

## Discovery

The portal root listed four retained dates. Metadata-only discovery read at
most the root, four date pages, and the two full-cycle (`00z`, `12z`) product
directories per date: a hard ceiling of 13 requests per family. The live run
used 12 requests. For the newest available `20260905 00z` cycle it enumerated
the full advertised cadence inside the 15-day window:

- AIFS ENS: 61 leads, 0 through 360 hours every 6 hours.
- IFS ENS: 85 leads, every 3 hours through 144 hours and every 6 hours from
  150 through 360 hours.

Discovery returns one candidate per actual lead whose valid time is inside the
requested window. It requires the `.grib2` object to be present in the listing
and derives the sibling `.index` name by replacing `.grib2`, rather than by
appending to it. Normal adapter `discover` and `fetch` still refuse at the
registry gate; only `discover_experiment` exposes this unregistered evidence
path.

## Representative f024 inventories

IFS ENS `enfo-ef` contained 8,500 index records, 47 parameters, and exactly
`type=pf`, `number=1..50`. The directory listed no control object and the index
contained no `cf` record. ECMWF's Cycle 50r1 documentation explains that
`enfo:cf` was discontinued and directs control users to `oper:fc`, which ECMWF
describes as bit-identical. The original retained capture keeps control `0`
named as missing and remains unchanged.

Primary sources are ECMWF's [current open-data guide updated for Cycle
50r1](https://confluence.ecmwf.int/spaces/DAC/pages/272310539/ECMWF%2Bopen%2Bdata%2Breal-time%2Bforecasts%2Bfrom%2BIFS%2Band%2BAIFS) and
[Cycle 50r1 discontinuation and equivalence
notice](https://confluence.ecmwf.int/spaces/FCST/pages/554148365/Data%2Bstreams%2Band%2Btypes%2Bto%2Bbe%2Bdiscontinued%2Bin%2BIFS%2Bcycle%2B50R1%2Band%2Buser%2Bimpact).

On 2026-09-05, `@TusharSariya` authorized exactly the six selected `oper:fc`
fields to enter the experimental IFS ENS member axis as producer-designated
control `0` ([approval](https://github.com/TusharSariya/Astraeus/issues/82#issuecomment-5553992154)).
No other deterministic product, field or inferred equivalence is permitted.

The follow-up capture reverified all 300 retained perturbed ranges, then
fetched only the six exact `oper:fc` ranges from the same 20260905 00Z f024
run. The control ranges total 3,896,612 bytes; the combined 306-range input is
203,987,411 bytes. The result is complete and QC-passed with all 51 members.
Its 596,426-byte Zarr artifact has SHA-256
`7e0520d3b764f6d9ce46a08522d1d3d7dbf830633657cf4fe18eefa41b53b6c4`.
The 235,760-byte receipt has SHA-256
`5a2ccc6e288a2879b7ad644e47586f189e5e391006fdc58150e99a93faaad3db`.
The retained 40,210-byte control index has SHA-256
`927c5d4e7550ba978afb1a05e0ba7ee0c09a288719eecb12765ab355791b62de`.
Every mapped range records the original `oper` stream, `fc` type, URL, index
identity, decoded GRIB identity (including `marsStream=oper`), and explicit
Cycle 50r1 mapping. Perturbed retrieval, mapped-control capture and assembly
timestamps remain separate. The receipt for this capture is the
`ecmwf-ensemble-20260905-cycle50r1-control` entry in
`docs/research/wayfinder/evidence/ecmwf-ensemble-20260905/receipts.json`
and the table below.

The six selected family fields (`tcc`, `2t`, `2d`, `10u`, `10v`, `msl`) used
300 ranges and 200,090,799 bytes. The immutable cropped Zarr zip is 584,371
bytes with SHA-256
`7a61b523459023d7c27566ec6671b2c00d914fe989246e0d3073eb0acce56c9d`.
The corrected retained receipt is 145,975 bytes with SHA-256
`9638e7566a7cf69ec5e1758dcaf63a40588bb3cef771fc0a305ae8be5eb509aa`.
Its manifest result was `complete=false`, `qc_passed=true`, with members 1
through 50 present and control 0 missing.

AIFS ENS `enfo-pf` contained 5,400 records, 29 parameters and members 1 through
50. Its separate `enfo-cf` contained 108 records and control 0. The nine
selected family fields (`tcc`, `2t`, `2d`, `10u`, `10v`, `msl`, `lcc`, `mcc`,
`hcc`) used 459 ranges and 451,054,255 bytes: 442,248,849 perturbed-member bytes
plus 8,805,406 control bytes. The immutable cropped Zarr zip is 907,863 bytes
with SHA-256
`3749a0e38f84af10d08c3e357fdbd7c58b0726db2bd078aa7d58899f63154bd1`.
The corrected retained receipt is 222,591 bytes with SHA-256
`3728ac50ab71ea54ae4257f5aab2b651091e4063048dc2759f39500620ff5c1e`.
Its result was `complete=true`, `qc_passed=true`, with all 51 members present
and member 0 flagged as the separately retrieved control.

Every range request required HTTP 206, exact `Content-Range`, and a body length
equal to the index `_length`. The artifact provenance carries the URL, byte
range, actual byte count, parameter, member and SHA-256 for every retained
input record. The correction covered 759 source GRIB records and all three
indexes; their URLs, byte ranges, byte counts and SHA-256 digests are
recorded in the receipts, and the records themselves are not retained in Git.
Offline replay verifies every index and range by
URL, interval, byte count and SHA-256, regenerates the artifact byte-for-byte,
then performs HTTP readback. The operation remained bounded by 759 ranges,
651,145,054 data bytes, an 8 MiB per-range ceiling and 60-second timeout. All
retained and replayed material remained below the 4 GiB scratch reservation;
the 64 GiB hot-storage quota was unchanged.

The first correction attempt was interrupted and is not validation evidence.
It retained 604 records totalling 548,100,041 bytes under
`/private/tmp/ecmwf82-interrupted-20260905T1810Z`; none of its results or
receipts is cited as verified.

## Data and reader proof

All decoded fields retained the producer's regular 0.25-degree source grid:
23 latitudes from 45 to 50.5 north and 49 longitudes from -58 to -46 east.
The adapter rejects any field or member with different coordinates, any cell
outside that exact box, non-finite coordinates, mismatched run/date/time/lead,
wrong normalized units, or an advertised selected field that did not arrive.
Cloud fields must decode with GRIB `stepType=instant`; no averaged cloud is
relabeled as instantaneous. The artifact has an exact `valid_time` dimension
of `2026-09-06T00:00:00` for this run and lead.

The real core reader opened both immutable artifacts through a test-only
FastAPI route at 47.5 N, 52.75 W and the exact valid time. All selected fields
and units for all 51 AIFS members and all 50 IFS members matched direct samples
from the retained artifacts, including numeric-or-null identity. AIFS control
member 0 returned nine numeric fields; examples were temperature 13.365875
degC, dew point 11.786041 degC, total cloud 100 percent and mean sea-level
pressure 1008.866150 hPa. Member `999` returned no values for either family.
The evidence route reports `operational: false` and is not a deployed API.

## Receipts

Provider payloads (GRIB records, `.index` objects and rebuilt Zarr artifacts)
are not retained in Git, per the owner decision of 2026-09-05 recorded in
[issue #70](https://github.com/TusharSariya/Astraeus/issues/70). What remains
is the receipt below, the machine-readable
`docs/research/wayfinder/evidence/ecmwf-ensemble-20260905/receipts.json`, the
condensed API readbacks beside it, and the capture script
`experiments/st-johns-weather-map/scripts/ecmwf_ensemble_evidence.py`, which
reproduces any capture from these parameters.

All requests were anonymous HTTPS `GET` against
`https://data.ecmwf.int/forecasts/20260905/00z/`, run stamp `20260905000000`,
lead 24 hours, every range answered HTTP 206 with an exact `Content-Range` and
a body length equal to the index `_length`.

| Capture | Source | Objects requested | Ranges | Range bytes | Indexes (bytes / sha256) | Artifact (bytes / sha256) | Capture time (UTC) | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ecmwf-ensemble-20260905-corrective` | `ecmwf-aifs-ens` | `aifs-ens/0p25/enfo/20260905000000-24h-enfo-cf.grib2`, `…-enfo-pf.grib2` | 459 | 451,054,255 | `cf` 25,806 / `146197f1…4c8b678a`; `pf` 1,386,284 / `81e3317c…0894aa64` | `ecmwf_aifs_ens_members.zarr.zip` 907,863 / `3749a0e3…f63154bd1` | captured 2026-09-05T18:11:36Z | complete, QC passed, 51 of 51 members, control `0` from the separate `cf` object |
| `ecmwf-ensemble-20260905-corrective` | `ecmwf-ens` | `ifs/0p25/enfo/20260905000000-24h-enfo-ef.grib2` | 300 | 200,090,799 | `ef` 2,004,415 / `13bec225…b84f8e62` | `ecmwf_ens_members.zarr.zip` 584,371 / `7a61b523…cce56c9d` | retrieved 2026-09-05T18:17:01Z | incomplete, QC passed, quality `suspect`, members 1–50 present, control `0` missing |
| `ecmwf-ensemble-20260905-cycle50r1-control` | `ecmwf-ens` | `ifs/0p25/enfo/…-enfo-ef.grib2`, `ifs/0p25/oper/20260905000000-24h-oper-fc.grib2` | 306 | 203,987,411 | `ef` 2,004,415 / `13bec225…b84f8e62`; `oper-fc-control0` 40,210 / `927c5d4e…791b62de` | `ecmwf_ens_members.zarr.zip` 596,426 / `7e0520d3…41b53b6c4` | perturbed 2026-09-05T18:17:01Z, control 2026-09-05T18:55:56Z, assembled 2026-09-05T18:56:05Z | complete, QC passed, 51 of 51 members, control `0` mapped from `oper:fc` |

Parameters requested were `10u`, `10v`, `2d`, `2t`, `msl`, `tcc` for
`ecmwf-ens`, plus `hcc`, `lcc`, `mcc` for `ecmwf-aifs-ens`. The full
per-range receipts produced by the live captures were 222,591 bytes
(`3728ac50…20ff5c1e`), 145,975 bytes (`9638e756…5eb509aa`) and 235,760 bytes
(`5a2ccc6e…faaad3db`); their digests are recorded in `receipts.json` and the
files themselves are not retained.

## Verification

```text
cd experiments/st-johns-weather-map/api
PYTHONPATH=.. uv run pytest tests/test_adapter_ensemble.py tests/test_ingest_http.py -q
cd ..
PYTHONPATH=. WEATHER_HTTP_MIN_HOST_INTERVAL=0 uv run --project api python scripts/ecmwf_ensemble_evidence.py /private/tmp/ecmwf82-corrected --family aifs
PYTHONPATH=. WEATHER_HTTP_MIN_HOST_INTERVAL=0 uv run --project api python scripts/ecmwf_ensemble_evidence.py /private/tmp/ecmwf82-ifs-corrected --family ifs
PYTHONPATH=. uv run --project api python scripts/ecmwf_ensemble_evidence.py /private/tmp/ecmwf82-aifs-replay --offline <capture-dir>/ecmwf-ensemble-20260905-corrective --family aifs
PYTHONPATH=. uv run --project api python scripts/ecmwf_ensemble_evidence.py /private/tmp/ecmwf82-ifs-replay --offline <capture-dir>/ecmwf-ensemble-20260905-corrective --family ifs
PYTHONPATH=. uv run --project api python scripts/ecmwf_ensemble_evidence.py /private/tmp/ecmwf82-cycle50r1-replay --offline <capture-dir>/ecmwf-ensemble-20260905-cycle50r1-control --family ifs
```

The `--offline` replays read a local capture directory produced by the live
commands above. Provider payloads are not retained in Git, so `<capture-dir>`
is a local path, never a repository path.

The AIFS receipt preserves retrieval at 2026-09-05T18:11:36Z and the IFS
receipt at 2026-09-05T18:17:01Z. Replay records its own later time separately.
The committed unit suite covers full-window discovery, the unchanged schedule
gate, separate-control assembly, missing control and selected-field behavior,
run/time/lead identity mismatch, unit mismatch, grid mismatch, valid-time
identity, exact input byte/checksum provenance, and refusal of ignored-range
200, malformed headers, short or overlong 206, and wrong `Content-Range`
responses. An ignored range is rejected before a body chunk is consumed and a
failed stream leaves no partial file.
