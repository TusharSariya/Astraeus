# Unused-work recovery and branch audit

September 8, 2026. Non-normative execution record. The owner explicitly asked
for unused branches/worktrees to be assessed for useful work to merge and issues
that could close. Four Astra-medium workers performed disjoint read-only audits;
root reviewed the recovery candidates. The normal dirty checkout was excluded.

## What is already on main

- [PR #296](https://github.com/TusharSariya/Astraeus/pull/296): initial reviewed source delivery, merged at `a4f77c6`.
- [PR #297](https://github.com/TusharSariya/Astraeus/pull/297): remaining source/API/frontend changes and fixes, merged at `773a793`.
- [PR #298](https://github.com/TusharSariya/Astraeus/pull/298): final VIIRS native inspection, merged at `2d87b67`.

All committed source work from the current team is included. Three older team
frontend worktrees retain generated-file differences; these were preserved,
not treated as missing finished features. Nine other clean, released team
worktrees were removed after complete preservation in main was verified.

PR #297 passed 2,896 backend tests (43 skips), 547 frontend tests, production
build, generated-contract drift checks and specctl. PR #298 added eight passing
Linux tests and independent review. Live captures remain outside Git.

## Legacy audit result

The [searchable inventory](legacy-work-audit-20260908.json) records every exact
head, branch/worktree, disposition, reason and relevant replacement or gate.
Initial comparisons used `773a793`; the later `2d87b67` delta was checked and
does not change the legacy conclusions. Squash merges were assessed using patch
equivalence, changed-file blobs and current implementations, not ancestry alone.

| Older worktrees | Count |
| --- | ---: |
| Already covered by main | 70 |
| Superseded by current implementations | 57 |
| Dirty and excluded from content inspection or cleanup | 18 |
| Historical or unaccepted design material | 12 |
| Requires contract reconciliation | 2 |
| Research-only recovery candidate | 1 |
| Total | 160 |

The separate 162 unattached branch refs reduce to 62 covered, 76 superseded,
11 current-team refs already assessed separately, four field-contract
reconciliation refs, six optional historical/design recoveries and three
selected research recoveries. Branches and worktrees are different inventory
units; these are not 322 independent missing features. No older production-code
branch was cleared for a direct merge.

Activity/process checks are point-in-time evidence. Dirty worktrees remain
untouched. Unknown branch ownership remains a cleanup hold. This audit does not
authorize deleting all covered or superseded history; any removal needs a fresh
activity/status check and preservation of unique files and captures.

## Recovered material

Only selected text was recovered; old stacked branches, prototype runtimes,
provider bodies and binary captures were not merged.

| Recovery | Original commit | Disposition |
| --- | --- | --- |
| [Raster compositing](../research/wayfinder/raster-compositing-compare.md) | `30792afafa1f` | Dated research for closed #44; library claims need revalidation before reuse. |
| [Workbench prior art](../research/wayfinder/workbench-prior-art.md) | `eb0ae0fc3f31` | Dated design rationale for closed #45. |
| [Renderer alternatives](../research/wayfinder/map-rendering-alternatives-2026.md) | `aa093e122fff` | Dated comparison for closed #56; no renderer migration approval. |
| [Free Open-Meteo access](../research/wayfinder/free-openmeteo-access.md) | `a9d933d969df` | Dated endpoint, provenance and budget research for closed #72. |
| [Band-math contracts](../research/wayfinder/band-math-renderer-contracts.md) | `d51b88206c52` | Research only; #57 still requires both working prototypes and measured browser results. |
| [RAQDPS field proposal](../../experiments/st-johns-weather-map/openspec/changes/raqdps-rdaqa-canonical-field-contract/proposal.md) | `9e4ed41`, `584eb2f` | Seven-file unaccepted proposal; #133 remains open. Rounding wording reconciled with its existing one-ULP rule; no field or source activation. |

All recovered text has an explicit historical/unaccepted note. No normative
status, implementation authority, data rights or scientific interpretation is
established by moving a document onto main.

## Retained decisions and issue state

- Snapshot API code remains gated by its unaccepted contract and missing DB/role prerequisites.
- HRDPA/HREPA #134, SST #153, AIWP #267/#268, reference inputs #123, CIOOS #112 and native GeoJSON drafts need current contract reconciliation before implementation.
- ECMWF #270 retains ensemble/control-field work; its earlier deterministic implementation is already represented in main.
- Field-wire and ensemble minimum-count policies require reconciliation with current contracts; old branch thresholds are not restored.
- Actual screen-reader work #69 remains unfinished; old prototype checklists are not spoken-output proof.
- RAP #271 and RRFS #260 remain applicable to Avalon. Older geographic exclusions were superseded by actual native-product evidence.

No additional whole issue became closeable through this audit. #54/#55/#241/#105
were already closed as completed; HRRR #259 was closed as not planned for Avalon
with native coverage evidence. Repository open issue count remains 80 at audit
completion. Research recovery does not close #57, #133 or any source family.

Verification for this documentation recovery: specctl, strict OpenSpec validation
of the recovered RAQDPS proposal, JSON inventory count/identity checks and
`git diff --check`. Runtime code is unchanged; no provider requests were made.
