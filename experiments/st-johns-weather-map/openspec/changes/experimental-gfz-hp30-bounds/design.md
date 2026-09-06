# Design

The worker calls `operation_bounds` before the payload-bearing discovery request.
That method proves the target has the measured 4096-byte allocation geometry
and launches a zero-input child to prove locked `RLIMIT_AS` and `RLIMIT_FSIZE`
support. Unsupported targets fail before network access.

The one response is streamed under 512 KiB. Its raw bytes remain the only
payload retained by the parent. Inspection and normalization each run in a
child with a 256 MiB address-space cap, a 16 KiB inspection reply cap, and a
64 KiB single-file output cap. The inclusive 24-hour half-hour selection admits
at most 49 rows before constructing the parent metadata list. Thus the parent
retains at most the 512 KiB raw input, one 512 KiB stdin transfer, a 16 KiB
reply, and 49 compact time strings while the child is limited separately; this
does not characterize `RLIMIT_AS` as a total-memory guarantee. Every top-level field, metadata field, value and datetime is
validated; malformed timestamps are refused without thinning. Native nulls
remain gaps. The one private workspace output is atomically promoted, and all
failure paths remove workspace and destination.

The bounded 2026-09-06 live response was 1444 bytes with 48 aligned rows,
SHA-256 `c1776a6ab858f98da2ccdfcb52fe3b7689f489fbcf57405d186fd6df9b20a844`.
Raw bytes, selected headers, actual completion, Linux artifacts and real-store
proof remain under `/tmp/gfz159-capture` for independent review. All 48 times
and values match through `ArtifactStore` publication and `LiveStore`; the real
HTTP products route reports record count 48 and the matching newest finite
value, which is the route's accepted summary boundary. The 64
KiB output ceiling is block aligned; the observed 2673-byte artifact occupied
one 4096-byte filesystem block. Admission adds one 4096-byte private
workspace-directory allocation allowance. There is no post-write peak claim.
