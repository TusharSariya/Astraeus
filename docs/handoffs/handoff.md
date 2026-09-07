# Autonomous execution handoff: deliver the working desktop evidence app

Updated September 6, 2026. This is the current non-normative execution record.
It supersedes earlier framework-first queue instructions while preserving their
history and the owner's earlier design selections.

## Reuse-first source workflow

Use [the durable reuse-first source workflow](../agents/reuse-workflow.md) before
starting or handing off a source slice. It is the current index for existing
clients, bounded workers, receipt/cache behavior, focused proof commands and
PR metadata. This handoff remains the record of completed work and decisions.

## Plasma demand slice completed, September 7, 2026

[PR245](https://github.com/TusharSariya/Astraeus/pull/245) merged at
`a07a632fa710a7b93ace5829f69eb5ffeb910585`; its merged tree matches reviewed
head `da6248b`. The selected-time SWPC plasma query uses bounded fixed-fixture
proofs: its Linux default worker ran with `--network none`, and its browser
card ran against a fixed live `/point` harness with zero provider requests.
Issue [#242](https://github.com/TusharSariya/Astraeus/issues/242) is closed.
The retained proof files are evidence, not reusable launchers; use the
reuse-first workflow above for the durable procedure.

## AQHI demand slice completed, September 7, 2026

[PR243](https://github.com/TusharSariya/Astraeus/pull/243) merged at
`76058369b622220cad82779ca1a1b968111960e4`. Its merged tree exactly matches
reviewed head `c28c805`. The default unselected point response now serves the
bounded `eccc-aqhi` station-demand observation without a retained artifact;
the browser proof used fixed local data and the Linux child-decoder proof used
fixed MockTransport data. No provider payload was committed or used for those
checks.

Issue [#241](https://github.com/TusharSariya/Astraeus/issues/241) remains open.
The accepted product-companion rule still excludes `air_quality` evidence from
an explicitly selected forecast product. That source-specific decision is
tracked separately by #244; do not infer selected-product AQHI behavior from
PR243.

## PR234 review correction checkpoint

The two independent-review blockers now preserve bounded RDPS request/transport
identity in point/profile provenance and disclose expired metadata on refresh
failure while withholding all expired values. Metadata is capped at four
64-KiB records and one further source TTL; no retained native values or exception
tracebacks back a failure. Directory refresh failures preserve the same identity.
Retained native proof was replayed offline with zero upstream access and all
25 receipt/value/unit/time/cell checks unchanged. See
[the review correction evidence](../research/wayfinder/rdps233/README.md#pr234-independent-review-corrections).
21 focused RDPS tests and the two corrected deterministic GFS fixture-clock
tests pass; OpenSpec 75/75 and specctl 0/0 pass. The preceding full API run's
2,090 passes/44 skips/two baseline fixture-clock failures remain recorded
honestly; no full rerun or RDPS reacquisition followed the owner correction.
Fresh independent targeted re-review of remediation head `e12a0f9` found no
remaining Standards or Spec blocker. The focused deterministic tests and exact
GitHub checks passed. PR234 was squash-merged as `77c857c` with its reviewed
tree unchanged. No normative or operational status is promoted.

## Destination and map ownership

## Current owner correction: timestamp-driven delivery

On September 6 the owner replaced the background-ingestion architecture with a
selected-timestamp live-query path and a simple anti-hammering cache. This is
the current execution authority and supersedes the full-run/two-retained-run
source sequence below where they conflict. Preserve the older record as history;
do not present it as the current delivery design.

The required path is: selected timestamp -> cache lookup -> one bounded upstream
fetch on a miss -> native normalization -> response and cache fill. Concurrent
identical requests deduplicate to one upstream operation. Each source declares a
finite freshness TTL; an unsupported, unavailable, or expired timestamp returns
an explicit absence and never falls back to a neighbouring instant. The cache
may use memory, files, or the existing database as a measured implementation
detail. It is not a retained evidence archive, a background full-run ingestion
system, a two-run publication store, or the deferred shared-snapshot framework.

Source map #70 owns complete eligible field dispositions and this bounded
provider-to-existing-client path. Application map #38 owns later visual redesign.
Revise #201 and #208 against this route before merging their preserved work;
reuse bounded transport, decode, native semantics, API, and client components,
but do not require persistent artifact publication or full-horizon prefetch.
PR207 merged at `855493dbdbb86d5c99357955d06ab3dbd83a8856` and closes the
CYYT TAF slice under this corrected architecture. `GET /aviation/taf` now
queries one canonical provider product/station request, caps and validates the
complete response, caches it for the provider's effective `max-age`,
conditionally revalidates its ETag, coalesces process-local concurrent fills,
and applies the selected timestamp only when filtering native half-open groups.
The Workbench consumes the live result directly. No ArtifactStore publication,
model-run retention, background refresh job, or two-run evidence store is part
of that path. Exact live review observed a 5,908-byte response, `max-age=60`, a
matching 304 revalidation, and three applicable native groups; the experiment
remains `operational: false`.

HRDPS, METAR/SPECI, and NOAA SWPC Kp now use this timestamp-demand contract.
PR221 (`baa7f78f00db1c806fb8cc20f9855bee7b8b8144`) completed Kp: current
observed and forecast documents are bounded, cached by canonical provider
request, conditionally revalidated, and filtered locally for the selected
instant. Scheduled Kp acquisition is disabled and retained Kp is not presented
as current demand evidence. Their historical publication evidence remains an
audit record, not an application prerequisite.
Merged integrity and provenance safeguards remain available where the cache or a
source-specific implementation actually uses them. OpenSpec status changes still
require the normal owner-controlled workflow.

[Source map #70](https://github.com/TusharSariya/Astraeus/issues/70) owns every
eligible free-access product from a selected timestamp through bounded provider
access, native normalization, a real API response, and consumption by the
**existing web application**. A source is complete only when every eligible
product field has a retrieved, missing, unsupported, or deferred disposition
and retained evidence proves the normal query path. Catalogue entries, adapter
fixtures, or isolated captures alone do not complete a source.

[Application map #38](https://github.com/TusharSariya/Astraeus/issues/38) remains
a separate, linked effort for the later desktop visual rebuild. Do not merge the
maps or create another master map. Source work may make routine changes needed
by the existing UI; new layout, styling, shared-snapshot UX, and desktop design
stay with #38.

### Current #38 queue disposition

The desktop implementation contract is pending owner decision in draft
[PR239](https://github.com/TusharSariya/Astraeus/pull/239). Accessibility issue
[#69](https://github.com/TusharSariya/Astraeus/issues/69) has passing isolated
prototype keyboard repairs, while reader, assembled-production, raster/Activity
and physical-device evidence remains open; it is not a certification or a
current application implementation slice. #65 is owner-only outdoor validation,
#53 remains deferred, #66 needs a camera-placement decision, and #54 and the API-contract proposal portion of #55 remain open;
[PR239](https://github.com/TusharSariya/Astraeus/pull/239) covers only the frontend
proposal portion of #55. Do not create a competing frontend change until the applicable
owner decision changes this disposition.

The owner's current autonomous product outcome is one working desktop application
that uses every relevant eligible source. #70 owns source truth through the
existing client; #38 owns the subsequent desktop interaction and visual rebuild
on that working data path. Treat these as two linked delivery stages, not two
competing products. Reconcile broad, duplicate, obsolete and deferred children
against this outcome instead of mechanically closing every historical ticket.
A source or app ticket closes only when its evidence is complete or a traceable
replacement, exclusion, external block or owner-approved deferral is recorded.

The owner previously approved a corrective sequencing change after the September 6 delivery
audit: first make one complete HRDPS vertical slice work through the current
refresh/store/API/web path, then repeat complete source paths. That sequence is historical after the timestamp-driven correction above. Further fragment,
shared-snapshot, scoped-database-role, and general framework extensions are
paused until a measured source or UI failure demonstrates their need. This
supersedes the earlier framework-first sequence; it does not say those earlier
features were never selected and does not revert merged safety work.

## Measured baseline

Current main is `d582113d3eaaecefcb81c415614b0e32892c369e` after the corrected
TAF, HRDPS, and GFS timestamp-demand integrations. The earlier HRDPS persistent-ingestion proof
remains in history as measurement and native-field evidence; it is not the
current delivery architecture.
The registry contains 123 records: 21 are `implemented-unverified`. Seventeen
records intersected ingestible configuration and a registered adapter, but only
`awc-metar-speci` and `noaa-swpc-kp` implemented both finite discovery and
payload resource bounds at that audit point. PR199 subsequently added the first
fully verified HRDPS vertical. Treat these as dated code-configuration counts,
not proof that every registered source is live in the application; each source
still needs the vertical definition of done below.

The current web client still reads `/point`, `/timeline`, `/layers`, `/catalog`,
`/sources/status`, and the existing image/feature routes. It makes no snapshot
request. Before the post-PR157 source queue, the recorded live audit found 35
layers, 118 catalogue records, 54 fields on the one-point response, sparse
timeline coverage, and null profiles. Recent bounded acquisition and safety PRs
improved evidence and failure handling, but many deliberately stopped before
publication or existing-UI integration.

Trace the baseline through [PR157](https://github.com/TusharSariya/Astraeus/pull/157),
the partial-cache refusal in [PR161](https://github.com/TusharSariya/Astraeus/pull/161),
the payload gates in [PR162](https://github.com/TusharSariya/Astraeus/pull/162)
and [PR166](https://github.com/TusharSariya/Astraeus/pull/166), the durable
reservation implementation in [PR173](https://github.com/TusharSariya/Astraeus/pull/173),
and the deferred shared-snapshot contract in
[PR195](https://github.com/TusharSariya/Astraeus/pull/195).

## Completed first slice, next source, and definition of done

[#196](https://github.com/TusharSariya/Astraeus/issues/196) is complete via
[PR199](https://github.com/TusharSariya/Astraeus/pull/199). The reviewed and
merged trees were identical. On preserved PostgreSQL and MinIO volumes, the
bounded HRDPS path published one immutable 48-field, 25-time artifact, served a
consistent 14:00Z revision through `/point`, `/timeline`, `/layers`, `/profile`
and the existing Brief and Workbench, then completed an explicit refresh with
zero provider payload because the retained run was complete. Independent proof
compared 1,200 GRIB field-time inputs and 26,462,400 cells with zero value,
unit, shape or hash mismatches. The source remains experimental and
non-operational; #187 still owns the additional 195 HRDPS vertical catalogue
IDs.

[#201](https://github.com/TusharSariya/Astraeus/issues/201) is complete through
[PR207](https://github.com/TusharSariya/Astraeus/pull/207): CYYT TAF now uses a
bounded selected-time cache and the existing Workbench. HRDPS selected-time
point, profile, and metadata availability followed in
[PR213](https://github.com/TusharSariya/Astraeus/pull/213). GFS selected-time
point delivery is in [PR212](https://github.com/TusharSariya/Astraeus/pull/212),
and [PR215](https://github.com/TusharSariya/Astraeus/pull/215) adds native
pressure profiles, provider-advertised timeline availability, and audit-hides
legacy stored rasters. [PR219](https://github.com/TusharSariya/Astraeus/pull/219)
renders one selected-time native GFS `total_cloud_geometric` grid from the
bounded demand cache. Its retained actual replay kept provider requests at 19
across point, catalogue, raster, and repeat-raster calls; missing cells remained
transparent and the current map disclosed native 18Z/run 12Z evidence. #208
stays open for remaining GFS fields and raster dispositions; #97 remains the
owning all-source completion tracker. Other aviation products remain with #115 and remaining source bounds
with #159.

Every subsequent source follows the current definition of done:

1. Enumerate all eligible product fields and exact dispositions; do not hide a family behind a selected sample.
2. Resolve the selected timestamp to the provider's native valid time and bound discovery, network, decode memory/files and response size before payload retrieval.
3. Preserve source/product/run identity, native units, geometry, masks, QC, missingness and provider publication/valid/retrieval times.
4. On a cache miss, fetch the smallest provider-native response that can answer the selected timestamp, normalize it and return it; cache hits issue zero provider payload and concurrent identical misses deduplicate.
5. Enforce a source-specific freshness TTL and return explicit unavailable/unsupported/expired states without nearest-time substitution.
6. Prove retained raw-to-normalized-to-real API values and existing-client consumption, plus malformed, oversized, timeout, cache-expiry and concurrency cases.
7. Pass relevant API, registry/profile, strict OpenSpec, specctl and CI gates, followed by independent evidence review.

Continue until #97 can verify all relevant eligible source dispositions and
integrations, then execute #38 against those real paths. During the queue, triage
tracker children into four explicit outcomes: required delivery, duplicate or
superseded with a replacement pointer, deferred with a stated product reason, or
blocked by a named owner/external fact. Research completion, a merged contract,
or an adapter that cannot publish does not by itself count as delivered.

## Deferred work and retained safeguards

- #158 missing-only repair and #159 source-bound coverage remain open and remain
  blockers of #97 for their honest residual obligations. They are not blockers
  of #196 unless its measurements demonstrate that full-fetch repair or a shared
  bound is required.
- Unmerged fragment manifests, shared 15-minute snapshots, selection-refresh
  jobs, and scoped database roles are parked. Preserved worktrees are evidence,
  not merged capability. Resume only with a reproduced partial-cache, concurrent
  revision, or privilege-boundary need and an explicitly bounded task.
- PR173's merged durable reservation/fencing safeguards remain in main. Do not
  delete or weaken them. Unsupported adapters continue to fail closed.
- Draft contract PRs #167, #168, #172, #175, and #179 are concrete owner
  decisions, not accepted blanket authority. Present their recommendations as a
  batch when they directly unblock source publication; do not acquire additional
  variants merely to create more contract questions.

## Fixed boundaries

Keep `operational: false`, registry ceilings, and the selected timestamp range of 24 hours back through 14 days ahead. The old 64 GiB/two-run persistence policy does not define the new query cache; give the cache its own measured finite ceiling and TTL. No cold tier, paid service, rented compute, provider outreach, implicit rights
acceptance, science promotion, or public deployment is authorized. No raw
provider payload belongs in Git. Retain bounded raw bytes, headers, exact HTTP
completion times and artifacts outside Git until independent review; commit only
compact receipts and tiny representative fixtures.

Tracking truth is GitHub. Keep no more than three active implementation tickets.
All detailed work is delegated from the root orchestrator; completed runtime
threads may be reused. A lead does not independently approve its own evidence.
Use an independent reviewer before merge, preserve user worktrees, integrate
current main before final gates, and make conventional commits/PRs with exact
`Spec-Refs` and `Verification`.

## Current worktrees and claims

- Root user checkout contains unrelated work and must not be mutated.
- #196 HRDPS is merged and closed; its bounded evidence remains outside Git for audit.
- #201 CYYT TAF is merged and closed through PR207; its provider-response cache is the source-local pattern, not a generic persistence framework.
- #208 GFS point, native pressure profile, provider-advertised timeline metadata, and one native geometric-total-cloud raster are merged through PR212/PR215/PR219. Legacy stored rasters are audit-only. GFS APCP, SST, AOTK, cloud-top pressure, and remaining native rasters stay open under #208/#97. The related #191/#111/#107/#85 issues currently own ECCC precipitation, ocean products, aerosol observations, and satellite cloud products respectively; they are related family tracks, not precise owners for these GFS rows. The next APCP slice requires the native interval/card choice recorded in `docs/research/wayfinder/gfs-apcp-native-intervals.md`.
- Consensus demand selection merged through PR225 (`2f28452`), and GFS native
  total/low/middle/high geometric-cloud demand rasters merged through PR224
  (`61a2a04`). #208 and #97 remain open for their named residual fields and
  layers; these merges do not make the source complete.
- #226 merged through PR227 (`a110841`) as the bounded ECCC CAP Current-Alerts demand-query slice under
  #137. It uses a finite current-document request cache and preserves native
  validity, geometry, text, envelope and transport provenance. A successful
  empty response from every declared Avalon box may answer zero; a partial or
  malformed response never becomes an all-clear. The live capture on 2026-09-06
  was empty, so nonempty presentation remains contract-fixture evidence until a
  real warning is observed. #137 stays open for broader hazards, and #84 remains
  the active GEFS source track.
- #228 merged through PR229 (`bbea8d4`) as the bounded
  `noaa-swpc-rtsw` magnetic-field demand migration. It replaces only the
  retained solar-wind read in the existing `/space-weather` and Sky/Brief path
  with a selected-time source-local cache while preserving every native
  spacecraft and quality field. #89 was already closed for its bounded
  experimental source-acquisition scope; #70 and #97 remain open for their
  broader delivery and final-coverage obligations. Plasma, propagated wind,
  historical products, OVATION and local magnetometer access are unchanged.
- `/private/tmp/astraeus-live-query-snapshot-api`, branch
  `execution/live-query-snapshot-api`, preserves two local API commits and is
  paused; do not merge it under the corrective sequence.
- `/private/tmp/astraeus-scoped-db-roles`, branch
  `execution/scoped-weather-db-roles`, preserves uncommitted scoped-role work and
  is paused.
- The #158 fragment worktree remains preserved and paused.
- The current product-outcome handoff update is isolated at
  `/private/tmp/astraeus-autonomous-app-goal`.

Research and handoff prose are non-normative. Only the owner changes accepted,
verified, or superseded specification status.

Spec-Impact: none; this records authorized execution order and completion proof.


## RDPS selected-time implementation awaiting independent review

Issue #233 / PR #234 implements the bounded native RDPS slice under #70:
six producer-native surface fields, nineteen current pressure-profile fields,
and advertised hourly timeline metadata through f084. The selected-time path
uses only a finite canonical-request cache (600-second TTL, four entries,
32 MiB), with no background full run, two-run retention or ArtifactStore
fallback. Native WindSpeed/WindDir prevent grid-relative components from being
mislabelled as earth-relative direction. The experiment stays operational:false.

Independent ecCodes comparison matched all 25 fields and nearest native cells;
point/profile/timeline repeats added zero RDPS requests. Actual aggregate peak
was 757,927,936 bytes under the 4 GiB cgroup ceiling. Existing Brief/Workbench
replay and profile table passed. Full API: 2,088 passed/50 skipped; focused
cutover 46 passed; registry 237 and four profiles; web 452/build; strict OpenSpec 75;
specctl 0 errors/0 warnings. See `docs/research/wayfinder/rdps233/README.md`.

The 214 additional vertical IDs remain with #188; additional mapped low levels,
surface pressure and native/generated rasters remain outside this slice under
#188/#70/#97. Generic retained-layer tests now use the independently registered
six-hourly IFS source; an explicit RDPS stored-layer test asserts it is hidden.
Older no-fallback tests use explicit unavailable demand fixtures so public
provider variability cannot change their expected empty-demand result.

PR #234 passed fresh independent targeted re-review after its two correction
findings, with zero remaining Standards or Spec blockers, and was squash-merged
as `77c857c`. The reviewed and merged trees match. The review covered the exact
typed provenance and expired-metadata paths; the wider native/UI proof remains
the previously accepted evidence above. No normative status was promoted. Raw
receipts, API responses and browser proof remain outside Git in
`/private/tmp/rdps233-live`; this is audit evidence, never an application archive.
