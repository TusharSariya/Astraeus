# Proposed CASHR rendered-image contract

> **Owner decision requested.** This is one concrete draft contract for issue
> #105. It remains non-normative and does not authorize a registry field, API
> route, publication, freshness claim, or `operational: true` status until the
> owner accepts it with the required executable contract and verification.

## Decision proposed for acceptance

Accept one source identity, `eccc-holyrood-cashr-dpqpe-rendered-v1`, for a
**paired** CASHR DPQPE rendered-image revision. A revision contains exactly two
same-`valid_time` artifacts:

```text
producer: Environment and Climate Change Canada
station_id: CASHR
product: DPQPE
phase: Rain | Snow
encoding: image/gif
valid_time: UTC instant parsed from YYYYMMDDTHHmmZ filename
source_qc: unknown
coverage: rendered-image-only
```

The selected source is the official MSC Datamart CASHR directory. A name must
match `YYYYMMDDTHHmmZ_MSC_Radar-DPQPE_CASHR_(Rain|Snow).gif`; a
`-Contingency` name is a different composite product and is refused. The
revision identifier is the pair of artifact SHA-256 values, source filenames,
and the listing SHA-256. Neither provider `Date`, HTTP completion, nor a
retrieval clock changes the producer revision identity.

The GIF bytes are immutable and byte-preserving. Required provenance for each
artifact is URL, filename, `valid_time`, raw-byte SHA-256, byte count,
`Content-Type`, `Content-Length`, `ETag`, `Last-Modified`, provider `Date` if
present, and transport completion time. The latter is retrieval provenance,
not a producer valid time.

## Semantics and quality

The product is an opaque rendered image only. The contract exposes no numeric
pixel, precipitation rate, reflectivity, hydrometeor class, quality mask,
radial velocity, grid, geometry, raw volume, or independent dual-polarization
moment. A producer statement that DPQPE is lowest-sweep,
dual-polarization-processed precipitation estimation is provenance text only;
it does not create an independently observed moment or numerical field.

`source_qc` is exactly `unknown`. Structural receipt/GIF validation is
reported separately as `structural_validation: passed | failed`; it must never
turn unknown provider QC into passed QC. A missing Rain or Snow counterpart,
invalid receipt, invalid/truncated GIF, ceiling breach, or transport failure is
`unavailable` and creates no revision. A blank, transparent, or zero-byte image
is never interpreted as no precipitation.

## Freshness

The [official MSC Datamart radar-image documentation](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radarimage-datamart_en/)
defines the filename UTC instant and describes six-minute availability for the
S-band radar imagery family. The retained official CASHR listing on 2026-09-06
also contained paired names at six-minute intervals (`00, 06, …, 54` minutes).
This draft proposes a **six-minute expected cadence** and the following
consumer-visible policy, calculated only from `valid_time` and the request
clock:

| `now - valid_time` | Status |
| --- | --- |
| `<= 18 minutes` | fresh |
| `> 18 and <= 60 minutes` | stale |
| `> 60 minutes`, future by more than 6 minutes, or no paired revision | unavailable |

Eighteen minutes is three source intervals and allows one missed producer
revision; it is not inferred from HTTP completion. Sixty minutes is ten
intervals and is the proposed availability cutoff. Retrieval completion is
shown separately so consumers can distinguish delayed acquisition from an old
producer image. These 18/60-minute thresholds are proposed policy, not an
owner-accepted freshness guarantee.

A revision-addressed byte request for a stale retained pair returns the bytes
with metadata status `stale`; it does not masquerade as current. Safety,
forecast, recommendation, and scoring consumers are ineligible to use stale
or unavailable images. They must receive the normal unavailable/degraded
result until a separate accepted rule authorizes image use.

## Retention and physical limits

Use the existing **24-hour observation-history retention policy**. At a
verified six-minute cadence it retains at most **240 paired revisions**, then
purges an entire oldest pair and its metadata atomically. This is not a
14-day forecast horizon. `current` is the newest fresh pair; `previous` is the
immediately preceding immutable pair. A stale retained pair remains readable
only by revision ID with explicit `stale` status, never as current.

Each response has these hard refusal limits before decoding or publication:

| Item | Limit |
| --- | ---: |
| directory listing | 128 KiB |
| one GIF stream and immutable artifact | 512 KiB |
| paired source bytes | 1 MiB |
| logical canvas | 4,096 × 4,096 pixels |
| frames | exactly 1 |
| image descriptor | positive dimensions wholly inside the logical canvas |
| metadata/receipt size | measured and bounded before activation |
| retained-store subquota | no new subquota is proposed |

At the retained capture, the Rain/Snow bytes were 25,291 and 35,867 bytes;
the local filesystem consumed 56 and 72 512-byte blocks (65,536 bytes total).
That capture is evidence only, not a storage reservation. The existing 64 GiB
allocation remains the only quota in this draft. Admission must account against
its actual physical allocation, including every retained copy, receipt,
metadata/index record, filesystem block, staging file, parent/child overlap,
and deletion/promote overlap. A logical-payload multiplication cannot establish
a physical quota or a safe subquota.

Activation must measure and record the peak physical allocation of a complete
operation on the target runtime, including the listing, both streamed source
files, immutable artifacts, metadata/receipt writes, all copies, and cleanup.
It must reserve that measured bound within the existing 64 GiB allocation
before the first allocation. Activation fails closed while the measurement,
reservation enforcement, or retained-copy accounting is unknown; logical byte
counts or post-hoc `getsizeof` measurements are insufficient.

## Alternatives considered

1. **Recommended: 24-hour observation history at verified six-minute cadence.**
   It follows the existing observation retention policy, bounds history at 240
   paired revisions, and preserves a revision-addressed stale audit trail.
2. **No image history/API until the measurement and owner contract exist.**
   This is safer if physical allocation cannot be measured or reserved, but it
   provides no retained current/previous artifact for inspection.
3. **Fourteen-day retention.** Rejected: that is a forecast-horizon concept,
   not the established observation-history policy, and no source or storage
   evidence here justifies extending radar observation retention.

## Immutable metadata and byte API

If accepted, expose only these revision-addressed endpoints:

```text
GET /v1/source-artifacts/eccc-holyrood-cashr-dpqpe-rendered/revisions/{revision_id}
GET /v1/source-artifacts/eccc-holyrood-cashr-dpqpe-rendered/revisions/{revision_id}/rain.gif
GET /v1/source-artifacts/eccc-holyrood-cashr-dpqpe-rendered/revisions/{revision_id}/snow.gif
```

Metadata returns source identity, revision ID, phase identities, source
filenames, `valid_time`, retrieval completion, freshness status, raw-byte
digests, byte counts, retained HTTP receipt fields, structural image
width/height/frame count, `source_qc: unknown`, and
`coverage: rendered-image-only`. Byte endpoints return precisely the immutable
selected bytes with `Content-Type: image/gif`, digest/ETag, and no transforms.

There is no `/current` endpoint, `/point` endpoint, raster/grid endpoint,
palette lookup, pixel API, or numerical unit. A caller selects a revision ID
from metadata; the API cannot silently substitute a newer artifact.

## Acceptance gate

Before any implementation or promotion, the owner must accept this document's
source identity, proposed six-minute cadence and 18/60-minute policy,
24-hour observation retention, measured physical reservation gate, and
revision-only API. The implementing change must add an owning manifest and API
schema, enforce the measured reservation before allocation, verify API byte
identity, stale and unavailable responses, remeasure target-runtime physical
allocation, and preserve source QC as unknown. Until those gates pass, the
existing experiment remains unregistered, unscheduled, `operational: false`,
and `complete: false`.
