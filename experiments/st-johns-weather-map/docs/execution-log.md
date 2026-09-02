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

### Resolved: `test_layer_frame_contract.py` asserted a server-side frame fallback no accepted requirement grants (2026-09-02)

`test_a_frame_advertised_before_the_artifact_rolled_still_draws` failed on
every branch, and it was not time-window flakiness: the file has one commit in
its history, `1062de8`, which introduced it already failing, and both
parametrisations use fixed instants. It demanded that a rolled-away instant
answer `200` with a substituted `X-Weather-Valid-Time`, where map-layers **"A
layer declares a staleness tolerance and renders nothing beyond it"** and the
pending `goes19-cloud-mask-overlay` requirement **"Frames are observed scans
only and staleness fails closed"** both require a 422 naming the nearest stored
frame — which is what `grids.render_grid_image` and `aurora.py` do. Nor did
`frame-fallback-and-viewport-layout` grant it: that change states "No API or
server change", keeps fallback in `web/src/` behind a visible disclosure, and
constrains observed groups to fall back previous-only, while the test demanded
the *newer* scan. Decision: the code conforms and the test was wrong. It is
rewritten as
`test_a_frame_rolled_beyond_tolerance_is_refused_naming_the_nearest_scan`,
asserting the 422 and that the body names the nearest stored frame's valid
time, on the same fixed instants. The owner may reverse this by writing a
requirement that authorises a server-side snap on the raster path and says how
the response discloses the substituted instant; the test would then be
rewritten against that requirement.

Caveat carried forward: the accepted heading in `openspec/specs/map-layers/`
still reads "renders nothing beyond it", while `openspec/config.yaml` already
carries the amended fallback-with-disclosure wording as a governing rule. The
two should be reconciled when `frame-fallback-and-viewport-layout` is archived.

### Step 3: evidence-classes-and-derived-here

Wave 1 (2026-09-02): three subagents, API owner (sections 1 and 2), ingest
and registry owner (sections 3 and 4), web owner (section 5 plus the step 2
browser pass). Merged on `execution/evidence-classes`.

Wave 2 (2026-09-02): the API and registry agents had built two different
seams (`get_entry` versus `get`, different entry names and range rules); the
registry's names won and the store was adapted. Added during implementation:
task 3.4 (every staged artifact declares its evidence classes, the store
refuses an undeclared one) and the fog-state registry entry, because `/point`
already derived fog state and the spec's first-entry list omitted it. Task 4.0
landed the delivery kind as `published_cell` | `reprocessed` |
`intermediary_derived` on all 64 records (60, 3, 1). The step 2 browser pass
found and fixed a scrubber axis label overlap at rails under about 1150 px.

Facts worth knowing after this step:

- Until an adapter declares classes on its artifacts, the store isolates them
  and serves `null` with a notice. Every existing adapter now declares.
- The web treats a missing class exactly like an unrecognised one; a layer
  with an unrecognised class keeps its imagery and shows the reason.
- Ensemble statistics and sector sampling are registered disabled until
  steps 7 and 9 implement them. No Open-Meteo adapter exists yet, so the
  WeatherNext 2 record has no artifact.

### Step 4: field-catalogue-and-families, section 3 (API)

The response contract was fixed before sections 3 and 4 started so the API and
the web could be built against it at once; it is in `design.md` under
"Response contract". Section 3 landed it on `api/weather_api/`:

- Task 3.0 re-keyed the API's own tables, which sections 1 and 2 had left
  alone on purpose. Until this landed the API looked for a `total_cloud` no
  adapter writes any more, so live cloud reached neither `/point` nor the
  raster layers. The live half of the check was run as a pytest that builds an
  HRDPS-keyed artifact through the store, not against the running stack: that
  stack is built from code predating the re-key and would have measured the
  old tables.
- `VARIABLE_LEVELS` lost its four upper-air entries to `catalogue.resolve()`,
  which answers a level-expanded variable with the one profile key plus its
  level. The rest of the table stayed: an artifact's own declared
  `vertical_level` is a retrieved fact and the catalogue's level convention is
  not, so only the level-expanded names take their level from the catalogue.
- `comparability` is a computed property of `PointResponse` rather than a
  stored list, so it cannot describe a set of members the response does not
  carry. Pairs are deduplicated on the unordered key pair, and a key served by
  two sources appears once as a pair naming that key twice - which is the
  `comparable: true` case the spec's "two comparable members" scenario asks
  for.

Facts worth knowing after this step:

- The four cloud keys are four API field names now. Nothing in a response says
  `total_cloud` any more; a client reading that name reads nothing.
- The catalogue carries no dew point on pressure levels. The unavailable
  profile list and the fixture profile therefore stopped serving one, rather
  than claiming `dew_point_2m` at 850 hPa. Recorded as an open question in
  `design.md`; extending the catalogue is registry work.
- A derived relative humidity is stamped `liquid` from its registered method's
  own declaration. It is the only phase in a response that does not come off
  an artifact attribute.
