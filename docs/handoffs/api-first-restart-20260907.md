# API-first delivery restart checkpoint — September 7, 2026

The owner explicitly requested a pause to restart Codex and reload concurrency
settings. Do not launch more agents until the owner resumes. All workers have
finished and source changes are committed locally. No remote push, PR, merge,
Wayfinder issue update, cloud deployment or credential connection occurred.

## Resume location and authority

- Integration: `/private/tmp/astraeus-api-first-delivery`, branch
  `execution/api-first-delivery`, implementation checkpoint `fa18b36`.
- Based on fresh `origin/main` `c88ff83` (Activity PR #295).
- The user's normal checkout `/Users/tusharsariya/Projects/Astraeus` is on
  `execution/activity-profiles` at `9af2aaf` with extensive unrelated WIP.
  Do not switch, reset, merge, commit or clean that checkout.
- Read this file and the current integration handoff, then inspect git status.
  Source work is under `experiments/st-johns-weather-map/`.
- Use `.agents/skills/manage-astraeus-specs/SKILL.md`, the accepted governance,
  and owning experiment contracts. The current user's API-first plan authorizes
  the isolated shared delivery experiment and named AQHI companion. Preserve
  `operational: false`, existing evidence models, and V1 admission boundaries.
- The original schedule was implementation until 17:15 PDT and final checks
  17:40–18:00 PDT on September 7. Account for the owner-requested restart;
  do not claim the broader plan completed at this checkpoint.

## Runtime and worker instructions

The owner wants an ultra orchestrator, Astra medium workers, and doubled the
backend roster from five to ten. Then the owner explicitly requested no more
launches while preparing the restart. Six backend identities have actually
worked; the remaining four have not been launched. One frontend worker finished.

`/Users/tusharsariya/.codex/config.toml` now has a validated `[agents]` section:

```toml
max_concurrent_threads_per_session = 7
default_subagent_model = "gpt-6-astra"
default_subagent_reasoning_effort = "medium"
```

The documented setting excludes the primary, permitting eight total when
honored. The pre-restart runtime still explicitly exposed four total slots.
Check the resumed runtime's actual limit. Do not claim it changed solely from
the file edit. All spawned workers used explicit `gpt-6-astra` / `medium`.

## Integrated work

The integration branch has reviewed source commits and these shared changes:

- `source_contract.py` freezes product/field/variant/level/run/location/time
  identities, capabilities and safe configuration state types in Pydantic.
- `source_delivery.py` provides descriptors, point reads and optional native
  Series planning over existing HRDPS/RDPS/GDPS/GFS and AQHI services. Acquisition,
  native timing, authentication and caches remain source-local.
- Existing catalogue/status responses carry declarative capabilities and
  configuration separately from successful retrieval and coverage.
- `desktop_series.py` uses the narrow interface, preserves full sample identity,
  validates explicitly requested dimensions before acquisition, and preserves
  the existing native gaps and finite snapshot limits.
- `scripts/generate_source_contract.py` generates affected OpenAPI and a shared
  deterministic fixture. Pinned openapi-typescript generates the client types.
  Canonical selection level and raw native level remain separate.
- Generic frontend selectors consume capabilities; Sources shows independent
  configuration status; per-reading identity is retained and validated.
- AQHI source refresh/concurrent-miss/expiry handling and station identity were
  repaired. Selected forecast responses now attach only the named native AQHI
  observation through the shared point seam and retain typed independent failure.
- GFS supports bounded actual latest/previous run discovery, named run reads,
  explicit refresh and four concurrent selection misses.
- Lightning has a bounded exact-frame source-local query/decoder/cache. Public
  point mapping remains held on the sampling-method contract decision below.
- Holyrood has a bounded paired CASHR DPQPE rendered-GIF query/cache. Its identity
  now reuses the existing native image adapter. It is not numeric radar evidence
  or a registered public image route.
- WeatherNext has a bounded retained-acquisition-manifest query/cache using the
  existing validator. It has no default GCS/auth transport or consumer mapping;
  do not call it a completed integration awaiting credentials alone.

Recent integration commits: `380218c` foundation; `826fa6e`/`fea45e5` lightning;
`abb051c`/`f7f65d9` Holyrood; `ffd46a5`/`acbf6f0` frontend;
`63a26b0` WeatherNext; `fa18b36` selected-model AQHI/native identity corrections.
Earlier AQHI and GFS commits are already in this branch; do not replay them.

## Completed worker commits awaiting root review/integration

| Worker / worktree | Pending commits | Delivered scope |
|---|---|---|
| source_gfs, `/private/tmp/astraeus-api-first-ecmwf` | `cb6c42a` | Isolated exact deterministic IFS/AIFS Single four-field coordinator and bounded decoder/cache; 32 tests, offline actual Linux decoder plus point sampler proof. No route/registry changes. |
| source_lightning, `/private/tmp/astraeus-api-first-lightning` | `a7b14b5` | OSTIA native chunk crossing acquisition fix; 14 fixture tests; missing chunks fail publication; no interpolation. |
| source_weathernext, `/private/tmp/astraeus-api-first-weathernext` | `f507704` | Official-source inference candidate handoff; docs only, no invented client or native validator. |
| source_noaa_ai, `/private/tmp/astraeus-api-first-noaa-ai` | `5f1807f` | Bounded anonymous AIWP FCN-v2-small availability receipt and precise missing NetCDF/scientific contract. No model payload/query/registration. Review receipt location against outside-Git live-capture policy. |

Other completed worker worktrees: `/private/tmp/astraeus-api-first-aqhi`,
`/private/tmp/astraeus-api-first-gfs`, `/private/tmp/astraeus-api-first-holyrood`,
`/private/tmp/astraeus-api-first-frontend`. Their submitted implementation commits
are already integrated. Worker previews/proof processes were stopped or exited;
do not stop unrelated user Docker services.

## Verification and evidence limits

At this pause, the combined root checkpoint passed:

- 43 tests in offline Linux: `test_observation_companions.py`,
  `test_source_delivery.py`, `test_desktop_series.py`, `test_holyrood_query.py`.
  This includes the actual kernel-bounded Holyrood leaf decoder. Read-only pytest
  cache warnings are expected from the mounted source tree.
- `uv run --project api python scripts/generate_source_contract.py --check`.
- `npm run check:source-types` and `npm run build` (existing chunk-size warning).
- `uv run --project tools/specs python tools/specs/specctl.py validate`: 0/0.
- `git diff --check`.

Earlier foundation/source tests passed (88 API tests plus one platform skip;
AQHI 25 Linux tests; lightning 20 Linux tests; GFS focused tests). The frontend
worker ran 509 tests before final correction, focused tests after correction,
build, existing desktop browser regression and the exact shared fixture proof.
Do not present these as a full final assembled-branch regression.

Outside-Git receipts include:

- `/private/tmp/astraeus-api-first-gfs-proof/proof.json`: retained actual GFS
  GRIB ranges through Linux decoder, zero provider traffic, zero repeat payloads.
- `/private/tmp/astraeus-lightning-api-first-proof/receipt.json`: two anonymous
  GeoMet requests, exact advertised 20:50Z frame, native bare empty object.
- `/private/tmp/astraeus-api-first-ecmwf-proof/proof.json`: pending worker's IFS
  and AIFS offline Linux decoder/point proof; 12 fixture requests per source,
  zero provider requests and zero additional cache-hit requests.
- `/private/tmp/astraeus-source-delivery-browser/` and
  `/private/tmp/astraeus-series-regression-browser/`: frontend fixture proofs.
- `/private/tmp/noaa-aiwp-bounded-receipt.json`: public listing only. Listed
  FOUR_v200_GFS 2026-09-07 12Z NetCDF is about 4.53 GB; no payload fetched.

The small anonymous AQHI capture verified transport and normalization (three
stations, St John's value 1.5, 21Z); do not conflate that with Linux fixture proof.
Existing retained native captures are under
`/private/tmp/astraeus-native-root-final-replay/`.

## Resume work, blockers and open questions

1. Review pending worker commits separately and cherry-pick serially. Do not
   represent their source-local candidate code as public API integrations.
2. Finish combined contract/API/client verification, including actual source
   consumption. Review Series sample identity against requested variant/level
   after retrieval (pre-acquisition capability validation already exists).
3. Review selected-model-unavailable plus available AQHI composition semantics
   and ensure the response mode/selection remains truthful. Current tests cover
   selected-model success, independent AQHI failures and invalid companions.
4. Configuration status currently returns anonymous-software ready for the five
   registered shared readers and unknown for others. The full source-specific
   missing configuration/access denied/product unavailable/compute/acquisition
   reporting and startup validation are not implemented yet.
5. Lightning: owner question pending for `wms_getfeatureinfo_pixel`, returned
   coordinates preserved, unknown coordinates on bare `{}` no-density result.
   Existing accepted point sampling contract only names rectilinear/curvilinear
   methods; proposal `71ede9a` is not accepted. Do not silently choose a method.
6. ECMWF: public demand exception #275 remains held. Existing scheduled IFS
   adapter refusal stays unchanged. The pending worker verified AIFS native tcc
   is percent while IFS is fraction; correct proposal wording before accepting
   a public mapping. No ENS/control assumptions or promotion.
7. Secret workflow: required `aws-secrets-manager` skill was not found in local
   skill roots or AWS MCP discovery. The owner has been asked for its path or an
   approved replacement. Do not read/connect credentials pending resolution.
   Never fetch Secrets Manager values directly; required workflow is asm-exec
   runtime resolution. Credential-free work remains independent.
8. WeatherNext current documentation reportedly changed its historical terms
   threshold to one hour; worker conservatively retained the earlier 48-hour
   gate. Independently verify exact current licensing before changing it.
   GCS statistics bucket is the preferred path; no API key or raw requester-pays
   member path. Software still lacks default authenticated acquisition and
   consumer field mapping. Maintain accurate terms versus access restrictions.
9. Aurora/NVIDIA: review `f507704` for model-specific initialization, channel,
   compute and deployment blockers. No free current hosted forecast is established.
   NOAA AIWP's public FCN-v2 file exists but has no settled Astraeus native
   field/grid/QC/bounded-subset contract. Do not invent one as credentials work.
10. Expand backend roster only after owner resumes. Suggested ready bounded
    assignments: named Open-Meteo delivery, existing ensemble delivery,
    observation companions, satellite/native evidence. Existing SST and NOAA AI
    work must not be duplicated. Confirm accepted contracts before writing code.
11. Update Source Wayfinder #70, App Wayfinder #38 and the existing handoff with
    exact completion states and one credential/prerequisite inventory. No issue
    or PR writes have been made in this session. Preserve deferred phone/camera/
    physical-testing boundaries. Finish passing integrations and durable handoff
    before claiming the overall plan complete.

Useful commands: `rg` is at
`/opt/homebrew/Caskroom/codex/0.153.4/codex-path/rg`. `uv`, `npm`, `docker`, `gh`
are available. Reusable locked Linux proof image:
`astraeus-lightning-proof:c88ff83`; mount the experiment at `/work:ro`, set
`PYTHONPATH=/work/api:/work`, workdir `/work`, `--network none --memory 1g`.
