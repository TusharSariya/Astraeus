## ADDED Requirements

### Requirement: The hot store is capped at 64 GiB and there is no cold tier
The `weather-artifacts` bucket SHALL carry a hard 64 GiB quota, set
idempotently by the worker before it enters its loop, enforced by the object
store itself and by the projection made before every download. There SHALL be
no cold, archive or overflow tier: no bytes are moved off the hot store and
nothing is read back from anywhere else. Reaching the quota SHALL fail
closed. It SHALL NOT be resolved by evicting a currently visible revision, by
publishing a thinner run, or by spilling elsewhere. A field whose source
could not be staged because the quota was reached SHALL be reported as
`retrieval failed` naming `quota_exceeded`, never as `null` and never as
`aged out`.

#### Scenario: The quota is reached mid-run
- **WHEN** projected usage for a staged revision would exceed 64 GiB
- **THEN** `QuotaExceeded` is raised before any upload, the job fails naming the cap and the projected size, the previously visible revision keeps answering, and no visible revision is evicted to make room

#### Scenario: There is nowhere to spill to
- **WHEN** the store is at the cap and a run needs room
- **THEN** the run fails, because no cold or overflow tier exists and none is created at runtime

#### Scenario: A reader asks for a field whose run was refused for room
- **WHEN** a request names a field whose only source failed staging on the quota
- **THEN** the response reports `retrieval failed` with reason `quota_exceeded`, distinct from `null`, from `blocked` and from `aged out`

#### Scenario: The quota is changed out of band
- **WHEN** the bucket quota differs from the configured 64 GiB at worker start
- **THEN** the worker resets it to the configured value and records that it did, because a quota changed with admin tools invalidates the guarantee the projection relies on

### Requirement: Retention is the sliding valid-time window used as a restart cache
The store SHALL retain exactly the frames whose valid time lies inside the
current evidence window, `now-24h` through `now+14d`, and SHALL purge a frame
once its valid time falls outside it. For a forecast source it SHALL retain
the latest complete run and the previous complete run and no more; a third
complete run SHALL displace the oldest at publication. For observation and
nowcast sources it SHALL retain the full 24 hours of history inside the
window. The store SHALL NOT accumulate a vintage archive: retaining every run
whose valid times still fall inside the window is forbidden, however much
room the quota leaves. The retained set is the restart cache and its only
purpose: it is what a restarting worker must not fetch again.

#### Scenario: A third complete run arrives
- **WHEN** a forecast source publishes a complete run while two are already retained
- **THEN** the oldest of the three is purged in the same operation that publishes the newest, and exactly two runs remain

#### Scenario: A frame falls off the back of the window
- **WHEN** a retained frame's valid time passes `now-24h`
- **THEN** it is purged and its stream records the last valid time held, so the frame is afterwards reported `aged out at <last valid time>` rather than `null`

#### Scenario: Room is available and history is still not kept
- **WHEN** the store is well below the 64 GiB cap and a run older than the previous complete run exists
- **THEN** it is purged anyway, because retention is a decision and not a consequence of free space

#### Scenario: Observations older than a day
- **WHEN** an observation frame's time passes `now-24h`
- **THEN** it is purged on the same rule as a forecast frame, and the three-hour high-cadence floor no longer applies

#### Scenario: A source with nothing inside the window
- **WHEN** every frame a source ever published has left the window
- **THEN** its fields report `aged out at <last valid time>`, the source is not reported as never retrieved, and no fetch of past frames is attempted to refill history

### Requirement: A purge never removes bytes a reader is holding open
The purge SHALL delete metadata rows before objects and SHALL never remove an
object a current pointer still references. A read in flight when a purge runs
SHALL either complete against the bytes it already verified or fail closed
with `StoreUnavailable`; it SHALL NOT return partially read bytes, and it
SHALL NOT fall back to a cached dataset whose revision the purge removed. An
object already gone SHALL NOT abort the sweep.

#### Scenario: A purge during a read
- **WHEN** the purge removes a revision while a request is downloading it
- **THEN** the request fails with `StoreUnavailable` or `ArtifactIntegrityError` and the response reports `unavailable`, rather than serving a truncated artifact

#### Scenario: A purged revision in the dataset cache
- **WHEN** a cached dataset's revision has been purged
- **THEN** it is dropped from the cache and never answers again, on the same rule that already drops a superseded revision

#### Scenario: An object already removed
- **WHEN** the purge deletes an object that is already gone
- **THEN** the sweep continues, because the metadata row is the record of truth

### Requirement: The store records the last valid time it held for every stream
For every logical stream the store SHALL record the latest valid time it has
ever held, and SHALL keep that record after the frames themselves are purged.
An absence caused by purging SHALL be reported as `aged out` carrying that
time. A stream with no such record SHALL report `null`, never `aged out`,
because a deployment that never held a frame must not claim it did.

#### Scenario: A stream that was held and purged
- **WHEN** a request names an instant a purged frame covered
- **THEN** the response reports `aged out at <last valid time>` naming the source

#### Scenario: A stream that was never held
- **WHEN** a request names a source that has never published here
- **THEN** the response reports `null`, because there is no last valid time to state

#### Scenario: The last-valid-time record cannot be read
- **WHEN** the metadata store cannot answer for a stream
- **THEN** the response reports `unavailable` naming that failure, never `aged out` and never `null`, because guessing which absence applies is itself a fabrication

## MODIFIED Requirements

### Requirement: The object exists before the row that points at it
Staging SHALL upload the immutable object first, compute its true SHA-256 and byte size, and only then insert the `staged` revision row carrying that digest and size. Storage room SHALL be reserved before the download, so an oversize artifact is never uploaded. Room SHALL be projected against the 64 GiB hot quota, counting the two-run staging overlap, and SHALL be refused with `QuotaExceeded` before any bytes are fetched. A projection SHALL NOT be satisfied by planning to purge a frame that is still inside the evidence window.

#### Scenario: Ordering
- **WHEN** an artifact is staged
- **THEN** the `put_object` call precedes the metadata insert, so publication can never expose a key with nothing behind it

#### Scenario: The cap is checked first
- **WHEN** staging an artifact that would exceed the 64 GiB cap
- **THEN** `QuotaExceeded` is raised before any upload, the job fails, and no visible revision is evicted to make room

#### Scenario: Replacing an existing revision
- **WHEN** projecting usage for an artifact that replaces one already staged
- **THEN** the replaced bytes are credited back in the projection

### Requirement: Staging debris is discarded without touching visible revisions
A restart sweep SHALL delete only `staged` revisions older than the abandoned-staging age and their objects, preserving every current pointer. Retention SHALL keep the latest and previous complete run per forecast stream and every observation or nowcast frame whose time lies inside the evidence window, purging every frame whose valid time falls outside `now-24h .. now+14d`. Rows SHALL be deleted before their objects, and an object already gone SHALL NOT abort the sweep. The sweep SHALL NOT delete a staged revision belonging to a run the worker is still fetching; a run abandoned mid-publication SHALL leave the previous visible run current.

#### Scenario: Interrupted staging
- **WHEN** the worker restarts after abandoning a staging attempt
- **THEN** the abandoned staged rows and objects are discarded and the last atomically visible run is still current

#### Scenario: An object that no longer exists
- **WHEN** deleting an object that has already been removed
- **THEN** the sweep continues, because the metadata row is the record of truth
