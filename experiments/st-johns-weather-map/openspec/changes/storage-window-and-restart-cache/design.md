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

## Open questions carried into implementation

- Whether the purge runs on a timer or at publication. Publication is
  simpler and keeps the store quiet, but a stack idle for a day would keep
  frames past the window edge until the next run publishes.
- The grace period for an artifact a reader has open when the purge decides
  to remove it, and whether the object store's own delete latency makes an
  explicit lease unnecessary.
- Whether observations and nowcasts should be purged on their native cadence
  or on the same sweep as forecasts.
