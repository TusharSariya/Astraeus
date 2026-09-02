# Design

## The contradiction, and why removal rather than repair

Three files disagree, and no data resolves them.

| Where | What it says |
| --- | --- |
| `openspec/specs/point-evidence-sampling/spec.md:58` | a consensus value needs an ensemble among the candidates |
| `api/weather_api/store.py:1156-1176` | a candidate must have `may_enter_consensus`, which is the registry's `consensus.eligible` |
| `registry/audit.py:68-69` | `consensus.eligible` requires `category == "deterministic_forecast"` |
| `api/weather_api/store.py:1173` | `is_ensemble` is `category == "ensemble"` |

A candidate must be eligible to count, deterministic to be eligible, and an
ensemble to satisfy the gate. The three have no common solution.

Repair would mean relaxing the audit rule so an ensemble may be eligible. That
was considered and rejected. The audit rule exists for a good reason recorded
in `registry/source_data.py:96-103`: category was once inferred, and the
inference let an ocean model vote on air temperature. Loosening it to admit
ensembles reopens exactly the door that comment closes. And repairing the
mechanism leaves the deeper problem: an ensemble mean is a value no centre
issued, averaging it into a 2.5 km regional field damps the gradients that
model exists to resolve, and hard-won facts 7 and 9 already record that the
cloud quantities being compared across centres are not the same quantity.

The owner's decision on 2026-09-02 was to remove it. The measured argument is
in `docs/research/ensembles-and-source-plurality.md` §5.

## Why removal is smaller than it sounds

`/point` already returns per-source fields for every source that published;
the consensus branch only replaced the temperature entry in the single case
that has never occurred. Removing it deletes a branch that has never been
taken in production. What changes for the reader is the badge, which stops
saying that a higher option failed and starts naming the ordering it applied.

## Two ingest shapes, because providers differ

Measured 2026-09-02 and recorded in the research document §3:

| Source | Shape | Evidence |
| --- | --- | --- |
| `noaa-gefs` | members | 31 per-member GRIB2 files per lead, control self-labelled `ENS=low-res ctl` |
| `eccc-reps` | members | 1239 `REPS.MEM.<VAR>.<NN>` GeoMet coverages, members 01-21 |
| `eccc-geps` | reduction | `ERMEAN`, `ERSSTD`, `ERC0`-`ERC100`, `PROB`; zero member layers |

A single "ensemble adapter" abstraction would have to guess which it is
looking at, so the registry declares the shape instead. That is why the
declaration is a requirement rather than an implementation detail.

The asymmetry is not a defect in GEPS. A provider that publishes its own mean
over its own members is publishing retrieved evidence; what this stack must
not do is recompute that statistic, or combine it with a statistic over a
different member set. A mean over 21 ECCC members and a mean over 31 NOAA
members are not the same quantity and do not average.

## Why the decoder must keep `number`

`ingest/grib.py:328` groups `number` with `time`, `step` and `valid_time` as
message scalars to drop, and line 356 drops those four without recording them,
unlike other scalar coordinates which survive as `level_type` and
`level_value`. The three time coordinates are recoverable from the artifact's
own axes. A member identity is not: once dropped, no downstream code can say
which member a value came from, and two members silently become one field.
That is why the requirement demands a failure rather than a best effort.

## Why an unaddressed member dimension is refused, not nulled

`_sample_dataset` already sets the precedent four lines above the bug.
`api/weather_api/store.py:638` refuses a dataset outright when it carries an
unrequested pressure dimension, rather than guessing a level. A member
dimension currently falls through to `float()` on a 31-element array, raises,
is caught, and becomes `None`. Refusing and reporting is the behaviour the
codebase already chose for the same class of problem, and a null there is
indistinguishable from a cell that genuinely held no number.

## What the registry `consensus` block becomes

It is removed rather than repurposed. Repurposing it as a display-ordering
weight was considered and rejected: the ordering is a short, global preference
(HRDPS, then RDPS, then evidence-only) rather than a per-record property, and
leaving a per-record field that only three records meaningfully set is how the
original contradiction went unnoticed. `registry/audit.py:65-69` loses its
rule; a record still carrying the field becomes an audit error, so the removal
cannot be half-applied.

## Open questions carried into implementation

1. Whether GeoMet WCS returns a usable Avalon subset per REPS member, and at
   what cost against the per-request and per-process upstream budgets that
   `geomet-wms-access` already enforces. 21 members times variables times
   leads is a large fan-out.
2. Whether GEFS publishes any instantaneous total cloud. `pgrb2a` carries only
   `TCDC:entire atmosphere:0-6 hour ave fcst`. If the average is all there is,
   GEFS cloud is not drawable beside HRDPS or GFS cloud.
3. Whether GEPS is reachable over MetPX Sarracenia, the one open ECCC route
   not probed, now that every HTTP path 404s.
4. What a member-aware render means. Spaghetti, spread shading and a member
   selector are three different products, and `web/src/App.test.tsx:229-267`
   currently pins that the interface offers none of them.
