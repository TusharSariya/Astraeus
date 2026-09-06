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

## Payload-bearing discovery continuation

Some small observation APIs expose no metadata-only request: discovery receives
the complete response and fetch normalizes the retained document. The worker
now has an optional seam that reserves the complete declared store and local
filesystem allocation before such discovery and holds one received-byte budget
through publication. No adapter is admitted by this change. In particular,
`noaa-swpc-kp-1m` remains blocked: a 27,925-byte bounded sample on 2026-09-06
does not prove a pre-allocation Python JSON decode-memory bound or physical
filesystem peak, and its capture receipt was not retained for independent
review. Post-hoc object sizing and logical Zarr byte counts were rejected as
insufficient evidence.

A replacement bounded capture retained its review material under
`/tmp/kp159-20260906/`: decoded raw response, response headers, receipt,
rebuilt artifact and HTTP/artifact comparison. The request completed at
2026-09-06T04:25:02Z with 28,003 bytes and 359 rows; raw SHA-256 is
`c60893f906fdcf5eada86433673f6dbcfff0d52cd5dc765a9995425ef3699c3c`.
The 5,548-byte artifact SHA-256 is
`f71275adf2db00e739773e66ecd0913f631e35d3e5f7c168a1dd4a59a25b1b63`.
The final HTTP row and artifact both carry 2026-09-06T04:21:00Z, Kp index 0,
estimated Kp 0.0 and provider code `0Z` (stored flag 0). This verifies content
and receipt plumbing only; it does not remove the decode-memory and physical
allocation blockers above or activate the adapter.
The deterministic all-row comparison is retained as
`/tmp/kp159-20260906/all-rows-comparison.json`. All 359 raw HTTP, artifact and
actual `LiveStore.read_series` rows normalize to SHA-256
`ff79d315bc2e66d7ead1df46e7d00e259665b7b0ab65287b758b84d276a98927`;
both comparisons report zero mismatches. It preserves the source HTTP
completion time above and `Last-Modified: Sun, 06 Sep 2026 04:23:03 GMT`.
