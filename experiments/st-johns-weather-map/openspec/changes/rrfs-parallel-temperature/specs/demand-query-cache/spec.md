## ADDED Requirements

### Requirement: Parallel RRFS temperature remains an isolated native experiment
The experimental reader SHALL select only RRFSv1.0 parallel North America
13-km `2dfld` instantaneous two-metre TMP, preserving deterministic identity,
exact run/validity, native K, native bitmap masks and unknown producer QC.
It SHALL remain operational false and SHALL NOT register public point delivery,
substitute REFS or RRFS3km, or claim a complete-model field manifest.

#### Scenario: Native product identity differs
- **WHEN** the message carries another process, level, time or rotated grid
- **THEN** decoding fails before a point is returned

### Requirement: Native selected-message access and caching stay finite
The reader SHALL fetch at most a 64-KiB index and one indexed message of at
most 2 MiB, require exact HTTP range compliance, and decode in the existing
bounded Linux process. It SHALL retain at most one 8-KiB point for a fixed
300 seconds, share concurrent identical acquisitions and refuse expired data.

#### Scenario: Explicit refresh fails with a fresh point already retained
- **WHEN** acquisition fails before the old point's original expiry
- **THEN** an ordinary read may still return that point until its original expiry

#### Scenario: The server sends a full forecast file
- **WHEN** the indexed range request returns HTTP 200 or mismatched Content-Range
- **THEN** the response is refused without decoding a full file
