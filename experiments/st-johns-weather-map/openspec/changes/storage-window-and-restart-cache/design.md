# Design

## Why 64 GiB and not more

`docs/research/wayfinder/size-probe-full-fields.md` measured three scenarios
resident, then added the two-run staging overlap `infra/STORAGE.md` already
mandates and about 20 percent headroom for container and manifest overhead:
core only needs about 18 GB, core plus planning reductions about 27 GB, core
plus planning with subsetted ensemble members about 44 GB. 64 GiB is the
smallest round quota that holds the widest scenario with real headroom, so a
sizing decision does not have to be revisited every time the catalogue grows
a family. It is not chosen to leave room for history: history is what the
sliding window deliberately does not keep.

The dominant consumer is unchanged. HRDPS at 377 coverages is 5.53 GB and 74
percent of the core scenario, of which 3.02 GB is its 206 pressure-level
coverages. If the quota ever binds, that is the first place to look.

## Why no cold tier

A cold tier would only be worth building if something needed to be read back
after it left the window. Verification scoring is out of scope (wayfinder
ticket 5) and forecast vintages are explicitly not retained. A tier with no
reader is a second failure mode with no benefit, and it would give the store
somewhere to spill to at the quota, which is exactly the fail-closed
behaviour this project does not want weakened. Reaching the quota must be a
failure the worker reports, not a condition the store silently resolves.

## Why a sliding valid-time window rather than a run-age window

The natural alternative is to retain by run age: keep every run issued in the
last N hours. Every source has its own cadence, so that expresses a different
amount of history per source, and it says nothing about what a reader can
actually be shown. A valid-time window says exactly one thing, in the units
the reader asks in: a frame is retained if and only if a request could name
its instant. The window bounds the API, the `FetchWindow`, the QC gate and
retention with one number pair, so those four cannot drift apart the way the
28-hour window and the 14-day planning tier already have.

The back edge is 24 hours rather than the 3 hours the current window uses,
because the core horizon tier is `24 h back to 24 h ahead` (wayfinder ticket
23) and because a day of observations is what makes a forecast frame's own
verification-free comparison legible to a reader. The forward edge is 14 days
because that is the planning tier and the furthest any admitted source
reaches (GFS, GEFS and GEPS at 384 h; the ECMWF families at 360 h).

## Why two runs per forecast source, and why that is not an archive

Atomic publication already needs the previous complete run to stay visible
while the next one stages, and a reader comparing the latest run against the
previous one sees run-to-run change without any statistic being computed.
That is the whole benefit, and it costs one extra run.

Retaining every run whose valid times still fall inside a 14-day window is a
different thing entirely: HRDPS alone would be dozens of runs, and the store
would become a vintage archive by accident rather than by decision. The owner
recorded that as an assumption on wayfinder ticket 20 and can override it
there. Until then the rule is stated as a ceiling, not as a consequence: two
runs per forecast source, and a third displaces the oldest at publication.

## The idempotency key

`(source_id, provider_run_id, valid_time)`. The provider run id comes from
the provider's own stamp, never from the ingest clock, which
`artifact-ingestion` already requires because deriving it from `now`
mislabels every run fetched after 00Z from the previous day's directory. The
frame time is compared as integer nanoseconds, as the out-of-window gate
already does, so a resolution difference cannot read as a missing frame.

A restart therefore asks one question per frame the window wants: is there a
published artifact for this key. Only the answers that are no become fetches.
An observation stream keys on its observation time in the same way.

## Why derived artifacts are recomputed rather than re-fetched

A derived-here artifact has no upstream to fetch from; its inputs do. If a
restart treated a missing derived artifact as a missing retrieval it would
re-fetch inputs that are already on disk, which is the expensive direction on
the constraint that actually binds. Recomputation reads the retained inputs
and nothing else. Where an input has aged out, the derived artifact is absent
and reports the aged-out state of its input, because a derivation whose input
is gone must not reach for a substitute.

## The three absence states, and the two that already existed

- `null`: never retrieved. Nothing was held.
- `blocked`: a licence, credential or partnership prevents retrieval
  (wayfinder tickets 19 and 25).
- `aged out at <last valid time>`: this deployment held the frame and purged
  it because its valid time left the window. New here.

Two neighbouring states stay distinct and must not be folded in.
`retrieval failed` means an attempt was made and broke, which is a live
condition a retry may clear. `available-not-stored`
(`field-catalogue-and-families`) means the producer publishes the field and
this deployment chose not to fetch it, which no retry clears. An aged-out
report carries the last valid time the store held, so the reader is told the
edge of what was ever available, not merely that something is gone.

## Seam: the restart cache, fixed before sections 3 and 4 started

The ingest owner and the storage owner code against this at the same time, so
it is written down rather than negotiated afterwards. Three methods on the
store, implemented in `ingest/store.py` over the existing schema and matched by
the storage owner on the API-side store:

    present_keys(source_id, provider_run_id) -> set[int]
        The valid times, as integer nanoseconds, already published under that
        run key. Read from the published revisions' own declared
        `valid_times`; a revision that declared none contributes nothing, so
        the worker fetches rather than assuming a frame it cannot see is
        present. Raises `StoreUnavailable` when the store cannot answer, which
        the scheduler turns into a failed source: an unknown cache state is not
        an empty one.

    sweep_abandoned_staging() -> int
        Discard staged rows older than the abandoned-staging age and their
        objects, preserving every current pointer. Named alias of the existing
        `restart()`, so the reconciliation reads as the three steps
        `ingestion-worker-scheduling` names.

    purge_outside_window(now) -> int
        Delete every retained revision all of whose declared valid times lie
        outside `sliding_window(now)`. Rows before objects; an object already
        gone does not abort the sweep; a revision that declared no valid times
        is left to `prune()`, which judges by run position, because purging on
        an instant the store cannot read would be purging on a guess.

The window itself is `WINDOW_BACK`, `WINDOW_FORWARD` and `sliding_window(now)`
in `api/weather_api/config.py`, read by `ingest` through `ingest/window.py`.

    WINDOW_BACK    = timedelta(hours=24)
    WINDOW_FORWARD = timedelta(days=14)
    sliding_window(now: datetime) -> tuple[datetime, datetime]
        UTC-aware `(now - WINDOW_BACK, now + WINDOW_FORWARD)`, both boundaries
        inclusive. A naive `now` is refused rather than assumed to be UTC.

`config.py` also carries what is sized from the window and must not drift from
it: `WINDOW_STEPS` (361), `STORAGE_CAP` / `STORAGE_CAP_BYTES` (64 GiB),
`KEEP_COMPLETE_RUNS` (2), `OBSERVATION_RETENTION` (= `WINDOW_BACK`),
`COLD_TIER` (`None`) and `AGED_OUT_FLAG`. It imports nothing but the standard
library, which is what lets `ingest/window.py` load it by path.

### The retention seam, storage side

The rules live in `infra/postgres/init/003_retention_window.sql`, because
publication and purge have to commit together and because the object keys a
purge frees must be queued by the same transaction that deleted their rows.
There is one purge: `ArtifactStore.purge_outside_window(now)` delegates to it
rather than deciding anything itself.

    weather_experiment.evidence_window(at)         -> (window_start, window_end)
    weather_experiment.purge_outside_window(at)    -> integer revisions purged
    weather_experiment.record_last_valid_time(source, stream, until)
    weather_experiment.claim_purged_objects(batch) -> setof object_key
    weather_experiment.reclaimable_bytes(at)       -> bigint
    weather_experiment.stream_last_valid_time      (table, never lowered)
    weather_experiment.purged_objects              (queue, rows before objects)
    weather_experiment.publish_run(run)            -> publishes AND purges

`publish_run` is replaced, not wrapped, so a caller cannot publish without
purging: a third complete run displaces the oldest in the same transaction that
makes the newest visible. A trigger stamps `artifact_revisions.valid_time_start`
/ `valid_time_end` from the artifact's own declared `valid_times` at insert, so
no adapter and no ingest code had to change for retention to become true.

Python callers, in `api/weather_api/store.py`, each taking either the
`LiveStore` reader or the `ArtifactStore` itself:

    published_frame_times(store, *, source_ids=None)
        -> dict[(source_id, provider_run_id), set[int]]   # nanoseconds
    stream_last_valid_times(store) -> dict[(source_id, logical_name), datetime]
    last_valid_times(store)        -> dict[source_id, datetime]
    record_last_valid_time(store, *, source_id, logical_name, valid_time)
    purge_outside_window(store, *, now=None, sweep=True) -> PurgeResult
    drain_purged_objects(store, *, batch=1000) -> (deleted, missing)
    reclaimable_bytes(store, *, now=None) -> int
    assert_room_for(store, additional_bytes, *, replacing_bytes=0, now=None)
    absence_state(store, source_id, *, held=...) -> (state, last_valid_time)

All of them raise `StoreUnavailable` rather than answering when the store
cannot be asked: an unknown cache state is not an empty one, and guessing
between `aged_out` and `null` is itself a fabrication.

### The absence state on the wire

Pinned here because the client was reading two carriers for the same fact.
One carrier: **`quality.flags`**. `quality.status` keeps exactly its four
values (`passed`, `suspect`, `failed`, `unknown`) and is never used to signal
an absence; ageing out is a retention fact about the store, not a verdict on
the value.

A field that is outside the window's retained set answers:

    value:                       null
    data_mode:                   "unavailable"
    quality.status:              unchanged, one of the four
    quality.flags:               ["aged_out", "aged_out:<source_id>", ...]
    provenance.last_valid_time:  an ISO instant with an offset

`aged_out`, `blocked` and `retrieval_failed` all ride `quality.flags`.
`available-not-stored` stays on `EvidenceField.storage`, which is where
`field-catalogue-and-families` put it. `last_valid_time` is null on every
value that is not an aged-out absence, and `Provenance` refuses `aged_out`
without one - a deployment that never held a frame must not claim it did, so
the flag and the instant stand or fall together and the client never has to
render an `aged_out` it cannot date.

The five states stay distinct and are named once, in
`weather_api.store.ABSENCE_STATES`:
`("null", "blocked", "aged_out", "retrieval_failed", "available-not-stored")`.

`/timeline` carries the same fact per hour, for the web to pick up later:

    items[].aged_out_sources: {"<source_id>": "<ISO instant>", ...}

It is empty for any hour that lists a product, and empty for every hour when
the store could not be read (a notice says so instead) - so an hour that holds
nothing and names nothing is an hour nothing ever covered. `/ready` and
`/layers` carry the same mapping at the response level as `aged_out_sources`.

A fourth method exists on the ingest side only, because the conflict is a
staging decision and never a read: `published_digests(source_id,
provider_run_id) -> dict[str, str]`, which `assert_run_identity` compares
against a fetched artifact's digest before the run row is touched, raising
`RunIdentityConflict`.

## Deviations recorded during implementation (section 4)

- **`ingest/window.py` loads the definition by file path, not as a package
  import.** `weather_api/__init__.py` imports the FastAPI app, which imports
  `ingest.contract`, which needs the window: importing `weather_api.config`
  the ordinary way is a cycle. The one module is loaded by path instead, so
  there is still exactly one definition and one file. It does mean the worker
  image must ship `api/weather_api/config.py`; it currently copies only
  `ingest/`, `registry/source_data.py` and `worker/`, so `worker/Dockerfile`
  needs that one `COPY` line before a live worker cycle can run. Left to the
  owner of the image packaging rather than edited here.

- **`FetchWindow.back_hours` / `forward_hours` became floats reading the
  shared offsets** rather than the literals `3` and `24`. They stay as
  parameters so a test can deliberately narrow the window; nothing in the
  adapters passes them.

- **The out-of-window gate moved out of `ingest/manifest.py` into
  `ingest/validate.py`.** `validate_run` calls `out_of_window_verdict` and
  raises whatever it returns. `_MAX_REPORTED_OUT_OF_WINDOW` stays in
  `manifest` as an alias so existing importers resolve.

- **`no_step_in_window` is a distinct flag, not an `out_of_window` one.** The
  spec requires a run carrying no in-window valid time to be refused; giving
  it an `out_of_window:` prefix would have made it count against the
  five-flag cap and read as one more misplaced step rather than as the run
  answering nothing the window asks about.

- **`null` outranks `aged_out` as a derived artifact's "worst" input state.**
  The spec says to report the worst input's state without ordering the two.
  An aged-out input names a last valid time the reader can act on; a null
  input says nothing was ever held here. Reporting the less informative state
  is the conservative direction.

- **The 25 GiB literals in `ingest/store.py` became the configured cap.**
  `LOCAL_STORAGE_CAP_BYTES` is 64 GiB, `QuotaExceeded` formats its message
  from `config.cap_bytes` rather than a literal so the outcome names whatever
  is configured, and `OBSERVATION_RETENTION` became 24 hours. Section 1 owns
  the same constant for the compose configuration and the bootstrap; this is
  the same value on both sides. Two assertions in `tests/test_ingest_store.py`
  that pinned 25 GiB were re-pinned to 64 GiB.

- **Three window assertions in `tests/test_ingest_manifest.py` were re-pinned.**
  They chose instants at `-8 h` and `+48 h` to be outside the old window;
  those are inside the new one, so they now use `-48 h` and `+15 d`.

## Deviations recorded during implementation (sections 1, 2, 3 and 5.1)

- **Retention moved into SQL rather than staying in Python.** The proposal's
  Impact list put the purge sweep in `api/weather_api/store.py`. It could not
  live only there: publication and purge have to be one transaction, the last
  valid time has to be recorded before the frames it describes are deleted, and
  the `current_artifacts` pointer has to go in the same statement as the
  revision or the foreign key refuses the delete. So the rules are
  `infra/postgres/init/003_retention_window.sql` and the Python on both sides
  asks that one function. `ingest/store.py::purge_outside_window`, which the
  ingest owner had implemented over the existing schema, now delegates to it -
  one purge, not two. Its three unit tests in `tests/test_worker_restart.py`
  were rewritten to assert the delegation; which frames leave the window is
  proved against a real PostgreSQL in
  `infra/postgres/tests/retention_invariants.sql`.

- **The valid-time span is stamped by a trigger, not by the caller.** Every
  adapter writes its own provenance shape and none of them agree, so reading
  the span out of `provenance->'valid_times'` at insert is the one place that
  holds for all of them. A revision that declares no frame times falls back to
  its run time rather than becoming unpurgeable.

- **The purge queues object keys instead of deleting them inline.** Rows before
  objects is a requirement, and the row deletion is inside a transaction that
  cannot also be doing S3 calls. `weather_experiment.purged_objects` holds the
  freed keys and `claim_purged_objects` hands each out once, so a sweep that
  dies mid-way resumes rather than leaking.

- **`scripts/sql-test.sh` runs every proof in `infra/postgres/tests/`**, each
  in its own psql session, requiring an `ALL … INVARIANTS HOLD` sentinel from
  each. It previously named `publication_invariants.sql` alone, so a second
  proof file would have been silently unrun.

- **`TimelineItem.aged_out_sources`, `ReadyResponse.aged_out_sources` and
  `LayersResponse.aged_out_sources` are new response fields.** The spec
  requires an emptied hour to state which of its sources aged out and
  readiness to say aged out rather than never retrieved; neither response had
  anywhere to put it. `ReadyResponse` also gained `notices`, so an unreadable
  last-valid-time record can name the failure instead of being reported as an
  absence.

- **The bootstrap resets the quota by setting it unconditionally and reports
  when the bucket was carrying something else**, rather than reading the value
  and branching. `mc quota set` was already idempotent; what was missing was
  the deployment saying that it had overridden an out-of-band value.

- **Two existing window assertions in `tests/test_wms_proxy.py` were
  re-pinned.** The proxied-layer extent test advertised 48 hourly frames to be
  partly outside the window; 48 hours is now well inside it, so it advertises
  400. The satellite scan test asserted 12 to 19 ten-minute scans (about three
  hours); the window reaches 24 hours back now, so it asserts about a day. Both
  still prove the advertised extent is intersected with the window rather than
  passed through.

## Open questions carried into implementation

- Whether the purge runs on a timer or at publication. Publication is
  simpler and keeps the store quiet, but a stack idle for a day would keep
  frames past the window edge until the next run publishes.
- The grace period for an artifact a reader has open when the purge decides
  to remove it, and whether the object store's own delete latency makes an
  explicit lease unnecessary.
- Whether observations and nowcasts should be purged on their native cadence
  or on the same sweep as forecasts.
