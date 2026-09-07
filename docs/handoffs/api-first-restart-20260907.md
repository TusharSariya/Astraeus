# API-first delivery restart checkpoint - September 7, 2026

The owner requested a second wind-down and restart, this time configuring **20
agents total**. All workers have finished. Do not launch or resume workers until
the owner continues after restarting. Work remains incomplete; this is a durable
pause, not completion of the source-delivery plan.

## Resume location and authority

- Integration worktree: `/private/tmp/astraeus-api-first-delivery`, branch
  `execution/api-first-delivery`. Source and client code is under
  `experiments/st-johns-weather-map/`. Latest implementation before this
  checkpoint is `dc13a3b`; use the branch HEAD for the checkpoint commit.
- Base: `origin/main` `c88ff83`, Activity PR #295. Nothing in this source batch
  has been pushed, opened as a PR, remotely merged or posted to the Wayfinders.
- Preserve the user's normal checkout `/Users/tusharsariya/Projects/Astraeus`,
  branch `execution/activity-profiles` at `9af2aaf`, with extensive unrelated WIP.
  Do not switch, reset, merge, commit or clean that checkout.
- Read this file, the current handoff, git status, the specification skill and
  owning experiment contracts. The September 7 user plan authorizes this
  isolated API-first experiment and selected-model AQHI companions. Preserve
  `operational: false`, evidence models, native science and V1 admission gates.
- Original schedule: implementation until 17:15 PDT, final checks 17:40-18:00
  PDT September 7. This second pause began about 15:30 PDT. Account for the
  owner-requested restarts; do not claim the broader task is finished.

## Runtime and worker instructions

`/Users/tusharsariya/.codex/config.toml` was changed and TOML-validated:

```toml
[agents]
max_concurrent_threads_per_session = 19
default_subagent_model = "gpt-6-astra"
default_subagent_reasoning_effort = "medium"
```

The [official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
counts spawned workers separately from the primary: 19 workers plus root permits
20 total when honored. The current runtime still exposes **8 total**; verify the
actual resumed runtime before claiming 20 became active. The owner wants root
on ultra and **every worker Astra medium**, in isolated worktrees. No new worker
was launched after this wind-down request. Do not fill slots without concrete,
independent work; use bounded assignments, review receipts and stop idle workers.

## Integrated implementation

- Pydantic source identity, declarative capabilities, safe configuration states,
  generated OpenAPI/TypeScript and deterministic shared wire fixtures.
- Narrow descriptor/point/optional native-Series seam over HRDPS/RDPS/GDPS/GFS,
  AQHI and named CAMS AOD. Native identity validation before acquisition and
  after reading prevents member/level substitution. Native gaps remain gaps.
- GFS actual latest/previous inventory, pinned runs, explicit refresh, coalesced
  misses and fixed expiry. Native K/Pa/etc. survive normalized point provenance.
- AQHI correct station/report identity, native QC preservation, bounded Linux
  decoding, expiry/refresh behavior and strict selected-model companion. A live
  observation now correctly makes the response live even if its selected
  forecast failed; the original forecast selection and unavailable fields stay.
- Safe recent read states have a finite 128-entry/300-second monitor. Typed
  HTTP denial survives actual AQHI wrapping. Named HRDPS/RDPS/GDPS/GFS reads use
  the observed seam. Status reads do no acquisition; readiness is not coverage.
  Full provider-specific configuration/startup assessment remains incomplete.
- CAMS AOD uses the existing named Open-Meteo adapter with a 60-second bounded
  Linux acquisition process, 2 in-flight requests, finite 32-entry/256KiB cache,
  fixed expiry and wrapped sample distance. `/point?product=CAMS AOD` exposes
  reprocessed, non-primary, available-not-stored evidence at the exact returned
  intermediary hour, with no invented producer run or native Series. Single-hour
  all-null data retains the adapter's existing QC refusal and unavailable result.
- Generic frontend point selectors consume `point_product`; conflicting tokens
  are refused and legacy absent metadata keeps the old mapping. Sources displays
  independent status; validated AQHI/SWOB failure receipts survive normalization.
- GEFS explicit refresh and complete-family coalescing retain old unexpired
  discovery after failed refresh. Native Series/inventory expansion remains open.
- SWOB explicit refresh plus cache-only native snapshot read hooks. It has not
  yet been added to the shared capability/Series interface.
- OSTIA correctly acquires all intersecting native chunks, maximum 16 per field,
  preserving masked cells and refusing missing chunks.
- GOES ACTPF has a bounded source-local granule/crop/cache path. Actual Linux
  validation rejects fractional phase codes and preserves native categories/DQF.
  No public point/image route was added for this new path.
- Lightning exact-frame source-local acquisition/cache/decoder is integrated;
  public point mapping remains held on the separate vocabulary decision below.
- Holyrood paired CASHR DPQPE rendered GIF query/cache is integrated with the
  existing adapter identity. This is image evidence, not numerical radar samples;
  a public image route has not been added.
- ECMWF deterministic IFS/AIFS Single four-field coordinator and bounded decoder
  are integrated as isolated code. Fixed monotonic expiry and native-unit
  provenance are corrected. IFS cloud fraction differs from AIFS percent.
  Existing refusal/public-dispatch gate is unchanged; ensembles remain separate.
- WeatherNext has a retained manifest validator/query/cache only. It does not
  yet have authenticated GCS acquisition, raw statistics Zarr decoding or client
  field mapping. Do not describe it as complete with only credentials missing.
- NOAA AIWP has a compact public listing receipt only (moved from test fixtures
  into research evidence). No 4.53GB model payload was fetched or decoded.
- Model-specific Aurora/Earth-2 requirements are recorded in
  `docs/research/wayfinder/inference-candidate-handoff.md` under the experiment.

Recent root commits: `1a99e63` AQHI response mode/actual identity; `8f1e74a` GFS
native units; `7008ffe` exact GOES categories; `fe6298b` CAMS total deadline and
sample distance; `e9be60c` nested receipt validation; `6ad34db` safe status and
named CAMS API; `f117fb8` generic point selector; `9ddad6c` CAMS storage/live
receipt; `dc13a3b` ECMWF native units. Earlier commits are already integrated.
**No worker implementation commits remain pending integration.**

## Verification and evidence limits

Before this pause, root shared/CAMS/status/AQHI/Series tests passed **73 tests,
1 host platform skip**. Generation and specctl passed. Final assembled checkpoint checks passed **142 offline Linux tests** across
CAMS, status, source contract, AQHI, Series and ECMWF; **103 frontend tests**;
generated TypeScript drift; and production typecheck/build. The known bundle
size warning remains. Do not conflate these focused checkpoint tests with the
still-pending full assembled regression.

Other completed worker checks: CAMS 66 offline Linux tests; ECMWF native-unit
regression 2 tests (red before fix); GOES 38 Linux tests; GEFS 37 tests; SWOB 20
Linux tests; OSTIA 14 tests. Frontend baseline after restart passed 520 tests,
including 8 real Chrome GLSL checks; final generic selector work passed 103
focused tests. Later shared changes still need the complete assembled run and
fresh CAMS UI/API consumption proof.

Live and offline receipts (raw data outside Git):

| Source | Exact evidence | Location |
|---|---|---|
| GFS | Current 18Z run /21Z frame, 22 public requests, 27,125,905 bytes, actual Linux decoder. Pinned Series HTTP proof replays captured bytes offline; repeats add zero requests. | `/private/tmp/astraeus-api-first-gfs-live-proof/` |
| AQHI | Station ABEFS/report AQ_OBS-ABEFS-20260907210000, 21Z value1.5 index. Successful proof: 1 GET/2,626B, actual Linux decoder, selected-model fixture composition and injected expiry failure. Two GETs total including harness retry. | `/private/tmp/astraeus-aqhi-live-proof/` |
| CAMS AOD | Exact 22Z intermediary value0.07, two anonymous downloads896B total,1.820s, zero repeat downloads, real default Linux process. Native run remains null;12Z metadata is context only. No live nulls encountered. | `/private/tmp/astraeus-api-first-cams-aod-live-proof/` |
| GOES ACTPF | Two public requests,2,172B listing +3,796,986B granule. Captured granule replayed through actual Linux crop186x465,44,600 readable cells and retained DQF. | `/private/tmp/astraeus-goes-phase-proof/` |
| ECMWF | Retained September5 IFS/AIFS payloads through actual Linux decoder/point sampler,12 fixture reads/source, zero provider requests and zero repeat payloads. No current live proof in this batch. | `/private/tmp/astraeus-api-first-ecmwf-proof/` |
| Lightning | Two anonymous GeoMet requests, exact advertised20:50Z frame, native bare empty object. Public evidence mapping held. | `/private/tmp/astraeus-lightning-api-first-proof/` |
| Frontend | Assembled selected-model/AQHI success and safe failure using actual fixed-fixture API responses and inspected screenshots. Latest CAMS selector only has unit/typecheck proof so far. | `/private/tmp/astraeus-assembled-frontend-proof/` |

CAMS proof saved all acquisition/assertion results before its final console
serialization failed on datetime; receipt/hash validation succeeded offline.
It was not reacquired. Compact metadata receipts in research docs are permitted;
raw live provider payloads remain outside Git.

## Configuration and owner-action inventory

No credentials were read or connected in this batch. Required exact
`aws-secrets-manager` skill was absent from local skill roots and AWS MCP
lookup. Owner was asked for its location or an authorized replacement. Never
call Secrets Manager get-secret-value/batch-get-secret-value or the agent daemon;
use the mandated asm-exec runtime resolution when that workflow is available.

| Source / chosen endpoint | Account and non-secret configuration | Software/configuration/live state | Precise remaining action |
|---|---|---|---|
| ECCC GeoMet/Datamart | Anonymous; no credentials | GFS/AQHI shared pattern and ECCC existing readers work; lightning/Holyrood source-local code | Resolve lightning point-method vocabulary; finish Holyrood public image delivery |
| ECMWF public Open Data | Anonymous; no archive account or key | Isolated deterministic software implemented and offline Linux-tested; public dispatch held | Owner resolution of demand exception #275 with distinct IFS/AIFS cloud units; then API/UI proof |
| Open-Meteo named CAMS AOD | Anonymous free noncommercial endpoint; no key connected | Source live-tested; API/shared fixture implemented; generic selector integrated | Verify assembled frontend consumption and applicable serving terms before any public production deployment |
| WeatherNext3 GCS statistics `weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/` | Approved Google identity, dataset approval and OAuth/ADC. No WeatherNext API key. Requester Pays disabled for chosen statistics bucket | Retained-manifest code only; default SDK/auth, raw decoding and consumer mapping unfinished; no authenticated proof | Supply secure workflow; establish approved identity entitlement and serving permission, implement/verify bounded native acquisition |
| Aurora1.5 customer-deployed Foundry | Documented legacy submission names `FOUNDRY_ENDPOINT`, `FOUNDRY_TOKEN`, `BLOB_URL_WITH_SAS`; deployment, atmospheric initialization and native channel contract also required | Requirements handoff only; no deployed/current forecast client or live proof | Select supported deployment/API version, establish compute/cost/input-output contract; then selected credentials through secure workflow |
| NVIDIA hosted FourCastNet historical demonstration | Optional bearer catalog credential; `NVIDIA_API_KEY` would be app-specific | Fixed historical-case demonstration does not meet current forecast delivery | Do not substitute for current forecast; select concrete current published output or versioned inference path |
| NVIDIA self-hosted FourCastNet NIM | `NGC_API_KEY`, suitable NVIDIA hardware and initialization data; other Earth-2 products differ | Version/channel/input/compute contract unresolved; no deployed client/live integration | Select concrete versioned product and initialized compute without assuming deployment is free |
| NOAA AIWP public S3 | Anonymous; no credential | Listing proves current FCN-v2-small object availability only | Establish bounded subset/NetCDF field/grid/unit/QC contract before acquisition/serving |

Current Google disclaimer page (updated September3) describes historical valid
times at least one hour old under CC BY4.0; newer/future-valid outputs have
experimental realtime terms. The existing validator conservatively keeps its
older48-hour gate. Root verified the current official page; changing the code
still requires reconciling that existing contract. Authentication and permission
to serve data are separate. Raw requester-pays members remain excluded.

## Resume priorities

1. Verify runtime exposes20total; restore only useful bounded tasks in Astra
   medium isolated worktrees. Do not repeat completed source implementations.
2. Run the full assembled backend Linux and frontend suites plus generated drift,
   build, strict OpenSpec and specctl. Review named deterministic point routes
   after switching them through the seam. No required full regression was claimed.
3. Prove CAMS selection and provenance with actual integrated backend fixtures in
   browser, reusing the existing source proof helpers. Reuse live captures.
4. Revisit source-status coverage: named point reads are monitored, but older
   direct consensus/observation call sites and platform/configuration prerequisites
   are not fully assessed. Do not label schema states as completed integrations.
5. Pending owner decisions remain lightning `wms_getfeatureinfo_pixel` (actual
   returned coordinates, unknown coordinates for bare{} no-density) and ECMWF
   demand exception #275. User concurrency replies did not approve these.
6. Continue ready higher-value source integration (ECMWF if approved, remaining
   RAQDPS/SST/ensembles/observations/satellite paths), then inference candidates
   whose actual contracts are settled. Missing compute is not credentials-only.
7. Update Source Wayfinder #70, App Wayfinder #38 and existing handoff with exact
   implementation/verification states; prepare reviewed passing PRs and merge
   serially under existing owner authorization. No remote writes occurred yet.
8. Preserve deferred phone/camera/physical-testing boundaries and remaining
   scientific/access contracts. The broader catalogue is not complete.

Useful tools: `rg` at
`/opt/homebrew/Caskroom/codex/0.153.4/codex-path/rg`; uv/npm/docker/gh available.
Locked offline Linux image `astraeus-lightning-proof:c88ff83`, experiment mounted
`/work:ro`, `PYTHONPATH=/work/api:/work`, workdir `/work`. Use appropriate memory
bounds; do not stop unrelated user Docker services. Current permission profile
is unrestricted with approval never; do not pass sandbox_permissions.
