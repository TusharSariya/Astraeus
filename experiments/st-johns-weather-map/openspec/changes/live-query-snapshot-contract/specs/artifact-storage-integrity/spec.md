## MODIFIED Requirements

### Requirement: Staging debris is discarded without touching visible revisions
A restart or expiry sweep SHALL preserve every current manifest and every
unexpired snapshot pin. Normal selectable forecast inventory SHALL keep the
latest and previous complete run per logical stream. An existing snapshot MAY
pin a displaced immutable fragment until its fixed 15-minute deadline, but a new
snapshot SHALL NOT select an already displaced run. Snapshot and acquisition
allocations SHALL fit inside the 64 GiB hot-store quota through the issue #173
durable allocator.

Deadline expiry SHALL enter revocation and SHALL NOT free capacity by itself.
Capacity remains charged until a fenced cleaner proves remote staging, local
workspace and allocation rows reconciled. Publication and release SHALL verify
the current operation UUID and fencing token; an expired or superseded owner
cannot publish, release or overwrite its successor.

#### Scenario: A third run displaces a pinned run
- **WHEN** an unexpired snapshot pins the oldest run as a third complete run publishes
- **THEN** new selection inventory exposes only latest and previous while the existing snapshot remains readable until its deadline within reserved capacity

#### Scenario: A stale worker finishes after revocation
- **WHEN** a worker presents an expired fencing token to publish fragments or release capacity
- **THEN** the operation is refused and the current reservation remains authoritative

#### Scenario: Interrupted staging
- **WHEN** the worker restarts after abandoning a staging attempt
- **THEN** the abandoned staged rows and objects are discarded only after fenced cleanup, and the last atomically visible manifest remains current

#### Scenario: An object that no longer exists
- **WHEN** fenced cleanup deletes an object that has already been removed
- **THEN** cleanup continues and reconciles the authoritative metadata allocation rather than exposing a partial manifest
