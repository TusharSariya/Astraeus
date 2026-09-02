# Handoff: 2026-09-02 wayfinder session, evidence-layer data foundation

Read this before `HANDOFF.md`. That file predates this session and its gate
list is now superseded by the apply order below. Everything here is on
`main` at `41389f9` and pushed.

## What this session did

Charted and fully worked a wayfinder map for the destination "a
data-foundation charter for the evidence layer": every present and
forward-looking source covering the evidence box has a recorded admission
decision, and the processing decisions that make retrieved data comparable
are settled and written as openspec change proposals. The decision layer
that scores activities is the next effort and is out of scope.

- Map: GitHub issue #5, `wayfinder:map`. Its Decisions-so-far section is the
  index of every decision, one line each, linking the ticket that holds the
  detail. Read it first.
- Tickets #6 to #30 are its sub-issues. All closed except #30.
- Glossary: `CONTEXT.md` at the repo root. Use its terms.
- ADR: `docs/adr/0001-five-evidence-classes.md` (amended same day to six).
- Research: thirteen non-normative files under `docs/research/wayfinder/`.
- Charter: seven openspec changes under
  `experiments/st-johns-weather-map/openspec/changes/`, all strict-valid.

## Owner decisions that shape everything (do not reopen without the owner)

- Six evidence classes on a required per-value provenance field: retrieved,
  reprocessed, derived-here, intermediary-derived, generated-display,
  uncalibrated observation. Derived-here is allowed on every data path when
  inputs are all retrieved (any sources), listed, the method is an enabled
  owner-approved derivation-registry entry, and quality is no better than
  the worst input. Same-field cross-centre blending stays forbidden.
- Field catalogue: one physical quantity per key, related quantities in
  families carrying comparability notes; every field every admitted source
  publishes is stored (GeoMet subsets server side; non-subsettable feeds
  store catalogue-family fields and mark the rest available-not-stored).
- Evidence box 45.0 to 50.5 N, 58.0 to 46.0 W; Avalon detail box 46.6 to
  48.2 N, 54.3 to 52.4 W. Avalon validated first.
- Storage: 64 GiB hot, no cold tier, sliding window 24 h back to 14 d ahead
  used as a restart cache; latest plus previous run per forecast source;
  idempotent re-fetch; no vintage archive; verification out of scope.
- Horizon tiers are valid-time ranges, not source lists. Staleness is one
  native interval; run-stale at twice producer cadence.
- Ensembles: all six families (REPS, AIFS-ENS, IFS ENS, GEFS, GEPS
  reductions, ICON-EPS); member is a first-class coordinate; statistics are
  derived-here within one family and run.
- Admissions: this is pure research, so admit everything including
  restricted-terms and NC-licensed sources for research use; credential-gated
  sources are admitted credential-required and fail closed until the owner
  supplies keys (owner has NC-SPACES, MADIS, NL 511 credentials to give).
- Activities are pluggable profile files over field families; a minimal site
  registry with hand-registered horizons; sector sampling along a bearing is
  a registered derivation. Cameras need licence or written permission (Fort
  Amherst first); their geometry is hand-registered and validated by landmark
  reprojection; derivations enter disabled until 30-day METAR validation.

## Apply order for the seven changes

1. `ensemble-members-and-source-plurality` (pre-existing, pending)
2. `frame-fallback-and-viewport-layout` (pre-existing, pending)
3. `evidence-classes-and-derived-here`
4. `field-catalogue-and-families`
5. `storage-window-and-restart-cache`
6. `horizon-tiers-cadence-and-staleness`
7. `ensemble-families-and-member-statistics`
8. `source-admissions-ledger`
9. `activity-profiles-sites-and-cameras`

Each later change modifies requirements earlier ones write. Three
reconciliations were made and are recorded on issue #27: the pending
ensemble change's "sampled member" requirement now permits registry
statistics; the partnership-only state lives only in the ledger; the horizon
staleness block is written on top of frame-fallback's version.

Every `tasks.md` names owned files, an owner per section, and an exact
verification command per task, ending in `make test`,
`openspec validate <change> --strict` and
`uv run --project ../../tools/specs python ../../tools/specs/specctl.py validate`.

## Facts learned this session that the code does not yet reflect

- DSCOVR has left the SWPC real-time solar-wind feeds; they interleave
  SWFO-L1, ACE and IMAP with quality flags the `noaa-swpc-rtsw` adapter does
  not store. SWPC's STEREO-A relay and hourly Kp prediction are stale behind
  HTTP 200.
- Nav Canada weather cameras moved behind NC-SPACES authentication; the
  registry endpoint is dead. RIOPS and CIOPS Datamart roots are 404 (GeoMet
  has them). RAQDPS moved to the dated WXO-DD path, not withdrawn.
- GeoMet WCS needs SUBSET plus mandatory FORMAT and SCALESIZE; BBOX is
  silently ignored. No layered cloud, cloud base, AOD or ECCC precipitable
  water exists on GeoMet. ECCC seeing and transparency indices do exist there
  as class integers. HRDPS has 40, 80 and 120 m fields and its own fog
  diagnostic.
- GEFS has no instantaneous total cloud anywhere. AIFS-ENS is the only family
  with per-member layered cloud.
- GOES-19 has no fog or cloud-base product; CCLF five-layer cloud fraction
  is the useful find. One in-situ marine observation exists in the box
  (SmartAtlantic St. John's).
- With every published field, core-only storage is about 7.5 GB resident and
  about 108 GB per cycle upstream; ensemble members everywhere would be about
  1.7 TB per cycle, which is why non-subsettable feeds store family fields
  only.
- The CAMS registry licence text disagrees with the ADS catalogue (CC BY 4.0).
- REWPS is Great Lakes only. Radiosonde is unavailable everywhere.

## Pre-existing validator failures, untouched

`interpolation-method-bench` and `spec/web-raster-rendering` fail
`openspec validate --all --strict`. They predate this session.

## What is next

- Owner: work #30 (NC-SPACES inventory) with the workspace open, and send the
  Fort Amherst camera and NRCan STJ magnetometer permission requests.
- Execution: begin at step 1 of the apply order through the handoff gates.
  Never mark a source active; `operational: false` on every response.
- Housekeeping: the thirteen local `research/*` branches are stale copies of
  files now on main and can be deleted with `git branch -D`.
