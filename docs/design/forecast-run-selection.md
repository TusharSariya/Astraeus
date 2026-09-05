# Forecast-run selection across Map and Series

Owner decision record for [Settle forecast-run selection across Map and Series](https://github.com/TusharSariya/Astraeus/issues/68). The owner selected the automatic default and explicit previous-run behavior; shared scope, Activity independence and URL persistence are also selected; removed-run and temporary same-source comparison behavior are also selected; the bounded snapshot-retention exception is also selected. No API behavior, retention rule or normative status is changed.

## Existing decisions and evidence

- [Storage/window owner decision](https://github.com/TusharSariya/Astraeus/issues/20): forecasts keep latest complete run plus previous complete run within the sliding valid-time window. An archive of every forecast vintage is excluded. The two-run policy is also present in the committed storage specification; root working changes are not its sole source.
- [Map decision](https://github.com/TusharSariya/Astraeus/issues/46#issuecomment-5532224119): latest frame at or before Focus instant while under an hour old; never future frames. Run identity comes from the returned evidence, with frames/ages and full provenance. No on-map compare.
- [Series decision](https://github.com/TusharSariya/Astraeus/issues/50#issuecomment-5548103502): Overview plus temporary Compare, preserving source identity, native samples, gaps and run/freshness disclosure. Temporary workspace selections are not saved or shared.
- Later API discussion selected fixed-revision paginated Series snapshots, explicit refresh and relevant-change notices. Run selection must not change later pages of an active snapshot silently.
- `web/src/runSegments.ts` already recognizes adjacent frames with different run times. Its comments describe a short cycle leaving previous-run frames at leads the new cycle does not reach. This is run disclosure, not an implemented run picker.
- Existing Map/Series prototypes do not implement run selection. The Map URL records layer id/opacity/enabled state, not a run selector. Retained storage objects or run metadata alone do not prove that an API can read an explicitly chosen previous run.

## Owner decisions: default and explicit run

The owner answered “yes, yes” to both choices:

1. **Automatic default:** “Latest available” follows the published evidence selection at each valid time, naming the actual run on each frame/segment. It may show an older run at a lead the newest complete run does not cover, but does not disguise that as one newer run. It preserves the existing Map frame-age rule and Series native timing. No new source substitution is introduced.
2. **Explicit previous-run choice:** selecting “Previous” resolves to a named, currently retained run and pins that run identity. It does not silently advance to a different run when another cycle arrives. Within that pinned run, absent frames stay absent; neither Latest nor another source fills them. The control displays the actual run time/id, not just a moving “previous” label.

Later decisions: source-wide versus per-layer scope; cross-view sharing and Activity independence; URL persistence versus the temporary Compare workspace; unavailable/evicted run behavior; and whether comparing two runs inside Series is in scope. These must not silently alter prior scoring/source-precedence or workspace-persistence decisions.

## Boundaries and verification

Read-only client audit completed. Explicit run filtering must happen before the Map's existing frame match; stepping uses inventories for selected runs. Keep the Focus instant on missing frames. Series keeps native timestamps and does not adopt the Map's at-or-before sample substitution. Valid time, run initialization, retrieval, artifact revision and freshness assessment are separate identities.

Backend audit: retention policy already commits to two runs, but current API sampling reads current artifacts and the OpenAPI exposes no run selector. `/layers` attributes overlapping retained times to the newest run, so its `runs` summary can omit a fully overlapping previous run. It is not a selectable-run inventory. A read-only live catalogue probe returned 35 layers and no nonempty `runs` arrays, so no positive previous-run read was demonstrated. A future picker needs explicit readable-run inventory and run/revision-aware request/cache identity; relabeling the current summary is insufficient.

Both audits preserve these gaps for the API proposal. No positive previous-run serving capability is claimed. Run-stale flags remain evidence disclosure, not an automatic reason to hide or switch a selected run. Observation/nowcast sources without forecast-run identity do not acquire artificial run controls.

Classification: no spec impact; documentation and proposed choices only. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-005. Required documentation check: specctl validate. Implementation verification belongs to the later proposal after owner decisions and accepted contracts.


## Owner decisions: scope and sharing

The owner confirmed all three choices in live review:

1. Apply a run choice to that forecast source's layers in Map and readings in Series, keeping the two views aligned. Scope the choice to an actual provider run family/logical stream; never assume unrelated streams or products share a run just because they share a provider. If a selected delivery cannot address that run, show it unavailable rather than substitute another. Observation layers have no forecast-run selector.
2. Keep Activity verdicts on the previously selected server-side source/run evaluation policy. A Map/Series browsing override does not silently alter a verdict or its score. Its input provenance still identifies the evidence it used; make a mismatch visible when relevant.
3. Store source/run browsing choices alongside Focus in the URL, using explicit run identity for pinned selections and an explicit automatic mode for Latest available. This does not persist the temporary Compare workspace's selected fields/layout, and a URL cannot promise retention of an old run.

Expiry behavior and simultaneous same-source run comparison remain separate decisions. The owner-selected bounded snapshot exception below reconciles ordinary two-run inventory with temporary snapshot pins; specification changes and capacity validation remain prerequisites to implementation.


## Owner decisions: removed runs and comparing runs

The owner answered “yes yes” to both choices:

1. If a pinned run is removed from the readable inventory, keep its identity selected and show “Selected run no longer available.” Keep Focus and instant unchanged. Offer an explicit “Use Latest available” action; never automatically replace the pinned run. A stale link behaves the same way. Distinguish removal from a frame gap in a still-readable run and from a temporary service failure. Snapshot retention conflicts remain separately unresolved.
2. Permit the two retained, readable runs of one source to be overlaid in the temporary Series Compare workspace. Each trace names its run and source with distinct line treatment; preserve native timestamps, gaps and per-reading provenance. This comparison does not alter the shared source/run choice for Map or Activity, adds no Map comparison, and is not saved/shared. No run-difference calculation or new statistic is implied.

The bounded retention exception selected below resolves this policy conflict; it has not been implemented.


## Owner decision: bounded snapshot retention exception

The owner answered “yes”: retain the normal latest-plus-previous run inventory, but allow already-created, unexpired Series snapshots to pin the exact older revisions they need until their fixed advertised expiry. When a third run arrives, the displaced run leaves the new-query/selectable inventory, while existing snapshot pages can still read their pinned revisions until expiry. These transient pins can make physical retention exceed two runs temporarily, so this is an explicit exception to the current hard two-run retention rule, explicitly selected by the owner for subsequent specification changes.

Pins cannot renew themselves on page reads or change checks. Once a run is outside the normal selectable inventory, new reads cannot pin it again. Keep the existing storage quota; snapshot admission must fit declared retention/capacity budgets, refusing additional snapshots when they cannot be supported. Do not evict promised live pins silently, expand storage, or weaken the existing ingestion quota failure behavior. Expiry releases pins and allows purge; failures caused by unreadable pinned objects remain explicit.

The alternative is to enforce the physical two-run ceiling strictly and invalidate affected snapshots at publication, making their advertised expiry only an upper bound. That would revise the earlier snapshot retention promise and require an explicit restart-required response. The owner selected the bounded retention exception, not early invalidation solely because a third run arrives.


## Resolution and implementation handoff

All eight owner choices are recorded above. The normal selector lists the latest and previous readable runs per actual source/run family. Explicit pinning does not create indefinite retention; an expired link retains its unavailable identity and requires explicit reselection. A still-valid snapshot may read a displaced revision through its existing cursor only until the fixed expiry.

Carry the decision into the API and front-end proposals. Required implementation work includes a true selectable-run inventory, run-aware reads/cache keys for each supported delivery path, explicit unavailable paths, correct current-versus-retained attribution, snapshot pin lifecycle/capacity, and independent Activity provenance. Do not infer capabilities from run headers or retained metadata alone.

Proposed verification: automatic mixed-run segments identify every actual run; pinned-run filtering precedes Map frame matching; selected-run gaps never fall through; Previous does not drift on publication; URL restoration retains exact identity or explicit absence; Compare traces remain independent from Map/Activity; a third publication removes an old run from new-query inventory but preserves an existing pinned snapshot until expiry; page/check calls cannot renew expiry; pins are released and purged afterwards; quota refusal does not silently evict live pins.

Spec-Impact: none for this decision record. Owner approval of the design exception is not a normative document status transition. Accepted contract/spec changes and mapped verification are required before implementation. Documentation checks passed; the proposed implementation cases have not run.
