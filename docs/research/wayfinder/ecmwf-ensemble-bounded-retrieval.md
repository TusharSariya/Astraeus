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
contained no `cf` record. Astraeus therefore keeps control `0` named as missing
and leaves its retrieval path unstated. It does not substitute the deterministic
`oper` product.

The six selected family fields (`tcc`, `2t`, `2d`, `10u`, `10v`, `msl`) used
300 ranges and 200,090,799 bytes. The immutable cropped Zarr zip is 584,371
bytes with SHA-256
`7a61b523459023d7c27566ec6671b2c00d914fe989246e0d3073eb0acce56c9d`.
The ordered per-range evidence manifest has SHA-256
`fe8706191b166f7fb8af2444c9f305813347aa7d3464c17700a214169a61a781`.
Its manifest result was `complete=false`, `qc_passed=true`, with members 1
through 50 present and control 0 missing.

AIFS ENS `enfo-pf` contained 5,400 records, 29 parameters and members 1 through
50. Its separate `enfo-cf` contained 108 records and control 0. The nine
selected family fields (`tcc`, `2t`, `2d`, `10u`, `10v`, `msl`, `lcc`, `mcc`,
`hcc`) used 459 ranges and 451,054,255 bytes: 442,248,849 perturbed-member bytes
plus 8,805,406 control bytes. The immutable cropped Zarr zip is 907,863 bytes
with SHA-256
`3749a0e38f84af10d08c3e357fdbd7c58b0726db2bd078aa7d58899f63154bd1`.
The ordered per-range evidence manifest has SHA-256
`78bc3fcc205523ab642642cdc9ddd3eb9245806af5600e01e503799c124ccacc`.
Its result was `complete=true`, `qc_passed=true`, with all 51 members present
and member 0 flagged as the separately retrieved control.

Every range request required HTTP 206, exact `Content-Range`, and a body length
equal to the index `_length`. The artifact provenance carries the URL, byte
range, actual byte count, parameter, member and SHA-256 for every retained
input record. Temporary global GRIB records were deleted after decoding, so
peak working storage stayed below one record plus the cropped arrays and final
artifact, far below the 4 GiB scratch reservation. The daily transfer cap was
off; the operation was still bounded by 13 metadata requests, 759 indexed
ranges, 651,145,054 data bytes, 8 MiB per-range ceiling, 60-second request
timeout and the two finite f024 artifacts. The 64 GiB hot-storage quota was not
changed.

## Data and reader proof

All decoded fields retained the producer's regular 0.25-degree source grid:
23 latitudes from 45 to 50.5 north and 49 longitudes from -58 to -46 east.
The adapter rejects any field or member with different coordinates, any cell
outside that exact box, non-finite coordinates, mismatched run/date/time/lead,
wrong normalized units, or an advertised selected field that did not arrive.
Cloud fields must decode with GRIB `stepType=instant`; no averaged cloud is
relabeled as instantaneous. The artifact has an exact `valid_time` dimension
of `2026-09-06T00:00:00` for this run and lead.

The real API reader opened the immutable AIFS artifact and served HTTP 200 at
47.5 N, 52.75 W for the exact valid time. Control member 0 returned nine
numeric fields; examples were temperature 13.365875 degC, dew point 11.786041
degC, total cloud 100 percent and mean sea-level pressure 1008.866150 hPa.
Perturbed member 1 also returned all nine numeric fields. Requesting nonexistent
member `999` returned no ECMWF field values and `data_mode=unavailable`; the
reader did not borrow a nearby member or manufacture a statistic.

## Verification

```text
cd experiments/st-johns-weather-map/api
PYTHONPATH=.. uv run pytest tests/test_adapter_ensemble.py tests/test_ingest_http.py -q
PYTHONPATH=.. WEATHER_HTTP_MIN_HOST_INTERVAL=0 uv run python <bounded retrieval script>
PYTHONPATH=.. WEATHER_DATA_MODE=live uv run python <real artifact HTTP readback script>
```

The committed unit suite covers full-window discovery, the unchanged schedule
gate, separate-control assembly, missing control and selected-field behavior,
run/time/lead identity mismatch, unit mismatch, grid mismatch, valid-time
identity, exact input byte/checksum provenance, and refusal of 200 full-body,
short 206 and wrong `Content-Range` responses.
