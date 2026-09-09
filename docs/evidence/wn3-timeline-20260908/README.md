# WN3 native timeline verification

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
Classification: isolated experiment. Owner's 2026-09-08 follow-up requests available
WN3 cloud times on the bottom timeline; no normative status transition.

The previous map-only `/layers` marker assembly omitted WN3 point selections.
The new `/sources/{source_id}/times` contract contributes native forecast valid
times for total-cloud mean in both WN3 scopes, including Data only. It decodes
only initialization and lead coordinates plus the pinned consolidated metadata,
not science arrays. Existing two-slot acquisition and run discovery are reused.
The past-week range makes permitted historical times reachable.

## Verification

- `uv run --project api pytest -q api/tests/test_source_times.py api/tests/test_source_grid.py api/tests/test_weathernext_native.py api/tests/test_weathernext_gcs_bridge.py`: passed, four platform skips.
- `uv run --project api pytest -q -rA api/tests/test_source_times.py`: seven passed, one Linux-only skip after adding cache coalescing/expiry coverage.
- `docker run --rm --network none --memory 2g -v <experiment>:/work:ro -w /work -e PYTHONPATH=/work/api:/work astraeus-lightning-proof:c88ff83 pytest -q api/tests/test_source_times.py`: seven passed before adding the parent-only cache test. Actual default decoder process exercised; zero provider network, no science chunks. Read-only pytest cache warning only.
- `npm run test -- src/workbench/sourceGrid.test.ts src/timelineModel.test.ts src/App.test.tsx`: 107 passed.
- `npm run test -- src/workbench/sourceTimes.test.ts`: four passed (native marker merging/run identity, malformed inventory, Data only/opacity reuse, obsolete response suppression).
- `npm run build`: passed; existing large bundle warning.
- Generated source contract check and `npm run check:source-types`: passed.
- `npx --yes @fission-ai/openspec validate weathernext3-surface-point --strict`: passed.
- `uv run --project tools/specs python tools/specs/specctl.py validate`: zero errors and warnings.

## Live provider and browser evidence

`live-times.json` contains seven native valid times from September 9 00Z through
06Z, from the published September 8 12Z run. `historical-times.json` contains 121
hourly times, September 2 00Z through September 7 00Z, respecting the strict
48-hour gate at acquisition. Objects in these responses are pinned root,
initialization and lead-coordinate objects only. These are actual upstream reads,
separate from deterministic fixtures. They are dated evidence, not a reusable
fresh inventory after their recorded expiry.

Chrome localhost:5173 was checked through CUA against the rebuilt live runtime.
The WN3-only stack displayed seven hourly markers and enabled previous/next frame
controls. Clicking the 02Z marker updated the URL, shared selected time, Point
data heading and grid to September 9 02Z; the reading completed as 99.8%. Tracks
showed the WN3 forecast label, Map + data, hourly valid times, six-hourly main runs,
seven selectable timestamps and the run identity. A screenshot was visually
inspected at the user's existing 1728×818 viewport with Tracks expanded; controls
and markers were legible. This follow-up did not repeat the prior grid work's
18-size/theme/zoom capture matrix.

## Bounds and limitations

Inventory covers at most two successfully discovered main-cycle roots at the
window ends, not an exhaustive archive/run browser. Missing discovery remains a
reported gap. Markers establish native time availability, not proof that every
science chunk can be fetched. Clicking selects the existing newest permitted run
for that instant; it does not pin the inventory's run as a requested override.
The app retains main-cycle discovery even though the provider initializes hourly.
Google's schedule: https://developers.google.com/weathernext/guides/dissemination.

Local API :8000 and web :5173 were rebuilt with compose.yaml plus
compose.weathernext.yaml. Existing Google identity was refreshed into API tmpfs;
no credentials were recorded. No commit was made; this extends the uncommitted
native grid implementation. Unrelated `.claude/` was not changed.
