> Non-normative decision preparation, 2026-09-05. This document changes no
> source state, quota, scheduler, retention rule, or specification status.

# Free-source capacity, refresh and retention budget

Issue [#74](https://github.com/TusharSariya/Astraeus/issues/74) asks for a
budget that preserves every relevant field and every ensemble member of each
admitted product. The owner resolved the shared-transfer policy on 2026-09-05:
"yeah increase our budget then maybe set the budget to off unless we are going
to run out of storage". Accordingly, there is no artificial shared daily
receive cap. Storage admission remains bounded by conservative measured
full-run projections, the existing 64 GiB quota and actual local free space.
Provider rate ceilings, zero-charge constraints and finite operation safety
bounds remain in force. The evidence is not yet sufficient to total the
completed 288-row roster, so unmeasured products remain non-operational.

## Decisions already in force

The following are inputs, not questions for this ticket:

- The hot object store is capped at **64 GiB**. There is no cold, overflow or
  vintage-archive tier.
- A forecast stream normally keeps the latest and previous complete runs.
  Observations and nowcasts keep 24 hours; the forward evidence window is 14
  days.
- A new run is staged completely before atomic publication. A quota failure
  preserves the visible revision and is reported as `retrieval_failed` with
  `quota_exceeded`.
- Every field every admitted producer product publishes remains in scope, at
  its admitted native resolution and with complete admitted ensemble
  membership. Capacity work does not silently thin fields, levels, members or
  resolution.
- Existing, unexpired Series snapshots may pin displaced revisions until
  their fixed expiry. The pins cannot renew themselves, cannot make an old run
  newly selectable, and cannot exceed the existing quota.
- Source access must incur no provider subscription, requester-pays transfer,
  paid query, rented compute or other charge. A free endpoint does not imply
  free local compute or unbounded requests and transfer.
- There is no shared daily receive allowance. This removes an artificial
  bandwidth policy ceiling; it does not make an individual probe, retrieval,
  decode, request count or runtime unbounded.

The first three points are implemented in the experiment's current storage
policy. Complete field/member scope is an earlier owner decision. The
snapshot-pin exception is an owner-selected design decision that still needs
an accepted specification and implementation.

## Correct peak-storage arithmetic

All quantities are bytes at the object-store boundary. Decimal measurements
are converted before comparison with the binary 64 GiB quota.

```text
H = 64 GiB                                  hard hot-store quota
U = bytes in the two normally retained visible runs
S = complete incoming staged run
P = bytes retained only because live snapshots pin displaced revisions
R = measured format, manifest, derived-artifact and sizing-error reserve
L_f = all additional bytes allocated on local filesystem f by the operation,
      including download/decode temporaries and staged/published files stored
      there, without double-counting an allocation already represented in S
M = measured filesystem overhead and sizing-variance allowance
D_f = free bytes on filesystem f, net of atomic concurrent reservations

admit a run only when U + S + P + R <= H
admit a snapshot only when U + S_committed + P + new_pin_bytes + R <= H
begin an operation only when L_f + M_f <= D_f for every filesystem f
```

`U` excludes staged objects and extra pinned-only objects. `P` excludes either
of the two normally retained runs. `S_committed` is the reserved complete-run
upper bound for staging that has been admitted but not yet published; it is
zero when no run admission is outstanding and becomes part of `U` only after
publication. These definitions prevent double-counting.
The projections must use complete-run and per-filesystem allocation upper bounds
established before the full download, then reconcile to observed bytes after
staging. `R`, `L_f` and `M_f` include measured expansion/overhead and a conservative
allowance for observed variance. No fixed percentage is inferred. If the
measurements cannot establish safe bounds, admission stops. Admission reserves
the projected allocations atomically, so concurrent acquisition tickets cannot
each rely on the same free bytes.

The older full-field probe measured only the then-current catalogue. Its widest
scenario was **18.23 GB for one run**. At publication peak the store can hold
two visible runs plus the next complete staged run: **54.69 GB = 50.93 GiB**.
The old memo's 36.5 GB figure covered two run-sized payloads, not this three-
payload publication peak. The measured old catalogue therefore leaves about
**13.07 GiB** under the hard quota for all extra snapshot-only pins, derived
and format overhead, manifests and sizing variance. That is not evidence that
the expanded roster fits. Admission uses measured product-specific overhead
and conservative safe bounds; there is no newly authorized fixed 20%
partition.

## What the older catalogue proves

The September 2 probe remains useful for its measured products, but its
latest-run-only, three-hour-observation assumptions are stale.

| Scenario from the probe | One-run resident | One-cycle upstream | Three-payload peak | Headroom under 64 GiB before `P+R` |
|---|---:|---:|---:|---|
| Core window | 7.48 GB | 108 GB | 22.44 GB (20.90 GiB) | 43.10 GiB |
| Planning, producer reductions | 11.07 GB | 525 GB | 33.21 GB (30.93 GiB) | 33.07 GiB |
| Planning, complete member sets | 18.23 GB | 1.73 TB | 54.69 GB (50.93 GiB) | 13.07 GiB |

These are not a budget for the current roster. They cover ECCC HRDPS/RDPS/
GDPS/REPS/GEPS, NOAA GFS/GEFS, ECMWF IFS/AIFS deterministic and ensembles,
DWD ICON Global, a GOES-19 cloud/fog set, and small carried observation,
ocean, point, text and space-weather families. GOES field counts and stored
sizes, compression, some ensemble enumeration, and CAPS-Ocean were already
marked estimates or unknown.

## Current roster: explicit unknown budget groups

The completed roster contains 118 registry rows and 170 overlapping research
rows. The following groups route all 288 accounting rows. A prior measurement
for one product in a group does not budget its other products or access paths.

| Ticket | Rows | Current capacity evidence |
|---:|---:|---|
| 77 WeatherNext | 5 | Proposed statistics sample caps only; live chunk/storage/refresh cost unknown |
| 78 Open-Meteo and Bright Sky | 23 | Weighted-call formula and limits known; response bytes, complete field/member request totals and decode cost unknown |
| 79 GeoMet WCS/WEonG | 7 | Older measurements for selected ECCC families; expanded coverage success and complete current bytes unknown |
| 80 ECCC air quality/precipitation/land | 13 | Unknown |
| 81 Native deterministic IFS/ICON/AIFS/RAP/NAM | 8 | Older IFS/ICON/AIFS estimates; RAP, NAM and current full artifacts unknown |
| 82 ECMWF ensembles | 4 | Older IFS ENS/AIFS-ENS estimates; current complete artifacts and decode peaks unknown |
| 83 REPS/GEPS | 2 | Older GeoMet estimates; current access/product completeness unknown |
| 84 GEFS/ICON ensemble | 2 | Older GEFS estimate; ICON ensemble route and both current full costs unknown |
| 85 Satellite cloud/atmosphere | 12 | Partial GOES estimates; remaining products unknown |
| 86 Aerosol/radiation/fire | 12 | Unknown |
| 87 Marine/ocean/ice/hydrometric | 38 | Small carried subset only; remaining products unknown |
| 88 Local/aviation observations | 21 | Small carried subset only; remaining products unknown |
| 89 Space weather | 18 | Small carried subset only; remaining products unknown |
| 90 Cameras/transport | 8 | Camera transfer estimate only; admitted products and retention unknown |
| 91 Terrain/light/site evidence | 18 | Unknown, including static snapshot size/refresh |
| 92 Orbital/celestial catalogues | 14 | Unknown |
| 94 Historical windows | 23 | No archive allocation exists; every selected acquisition needs a separate bounded snapshot size |
| 95 Local FourCastNet | 6 | Model/checkpoint, peak RSS, runtime, outputs and persistence unknown; rented compute forbidden |
| 96 Published AI forecasts | 1 | Unknown |
| 97 Coverage handoff | 53 | Verification routes overlap the groups above; do not add them twice |

Until its target task records the fields, levels, members, leads, cadence,
wire bytes, stored bytes and peak decode resources, each unknown group remains
`operational: false`. This is a measurement gate, not a decision to discard its
contents.

## Refresh, request and compute accounting

Every product/access path must publish this ledger before admission:

| Dimension | Required measurement |
|---|---|
| Identity | producer product, access path, run/publication/retrieval identity |
| Scope | every relevant field, level, member, lead, valid time and native grid |
| Requests | documented provider weights and ceilings; metadata, ranges, retries and failures included |
| Transfer | bytes received for metadata, indexes and payload separately; server-side subset versus whole-file amplification |
| Storage | original, normalized, rendered/derived and manifest bytes per complete run or snapshot |
| Staging | complete staged upper bound and post-stage observed reconciliation |
| Decode | peak RSS, temporary disk, wall time and CPU time on the actual local machine |
| Refresh | native publication cadence, measured availability lag, retry policy and maximum daily cycles |
| Retention | forecast run count, observation duration, static refresh/expiry, and extra pinned-only bytes |
| Charges | source fee, requester-pays, query, egress and compute each separately proven zero or blocked |

Discovery is metadata-first. Enumerate the complete inventory and inspect
indexes/chunk layouts before payload retrieval. Probe limits are finite and
sized from that metadata: bound the request count, bytes, temporary disk,
decoded memory and wall time needed to establish a conservative complete-run
projection, then stop at those limits. Where metadata cannot size a safe probe,
use the existing discovery defaults of at most 4 MiB metadata, 64 MiB received,
256 requests and five minutes. A probe limit may be raised to retrieve a known
representative artifact only after its metadata supplies a safe size/resource
bound. A tiny bounding box or response does not prove cheap access when remote
chunks or whole GRIB files are large.

### Known request budget

Open-Meteo documents public free-use ceilings of 600 weighted calls/minute,
5,000/hour, 10,000/day and 300,000/month. The source investigation proposes a
stricter shared local ceiling of **40/minute, 400/hour, 2,000/day and
50,000/month**, one request at a time. Those exact limits should be carried
forward; a generic percentage would be less clear. Variable, location, day and
ensemble-member weights are counted, including failed/retried calls. A 429
stops the batch and uses bounded backoff. These remain proposed until the owner
accepts the budget requirement.

WeatherNext metadata establishes that the selected 18 statistics chunks total
375,209,154 compressed bytes. The owner increase permits a finite 512 MiB
received probe bound for that known sample; it replaces the initial 64 MiB
receive cap for this probe only. No sample pass has occurred yet, and the
decoded-memory, output, request and time bounds must be set from the now-known
chunk shape before retrieval. These are sample limits, not a full-source
budget. The full 64-member surface is requester-pays and excluded by the no-
charge boundary.

All other provider request and compute budgets are unknown. Provider limits
are always hard ceilings. The owner chose to leave the shared daily direct-feed
receive allowance off, so neither 128 GiB/day nor 2 TiB/day is a policy limit.
Each operation still needs a metadata-sized finite request, byte, memory,
temporary-disk and time bound. A scheduler must also cap concurrency, honor
provider throttling and cancellation, and refuse work whose full-run or local
resource bound is unknown. Once the relevant acquisition contract and these
gates permit it, the active implementation scope authorizes ordinary bounded
full-field verification without another capacity approval. Automatic or
unbounded downloads, paid access, billing changes and production scheduler
changes remain outside this decision.

When a provider/request/byte/compute budget is exhausted, the attempted source
reports `retrieval_failed` with `upstream_budget_exhausted`, preserves the last
visible revision, and retries only in the next allowed window. It never
reports `null`, invents absence, drops members/fields, or substitutes another
source. A product unavailable because it has not yet passed capacity admission
remains non-operational and is not advertised as retrieved.

## Decision resolution and delegated gates

Issue 74's policy choice is resolved: preserve the 64 GiB quota, use measured
product-specific overhead and free-space safety gates, and configure no shared
daily receive ceiling. The acquisition tickets for issues 77-96 own the
remaining product measurements. Each product stays non-operational until its
ledger establishes conservative complete-run, staging, pin, overhead, request,
decode and temporary-disk bounds and proves all charge surfaces zero.

This owner answer does not authorize `accepted` or `verified` specification
status. The OpenSpec change remains draft, and no production runtime or
scheduler behavior may change until the requirement is accepted under
GOV-SPEC-002. Issue 74 can close as a policy decision while the source-specific
measurement and implementation gates remain tracked by their acquisition
tickets.

## Verification

- Arithmetic recomputed in GiB from the cited decimal measurements.
- Roster group counts generated from
  `docs/research/free-source-implementation-roster.json`; issue 97 overlap is
  identified rather than double-counted.
- `openspec validate free-source-capacity-budgets --strict`
- `uv run --project tools/specs python tools/specs/specctl.py validate`

Both commands passed on 2026-09-05; `specctl` reported 0 errors and 0 warnings.

Spec-Impact: none. This is research and owner decision preparation; the linked
OpenSpec change remains a draft requirement change.
