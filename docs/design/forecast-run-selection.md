# Forecast-run selection across Map and Series

Discussion draft for [Settle forecast-run selection across Map and Series](https://github.com/TusharSariya/Astraeus/issues/68). No owner run-selection choices have been made yet. No API behavior, retention rule or normative status is changed.

## Existing decisions and evidence

- [Storage/window owner decision](https://github.com/TusharSariya/Astraeus/issues/20): forecasts keep latest complete run plus previous complete run within the sliding valid-time window. An archive of every forecast vintage is excluded. The two-run policy is also present in the committed storage specification; root working changes are not its sole source.
- [Map decision](https://github.com/TusharSariya/Astraeus/issues/46#issuecomment-5532224119): latest frame at or before Focus instant while under an hour old; never future frames. Run identity comes from the returned evidence, with frames/ages and full provenance. No on-map compare.
- [Series decision](https://github.com/TusharSariya/Astraeus/issues/50#issuecomment-5548103502): Overview plus temporary Compare, preserving source identity, native samples, gaps and run/freshness disclosure. Temporary workspace selections are not saved or shared.
- Later API discussion selected fixed-revision paginated Series snapshots, explicit refresh and relevant-change notices. Run selection must not change later pages of an active snapshot silently.
- `web/src/runSegments.ts` already recognizes adjacent frames with different run times. Its comments describe a short cycle leaving previous-run frames at leads the new cycle does not reach. This is run disclosure, not an implemented run picker.
- Existing Map/Series prototypes do not implement run selection. The Map URL records layer id/opacity/enabled state, not a run selector. Retained storage objects or run metadata alone do not prove that an API can read an explicitly chosen previous run.

## First discussion round

Proposed, not selected:

1. **Automatic default:** “Latest available” follows the published evidence selection at each valid time, naming the actual run on each frame/segment. It may show an older run at a lead the newest complete run does not cover, but does not disguise that as one newer run. It preserves the existing Map frame-age rule and Series native timing. No new source substitution is introduced.
2. **Explicit previous-run choice:** selecting “Previous” resolves to a named, currently retained run and pins that run identity. It does not silently advance to a different run when another cycle arrives. Within that pinned run, absent frames stay absent; neither Latest nor another source fills them. The control displays the actual run time/id, not just a moving “previous” label.

Later decisions: source-wide versus per-layer scope; cross-view sharing and Activity independence; URL persistence versus the temporary Compare workspace; unavailable/evicted run behavior; and whether comparing two runs inside Series is in scope. These must not silently alter prior scoring/source-precedence or workspace-persistence decisions.

## Boundaries and verification

Read-only client audit completed. Explicit run filtering must happen before the Map's existing frame match; stepping uses inventories for selected runs. Keep the Focus instant on missing frames. Series keeps native timestamps and does not adopt the Map's at-or-before sample substitution. Valid time, run initialization, retrieval, artifact revision and freshness assessment are separate identities.

Backend audit: retention policy already commits to two runs, but current API sampling reads current artifacts and the OpenAPI exposes no run selector. `/layers` attributes overlapping retained times to the newest run, so its `runs` summary can omit a fully overlapping previous run. It is not a selectable-run inventory. A read-only live catalogue probe returned 35 layers and no nonempty `runs` arrays, so no positive previous-run read was demonstrated. A future picker needs explicit readable-run inventory and run/revision-aware request/cache identity; relabeling the current summary is insufficient.

Both audits preserve these gaps for the API proposal. No positive previous-run serving capability is claimed. Run-stale flags remain evidence disclosure, not an automatic reason to hide or switch a selected run. Observation/nowcast sources without forecast-run identity do not acquire artificial run controls.

Classification: no spec impact; documentation and proposed choices only. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-005. Required documentation check: specctl validate. Implementation verification belongs to the later proposal after owner decisions and accepted contracts.
