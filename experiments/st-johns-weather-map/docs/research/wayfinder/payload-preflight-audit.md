# Payload resource preflight audit

Captured September 6, 2026 for issue 159. This is non-normative execution
evidence. No provider payload was retrieved or retained for this audit.

## Observed call order at `4d8d899`

`worker.runtime.run_source` called `adapter.discover`, inspected the retained
window and then called `adapter.fetch`. Only after `fetch` returned local
artifacts did `ArtifactStore.stage` call `check_projection`, one artifact at a
time. The check therefore did not reserve a complete run before network reads,
did not account for temporary/decode space and was not atomic across competing
operations.

Several adapters retrieve JSON feeds or indexes during `discover`, so guarding
only `fetch` would still permit payload bytes before admission. Discovery now
requires its own measured received-byte bound before any request; unknown
discovery bounds fail closed. Retry and terminal error bodies count against the
active discovery or fetch operation instead of disappearing from accounting.

`PoliteClient.download` and the active `get_bytes` implementation streamed with
per-call byte ceilings and removed partial files. `download_ranges` called
`get_range`, which used a buffered response; an ignored or oversized range
could therefore enter memory in full before the aggregate ceiling ran. A
second `get_bytes` definition shadowed the headers-returning implementation
expected by two WCS paths. Generic `get` and `get_text` consume the active
discovery or fetch budget while streaming. Range reads refuse before the
request when the requested bytes do not fit the remaining budget, then require
the response `Content-Range` and body length to match the request.

## Admission result

The runtime registers 30 adapters. Seventeen currently pass the existing
registry scheduler gate: `awc-metar-speci`, `awc-taf`, `dwd-icon-global`,
`eccc-aqhi`, `eccc-cap-alerts`, `eccc-gdps`, `eccc-hrdps`, `eccc-lightning`,
`eccc-radar`, `eccc-rdps`, `eccc-swob`, `ecmwf-ifs`, `noaa-gfs`,
`noaa-goes-east`, `noaa-swpc-kp`, `noaa-swpc-ovation` and `noaa-swpc-rtsw`.
None supplies measured `DiscoveryBounds` or a complete-operation
`ResourceBounds` declaration at this revision. The repaired worker therefore
refuses their upstream retrieval
with `upstream_budget_exhausted` until their acquisition tickets provide
source-specific measured store, filesystem, margin and received-byte bounds.
Existing per-response constants are useful lower-level controls but do not
establish a complete-run bound and are not promoted into one by arithmetic or
a generic percentage.

## Enforcement boundary and remaining work

The single worker applies the measured discovery byte bound, then reserves
projected hot-store bytes and local filesystem bytes
plus the adapter's measured margin before `fetch`. Reservations are atomic
among operations in that process. Actual received bytes are counted across
streamed, ordinary and byte-range HTTP reads. Temporary/extraction output and
staged artifacts are reconciled to their declared bounds before publication;
an underestimated operation is cleaned up and publishes nothing.

The local-filesystem reconciliation detects an underestimated extraction after
the adapter returns; it is not an operating-system quota and does not constrain
the instantaneous extraction peak. Each decoder/extractor still needs a
source-specific construction that cannot write beyond its reserved bound.
Separate capture scripts and multiple worker processes do not share the
process-local ledger. They require external coordination now, and a durable
reservation ledger before multi-process ingestion is enabled.

The issue 74 owner decision keeps the 64 GiB hot quota and no cold tier,
requires measured margin and unknown bounds to fail closed, and removes the
artificial daily download ceiling. This repair does not change registry states,
enable adapters, promote OpenSpec status or set `operational: true`.

## First payload-bearing discovery measurement

The isolated `noaa-swpc-kp-1m` adapter is the first complete-operation example.
Its endpoint has no separate metadata object: the one bounded JSON response is
both discovery evidence and the fetch input. Complete hot-store and local
filesystem capacity is therefore reserved before `discover`; that reservation
and the operation-wide received-byte counter remain held through publication.
The decoded rows stay in the candidate and `fetch` performs no second request.

A bounded live read on 2026-09-06 received 27,925 bytes and 358 records from
the Kp-1m endpoint
(`sha256:8e3fad57b946c87aef24989d78bbbc9a25f74a55baa041f59356d33b6ee8b12b`).
No response body was retained. Admission deliberately uses the existing full
512 KiB SWPC small-feed ceiling rather than extrapolating that sample.

The minimum compact encoding containing all four required keys is 56 bytes,
so a conforming 512 KiB document cannot contain more than 9,362 records. The
normalized output has four eight-byte arrays per record (time and three data
variables). Its directory/archive allocation is therefore twice the array
bytes plus a 16 KiB metadata envelope measured by the maximal-row synthetic
fixture: 631,936 bytes. The bounded writer checks every directory-store write,
then computes the exact ZIP_STORED headers and payload size and refuses before
creating the archive if directory plus archive would cross that allocation.
The maximal 9,362-row fixture produced a 22,567-byte archive. Margin is zero
because the declared filesystem allocation already includes both simultaneous
copies and exact container records; it is not a percentage or free-space
allowance. A record above the wire-derived count is refused, never truncated.
The maximal candidate graph with distinct numeric and string values measured
3,878,579 bytes under the runtime's recursive `sys.getsizeof` accounting. Its
retained-memory admission is 4 MiB; the worker refuses the candidate before
fetch when that measured envelope is crossed.
