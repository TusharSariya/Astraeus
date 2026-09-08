# API-first source delivery - September 7, 2026

Current execution record, updated September 8 00:08 UTC / September 7 17:08 PDT.
The source plan remains incomplete. This replaces the earlier restart checkpoint.

## Workspace and authority

- Integration: `/private/tmp/astraeus-api-first-delivery`, branch
  `execution/api-first-delivery`, base `origin/main` c88ff83 (PR #295).
- Preserve the unrelated dirty normal checkout at
  `/Users/tusharsariya/Projects/Astraeus`, branch `execution/activity-profiles`.
- Runtime exposes **20 total slots**, root plus 19 workers; all workers are
  explicitly Astra medium in isolated worktrees. Capacity is not a claim that
  every worker is running at each instant. Workers have bounded implementation
  and separate review assignments; completed work must not be repeatedly tested
  without a new change, failure or unresolved concern.
- Owner explicitly authorized API-first experimental source delivery, existing
  Google authentication, issue updates and closure of completed issues. The
  missing `aws-secrets-manager` skill no longer blocks the selected Google
  profile: the owner explicitly directed using existing auth. No token, signed
  URL or credential material belongs in logs, Git, browser data or provenance.
- Source admission, operational status, new scientific interpretation, phone,
  camera placement and physical verification remain separate. Lightning point
  vocabulary still awaits the specific owner decision recorded below.
- Implementation cutoff: September 7 17:15 PDT. Finish active work and checks;
  final passing merges and handoff window 17:40-18:00 PDT.

## Integrated behavior

The generated Pydantic/OpenAPI/TypeScript contract distinguishes source identity,
implemented capabilities, actual readings, coverage and safe configuration/read
states. GFS and AQHI prove the narrow descriptor/point/optional native-Series
interface. Shared deterministic fixtures currently cover catalogue/status,
GFS Series, AQHI companions/failures and CAMS AOD. New ECMWF/image shared fixture
builders are in progress; their existing browser proofs use captured API data.

- GFS: actual latest/previous run selection, pinned native Series, explicit
  refresh, native units, finite coalesced caches and fixed expiry.
- AQHI: strict selected-model observation companion, native station/report/QC,
  bounded Linux decoding, typed safe failures and correct response data mode.
- ECCC HRDPS/RDPS/GDPS: actual source-local explicit refresh handling and safe
  observed reads, including existing consensus call sites.
- ECMWF IFS/AIFS Single: bounded four-native-quantity point delivery plus the
  existing derived RH, exact run/time/cell, preserved distinct native cloud
  units, typed acquisition receipts, available-not-stored and non-primary.
  ENS/AIFS ENS and scheduled ingestion admission remain separate.
- CAMS AOD: exact intermediary-hour point evidence, finite Linux acquisition
  and cache, unknown producer run, non-primary status, corrected UI precision.
- GEFS/SWOB: shared point capabilities over their native query services. GEFS
  preserves combined member/statistic selectors and selected-lead run metadata.
  SWOB preserves actual `msc_id-value` and `*-data_flag-value` metadata and QC;
  absent instantaneous winds stay null. Neither gains synthetic Series.
- Holyrood: explicit exact-time paired metadata and cache-only exact-revision
  Rain/Snow GIF routes, original images in the inspector, validated receipts,
  failed-refresh retention and expiry withholding. Native scientific freshness,
  QC and georeferencing remain unknown. Listing bound is 512 KiB; each GIF
  remains bounded at 512 KiB. No numerical radar interpretation.
- OSTIA: isolated bounded daily acquisition, all intersecting native chunks,
  forced-termination scratch cleanup and final-download timestamp/expiry.
  Shared API integration and OISST remain incomplete.
- GOES ACTPF: isolated bounded native point reader preserves phase codes, DQF,
  exact scan interval, projection and sampled coordinates. Shared point mapping
  remains incomplete because existing generic sampling loses native context.
- WeatherNext: native statistics Zarr decoder plus explicit authenticated,
  generation-pinned GCS transport. Actual longitude `degrees` is accepted only
  with explicit `standard_name=longitude`; radians and missing units refuse.
  Bounded process bridge and query/API/cache wiring are separate deliverables.

## Evidence and current verification

| Source | Actual evidence | External proof location |
|---|---|---|
| GFS | September 7 18Z run /21Z frame, 22 anonymous requests, 27,125,905 B, real Linux decoder; captured-byte Series API replay, repeat zero downloads | `/private/tmp/astraeus-api-first-gfs-live-proof/` |
| AQHI | September 7 21Z ABEFS report, value 1.5 index; successful GET 2,626 B, real Linux decoder; two total requests including harness retry | `/private/tmp/astraeus-aqhi-live-proof/` |
| CAMS AOD | September 7 22Z intermediary value 0.07; two GETs 896 B, default Linux process; repeat zero downloads; browser fixture consumption | `/private/tmp/astraeus-api-first-cams-aod-live-proof/` |
| IFS/AIFS Single | September 7 12Z run /September 8 00Z lead; eight requests each, 3,039,613 /3,568,762 B; native Linux decode, exact point, zero repeat requests; subsequent API/browser replays offline | `/private/tmp/astraeus-ecmwf-current-live-proof/`, `...-current-api-proof/`, `...-browser-proof/` |
| Holyrood | September 8 00:00Z current pair; three GETs 32,914 B, 580x480 original GIFs; actual Linux validator and mounted API, zero extra cache/API requests. UTC rollover made the live listing small; large-directory capacity is fixture-tested | `/private/tmp/astraeus-holyrood-current-live-proof/` |
| SWOB | One GET 25,089 B; original decoder refused native ID alias. Corrected decoder replays those current bytes offline through actual API: station 8403603, September 7 23Z, 15.9 C /13.5 C /85% /1001.6 hPa /null winds. QC unknown; repeat zero payloads | `/private/tmp/astraeus-swob-current-live-proof/` |
| WeatherNext | Existing astraeus profile authenticated; exact historical root metadata HTTP 200, 182,540 B, 133 nodes. Subsequent real Linux historical precipitation p10 point: August 1 06Z, 0.0 m, 11 HTTP operations /2,003,960 B. No current/future serving or cloud-field proof | `/private/tmp/astraeus-weathernext-access-proof/` |
| NOAA AIWP Aurora | Current AURO_v100 GFS/IFS objects discovered; 262,144 B exact range establishes HDF5 native variables/grid/41 six-hour steps. No forecast values, full-file decode or Aurora 1.5 checkpoint identity established | `/private/tmp/astraeus-aiwp-prefix-proof/` |

Frontend assembled checkpoint: **541 passed**, production build passed; registry
**237 passed**. The first full Linux backend run returned **2,576 passed,
41 skipped, six failures**. Five were fixture compatibility/path failures and
have committed corrections; the unchanged Kp thread-start failure did not
reproduce in focused checks. A full corrected assembled run is required before
merge. Do not call focused reruns a passing full suite. Specctl and strict
API-first OpenSpec passed; 17 governance unit tests passed. New source commits
still require separate review/integration and appropriate final checks.

## One current access and configuration inventory

| Source / selected endpoint | Account / non-secret configuration | Implemented / configured / live state | Precise remaining action |
|---|---|---|---|
| ECCC GeoMet/Datamart | Anonymous; no credentials | AQHI and Holyrood delivery live/replay verified; lightning isolated exact-frame code | Resolve lightning `wms_getfeatureinfo_pixel`, returned coordinates and bare empty-object meaning; no invented science |
| ECMWF public Open Data | Anonymous; no archive account/key | Deterministic IFS/AIFS point/API/client verified | Complete separate ENS/AIFS ENS contracts/fields; no admission inferred |
| Named Open-Meteo | Anonymous selected endpoints; intermediary and applicable terms preserved | CAMS AOD verified; GFS-Wave source wrapper under review | Integrate ready wrappers and verify exact consumer identity; public production serving terms separate |
| WeatherNext3 statistics GCS | Existing `astraeus` gcloud profile works; project unset; ADC untouched; Requester Pays OFF. No WeatherNext API key | Root metadata and one historical native point retrieved with runtime auth; decoder/transport implemented, bounded bridge active | Finish bridge review, cache/manifest/API/frontend integration, requested fields and explicit temporal/serving terms. Keep raw requester-pays members excluded |
| Aurora1.5 Foundry | `FOUNDRY_ENDPOINT`, `FOUNDRY_TOKEN`, `BLOB_URL_WITH_SAS`; deployed model, native initialization and storage required | Versioned isolated SDK client being implemented; no deployment or inference proof | Establish concrete compute/cost/initializer and configure selected endpoint through runtime auth; credentials alone do not supply a forecast |
| NVIDIA FourCastNet NIM1.0.0 | Deployed endpoint, `NGC_API_KEY` for NGC setup, hardware and 73-channel initialization required | Versioned request/archive client being implemented; no deployed inference | Establish deployment/input ownership and output scientific mapping; hosted four-sample demonstration is not current delivery |
| NOAA AIWP AURO/GraphCast/Pangu/FourCastNet | Anonymous public S3; preserve publisher/model version/initializer identity | Current AURO_v100 GFS/IFS objects and native header verified; bounded range reader in progress | Decode bounded actual forecast values and establish checkpoint/field/QC contract; AURO_v100 is not proven Aurora1.5 |
| RAQDPS/RDAQA, OSTIA/OISST, NL air quality, GEPS | Selected public endpoints; product-specific native/QC/rights contracts | Source-local slices or guards implemented/in review; not all public consumers complete | Retain exact missing native contracts and unfinished fields; do not thin required chemistry or relabel member/reduction identity |

Blank documented inference configuration names (no values supplied):

```dotenv
FOUNDRY_ENDPOINT=
FOUNDRY_TOKEN=
BLOB_URL_WITH_SAS=
NGC_API_KEY=
```

Google historical/future terms are separate from authentication. Current official
terms use at least one-hour-old valid times for CC BY4.0; the existing decoder
conservatively retains its older 48-hour gate pending contract reconciliation.

## Tracker and next actions

#54 and #55 were closed after confirming their already-merged proposal/contract
deliverables. Both Wayfinders received current progress comments:
[#70](https://github.com/TusharSariya/Astraeus/issues/70#issuecomment-5577029017),
[#38](https://github.com/TusharSariya/Astraeus/issues/38#issuecomment-5577029172).
#241 AQHI and #105 Holyrood are closure candidates after the source batch passes
and merges. Keep #208 (remaining fields), #270 (ensembles), #247 (lightning),
#140 (WeatherNext serving/integration), #133 (chemistry), #153 (OSTIA/OISST)
and the broader source milestone open until their actual requirements finish.

No source-batch remote merge has happened at this checkpoint. Finish reviewed
worker changes serially, run the complete assembled check, push/open the source
PR, merge only after required checks pass, then close completed issues and append
merge evidence to both Wayfinders and this handoff. Preserve every residual.
