# Native Series implementation evidence, September 7, 2026

Conforming implementation under the existing single owner acceptance record;
GOV-SPEC-001, GOV-SPEC-004 and GOV-SPEC-006. This records implementation choices,
not a new product decision or a verified source/status transition.

## Implemented seam and bounds

`api/weather_api/desktop_series.py` adds `POST /point/series` and
`POST /point/series/changes`, retaining existing `EvidenceField` / `Provenance`.
Initial reads accept exact coordinates, an offset-qualified half-open window,
canonical catalogue keys and request-local selector IDs. Continuations accept
only their opaque signed cursor. Selected response backing stays process-local.

| Bound | Implementation |
|---|---|
| Selectors | 1–2; duplicate selector IDs rejected |
| Window | Positive, at most 24 hours |
| Native acquisition | At most 12 distinct source/timestamp point reads, sharing one read across selected fields from that source/time |
| Returned samples | At most 48, including native nulls |
| Selection bytes | At most 512 KiB including charged selection/cursor/identity metadata |
| Page | 1–24 units; a native reading or a row with no readings occupies a unit |
| Read duration | 45 seconds; timed-out source operation retains its slot until it exits, then stops before another point read |
| Concurrent acquisition | Two slots, no unbounded executor queue |
| Cache | At most 16 selections and 8 MiB serialized backing; five-minute fixed, nonrenewing expiry |

The existing coordinator still owns each individual transport/decoder bound and
source cache. HTTP timeout does not claim to forcibly kill its running worker.
No source worker/decoder, database, artifact store or ingestion schedule changed.
Capacity rejects new selections instead of evicting an unexpired reader pin.
Expired cursors remain distinguishable after lazy backing cleanup through their
signed expiry; process restarts cannot recover response backing.

Change checks consult only the selected native source/fields, comparing original
identities, values, availability and interpretation metadata. Retrieval time,
freshness and transport revalidation receipts do not themselves signal a change.
A source's ordinary finite cache may still answer the check; the response and UI
say so. Failed comparison is unknown; a slow comparison cannot outlive expiry.
Checks never replace displayed values or acknowledge a previously observed change.

## Native delivery coverage and residuals

This slice uses HRDPS, RDPS, GDPS and GFS coordinators' native inventory and exact
point sampling seams directly. It does not use the hourly `/timeline`, `/point`
observation fanout, or a retained-store fallback. It filters every returned field
by canonical key, exact advertised native valid time and source identity.
An empty consulted run listing is unknown, not proof of source-wide absence.
Fields missing from advertised timestamps are unknown; explicit returned nulls
remain native absences. Unsupported sources and unsupported named run pins are
explicitly unavailable, without substitutes.

Still open: inventory/read support for actual named previous runs and two-run
comparison; additional native observation/ensemble/environmental readers; full
source field admission; imagery availability/joins; camera metadata. Four
coordinator connections do not complete those source issues or the full Series
view. No live provider payload was captured or committed in this slice.

## Mapped verification

- `api/tests/test_desktop_series.py`: sparse independent timestamps, exact source
  filtering, zero/native absence, immutable pages, altered cursor, geographic
  refusal, window/read/byte/capacity limits, concurrent misses, failed refresh,
  deadline slots, unrelated/relevant update, fixed expiry including during check.
- Existing HRDPS/RDPS/GDPS/GFS query tests exercise their existing cache/sample
  seams. Two catalogue-exclusivity assertions failed identically at the preceding
  merged Bench revision; they now assert their particular live proxy survives a
  failed legacy store without excluding other admitted proxies.
- `web/src/workbench/NativeSeries.test.tsx`: native tables/axes, cursor continuation,
  exact Focus, cross-view and Compare selection persistence, explicit refresh,
  failed replacement, fixed expiry, and StrictMode initial-read replay.
- `web/scripts/prove-desktop-series.mjs`: real Chrome, fixed responses and clock,
  all external requests blocked; shared Bench, native null/zero, inspection and
  Escape focus return, Compare pin continuity, change check, failed refresh,
  expiry, three themes and 200% text zoom. Receipts/screenshots remain outside Git
  at `/tmp/astraeus-series-proof/`. This is browser verification, not a provider,
  screen-reader or outdoor proof.

The controller lives in App so changing stage/dock does not discard a selection.
Overview and temporary Compare share two selected tracks with separate value axes;
changing the Compare display alone does not acquire a replacement. Unknown class,
refused derivation and unmodelled provenance do not become plotted numbers.

Final validation is recorded in the pull request and existing handoff.

Validation: affected API/source suites 89 passed; complete client suite 473
passed, followed by the final eight Focus/Series cases after the unresolved-site
guard; production build passed. Both changed OpenSpec packages passed strict
validation and repository specctl reported zero errors/warnings. The browser
procedure passed after final view changes. The prior merged revision reproduced
both repaired catalogue assertions (two failures), establishing fixture drift.


## Read-only camera and geometry completion

The Sky batch adds `/registry/cameras` beside the existing site/horizon read.
An explicit public-field allowlist separates registry eligibility from image
implementation and actual retrieval. Version hashes cover only public content;
private terms/endpoints and audit exception text never enter the response.
Existing camera audit/refusal logic remains the authority. Outside-core point
and astronomy reads now return the typed `outside_supported_area` refusal with
exact requested coordinates. Unsupported geometry returns nulls. Registry,
camera, site, space-weather and astronomy checks: 77 passed, six kernel-dependent
astronomy tests skipped. This completes task 5, not imagery joins or camera delivery.


## Activity curve and input implementation checkpoint

The registered `activity_verdict` v1 entry now declares one profile input and
0–100 refused-outside-range output. `registry/grading.py` implements the adopted
step, directional linear, exponential and band curves, named threshold anchors,
low_cap, non-overridable shape parameters and override/anchor refusals.
`profiles/evidence.py` selects exact native source inputs with disclosed skips
and no averaging, then emits typed hard-stop/criterion evidence with original
values, defaults/overrides, loss, declared/evaluated/retained weight and reasons.
Failed QC, refused/unmodelled provenance, incompatible units, absent or ambiguous
native readings cannot become evaluated grades or clear hard stops.

Mapped tests: `test_activity_grading.py` contains hand-calculated boundaries,
comfort bands, corrected aurora direction, cloud low_cap and invalid overrides;
`test_activity_evidence.py` covers exact timestamps/source isolation, source
precedence, failed/suspect/unknown quality, stale retrieval, unit mismatch,
refusal flags and method switches. Together with affected registry/profile/model
checks: 160 tests pass. Seventeen affected client tests and build pass; strict
OpenSpec and specctl pass. Review is a separate main-agent pass.

Tasks 8–11 remain open: no aggregate score, profile-version change, verdict route
or Activity view completion is claimed by these components. A specific owner
question is pending: #64 requires active weights to total 1 while excluding
unverified paths; the running PM2.5 0.15 weight has no admitted RAQDPS path (#172).
Normalize the remaining selected weights or withhold the profile until its
complete selected budget exists. Dependent budget aggregation is held; other
desktop work can continue. No default scientific choice is inferred from elapsed
time or a registry declaration.


## Layer identity and imagery availability completion

Layer now carries explicit source/catalogue-field associations with known,
partial or unknown mapping status and reasons; declared field labels remain
separate from canonical keys. Mapping originates at the owning query/spec or
artifact declaration, never a product/title guess. Mixed SWOB declarations
list every supported field. The known HRDPS and HRDPS-WEonG proxy associations,
GFS demand grids, CAP, AQHI, OVATION and local grid/satellite records are exposed.
RDPS-WEonG lacks its own source record; GeoMet GOES composites do not have an
explicit association in their declaration, so those mappings remain unknown.
Unknown bundle fields retain their explicit source and unmapped declaration.

A separate imagery record declares status, assessment time, basis, published
times and reason. Existing Layer.times semantics are unchanged. Provider inventory is not retrieval/coverage proof. GFS availability names
validated cloud grids actually present in its finite cache, separately from a
new acquisition or point-coverage claim. A local grid/renderer is not a guarantee the next raster render will succeed. Stored sample times
alone do not establish upstream imagery availability. Station/CAP features
explicitly have no raster imagery. OVATION listing remains requestable with
unknown image times and makes no new request. Run attribution exposes its
assessment time while retaining the existing single run origin and frame runs.

Sources and Map use validated explicit associations and preserve old/malformed
metadata as unknown. A source inspector shows associated layers separately from
point readings; imagery times remain separate from listed samples and actual
draw receipts. No new source query, cache, persistence or timing rule is added.

Verification: 132 affected API tests pass, two existing opt-in live checks skip;
full client suite 485 passed, followed by 28 focused workbench cases after the
final metadata naming fix; build passes. A pre-existing proxy-exclusivity
assertion failed identically on parent 2409906 and is repaired to assert every
declared proxy remains live_proxy without excluding existing demand layers.
The baseline receipt is `/tmp/astraeus-layer-baseline.log` outside Git.
Fixed Chrome proof `web/scripts/prove-desktop-layer-identity.mjs` passes with
all external requests blocked; screenshots/receipt remain in
`/tmp/astraeus-layer-proof/`. No live source or physical-accessibility proof.
Task 4 is complete; source admission and remaining desktop obligations are not.


## September 7 named-run implementation

The existing HRDPS/RDPS/GDPS demand coordinators now expose finite latest/previous
candidates from their existing bounded directory discovery. Named reads resolve
one candidate before native-lead matching and reuse the existing run-specific
cache and decoder. The inventory retains at most two metadata candidates with
fixed expiry; failed refresh cannot return expired candidates. No new provider
archive, database, scheduled job, acquisition format or scientific mapping.
The source listing's older dated roots are not inferred when absent.

Native Series returns candidate IDs/times and an explicit inventory limitation.
Latest fills only timestamps absent from the newest listed run with actual prior
run segments. Named reads never substitute another run. Acquisition bounds count
source/run/time tuples, so comparison still fits the existing 12-read limit.
The relevant-evidence change baseline excludes unrelated inventory updates.
Existing unexpired selections keep their original rows and fixed expiry.
GFS retains its existing latest-only reader; other sources keep explicit native
reader absence. These are source integration residuals, not invented run access.

The desktop writes source-scoped pins beside Focus in the URL. Temporary
same-field run comparison uses discrete circle/square markers on one compatible
axis and native tables with zeros and checked gaps. It does not change the
browsing pin or Activity, persist comparison, or calculate a difference. Removed
pins remain selected with explicit Latest recovery. Current Map delivery routes
do not accept named runs: explicitly mapped layers and matching point-ledger
values are withheld for a pin, preserving the stack and inspector refusal.
Unmapped layers remain explicitly unscoped; no title-based association is added.

Verification: 66 affected API tests pass, including all three existing query
suites, inventory concurrent misses/fixed expiry/failure/removal, two-run keys,
segment provenance, wrong-run refusal and relevant change baselines. Three
fixed-date HTTP failures reproduce on unchanged parent 2409906; affected test
modules now pin their HTTP clock. Receipt: `/tmp/astraeus-runs-clock-baseline.log`.
489 full client tests pass; after final display fixes, 97 affected client tests
and production build pass. Strict validation of both desktop OpenSpec changes
and repository specctl pass. Main-agent review found and fixed a named-query
failure attaching the default-run expiry receipt; a regression case covers both
RDPS and GDPS. No independent-agent review is claimed.

`node web/scripts/prove-desktop-runs.mjs` (from the experiment directory, with
its Vite server on 5242) passes using a fixed clock, constructed API responses,
Chrome and blocked external requests. It covers URL pin, two-run overlay, native
missing sample, three themes, 200% text zoom, view-switch retention, Map refusal
inspection and explicit Latest recovery. Screenshots/receipt are outside Git in
`/tmp/astraeus-runs-proof/`; no new provider-live or physical-accessibility proof.


## Activity state/score aggregation checkpoint, September 7, 2026

`api/weather_api/profiles/verdict.py` implements the selected six-state
precedence over already-admitted criterion evidence. A lazy grading callback is
never called after a fired hard stop. Unknown stops preserve grades/coverage but
withhold scores. Lower conditions remain flags. Positive weights must sum to
one; no incomplete budget is normalized. Every active criterion must retain its
row, blocked access only reduces reachable weight, and coverage floor 0.60 is
inclusive. Score uses evaluated weight; zero-weight context is not graded.
Weighted-loss ties follow profile-file order, using decimal products so binary
rounding cannot falsely break a tie. Evaluated native quality/freshness is
preserved, with unknown age remaining unknown and no additional freshness gate.
Returned evidence is copied, including its native nulls and QC reasons.

This is an aggregation seam, not `/verdicts` or an admitted profile. Its quality
and freshness summarize evaluated hard-stop/criterion inputs; the eventual
route must also account for geometry/applicability evidence. The caller still
owns registered method refusal, versioned profile validation/admission, source
selection, explicit applicability, geometry, acquisition and finite caching.
The recorded active-budget decision is unresolved; no deployed profile weights
or source admission have changed. Tasks 8–11 remain open for those integrations.

Verification: `uv run --project experiments/st-johns-weather-map/api pytest
experiments/st-johns-weather-map/api/tests/test_activity_verdict.py
experiments/st-johns-weather-map/api/tests/test_activity_evidence.py
experiments/st-johns-weather-map/api/tests/test_activity_grading.py -q` passes
41 cases, including 21 aggregation cases. The fixtures are explicitly constructed,
not real profile scores or verified field paths. Strict API OpenSpec and specctl
pass. Separate main-agent review caught binary tie ordering and excluded computed
serialization properties when copying typed evidence. No API/client/registry
behavior is enabled by this helper alone.
