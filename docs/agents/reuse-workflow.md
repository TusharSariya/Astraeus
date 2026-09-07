# Reuse-first source workflow

This is a non-normative working index. It points to maintained code and checks;
the source registry and accepted OpenSpec contracts remain authoritative.

## Start every source slice with the existing seam

1. Read `AGENTS.md`, the relevant issue and its comments, then the source row
   in `experiments/st-johns-weather-map/registry/source_data.py`.
2. Search current main before creating a client, parser or cache. From the repo
   root:

   ```sh
   git fetch origin main
   git ls-tree -r --name-only origin/main -- experiments/st-johns-weather-map/api/weather_api | grep -E 'query|source-name'
   git grep -n -E 'source-id|product-name' origin/main -- experiments/st-johns-weather-map
   gh issue list --state open --search 'source-name in:title' --limit 20
   gh pr list --state all --search 'source-name in:title' --limit 20
   ```

3. Reuse the narrowest existing source seam. Read its fixed-fixture tests before
   choosing a request, decoder, cache, receipt or public model shape. If the
   accepted source identity, time rule, unit, quality meaning or failure state
   is absent or conflicts, record the decision needed on the issue and stop
   before implementing it.
4. Write the claimed source, canonical endpoint, accepted contracts, owned
   files and reusable seam in the issue before code. Update that record when
   the actual request, test command, receipt location or browser runtime
   changes.

A hostname is not source identity. A response that can contain a partner or
third-party station needs a source-identity guard before its values are served.

## Existing seams

| Need | Reuse first | Notes |
| --- | --- | --- |
| ECCC GeoMet WMS/point semantics | `ingest/adapters/eccc_geomet.py` (`GeoMetClient`) | It owns WMS URL construction, capabilities, axis-order and service-exception handling. |
| ECCC Datamart selected native data | `ingest/adapters/eccc_datamart.py`, `api/weather_api/gdps_query.py` | Reuse run/lead identity and bounded native decoding. |
| AWC METAR and TAF | `api/weather_api/metar_query.py`, `api/weather_api/taf_query.py`, `ingest/adapters/awc.py` | Preserve report identity, valid time and existing parser semantics. |
| SWPC Kp, magnetometer and plasma | `api/weather_api/swpc_kp_query.py`, `api/weather_api/swpc_rtsw_query.py`, `api/weather_api/swpc_rtsw_worker.py`, `api/weather_api/swpc_plasma_query.py`, `api/weather_api/swpc_plasma_worker.py` | These model mutable-feed time selection and typed receipts. |
| AQHI station observations | `api/weather_api/aqhi_query.py`, `api/weather_api/aqhi_query_worker.py` | Reuse station identity, distance and native-observation handling only where its accepted rule fits. |
| GFS-Wave or OVATION | `api/weather_api/openmeteo_gfs_wave_query.py`, `api/weather_api/ovation_query.py`, `api/weather_api/ovation_query_worker.py` | Keep their declared evidence class and producer/run semantics. |
| Bounded decode | `ingest/isolation.py` (`run_bounded_process`, `ProcessAllocationLimits`) | Decode untrusted provider bodies in the bounded child process. |
| Fixed HTTP and API routes | `httpx.MockTransport`, FastAPI `TestClient`, and the closest `api/tests/test_<source>_query.py` | Reuse these deterministic test seams before creating a launcher or test-only client. |
| Transport and receive budget | `ingest/http.py` (`PoliteClient`), `ingest/resources.py` (`acquisition_budget`) | Source adapters share pacing/retries and byte caps. Demand readers need final-byte receipts and redirect policy; inspect an existing demand service before sharing transport behavior. |
| Public receipt/cache models | `api/weather_api/models.py` and the closest demand query test | Keep request identity, safe headers, final-byte time, byte count, digest, expiry and typed expired metadata bounded. |

The current demand readers intentionally contain source-local cache and receipt
logic. Do not replace one with `PoliteClient` without preserving the demand
contract's no-redirect, final-byte and public-receipt behavior. A shared
bounded demand transport helper is a future refactor only after a contract and
migration plan exist.

## Tight vertical-slice loop

Run commands from the stated directory and record the exact target test, not a
full suite by habit.

```sh
# repository root: specification and PR-traceability gate
uv run --project tools/specs python tools/specs/specctl.py validate

# experiment root: focused source/API tests
cd experiments/st-johns-weather-map
uv run --project api pytest -q api/tests/test_<source>_query.py

# client changes only
cd web
npm test -- src/api.test.ts src/App.test.tsx
npm run build
```

Use `httpx.MockTransport` for a fixed body, FastAPI `TestClient` for the public
route, and an injected clock for cache hit, coalescing, expiry, replacement
failure, advancing final-byte freshness and individual-null tests. A source query answers only the
accepted native time/selection rule. Expired values are withheld; bounded
identity/expiry metadata may remain when its contract allows it.

For a default bounded child, prove the real process seam in Linux with the
source's focused test and a fixed `httpx.MockTransport` body. First prepare an
exact-head test image or mounted environment with the locked dependencies while
network is available. Then run the proof with network disabled:

```sh
cd experiments/st-johns-weather-map
# Use the exact prepared image and test name recorded by the source slice.
docker run --rm --network none --memory <source-limit> \
  -v "$PWD:/work:ro" -w /work <exact-head-prepared-image> \
  pytest -q api/tests/test_<source>_query.py::<default-child-test>
```

A clean `uv` image with an empty environment cannot install dependencies under
`--network none`; the preparation is separate from the proof. The proof
records the image digest, fixture request count and zero provider requests. A
new low-limit worker should use exactly one `{output}` placeholder and prefer
an absolute leaf script: AQHI needed that to avoid importing the full API under
its memory limit. Existing workers may use a module launcher only when their
actual Linux child test proves it stays within its declared limit. macOS may
reject locked `RLIMIT_AS`, so Linux is the proof environment. The test proves a
fixed fixture with no provider network; it does not make a temporary launcher,
receipt or captured body a permanent tool or Git artifact.

For the one browser proof, the runtime owner launches an exact-head fixed-live
harness with provider transport blocked. Confirm which endpoint supplies each
card: `/point` often supplies the selected `valid_time`, while a source-specific
endpoint such as `/space-weather` may provide the card data. The browser waits
for `DOMContentLoaded`, then locates the specific rendered card rather than
waiting for network idle. Read the displayed value, source, native time, quality
and receipt disclosure. Record ports, head and whether any provider request
occurred in the issue or handoff. The Linux proof establishes the production
worker/cache seam; the browser proof establishes client rendering against its
fixed-live API. Other agents inspect only after the runtime owner hands it off.

## Orchestrate one source job

Start with one brief that is specific enough to review before code:

```text
Issue and accepted contracts:
Source/product and canonical request:
Native identity, time, fields, units, quality and missingness:
Existing seam and fixed fixture:
Owned source/shared/proof files and worktree/head:
First observable artifact and its completion criterion:
Required API, client, Linux and browser gates:
Known owner decision or external blocker:
```

The first checkpoint completes the native request contract. Account for request
geometry, the full distance-aware search area, pagination or another proof that
the bounded result is complete, station/member/run identity, exact time
selection, field and quality semantics, final-byte receipt, cache expiry,
public response mapping and executable DQC. Read the latest issue, handoff and
worktree before reviewing; an earlier description is not evidence about a
newer tree. Reuse transport, cache and decoder machinery independently from
field/QC semantics: inherited code is not authority for a scientific mapping,
so preserve native values and tokens as unknown until an accepted contract maps
them. A reviewer returns one consolidated contract finding set before the Linux
or browser proof starts.

Use observable milestones for coordination. A checkpoint names the worktree and
head, changed files, exact command and process/session when one is active, its
latest result, and the one remaining blocker or next completion criterion.
Update at a meaningful state change, not every poll. The runtime owner hands off
API and web ports, process/session ids, served head, fixture identity and exact
tab URL once; other agents inspect those same handles. An orchestrator sends a
status request when this checkpoint is missing, and interrupts only after a
read-only check shows that the reported state is stale or progress has stopped.
The interruption states that evidence and the bounded next action.

Prove the actual default child path with fixed data early; an injected decoder
does not prove command construction, the `{output}` placeholder, package import
cost or Linux allocation limits. Then run the affected cache/API test, client
normalization and card test, build, strict OpenSpec validation and `specctl` as
the change requires. Batch exact-head review findings before correction. After
one supported correction, rerun only checks affected by that correction unless
a broader gate is explicitly required.

On a proof failure, inspect the same process output and artifact before starting
another process. Classify it as product code, fixture/harness, stale runtime,
contract conflict or environment. Preserve a valid prior receipt and use it for
offline replay; reacquire only when the proof specifically requires new source
bytes. A contract conflict goes to the owner with the smallest concrete choice,
while the held branch remains untouched and an independent ready task may
continue.

A handback names the exact clean head, review verdict, required checks, evidence
paths and hashes, owned processes still running, and open residuals. It states
which evidence is temporary and whether provider traffic occurred. The receiver
acknowledges ownership before editing or stopping a process.

### Model and effort routing (provisional)

Choose model and reasoning effort when dispatching a fresh job, then record the
assignment in the ledger. An existing agent keeps its current assignment unless
the runtime explicitly supports changing it; otherwise create the next job with
the revised choice and state that limitation. Optimize the total cost of a
reviewed successful result, including reviewer work, retries and rework, rather
than the lowest input-token rate.

Official API model ids, roles and list prices below were checked on 2026-09-07.
Prices are US dollars per one million API tokens; they are not verified charges
for a Codex agent job. The public model pages do not provide a four-model
benchmark by reasoning effort or a cost-per-reviewed-success curve.

| Model | Official API role | Input / output list price | Effort evidence |
| --- | --- | --- | --- |
| [`gpt-6-astra`](https://developers.openai.com/api/docs/models/gpt-6-astra) | Hardest end-to-end work | $10 / $50 | Public API: low through max. The current dispatcher also exposes ultra, whose cost/effect is unmeasured. |
| [`gpt-5.6-sol`](https://developers.openai.com/api/docs/models/gpt-5.6-sol) | Complex professional work | $4 / $20 | Public API: none through max. Current dispatcher: low through ultra; none is unavailable here. |
| [`gpt-5.6-terra`](https://developers.openai.com/api/docs/models/gpt-5.6-terra) | Balanced intelligence and cost | $2 / $12 | Public API: none through max. Current dispatcher: low through ultra; none is unavailable here. |
| [`gpt-5.6-luna`](https://developers.openai.com/api/docs/models/gpt-5.6-luna) | Cost-sensitive, high-volume work | $0.20 / $1.20 | Public API: none through max. Current dispatcher: low through max; none is unavailable here. |

The following task mapping is a medium-low-confidence hypothesis until the
ledger records comparable reviewed jobs. Escalation applies to a fresh job;
changing an existing agent is unavailable unless the runtime says otherwise.

| Task family | Initial model / effort | Escalation trigger | Evidence / confidence |
| --- | --- | --- | --- |
| Bounded lookup or docs correction | Luna low pilot | Contract ambiguity or code changes appear: use Terra medium. | Model role/price high confidence; task mapping medium-low. |
| Routine accepted source implementation | Terra medium | A substantive first review or focused test finds a cross-module defect: use Sol high for the next bounded job. | Model role/price high; repository cost-per-success unknown. |
| Standards and specification review | Sol medium, independent from the author | Cross-contract or scientific conflict cannot be resolved in one bounded pass: use Astra high. | Independence is repository policy; model mapping medium-low. |
| Deterministic runtime or browser diagnosis | Terra medium | One same-handle diagnostic leaves the failure unexplained: use Astra high for the next diagnostic job. | Retry-count comparison pending. |

For each completed job record task family, assigned model, effort, escalation,
evidence confidence, verified input/output tokens and cost when the runtime
provides them, retries/rework, elapsed measure and completion quality. Use
`unknown` rather than estimating absent telemetry. Pricing or benchmark values
belong here only with a dated official source or a named reproducible local
measurement.

### Learning ledger

Consult this ledger when dispatching a related job. Update it only when a
milestone supplies new evidence or tests a workflow change; link durable
artifacts rather than copying transcripts. `Unmeasured` is the correct outcome
when the repository has no timing or token telemetry.

| Job | Model / effort / cost | Observed bottleneck and evidence | Change tried | Rework and completion evidence | Next check |
| --- | --- | --- | --- | --- | --- |
| [AQHI #243](https://github.com/TusharSariya/Astraeus/pull/243) | unknown / unknown / unknown | The injected decoder passed before the real command exposed a missing output argument and full-package import exceeding the child limit. | Move the fixed default-child command test before API/UI proof. | One worker-launch correction; corrected leaf worker merged after exact-head review. | Confirm the next low-limit worker passes its default child before shared integration. |
| [Plasma #245](https://github.com/TusharSariya/Astraeus/pull/245) / [workflow #248](https://github.com/TusharSariya/Astraeus/pull/248) | unknown / unknown / unknown | Browser proof retried around `networkidle`, a missing `/point` prerequisite and label casing; checkpoint results arrived late. | Record exact handles and served head, use `DOMContentLoaded`, and separate source rendering from Linux worker/cache proof. | Proof and docs corrections; both PRs merged. #245 PR open-to-merge interval was about 40 minutes, not total implementation time. | Count proof retries and handoff corrections on the next card integration. |
| [handoff #249](https://github.com/TusharSariya/Astraeus/pull/249) | unknown / unknown / unknown | The first handoff scope statement required a successor correction. | Review the latest linked artifact and exact head before returning a verdict. | One docs successor; merged after an approximately 19-minute PR open-to-merge interval. Pre-PR work is unknown. | Verify current issue/PR state in the first review pass. |
| [Lightning #247](https://github.com/TusharSariya/Astraeus/issues/247) | unknown / unknown / unknown | Sampling authority surfaced after implementation began. | Complete one consolidated native-request and contract review before proof. | In progress; completion quality and elapsed implementation time are unknown. | Do not start Linux/browser proof until that review returns zero blockers or an owner decision. |
| [SWOB #251](https://github.com/TusharSariya/Astraeus/issues/251) / [PR #254](https://github.com/TusharSariya/Astraeus/pull/254) | unknown / unknown / unknown | The first author produced no code checkpoint; after ownership transfer, early review exposed request geometry, enumeration, report identity, inherited QC meaning and DQC gaps. | Transfer one clean worktree, then batch native-request and contract findings before proof; separate reusable mechanics from unapproved field semantics. | Exact-time MSC-only six-field demand, finite receipt/cache and scheduled-ingestion refusal merged at `978f6f8`; external Linux/browser receipts were preserved, #251 closed and partner residual #116 remains open. Token cost and total elapsed time are unknown. | Apply the complete first checkpoint before code on the next station source. |
| Orchestration | unknown / unknown / unknown | Repeated status-only prompts and interruptions followed missing artifact checkpoints and added task switching; no token telemetry exists. | Dispatch fewer scoped tasks, require observable checkpoints, and interrupt only with current read-only evidence. | Unmeasured. | Check whether the next job reaches its first targeted test and review without reassignment. |

## PR and handoff

Use the repository template. The governance parser requires all of these as
literal lines in the body:

```text
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004
Verification: exact command — result
```

Every referenced ID also needs a clickable link. Use a conventional lowercase
title such as `feat(source): add exact source query`; `docs(scope): ...` is the
same rule. Create PR bodies in a file and pass `--body-file` to `gh`.

Before merge, bind review, evidence and checks to the exact head. After a
squash merge, compare the reviewed head tree with `origin/main`, record the
merge SHA and remaining issue decision, then remove only the owned temporary
runtime and worktree. Add a short current note to `docs/handoffs/handoff.md`
when a completed slice leaves reusable workflow knowledge; keep historical
entries as history rather than copying them into this index.

Queue merges serially. A mergeable status does not prove the branch satisfies
an up-to-date-base rule; the actual merge result is authoritative. When only
documentation advanced the base, perform the required rebase, compare the
implementation tree with the reviewed tree, and reuse its proofs. Rerun only
checks affected by a real conflict or content change.
