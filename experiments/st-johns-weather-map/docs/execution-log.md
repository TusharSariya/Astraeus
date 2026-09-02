# Execution log: evidence-layer data-foundation charter

Started 2026-09-02 after the wayfinder map (issue #5) closed. The apply order
and owner decisions are in `session-2026-09-02-wayfinder-handoff.md`. This
file records what execution did, in order, and the triage of changes that
predate the charter.

Working rules for this log's sessions:

- Tasks are handed to Opus subagents, at most three at a time, each owning
  disjoint files, each in its own git worktree; the orchestrator merges and
  runs the gates.
- No registry status is promoted, `operational` stays `false`, nothing enters
  a production path (experiment, Spec-Impact: none).
- Only the owner authorises archiving a change into `openspec/specs/`.

## Triage of the pending changes that predate the charter (2026-09-02)

Complete, awaiting owner archive (every task ticked):
`interpolation-method-bench`, `space-weather-aurora-evidence`,
`upper-air-seeing-transparency`, `goes19-cloud-mask-overlay`,
`high-contrast-weather-reference-map`, `rendered-grids-and-raster-fidelity`,
`gfs-provider-cloud-strata`. Archive order constraint: the bench before
`generated-cloud-development`.

Implemented, one live gate open each (Docker rebuild plus a worker cycle or a
browser pass): `believable-cloud-motion`, `generated-cloud-development`,
`hrdps-rdps-rendered-cloud`, `multi-frame-cloud-motion`,
`night-sky-darkness-ephemeris`, `scrub-performance-and-motion-interpolation`,
`timeline-playback-and-frame-markers`. These gates run together in one
rebuild wave once the current stack is no longer needed for other
verification.

Not implemented, kept, slotted after step 9 of the apply order:

- `cloud-and-fog-evidence` (31 tasks). Compatible with the charter with one
  amendment: `fog_state` derived from METAR present-weather codes must be a
  `derivation-method-registry` entry of class `derived_here`, not a bare
  named derivation. WP3's live-proxy fog imagery is unchanged.
- `observations-strata-satellite` (25 tasks). Compatible: observations
  surviving a product selection is what source plurality already requires;
  the satellite proxies and the band filter are display-only.

Carried forward: `ensemble-members-and-source-plurality` task 2b.5 (the
delivery-kind field) had no implementing change; it is now
`evidence-classes-and-derived-here` task 4.0. Its owner gates 6.1 to 6.4 were
ticked against the wayfinder decisions of 2026-09-02.

## Steps

### Step 1: ensemble-members-and-source-plurality

Owner gates 6.1 to 6.4 recorded against tickets 17, 22, 24, 25 and 28.
2b.5 carried to step 3. Nothing left to implement in this change.

### Step 2: frame-fallback-and-viewport-layout

Open: task 4.2, the 700 px and 900 px browser passes. Running in wave 1.

### Step 3: evidence-classes-and-derived-here

Wave 1 (2026-09-02): three subagents, API owner (sections 1 and 2), ingest
and registry owner (sections 3 and 4), web owner (section 5 plus the step 2
browser pass). Gate 6.1 runs on the merged tree.
