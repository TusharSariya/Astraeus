# Autonomous execution handoff: sources, then desktop app

Updated September 6, 2026. This is a non-normative execution record, not a new
Wayfinder map or a change to application behavior.

## Current state and owner authorization

The full experimental weather-map stack merged to main in PR157, commit
6322b1174e566c1a26c1da79bd837201bc898f2b. All18 former open stacked PRs were
included and closed as superseded. Read
`experiments/st-johns-weather-map/docs/main-integration.md` for pinned heads,
cache corrections and combined verification.

The owner approved the ordered queue below and instructed "Implement the plan":
sources first, then desktop app/design; fresh Sol leads and bounded Terra/Luna
workers; review and merge passing experimental work without routine approval
prompts; keep human/external blockers visible and continue eligible work.

The owner explicitly said "skip the phone brief". #53 remains open, deferred
and unclaimed. #55 excludes phone work and its native blocker edge from #53 was
removed. #38 records desktop scope and the phone deferral. Do not build phone
layouts or responsive-phone studies in this run.

## Immediate runtime blocker

The worker-level #159 preflight and payload-discovery reservation seams merged
through PR166 at `86355f9c81f956eb2d7a123a7e940f3ee6bb9066`.
Scheduler-eligible adapters without measured complete-operation bounds remain
fail-closed while source-specific memory and physical-allocation enforcement is
implemented. #118 is closed; #123/#137 partial proofs merged in PR165/PR164 but
their contracts remain in #167/#168; #158 awaits the owner's fragment choice;
#133 awaits its contract/publication path and #105 is active. The owner
authorizes completed-thread reuse. The root
orchestrator delegates implementation and independent evidence review while
keeping claims and isolated worktrees coordinated.

## Mandatory inputs and boundaries

Read AGENTS.md, the repository manage-astraeus-specs skill, docs/specv1/README.md,
GOVERNANCE.md, CONTEXT.md, docs/agents/issue-tracker.md, map70 Notes and the exact
issue with its native blockers. Read relevant accepted requirements and owning
experimental OpenSpec before behavior changes. Missing/draft/conflicting
production or scientific authority remains a human decision. The existing
experimental seams do not authorize normative promotion.

Use current origin/main in a new isolated worktree per ticket. Root user WIP
remains at /Users/tusharsariya/Projects/Astraeus on execution/activity-profiles
at9af2aaf: do not reset, switch, merge into or commit that checkout. The old
prepared #118/#123 worktrees start at fe9a24f and are stale; use fresh main-based
worktrees. Preserve other users' worktrees and raw-data ownership.

Keep operational:false, registry ceilings, 64GiB hot quota, two complete
forecast runs, 24h observation history and 14d forecast horizon. No cold tier,
paid service, rented compute, provider outreach or implicit rights acceptance.
No raw provider payload or rebuilt artifact belongs in Git. Keep only compact
receipts (URL/params/bytes/SHA/actual capture time/artifact revision and actual
API comparison results) and small hand-trimmed representative fixtures.
Bound each capture and extraction, account for concurrent tasks and physical
disk margin, and delete task-owned captures only after root review.

## Queue and priority

Tracking truth is GitHub Issues on TusharSariya/Astraeus. Rows below are priority
batches, not barriers: native blockers take precedence and available slots may
be filled from later rows. At most three implementation tickets are active.

First complete the new audit/repair follow-ups: #158 missing-only acquisition
after partial cache hits, and #159 resource preflight before payload retrieval.
Both are native children of #70 and native blockers of final verification #97.
The shared #159 gate is implemented and tested; source-specific bounds remain
incremental work. #158 remains pending the owner's fragment choice.

| Batch | Tasks |
| --- | --- |
| 1 | #118 NL air quality; #123 IERS time inputs/kernels; #137 ECCC alerts/outlooks |
| 2 | #133 RAQDPS/RDAQA; #105 Holyrood radar; #109 CWFIS/FIRMS |
| 3 | #116 SWOB/city observations; #115 aviation hazards; #153 SST freshness/admission |
| 4 | #143 JMA levels; #144 MOSMIX gusts; #145 GeoMet field accounting |
| 5 | #142 Open-Meteo/Bright Sky admission; #141 GeoMet contracts; #140 WeatherNext temporal coverage |
| 6 | #134 HRDPA/HREPA; #136 RDPA geometry/units; #135 HRDLPS/CaLDAS |
| 7 | #84 GEFS/ICON ensemble; #147 REPS fields; #148 GEPS reductions |
| 8 | #102 VIIRS/JPSS clouds; #103 NUCAPS profiles; #107 aerosols |
| 9 | #106 native CAMS; #108 AERONET/eligible AQ observations; #104 Copernicus/MODIS/GPM |
| 10 | #119 terrain/canopy; #121 night-light/sky brightness; #122 land/site access |
| 11 | #120 buildings/OSM; #124 eclipse/geometry catalogues; #125 orbital/small bodies |
| 12 | #117 community weather/MADIS; #90 permissioned cameras/transport; #126 meteor/photometry/transients |
| 13 | #99 Open-Meteo marine/GFS-Wave; #112 buoys/water levels; #113 hydrometric |
| 14 | #110 ocean/wave/surge; #111 remaining SST/ice/satellite ocean; #114 marine advisories |
| 15 | #93 historical acquisition decision; #95 local FourCastNet feasibility |
| 16 | #94 approved historical windows; #127 NOAA AI-GFS/AI-GEFS |
| 17 | #97 integrated source verification and handoff |

#142 follows #143/#144; #111 currently depends on #153; #94/#127 depend on #93.
Do not repeat merged SST implementation: #153 remains open because the captured
latest analyses were outside the24h window and those source IDs have no owner
admission resolution. Marine work needs a concrete activity connection and
eligible path. #145 may expose more bounded field children; #95 only graduates
inference integration children after feasibility and evidence-class decisions.
New required children must block final verification; metadata or tiny selected
samples cannot establish whole-source coverage.

Family milestones close only after their actual requirements and children:
#78 named Open-Meteo/Bright Sky; #80 ECCC analyses; #85 cloud/radar satellites;
#86 aerosol/radiation/fire; #87 marine/ocean/hydrometric; #88 local/aviation;
#91 terrain/site; #92 celestial; #96 published AI products. Close #70 only after
#97 establishes completion; unresolved required work is not implemented.

## Desktop app/design sequence

Begin when eligible source work is finished or waiting on external input.

1. In parallel where capacity allows: #57 resolve the obsolete band-math scope
   and numeric-input blockers; #69 reuse existing accessibility repairs and
   finish reader verification; #66 prepare and resolve camera placement.
2. #65 prepare outdoor red-night testing and obtain the owner's observations.
3. #54 settle remaining prototype-backed API contracts after native blockers.
4. #55 desktop front-end/API proposals, excluding phone #53.
5. #38 record desktop completion while retaining the explicit phone deferral.

#57's old swipe language predates the owner's exclusion of on-map comparison.
Do not silently restore it or compare unlike cloud fields. #69 already has
prototype repairs on dedicated branches; real screen-reader output remains
unverified. #65 is physical human work. #66 requires a placement decision and
source eligibility; registered metadata does not authorize camera image reuse.
The current app queue ends in design/proposals. Create bounded implementation
children from resolved contracts rather than inventing wire formats or science.

## Agent, review and merge protocol

Each ticket has one fresh Sol lead; Terra handles complex bounded implementation
or review; Luna handles bounded catalogue, fixture and documentation work. With
four runtime slots total, root plus three leads leaves no nested-worker slot.
Stagger leads when a complex ticket needs a subtree. Claim before work, but
release claims when launch fails and no work is active. Never reuse completed
agents on unrelated tickets.

Root reviews field dispositions, bounded live evidence, artifacts, actual HTTP
readback, negative tests and provenance. Leads do not self-close issues or
promote admission. Rebase/integrate current main, resolve conflicts preserving
both intents, run relevant checks, merge passing work, then close with a
resolution and context pointer. Keep branches short instead of rebuilding a
large PR stack. Human/external decisions get precise evidence and remaining
actions while unrelated eligible work continues.

Verification: API/registry tests, relevant strict OpenSpec, specctl validate and
traceable Spec-Refs/Verification metadata on every change. Run web, SQL and
storage checks when affected and at combined milestones. No fixture or static
accessibility check substitutes for required real evidence. A no-data source
is an explicit unavailable/unsupported disposition, never a favorable value.

## Completed during queue setup

- Deferred #53 and removed its native blocker from #55; updated #38/#55 scope.
- Created #158/#159, linked them to #70 and as native blockers of #97.
- Saved the owner-approved queue and runtime blocker here.
- No new source implementation or provider capture was completed in this setup.

Spec-Impact: none; execution handoff only, with no application behavior change.
