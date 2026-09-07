# Current GFS point and pinned Series proof, September 7

Evidence only; no source admission or runtime change. Source code was fixed at
`14aac25a258e02e6db098ebeb8a21ebe66aa85d5`. The prepared Linux image was
`sha256:aacbd8b2f012e571c45c5a3b88d9935aaa72e6506bbad14bcd970766cb7697ff`,
with that head's API, ingest and registry directories mounted read-only.

## Live acquisition

Anonymous public GFS S3 discovery returned latest `gfs-2026090718` and previous
`gfs-2026090712`. The actual latest-run listing advertised f003. One selected
frame, valid `2026-09-07T21:00:00Z`, was acquired and decoded by the production
bounded Linux worker. No other frame or provider was queried. Temporary HTTP
instrumentation rejected every unrelated provider host and retained native
response bodies outside Git.

The shared `SourceReader.read_point` returned 16 fields. Generated identities
matched actual source `noaa-gfs`, product `gfs`, deterministic variant, 18Z run,
21Z valid time, native level and sampled cell. At requested 47.5615/-52.7126,
the sampled cell was 47.5/-52.75, approximately 7.392 km away. Temperature was
17.119964599609375 degC, dewpoint 14.118316650390625 degC, MSL pressure
1000.56884765625 hPa, and total/low geometric cloud were actual retrieved zero
percent values.

- 22 actual provider requests: two discovery indexes, one run listing, one
  selected-frame index and 18 bounded ranges.
- Total received: 27,125,905 bytes; range payload: 26,975,882 bytes.
- Last live final-byte receipt: `2026-09-07T21:56:00.242481Z`.
- Normalized surface/upper-air payloads: 472,116/69,946 bytes.
- Normalized digest:
  `754f419cbd173717fd852387f3a753a90c0746a65b12cd6668412307303a4e06`.

## API and cache replay

The first proof script called the wrong Series path and received HTTP 404 after
successful live point acquisition. The actual path is `/point/series`. The
corrected proof reused those just-acquired native bodies rather than downloading
another payload. This second leg ran with Docker `--network none` and exact
request/body-digest checks; it is explicitly replay evidence, not another live
provider check.

`POST /api/experiments/weather/v0/point/series` with the named 18Z run, a
one-minute window beginning at 21Z, and the `temperature_2m` deterministic
selector returned HTTP 200 with exactly one available sample. Snapshot identity
retained the actual run/valid time, 2-m level, product, native sampled cell and
same artifact digest as the live point. Shared point plus Series plus repeated
point and Series reads remained at 22 fixture requests, zero provider requests,
and zero additional payload requests. The source cache returned the identical
entry and content identity. No consensus, METAR or AQHI seam was invoked.

## Residual found by independent native inspection

The raw selected `2t` GRIB record declares units K and nearest-cell value
290.269970703125 K. This agrees with the normalized API temperature within
float32 rounding. However, API `provenance.original_units` says `degC` instead
of K. Run, valid time and level are correct. Original-unit propagation through
the shared sampler remains an evidenced follow-up; this proof does not claim
that provenance detail is correct. No shared code was edited.

## Receipts and verification

Temporary evidence root: `/private/tmp/astraeus-api-first-gfs-live-proof/`.
`capture-summary.json` indexes all live receipts and hashes the point,
generated identities, public inventory, replay Series, replay proof and
independent native-temperature inspection. Raw bodies remain in `raw/`.
Replay retrieval-completion timestamps describe replay execution and are not
substituted for the original live receipts. All owned containers exited.

This was one live native-frame acquisition plus one offline replay, not a
12-frame Series sweep. `specctl validate` passed with zero errors/warnings.

Spec-Impact: none; records fixed-head execution evidence and an existing unit
provenance residual without changing source or API behavior.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
