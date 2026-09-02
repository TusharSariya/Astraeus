# Design

## Why a tier is a range and not a source list

The obvious reading of "assign sources to the two horizon tiers" is a
partition: HRDPS and radar in the core tier, GFS and the ensembles in the
planning tier. That reading fails on the measurements. GFS is hourly to f120
and reaches 384 h, so a partition that puts it in the planning tier deletes a
source that covers hour 3 as well as day 14. ICON stops at 180 h, so a
partition that puts it in the planning tier promises a coverage it cannot keep
past day 7. IFS reaches 360 h at 00z and 12z and 144 h at 06z and 18z, so its
tier would change four times a day.

Making the tier a valid-time range moves the variable to where it actually
lives: the source's own reach. The tier then says only what the reader is
looking at, and the reach says what can answer. Coverage at an instant is a
containment test, computed, not a table someone maintains.

## Why scheduling needs measured latency and not just cadence

`source-registry-catalogue` derives cadence from the registry's prose, and the
worker schedules on it. A 00z GFS run scheduled at 00z finds nothing: the
measured publication of its final lead was T+5 h 18 m. The failure is not
harmless, because `run_source` classifies "upstream had nothing usable" as
`cancelled`, so a schedule that is systematically early manufactures a stream
of cancellations that look like an upstream problem.

Cadence plus measured latency puts the first attempt where the run has actually
been observed to appear. Polling covers the variance around that estimate, and
the ten-minute interval is bounded so a run that never appears cannot spin: the
poll stops at the next scheduled run time for that source, because at that
point the missing run is superseded, not late.

The estimate must be re-measured because it is not a constant. GDPS layer
availability is not even atomic within one run (total cloud on the 00z run
beside 2 m humidity still on the previous 12z, in one capabilities document),
so latency is a per-source measured quantity with a spread, not a producer
promise. The heartbeat already carries per-source ingestion progress and is
written atomically before each source, which makes it the right place to record
the observed publication instant.

## Starting latency values, and what they are not

| Source | Run cadence | Starting latency |
| --- | --- | --- |
| DWD ICON global | 00/06/12/18 | about T+3.5 h |
| NOAA GFS | 00/06/12/18 | about T+5.3 h |
| NOAA GEFS | 00/06/12/18 | about T+5.3 h, final leads later, unbounded above |
| ECMWF IFS, IFS ENS, AIFS single, AIFS-ENS | 00/06/12/18 | about T+7.6 h |
| ECCC GDPS, GEPS (GeoMet) | 00/12 | unmeasured, bounded below only |
| ECCC REPS | 4 per day | unmeasured |

These are three live measurements taken on 2026-09-02 and recorded in
`docs/research/wayfinder/planning-horizon-matrix.md`. They are seed values for
the estimator, not producer commitments. A source with no measured latency
starts polling at its run time and carries `latency_measured: false` until the
worker has observed a publication, which is why the spec makes an absent
latency a stated condition rather than a default.

## Why staleness is two separate facts

Frame staleness asks whether the instant on the screen is near a published
frame. Run staleness asks whether the run that produced that frame is still
current. The two come apart in exactly the case that matters: a 14-day forecast
frame from a run published thirty hours ago sits perfectly inside a six-hour
step tolerance and is still evidence from a run that has been superseded twice.
Half a cadence answers neither question well, and it is the reason the existing
tolerance is three minutes for radar when the layer's own interval is six.

One native interval is the layer's own resolution: within it there is a frame
that genuinely belongs to the requested instant. Twice the producer cadence is
the run equivalent: one missed run is a delay, two is a source that has stopped
publishing. `run_stale` is a flag on the frame and never a reason to hide it,
because a stale run that is the only evidence is still the only evidence, and
the governing rule forbids substituting anything for it.

## Why a short cycle keeps the previous run

IFS at 06z reaches 144 h where the 00z run reached 360 h. Dropping to the newest
run everywhere would delete nine days of already-retrieved evidence four times a
day. Keeping the previous run for the leads the new one lacks retains it, and
labelling both with their run time keeps the reader from reading a single
continuous curve across two runs. What is forbidden is blending them or
presenting the join as one series: two runs are two pieces of evidence, shown
as two.

## Seam

Fixed before any owner started (2026-09-02), so the registry, the worker, the
API and the web are built against one vocabulary. Names below are the names
on the wire and in code; the spec deltas use the same ones.

### Where the code lives

`tasks.md` was written before the code existed. The owned files are:

- registry: `registry/source_data.py`, `registry/schema.json`,
  `registry/audit.py`, `registry/README.md`, `registry/tests/test_reach.py`,
  and the scheduler-facing view `ingest/registry.py` (`IngestConfig`).
- worker: `ingest/scheduler.py` (pure decisions) and `worker/runtime.py`
  (effects, heartbeat), `ingest/adapters/eccc_datamart.py` (the declared
  fallback path), tests `api/tests/test_worker_scheduling.py` and
  `api/tests/test_worker_heartbeat.py`.
- API: `api/weather_api/app.py`, `models.py`, `store.py`, `grids.py`,
  `satellite.py`, `aurora.py`, the read side of `ingest/store.py`
  (`retained_artifacts`), tests `api/tests/test_timeline.py` and
  `api/tests/test_layers.py`.
- web: `web/src/TimelineDock.tsx`, `App.tsx`, `api.ts`, `types.ts`,
  `styles.css`, new `CoveragePanel.tsx`, `tierBoundary.ts`, `runSegments.ts`
  and tests `boundary.test.tsx`, `coverage.test.tsx`, `runchange.test.tsx`.

### Registry record fields (`registry/source_data.py`, validated by `registry/audit.py`)

All optional in `schema.json`; the audit requires them where a registered
adapter exists (source ids parsed statically from `ingest/adapters/*.py`,
the way `declared_field_keys` parses field keys).

```
"reach": {
  "earliest_hours": 0,                       # earliest valid time relative to run time, hours (negative = before)
  "latest_hours": 48,                        # latest valid time relative to run time, hours
  "per_cycle": {"00": 360, "06": 144, "12": 360, "18": 144}   # optional; latest_hours by UTC run hour "HH"
}
"run_cadence_seconds": 21600                 # forecast records (category in ingest.registry.FORECAST_CATEGORIES); absent elsewhere
"native_cadence_seconds": 360                # observation and nowcast records; absent on forecast records
"publication_latency": {                     # forecast records only
  "estimate_seconds": 19080,                 # null when nothing is measured and no seed exists
  "observation_count": 0,
  "last_observed": null,                     # ISO instant of the most recent observed publication
  "measured": false,                         # true only after this deployment observed a publication
  "basis": "seed: docs/research/wayfinder/planning-horizon-matrix.md, 2026-09-02"   # or "none"
}
"datamart_fallback_path": "https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/continental/2.5km/{HH}/{FFF}/"   # ECCC Datamart records only
```

An observation covers its own instant: `reach = {"earliest_hours": 0,
"latest_hours": 0}`. Seeds: ICON 12600 s, GFS 19080 s, GEFS 19080 s (final
leads later, unbounded above; say so in `basis`), the four ECMWF records
27360 s. GDPS, GEPS, REPS and WeatherNext 2: `estimate_seconds: null`,
`measured: false`, `basis: "none"`.

Audit rules: a registered-adapter record must carry `reach`; a forecast one
must carry an integer `run_cadence_seconds > 0` and a `publication_latency`
block; a non-forecast one an integer `native_cadence_seconds > 0`.
`measured: false` requires `observation_count == 0` and `last_observed:
null`; `estimate_seconds: null` requires `measured: false`; a non-null
estimate requires a non-empty `basis`; `measured: true` requires
`observation_count >= 1` and `last_observed`. `per_cycle` keys are two-digit
UTC hours and their count matches `86400 / run_cadence_seconds`.

### `ingest/registry.py`

```python
@dataclass(frozen=True)
class Reach:
    earliest_hours: float
    latest_hours: float
    per_cycle: Mapping[str, float] = field(default_factory=dict)   # "HH" -> latest_hours
    def latest_hours_for(self, run_time: datetime) -> float: ...       # per_cycle[run_time UTC "%H"] else latest_hours
    def span(self, run_time: datetime) -> tuple[datetime, datetime]: ...
    def covers(self, run_time: datetime, instant: datetime) -> bool: ...

@dataclass(frozen=True)
class PublicationLatency:
    estimate_seconds: int | None
    observation_count: int
    last_observed: datetime | None
    measured: bool
    basis: str

class IngestConfig:  # new fields, all defaulting to None
    reach: Reach | None
    run_cadence_seconds: int | None
    native_cadence_seconds: int | None
    publication_latency: PublicationLatency | None
    datamart_fallback_path: str | None
    # ingestible now also requires reach is not None and one of the two cadences
```

### Worker (`ingest/scheduler.py`, `worker/runtime.py`)

- `POLL_INTERVAL_SECONDS = 600`. Forecast first attempt: `run_time +
  publication_latency.estimate_seconds` when the estimate is not null, else
  `run_time`; then a poll every 600 s bounded by the next run time. The
  bounded cancellation detail reads
  `run <provider_run_id or run_time ISO> did not appear after polling <N> min; previous run stays visible`.
- Observation and nowcast sources: rescheduled every `native_cadence_seconds`.
- Heartbeat `sources[source_id]` gains
  `"publication_latency": {"estimate_seconds", "observation_count", "last_observed", "latency_measured", "basis"}`
  and `"last_observed_publication": ISO | null`. Written only from an
  observed publication; a run that never appeared leaves it untouched.
- The short-cycle decision is a pure function
  `short_cycle_plan(previous_run, newest_run) -> ShortCyclePlan` naming which
  leads each run serves; the API serves them (below).
- ECCC Datamart: when the primary path answers nothing, the adapter tries
  `datamart_fallback_path` (only when declared) and records the answering
  path in `RunResult.notes` and each artifact's `provenance["datamart_path"]`.

### API responses

`TimelineResponse` gains:

```
"boundary": ISO                                  # reference + 24 h
"tiers": [{"id": "core", "start": ISO, "end": ISO}, {"id": "planning", "start": ISO, "end": ISO}]
```

`TimelineItem` gains:

```
"tier": "core" | "planning"
"coverage": [ {"source_id": str, "provider_run_id": str, "run_time": ISO | null,
               "run_cadence_seconds": int | null, "run_age_seconds": int | null,
               "run_stale": bool | null, "run_stale_reason": str | null} ]   # sorted by source_id then run_time; [] = nothing covers
"coverage_notice": str | null                    # "nothing covers this instant" when [] and the store answered; null otherwise
```

Coverage of an hourly item = declared `Reach.covers(run_time, hour)` for a
retained run, intersected with the span of frames that run actually
published. A run's `run_time` is the adapter-declared
`provenance["run_time"]`; `model_runs.run_time` is stamped with the
retrieval time when an adapter declared none and is never a run-time claim.

`Layer` gains (all with defaults so the fixtures, satellite, aurora and grid
constructors keep working):

```
"run_time": ISO | null
"run_stale": bool | null
"run_stale_reason": str | null                   # required when run_stale is null
"run_cadence_seconds": int | null
"frames": [{"valid_time": ISO, "run_time": ISO | null, "provider_run_id": str | null, "run_stale": bool | null}]   # one per entry of `times`, same order
"runs": [{"provider_run_id": str, "run_time": ISO | null, "run_stale": bool | null, "frame_count": int}]
```

`run_stale = run_age > 2 * run_cadence_seconds`; null with
`run_stale_reason` when the run time or the cadence is unknown, and on
observation layers ("observation layer: no run concept"). A refused instant
outside both tiers names both ranges. `staleness_tolerance_seconds` =
`cadence_seconds` (min 60), 900 when the cadence cannot be derived.
`Provenance` gains `run_stale: bool | None = None` and
`run_stale_reason: str | None = None`, set on live `/point` fields.

`ingest/store.py` gains a read `retained_artifacts(source_ids=None)`
returning the current revision and, where the previous complete run is still
retained under the two-run ceiling, that run's superseded revisions, each
tagged with its `provider_run_id` and `run_time`. `/layers` serves the leads
the newest run lacks from the previous run through it.

### Web

Reads exactly the shapes above. The scrubber spans `/timeline` `start..end`
(24 h back, 14 d ahead); the boundary is `timeline.boundary`; the per-instant
list is the `coverage` of the hourly item containing the selected instant;
run segments come from `layer.frames[].run_time`, and display interpolation
never pairs two frames whose `run_time` differ.

## Open questions carried into implementation

- Whether the latency estimator should be a rolling median or a high quantile.
  A median schedules half the fetches early; a high quantile wastes horizon.
  The spec requires the estimate be measured and its basis published, and
  leaves the statistic to implementation with the choice recorded.
- Whether GDPS needs per-layer latency rather than per-source, given that its
  layers were measured on two different runs in one capabilities document.
- Whether the ten-minute poll should back off for sources whose measured
  latency spread is wide.
