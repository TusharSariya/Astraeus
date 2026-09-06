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

The official Datamart naming documentation defines the filename UTC instant.
The retained official listing on 2026-09-06 contained paired CASHR filenames at
six-minute intervals (`00, 06, …, 54` minutes); the retained documentation also
describes six-minute availability for the S-band radar imagery family. This
draft therefore fixes a **six-minute expected cadence** and the following
consumer-visible status, calculated only from `valid_time` and the request
clock:

| `now - valid_time` | Status |
| --- | --- |
| `<= 18 minutes` | fresh |
| `> 18 and <= 60 minutes` | stale |
| `> 60 minutes`, future by more than 6 minutes, or no paired revision | unavailable |

Eighteen minutes is three source intervals and allows one missed producer
revision; it is not inferred from HTTP completion. Retrieval completion is
shown separately so consumers can distinguish delayed acquisition from an old
producer image.

## Retention and physical limits

Retain the newest **3,360 paired revisions** (14 days at six-minute cadence),
then delete an entire oldest pair atomically with its metadata. This is the
current/previous policy: `current` is the newest fresh pair, and `previous` is
the immediately preceding immutable pair; stale pairs may be read only by
revision ID, never relabeled current.

Each response has these hard refusal limits before decoding or publication:

| Item | Limit |
| --- | ---: |
| directory listing | 128 KiB |
| one GIF stream and immutable artifact | 512 KiB |
| paired source bytes | 1 MiB |
| logical canvas | 4,096 × 4,096 pixels |
| frames | exactly 1 |
| image descriptor | positive dimensions wholly inside the logical canvas |
| retained pair metadata and receipts | 16 KiB |
| retained store including filesystem blocks and metadata | 4 GiB |

At the retained capture, the Rain/Snow bytes were 25,291 and 35,867 bytes;
the local filesystem consumed 56 and 72 512-byte blocks (65,536 bytes total).
The 4 GiB store reservation is deliberately based on the hard one-MiB pair
ceiling: 3,360 pairs need 3.282 GiB of payload, leaving 0.718 GiB for receipts,
metadata, block allocation, indexes, and deletion overlap. It fits inside the
existing 64 GiB experiment allocation but does not authorize a capacity claim.

Activation must measure and record one complete operation's peak physical
allocation: listing, both streamed source files, both immutable artifacts,
metadata/receipt writes, parent/child overlap, and delete/promote overlap.
Activation fails closed unless that measured peak and the 4 GiB reservation are
enforced before the first allocation; logical byte counts or post-hoc
`getsizeof` measurements are insufficient.

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
source identity, six-minute cadence, thresholds, retention/physical reservation,
and revision-only API. The implementing change must add an owning manifest and
API schema, enforce the stated reservation before allocation, verify API byte
identity and all unavailable cases, remeasure peak physical allocation on the
target runtime, and preserve source QC as unknown. Until those gates pass, the
existing experiment remains unregistered, unscheduled, `operational: false`,
and `complete: false`.
