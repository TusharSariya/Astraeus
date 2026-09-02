## Why

The glossary calls a horizon tier "one of two forecast ranges served", and the
registry has no field that says how far any source reaches. Scheduling is
derived today from a record's prose cadence alone
(`source-registry-catalogue`: "Freshness thresholds and cadences are derived,
never defaulted into existence"), which schedules a fetch at the moment a run
is nominally due rather than at the moment it is actually published. The
measured gap is large: `docs/research/wayfinder/planning-horizon-matrix.md`
timed ICON's final lead at about T+3.5 h, GFS at about T+5.3 h and the whole
ECMWF dissemination near T+7.6 h. A schedule blind to that difference either
fetches nothing or fetches a run that does not exist yet, and reports the
absence as an upstream failure.

Staleness has the same shape of defect. `map-layers` derives
`staleness_tolerance_seconds` as half the derived cadence, which for a
six-minute radar layer is three minutes and for a three-hourly planning step
is ninety minutes, neither of which is a native interval. And nothing
anywhere records that a run itself has gone old: a frame from a twelve-hour-old
GFS run is served with exactly the same standing as one from the run published
twenty minutes ago.

The owner resolved wayfinder ticket
[#23](https://github.com/TusharSariya/Astraeus/issues/23) on 2026-09-02: a tier
is a valid-time range, not a source list; no source is assigned to a tier;
every source declares its reach and covers every instant it reaches. Refresh is
scheduled from producer run cadence plus measured publication latency, with
ten-minute polling and the dated WXO-DD Datamart fallback for ECCC, and latency
is re-measured in the worker heartbeat. Frame staleness tolerance is one native
interval per layer. A run older than twice its producer cadence is flagged
`run_stale`. A short cycle keeps the previous run serving the leads the new run
lacks. The timeline shows the boundary, the step change beyond it, and the
covering sources per instant.

What remains unverified: the latency figures are three live measurements on one
day, not a distribution, so they are starting values that the deployment must
re-measure rather than facts to encode. GEPS publication latency was bounded
from below only and never measured; REPS latency is unverified entirely;
WeatherNext 2 is credential-blocked and both its cadence and its latency are
unknown. Every one of those is a source with no measured latency, and this
change specifies what happens to such a source rather than guessing a number
for it.

This change does not restate the window bounds. The sliding valid-time window
from 24 h back to 14 d ahead, its retention and its restart-cache behaviour
belong to the parallel `storage-window-and-restart-cache` change; the tier
boundaries here are named as the ranges the reader is shown, and the window
those ranges sit in is that change's to define.

## What Changes

- **A tier is a valid-time range.** The core tier is 24 h back to 24 h ahead;
  the planning tier is 24 h to 14 d ahead. A tier names no sources and excludes
  none.
- **Every admitted source declares its reach** in the registry: the earliest
  and latest valid time it can cover, per run cycle where cycles differ. A
  source with no declared reach is not schedulable and is served to nobody.
- **A source covers every instant it reaches.** At any instant the reader sees
  every source whose reach contains it, on both sides of the 24 h boundary.
  Nothing is filtered out for being a "planning model" near in, or a "core
  model" far out.
- **Forecast refresh is scheduled from run cadence plus measured publication
  latency**, starting from the values in the planning-horizon matrix (ICON
  about T+3.5 h, GFS about T+5.3 h, ECMWF about T+7.6 h), then polled every ten
  minutes until the run appears, bounded, with the dated WXO-DD Datamart path
  as the ECCC fallback. The observed publication instant is recorded and the
  latency estimate is re-measured in the worker heartbeat.
- **Observations and nowcasts refresh at native cadence**: radar 6 min,
  lightning 10 min, GOES 10 min, METAR and SWOB hourly, and SWPC per feed
  rather than as one number - the solar wind magnetometer is 1 min, but the
  planetary K index is 3 h and the OVATION nowcast 10 min, each as its own
  record's prose states.
- **Frame staleness tolerance becomes one native interval per layer**, replacing
  the half-cadence rule: 6 min for radar, 1 h for hourly model frames, 3 h or
  6 h for planning steps. Beyond it the existing disclosure rule applies
  unchanged.
- **Run staleness is a distinct flag.** A run older than twice its producer's
  run cadence is flagged `run_stale` on every frame it feeds, independently of
  whether that frame is inside its own staleness tolerance.
- **A short cycle does not shorten the horizon.** Where the latest run reaches
  less far than its predecessor (IFS and IFS ENS at 06z and 18z reach 144 h
  against 360 h), the previous run keeps serving the leads the new one lacks,
  and both runs are labelled with their run time wherever they are drawn.
- **The timeline shows the boundary and the covering sources.** The 24 h
  boundary is marked, the step change in cadence and source set beyond it is
  visible, and each instant lists the sources covering it with their run times
  and staleness flags.

## Capabilities

### Modified Capabilities

- `source-registry-catalogue`: reach, run cadence and measured publication
  latency become declared, validated registry facts; an undeclared reach makes
  a source non-schedulable.
- `ingestion-worker-scheduling`: forecast scheduling from cadence plus measured
  latency, bounded ten-minute polling, the ECCC dated Datamart fallback,
  observation scheduling at native cadence, and latency re-measurement in the
  heartbeat.
- `evidence-window-timeline`: the two tiers as valid-time ranges, per-instant
  source coverage from declared reach, and run staleness on the timeline.
- `map-layers`: staleness tolerance becomes one native interval; frames carry
  their run time and `run_stale`; the previous run serves leads a short cycle
  lacks.
- `web-evidence-interface`: the boundary, the step change, the per-instant
  covering sources with run times, and the run-stale disclosure.

## Ordering

This change is applied after `frame-fallback-and-viewport-layout` and `storage-window-and-restart-cache`. Its modification of the map-layers staleness requirement is written against the frame-fallback version (disclosed fallback by group), changing only the tolerance rule from half a cadence to one native interval and keeping every frame-fallback scenario.

## Impact

- `registry/source_data.py`: `reach`, `run_cadence_seconds` and
  `publication_latency_seconds` (measured, with the observation count) per
  forecast record; `registry/audit.py` refuses a schedulable record with no
  reach.
- `worker/`: schedule computation from cadence plus latency, the bounded poll
  loop, the ECCC dated-path fallback, and the measured-latency write in the
  heartbeat document.
- `api/weather_api/`: `tier`, `reach`, `run_time` and `run_stale` on layer,
  timeline and point responses; per-instant coverage from declared reach.
- `web/src/`: the 24 h boundary marker, the step change, the per-instant source
  list with run times, and the run-stale badge.
- No new upstream source and no registry promotion. Spec-Impact none outside
  the experiment.
