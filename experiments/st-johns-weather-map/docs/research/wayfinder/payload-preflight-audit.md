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
