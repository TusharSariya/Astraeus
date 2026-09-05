> Non-normative decision preparation, 2026-09-05. This document changes no
> source state, quota, scheduler, retention rule, or specification status.

# Free-source capacity, refresh and retention budget

Issue [#74](https://github.com/TusharSariya/Astraeus/issues/74) asks for a
budget that preserves every relevant field and every ensemble member of each
admitted product. The evidence is not yet sufficient to total the completed
288-row roster. This document makes that incompleteness explicit and proposes
the admission arithmetic and measurements needed before any new source becomes
operational.

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

admit a run only when U + S + P + R <= H
admit a snapshot only when U + S_committed + P + new_pin_bytes + R <= H
```

`U` excludes staged objects and extra pinned-only objects. `P` excludes either
of the two normally retained runs. `S_committed` is the reserved complete-run
upper bound for staging that has been admitted but not yet published; it is
zero when no run admission is outstanding and becomes part of `U` only after
publication. These definitions prevent double-counting.
The projection must use a complete-run upper bound established before the full
download, then reconcile to observed bytes after staging.

The older full-field probe measured only the then-current catalogue. Its widest
scenario was **18.23 GB for one run**. At publication peak the store can hold
two visible runs plus the next complete staged run: **54.69 GB = 50.93 GiB**.
The old memo's 36.5 GB figure covered two run-sized payloads, not this three-
payload publication peak. Reserving 20% of the cap leaves 51.2 GiB for `U+S`,
so the measured old catalogue fits by only about **0.27 GiB**, before any
snapshot-only pin. The existing statement that 64 GiB provides real headroom
therefore does not hold for two visible runs plus a third staged run and pins.

### Proposed provisional partition - owner decision required

| Envelope | Proposed cap | Purpose |
|---|---:|---|
| Payload, `U+S+P` | 51.2 GiB (80%) | Normal retained runs, complete staging and fixed-expiry snapshot-only pins |
| Nonpayload reserve, `R` | 12.8 GiB (20%) | Derived artifacts, format/manifest overhead and estimate error |
| Total | 64 GiB | Existing hard quota |

The 20% nonpayload reserve is provisional; representative artifacts must
replace it with an observed p95 expansion/overhead plus a recorded margin.
Snapshot pins compete inside the remaining 80%, after complete normal
retention and staging are counted. Thus the older widest scenario leaves only
about 0.27 GiB for pins or catalogue growth. If the owner declines this split,
the replacement must still reserve explicit nonzero overhead and account for
already-promised pins.

## What the older catalogue proves

The September 2 probe remains useful for its measured products, but its
latest-run-only, three-hour-observation assumptions are stale.

| Scenario from the probe | One-run resident | One-cycle upstream | Three-payload peak | Status under proposed 51.2 GiB payload envelope |
|---|---:|---:|---:|---|
| Core window | 7.48 GB | 108 GB | 22.44 GB (20.90 GiB) | Fits known payload |
| Planning, producer reductions | 11.07 GB | 525 GB | 33.21 GB (30.93 GiB) | Fits known payload |
| Planning, complete member sets | 18.23 GB | 1.73 TB | 54.69 GB (50.93 GiB) | Fits by about 0.27 GiB |

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
indexes/chunk layouts before payload retrieval. Fetch representative chunks
under a small explicit cap, calculate the worst-case complete run, and stop if
the bound is unknown or exceeds an envelope. A tiny bounding box or response
does not prove cheap access when remote chunks or whole GRIB files are large.

### Known request budget

Open-Meteo documents public free-use ceilings of 600 weighted calls/minute,
5,000/hour, 10,000/day and 300,000/month. The source investigation proposes a
stricter shared local ceiling of **40/minute, 400/hour, 2,000/day and
50,000/month**, one request at a time. Those exact limits should be carried
forward; a generic percentage would be less clear. Variable, location, day and
ensemble-member weights are counted, including failed/retried calls. A 429
stops the batch and uses bounded backoff. These remain proposed until the owner
accepts the budget requirement.

WeatherNext statistics sampling has proposed experimental caps of 64 MiB
received, 128 MiB decoded arrays, 5 MiB output, 256 requests and five minutes.
They are sample limits, not a full-source budget. The full 64-member surface is
requester-pays and excluded by the no-charge boundary.

All other provider request, byte and compute budgets are unknown. Provider
limits are always hard ceilings. The remaining owner decision is the lower
shared local direct-feed receive allowance; a proposed **128 GiB/day** would
fit the older probe's lower-scope core ICON plus GFS transfer (about 96.9 GB)
as an arithmetic comparison only. It does not satisfy the accepted +14-day
planning scope or authorize a reduced field/lead acquisition. At that ceiling,
the measured wide-planning native streams, four-cycle cadence and 259-539 GB
single ensemble runs remain blocked unless a producer-side access path proves
lower amplification without reducing fields, leads, members or resolution.
This is a proposed design ceiling, not authorization to transfer 128 GiB. Before
approval and full-field measurement, discovery uses at most 4 MiB metadata,
64 MiB received, 256 requests and five minutes per bounded probe, then stops if
a whole-file or complete-run bound is still unknown.

When a provider/request/byte/compute budget is exhausted, the attempted source
reports `retrieval_failed` with `upstream_budget_exhausted`, preserves the last
visible revision, and retries only in the next allowed window. It never
reports `null`, invents absence, drops members/fields, or substitutes another
source. A product unavailable because it has not yet passed capacity admission
remains non-operational and is not advertised as retrieved.

## Owner frontier

1. Approve or replace the provisional 80/20 hot-store envelope so the
   already-selected snapshot-pin exception and complete-run staging have an
   explicit admission boundary under the fixed quota.
2. Approve a shared local direct-feed receive allowance. Recommendation:
   128 GiB/day during the experiment, with provider ceilings still stricter
   and no automatic increase. A higher allowance should be an explicit number,
   not inferred from free source access.

After those answers, the draft OpenSpec change can be revised and submitted for
the owner's separate normative status approval. Silence does not accept either
choice.

## Verification

- Arithmetic recomputed in GiB from the cited decimal measurements.
- Roster group counts generated from
  `docs/research/free-source-implementation-roster.json`; issue 97 overlap is
  identified rather than double-counted.
- `openspec validate free-source-capacity-budgets --strict`
- `uv run --project tools/specs python tools/specs/specctl.py validate`

Spec-Impact: none. This is research and owner decision preparation; the linked
OpenSpec change remains a draft requirement change.
