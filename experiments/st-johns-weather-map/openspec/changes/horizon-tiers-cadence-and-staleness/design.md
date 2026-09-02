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

## Open questions carried into implementation

- Whether the latency estimator should be a rolling median or a high quantile.
  A median schedules half the fetches early; a high quantile wastes horizon.
  The spec requires the estimate be measured and its basis published, and
  leaves the statistic to implementation with the choice recorded.
- Whether GDPS needs per-layer latency rather than per-source, given that its
  layers were measured on two different runs in one capabilities document.
- Whether the ten-minute poll should back off for sources whose measured
  latency spread is wide.
