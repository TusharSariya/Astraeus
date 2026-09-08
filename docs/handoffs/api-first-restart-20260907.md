# API-first source delivery - September 7, 2026

## Resumed completion batch

The owner closed #69, #57 and #65 as no longer relevant; all three are closed
as not planned, without claiming their unfinished procedures passed. #70 is
the active source objective. PR #299's legacy recovery is merged at `538a363`.
The integration branch is now `execution/source-map-completion`; the normal
dirty checkout remains untouched. Earlier deadline and open-desktop-check
references below are historical and superseded by the resumed owner direction.

This batch integrates OSTIA's exact daily point product, historical WeatherNext
configuration/API delivery, and a RAP cache-expiry correction. OSTIA's native
float32 coordinate quantization is preserved rather than rejected as an
irregular grid. Captured actual API/browser readback covers SST, uncertainty,
mask, native analysis time and revision. WeatherNext preserves the historical
temperature provider mean and the conservative greater-than-48-hour gate;
denied access is safely distinguished from missing configuration.

The host Google profile is verified separately from the running Docker API.
Docker has no configured WeatherNext runtime identity; the new source status
reports missing configuration. The exact nonsecret configuration and runtime
boundary are recorded in
[the WeatherNext shared-API handoff](../../experiments/st-johns-weather-map/docs/research/wayfinder/weathernext-shared-api-20260908.md).
Remaining WeatherNext fields, temporal coverage and future-serving permission
are not completed by the historical temperature path.

All three daily/historical browser replays (OSTIA, OISST and WeatherNext) pass
with exact Focus/URL and complete provenance preservation, with no provider
requests. Existing explicit ISO Focus entry supports dates older than the map
scrubber window. The frontend passes 550 tests and a production build; regenerated
shared fixture consumption passes eight tests. Combined OSTIA/WeatherNext/source
API seam checks pass 35 tests. Final backend/registry checks and merge receipt
are recorded in the completion PR before issue closure.

RAP public mapping, GOES typed satellite provenance and lightning WMS pixel
semantics remain distinct contract decisions. GEPS's four mapped reductions
are the next shared-delivery slice; the fifth raw gust reduction and remaining
527 reductions are not silently admitted.

Current execution record, updated September 8 01:11 UTC / September 7 18:11 PDT.
PR #296 is merged into main at a4f77c63b90acfd8cf1e5d797ee9414236d21839.
PR #297 is also merged into main at 773a793540e85f59586828374e9f216040964b25.
PR #298 merged the last reviewed VIIRS native-inspection helper at `2d87b67`.
All committed current-team source work is on main.
The owner has now authorized auditing older unused branches/worktrees for useful
work to consolidate. The four-worker legacy value audit is complete; see the
[full disposition and recovery record](legacy-work-audit-20260908.md).
The overall source plan remains incomplete.

## Workspace and authority

- Integration: `/private/tmp/astraeus-api-first-delivery`, branch
  `execution/legacy-audit-recovery`, based on merged PR #298.
  The earlier delivery branch preserves the pre-rebase history.
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
GFS Series, AQHI companions/failures, CAMS AOD, ECMWF acquisition receipts,
Holyrood native images and SWOB station evidence. Generated contracts have a
default fixture consumer test, without requiring environment overrides.

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
| WeatherNext | Existing astraeus profile authenticated; root metadata HTTP 200, 182,540 B, 133 nodes. Historical August 1 06Z precipitation p10 0.0 m: 11 HTTP operations /2,003,960 B. Historical temperature mean 285.33551025 K (12.18551025 C): 11 operations /19,691,271 B; repeated read reused its receipt. No current/future serving or cloud-field proof | `/private/tmp/astraeus-weathernext-access-proof/` |
| NOAA AIWP Aurora | Current AURO_v100 GFS/IFS objects discovered; 262,144 B exact range establishes HDF5 native variables/grid/41 six-hour steps. No forecast values, full-file decode or Aurora 1.5 checkpoint identity established | `/private/tmp/astraeus-aiwp-prefix-proof/` |

Final frontend: **547 tests across 40 files passed**, production build passed,
SWOB browser proof passed with zero provider requests. Registry: **237 passed**.
Final assembled Linux backend: **2,896 passed, 43 skipped, zero failures**
in 366.94 seconds. Generated OpenAPI/TypeScript/fixtures reproduce with no drift.
The preceding run had 2,831 passes, 42 skips and one asynchronous SIGKILL test
observation race. The test fix passed 18 tests/one platform skip and a negative
control with group termination disabled. Specctl: zero errors/warnings.

The final delta includes shared METAR/GFS-Wave/OISST point capabilities, GFS's
already-decoded precipitable-water descriptor, and native-observation Product
selection. OISST uses its current five UTC calendar dates rather than the
forecast UI's 24-hour lookback. Eight source-point Linux integration tests pass,
including 36- and 96-hour publication lag. A captured real OISST native decoder
plus HTTP replay preserves September 6 12Z, 14.53 C SST, 0.29 C uncertainty and
revision `oisst-20260906-preliminary-118b45151142aaf5`; repeated GET adds no
acquisition. Receipt: `/private/tmp/astraeus-oisst-live-proof/http-proof-receipt.json`.

Reviewed isolated helpers also cover WeatherNext historical temperature mean,
GraphCast native points, RAP awip32, RRFS parallel temperature and thunderstorm
native reports. RAP boundary sampling retains its native-cell halo; RRFS times
canonicalize to UTC before cache keys and lead arithmetic. Independent review
cleared both fixes. Outlook refresh creates distinct acquisition revisions while
retaining a separate content digest. GraphCast's optional h5py tests skip in the
normal API environment and pass 21 tests in the explicit HDF5 proof image.
These helpers do not imply shared API admission or operational readiness.

## One current access and configuration inventory

| Source / selected endpoint | Account / non-secret configuration | Implemented / configured / live state | Precise remaining action |
|---|---|---|---|
| ECCC GeoMet/Datamart | Anonymous; no credentials | AQHI and Holyrood delivery live/replay verified; lightning isolated exact-frame code | Resolve lightning `wms_getfeatureinfo_pixel`, returned coordinates and bare empty-object meaning; no invented science |
| ECMWF public Open Data | Anonymous; no archive account/key | Deterministic IFS/AIFS point/API/client verified | Complete separate ENS/AIFS ENS contracts/fields; no admission inferred |
| Named Open-Meteo | Anonymous selected endpoints; intermediary and applicable terms preserved | CAMS AOD verified; GFS-Wave wrapper integrated and actual HTTP proof recorded | Keep intermediary and unknown producer-run identity visible; public production serving terms remain separate |
| WeatherNext3 statistics GCS | Existing `astraeus` gcloud profile works; project unset; ADC untouched; Requester Pays OFF. No WeatherNext API key | Authenticated metadata and historical precipitation/temperature retrieved; decoder, bounded bridge and cached historical point adapter implemented | Shared configuration/registration/API/frontend wiring and remaining requested fields are unfinished. Conservative 48-hour gate remains; reconcile serving terms separately. Keep raw requester-pays members excluded |
| Aurora1.5 Foundry | `FOUNDRY_ENDPOINT`, `FOUNDRY_TOKEN`, `BLOB_URL_WITH_SAS`; deployed model, native initialization and storage required | Versioned isolated SDK client implemented and fixture-tested; no deployment or inference proof | Establish concrete compute/cost/initializer and configure selected endpoint through runtime auth; credentials alone do not supply a forecast |
| NVIDIA FourCastNet NIM1.0.0 | Deployed endpoint, `NGC_API_KEY` for NGC setup, hardware and 73-channel initialization required | Versioned request/archive client implemented and fixture-tested; no deployed inference | Establish deployment/input ownership and output scientific mapping; hosted four-sample demonstration is not current delivery |
| NOAA AIWP AURO/GraphCast/Pangu/FourCastNet | Anonymous public S3; preserve publisher/model version/initializer identity | Current AURO_v100 headers and bounded range reader verified; real GRAP_v100 GraphCast temperature/pressure point decoded from 48 ranges /3 MiB | GraphCast still needs isolated delivery/cache/API and accepted field contracts; AURO_v100 forecast values and Aurora1.5 identity remain unproved |
| RAQDPS/RDAQA, OSTIA/OISST, NL air quality, GEPS | Selected public endpoints; product-specific native/QC/rights contracts | Source-local slices or guards implemented; OISST shared HTTP verified, OSTIA/chemistry/GEPS/NL public consumers remain incomplete | Retain exact missing native contracts and unfinished fields; do not thin required chemistry or relabel member/reduction identity |

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

## Tracker, consolidation and remaining work

Merged [PR #296](https://github.com/TusharSariya/Astraeus/pull/296) at
`a4f77c63b90acfd8cf1e5d797ee9414236d21839`. Closed #54/#55 for their previously
merged proposals and #241/#105 for completed AQHI/Holyrood delivery.
Both Wayfinders have actual merge evidence and scoped residuals.

The owner then authorized closing tasks proven inapplicable to the Avalon map.
Closed [HRRR #259 as not planned](https://github.com/TusharSariya/Astraeus/issues/259#issuecomment-5577398482):
both tested native sectors contain zero cells in the Avalon evidence box.
This does not deny the recorded Denver/Anchorage supported-Focus evidence.
RAP #271 and RRFS #260 remain open: newer native products prove Avalon coverage.
Regional exclusions within mixed issues do not justify closing applicable parts.
**80 issues remain open** after these five closures.

Keep #208 (remaining fields), #270 (ensembles), #247 (lightning vocabulary and
empty-frame semantics), #140 (WeatherNext shared delivery/serving), #133
(chemistry), #153 (remaining OSTIA integration), #137 (broader outlook paths),
#99 (currents/GloFAS), #112 (marine contract), #115 (aviation scope) and #116
(partner rights/observation contracts) open until their actual criteria finish.
Missing credentials, contracts or compute are not geographic exclusions.

Nine clean, released current-team worktrees were removed with ordinary non-force
`git worktree remove` after verifying all their changes in merged main. All
branches remain; unrelated and unmerged worktrees were preserved. Receipt:
`/private/tmp/astraeus-worktree-cleanup-receipt.json`. Inventory initially counted
213 worktrees and 358 branches; removal leaves 204 worktrees. The broad stale
workspace inventory still needs a separate evidence-based preservation audit.

Merged [PR #297](https://github.com/TusharSariya/Astraeus/pull/297)
at `773a793540e85f59586828374e9f216040964b25`. Final backend receipt:
`/private/tmp/astraeus-final-consolidation-api.log`. Both Wayfinders record its
actual merge. No additional whole open issue is proven complete by that delta.

VIIRS commit a370282 is independently reviewed, passes eight Linux tests on
assembled main, and is merged by PR #298. It preserves native raw categories, diagnostics and geolocation
from an exact retained NOAA-20 granule in a bounded process. The captured swath
is in central Asia, not Avalon; #102 remains open for geographic discovery, QC
meaning, applicable point/cache/API delivery and the other VIIRS products.

The owner explicitly authorized the legacy-work value audit after the initial
cutoff. Three auditors own disjoint groups of 54/53/53 older worktrees; a fourth
owns 162 branches without attached worktrees. Manifest:
`/private/tmp/astraeus-legacy-work-audit.json`. They must exclude active or
uncertain worktrees and report exact missing commits, value, contract/issue
mapping and required checks. Audit is read-only; no wholesale deletion or
completion claim is authorized by a branch count. Root owns review and merges. No completed worker
should be described as actively running. Do not restart excluded HRRR work or
retest completed sources without a new failure, change or unresolved concern.

Legacy audit complete: 70 older worktrees covered, 57 superseded, 18 dirty
excluded and 15 documentary/reconciliation candidates. No old production-code
branch is ready for direct merge; selected historical text is recovered on the
current branch. No additional whole issue qualified for closure.
