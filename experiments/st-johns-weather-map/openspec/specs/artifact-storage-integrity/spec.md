## Purpose
Define how validated runs become durable, immutable, atomically visible artifacts in MinIO plus PostgreSQL, and how a reader proves that the bytes it opens are the bytes that were published, so that a truncated, substituted, superseded or half-written artifact is treated as an outage rather than as evidence.

## Requirements

### Requirement: A run is published as one unit or not at all
Every artifact of one run SHALL be staged first and published together in a single transaction through the schema's own `publish_run` function. Publication SHALL be refused unless the parent run row is itself `complete` and `qc_passed`. There SHALL be no partially published run: a failed manifest validation leaves the prior `current_artifacts` pointer exactly where it was.

#### Scenario: An incomplete or failed-QC run
- **WHEN** a run's verdict has `complete=False` or `qc_passed=False`
- **THEN** its artifacts may be staged but `publish_run` is never called, and the previously visible revision continues to answer

#### Scenario: A crash between artifacts
- **WHEN** the worker is interrupted after staging some artifacts of a run
- **THEN** no logical stream has advanced, because visibility flips once per run rather than once per revision

#### Scenario: A run with no artifacts
- **WHEN** a run produced no artifacts
- **THEN** neither the object store nor the metadata store is touched

#### Scenario: Publication logic is not reimplemented in Python
- **WHEN** a revision or run is published
- **THEN** the flip is delegated to the schema function, never performed by application-side updates

### Requirement: The object exists before the row that points at it
Staging SHALL upload the immutable object first, compute its true SHA-256 and byte size, and only then insert the `staged` revision row carrying that digest and size. Storage room SHALL be reserved before the download, so an oversize artifact is never uploaded.

#### Scenario: Ordering
- **WHEN** an artifact is staged
- **THEN** the `put_object` call precedes the metadata insert, so publication can never expose a key with nothing behind it

#### Scenario: The cap is checked first
- **WHEN** staging an artifact that would exceed the 25 GiB cap
- **THEN** `QuotaExceeded` is raised before any upload, the job fails, and no visible revision is evicted to make room

#### Scenario: Replacing an existing revision
- **WHEN** projecting usage for an artifact that replaces one already staged
- **THEN** the replaced bytes are credited back in the projection

### Requirement: Bytes are verified against the recorded digest and size on read
Before an artifact is cached or parsed, the downloaded bytes SHALL be checked against the size and SHA-256 recorded when the revision was staged. A mismatch, or a revision with no recorded digest, SHALL raise `ArtifactIntegrityError` and be treated as unavailable. The verified file SHALL only be moved into place after verification; a partial download SHALL be removed.

#### Scenario: The digest does not match
- **WHEN** the downloaded bytes hash to something other than the recorded SHA-256
- **THEN** the artifact is refused and reported as a skip, never parsed and never served

#### Scenario: The size does not match
- **WHEN** the byte count differs from the recorded size
- **THEN** the artifact is refused with the recorded and observed sizes stated

#### Scenario: No digest was recorded
- **WHEN** a revision carries no `sha256` in its provenance
- **THEN** the bytes are unverifiable and are therefore treated as unavailable, not as evidence

### Requirement: A reachable metadata store is not a reachable object store
Every sampling and coverage path SHALL probe the object store before answering, because PostgreSQL and MinIO fail independently. With the object store unreachable, a cached dataset SHALL NOT keep answering: a revision may have been superseded and cannot be checked, so a cached answer would present withdrawn evidence as current.

#### Scenario: The object store has gone away
- **WHEN** MinIO is unreachable while PostgreSQL still answers
- **THEN** `StoreUnavailable` is raised and the API reports `unavailable`, rather than serving from the in-process dataset cache

#### Scenario: The answer does not depend on process uptime
- **WHEN** the same request is made in a long-running process and in a freshly started one under the same outage
- **THEN** both report unavailable, because a truth boundary that depends on how long the process has been up is not a boundary

#### Scenario: A superseded revision is forgotten
- **WHEN** a cached revision is no longer among the current artifacts
- **THEN** its dataset is dropped from the cache

#### Scenario: The dataset cache is bounded
- **WHEN** more than the maximum number of datasets have been opened
- **THEN** the least recently used entries are evicted, because every new run mints new revision ids and an unbounded cache would grow without limit

### Requirement: Staging debris is discarded without touching visible revisions
A restart sweep SHALL delete only `staged` revisions older than the abandoned-staging age and their objects, preserving every current pointer. Retention SHALL keep the latest and previous complete run per logical stream, with high-cadence observations additionally retained for three hours. Rows SHALL be deleted before their objects, and an object already gone SHALL NOT abort the sweep.

#### Scenario: Interrupted staging
- **WHEN** the worker restarts after abandoning a staging attempt
- **THEN** the abandoned staged rows and objects are discarded and the last atomically visible run is still current

#### Scenario: An object that no longer exists
- **WHEN** deleting an object that has already been removed
- **THEN** the sweep continues, because the metadata row is the record of truth

### Requirement: Missing store configuration is reported, not defaulted
Store configuration SHALL be read from the environment and SHALL raise `StoreUnavailable` naming the missing variables rather than substituting defaults. The storage cap SHALL be parsed from its configured unit suffix.

#### Scenario: A missing database URL or bucket
- **WHEN** any of the required store environment variables is absent or blank
- **THEN** `StoreUnavailable` is raised naming exactly which are missing

### Requirement: Zarr artifacts are deterministic and round-trip before they are trusted
A normalized dataset SHALL be written to a temporary directory store and only then zipped with sorted entries, fixed timestamps and no compression, so the same dataset always produces the same bytes and the recorded SHA-256 means something. The archive SHALL be reopened and checked for every expected variable and coordinate before the caller may hash and upload it.

#### Scenario: A duplicate metadata entry
- **WHEN** an artifact is written
- **THEN** it is not written directly into a zip store, because appending rather than replacing left two copies of every metadata document and emitted duplicate-name warnings

#### Scenario: A round-trip that loses a variable
- **WHEN** the reopened archive is missing an expected variable or coordinate
- **THEN** writing fails with a `GribError` naming what was lost, because an artifact that does not reopen is worse than no artifact — it publishes as evidence
