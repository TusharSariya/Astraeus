# Design

The worker reserves the whole operation before discovery because both SWPC
documents are payload-bearing. Each response is streamed under a 512 KiB cap.
The parent retains at most two capped byte strings plus bounded inspection
replies. Each decoder starts with a locked 256 MiB `RLIMIT_AS`, 512 KiB
`RLIMIT_FSIZE`, and finite stdin/stdout/stderr channels. Unsupported limits fail
closed.

Normalization writes exactly one ZIP in a private sibling directory. Success
renames that file atomically; failure removes the workspace and destination.
The supported Linux target measured 4096-byte allocation and stat blocks. The
512 KiB file limit is exactly block aligned. Admission includes two 512 KiB
outputs and two 4096-byte workspace-directory allocation allowances. A target
whose file or fragment block differs fails before normalization. There is no
post-write peak claim and no guessed percentage margin.

The 2026-09-06 bounded capture retained outside Git contains 57 observed rows
(4401 bytes, SHA-256 `8a0913f35f9e0e2316ec7ac8cc837b332ca1c4904e39c442999bd1d9b8f2c88d`)
and 81 forecast rows (6910 bytes, SHA-256
`01c0be6ac8ca8b8b1a8bafeb4651d8b4a3df481993cff3bd6e21de638eee6374`).
Linux replay published both actual ZIPs through an isolated PostgreSQL database
and MinIO object keys, then preserved every timestamp, Kp, running-a value, and
provider forecast status through `LiveStore.read_series` and the real HTTP
space-weather route (57 observed and 81 forecast readings). Synthetic documents immediately
below 512 KiB produced 6553 observed and 6096 forecast rows under the same
limits. Raw data and replay artifacts remain in `/tmp/swpc-kp159-study` for
independent review.
