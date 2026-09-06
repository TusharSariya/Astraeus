# Handoff: 2026-09-02 execution session, steps 1 to 7 of the apply order

Read this before `docs/execution-log.md` (the running log) and after
`session-2026-09-02-wayfinder-handoff.md` (the owner decisions and the
apply order). This session executed steps 1 to 7 of the nine-step apply
order and stopped, at the owner's request, just before step 8.

## Where everything is

Stacked pull requests, each green under `make test` in the main checkout,
none merged to main yet (main has branch rules: pull request plus the
spec-governance check):

| PR | Step | Branch | Base |
| --- | --- | --- | --- |
| #31 | 1 to 3: ensemble-members owner gates, frame-fallback closed, evidence classes | `execution/evidence-classes` | main |
| #32 | 4: field catalogue and families | `execution/field-catalogue` | #31 |
| #33 | 5: storage window and restart cache | `execution/storage-window` | #32 |
| #34 | 6: horizon tiers, cadence and staleness | `execution/horizon-tiers` | #33 |
| #35 | 7: ensemble families and member statistics | `execution/ensemble-families` | #34 |

Merge them in order, or rebase each onto main after the previous lands.
The main checkout is on `execution/ensemble-families`; the working tree is
clean apart from `.repowise/` and `web/node`. No agent worktrees remain.

Gate on the tip of #35: API 1308 passed, 25 skipped; web 383 passed in 19
files; registry 111 passed; SQL publication and retention invariants PASS;
specctl 0 errors, 0 warnings. `make up` is healthy from #33 onward.

## What remains

1. Step 8, `source-admissions-ledger` (61 tasks, mostly one registry record
   each; the ledger table in its `design.md` is the source of truth).
   Branch from `execution/ensemble-families`, integration branch
   `execution/source-admissions`, pull request based on #35.
2. Step 9, `activity-profiles-sites-and-cameras` (23 tasks). Relies on the
   `partnership-only` state step 8 defines. Cameras: none admitted, Fort
   Amherst permission request first, derivations enter disabled.
3. Owner gate 6.4 of step 7: the minimum member count per statistic entry.
   Open for the owner; nothing invents one at derive time.
4. The two older pending changes kept after triage,
   `cloud-and-fog-evidence` and `observations-strata-satellite`, slotted
   after step 9 (see the triage section of the execution log).
5. The seven older complete changes await the owner's archive decision, and
   seven implemented ones each need one Docker rebuild gate; the stack is
   now buildable, so one rebuild wave covers them.
6. Live smokes: no ensemble family is schedulable (all `unverified`), and
   HRDPS and RDPS publication latency is null until measured. Every source
   stays `implementing` or lower; nothing is `active`.

## How to run the next step (owner's method, 2026-09-02)

Spawn ONE Fable subagent as the change lead for the change, in its own
worktree, with the brief used for steps 6 and 7 (the execution log's
"Method change" section summarises it):

- The lead divides the change by file ownership, pins every seam
  (function names, response shapes, registry fields) into `design.md` under
  a "Seam" heading and into each prompt, and spawns ONE FRESH AGENT PER TASK
  (clean context, one task verbatim with its verify command, owned files,
  seam, standing rules, commit trailer, short report limit). Agents are
  never resumed; the next task gets a new agent.
- At most three task agents at once, only when their tasks touch disjoint
  files. Tasks sharing a file run one after another, each from the merged
  integration branch. In step 8 most record tasks edit
  `registry/source_data.py`, so pair each record agent with schema, audit,
  secrets, docs or test tasks to keep three busy.
- Opus for `store.py`, ingest, adapters, the derivation registry, SQL and
  spec deltas; Sonnet for registry records, docs and test-only or
  display-only work.
- Agents commit before running long suites (a rate limit killed a lead and
  two task agents mid-suite in step 7; their committed work survived, their
  uncommitted work had to be rescued by hand).
- A fresh worktree skips the numpy and xarray tests (36 skipped instead of
  25), so the lead's counts are indicative. The main session checks out the
  lead's branch in the main checkout (release the lead's worktree first:
  `git worktree unlock` then `git worktree remove --force`), runs
  `make test` and strict `openspec validate`, ticks the gate task, appends
  the step to `docs/execution-log.md`, pushes, and opens the stacked pull
  request. The main session stays out of the change's internals.

## Decisions taken this session that the owner may want to review

- `test_layer_frame_contract.py` asserted a server-side frame substitution
  the accepted map-layers requirement forbids; rewritten to the accepted 422
  (execution log, "Resolved"). Reverse by writing a server-side snap
  requirement.
- The pressure-level dew point stopped being served because the catalogue
  has no key for it (field-catalogue tasks 6.4).
- The delivery kind is named `published_cell`, not `retrieved`, per the spec
  deltas.
- Owner gates 6.1 to 6.4 of the ensemble-members change and 6.1 to 6.3 of
  the ensemble-families change were ticked against the wayfinder tickets
  rather than asked again.

## Facts learned that the code now reflects

- Both Docker images ship the `registry` package and the worker ships
  `api/weather_api/config.py`, which `ingest/window.py` loads by path to
  avoid a circular import through the FastAPI app.
- `pyproject.toml` sets `addopts = "-q"`, so `pytest -q` prints no summary
  line; run bare `uv run pytest` for counts.
- Retention lives in SQL (`003_retention_window.sql`) so publication and
  purge are one transaction; `ArtifactStore.purge_outside_window` delegates
  to it.
- The scheduler lives in `worker/runtime.py`; `ingest/scheduler.py` holds
  the decisions as pure functions.
