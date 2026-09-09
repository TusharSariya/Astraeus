# September 9 workbench integration

Classification: Experiment. The owner requested committing and merging the accumulated workspace work into main on September 9, 2026. No normative status or production profile changes.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006

Includes native WeatherNext maps/times, Atlantic demand clouds, IFS products and ensembles, forecast comparison, one timeline, temperature-based precipitation colours and explicit source selection, and preservation of radar provider RGB. The owning experimental contracts and detailed browser/live receipts accompany each feature under this evidence directory's siblings. Local `.claude/` settings and scratch worktrees are excluded.

Integration repairs reject malformed IFS catalogue/inventory responses without crashing the application, scope discovery search/focus to its own input, regenerate field metadata, and migrate the desktop expiry/no-extra-request check to the comparison endpoint. Legacy ECMWF point receipt fixtures explicitly inject the legacy adapter; new Atlantic IFS coverage remains in test_ifs_selection.py. The catalogue-selection test allows 15 seconds for the expanded native catalogue. Two missing SWOB scenarios restate existing experimental requirements without changing their behavior.

Verification (September 9, local macOS; no new live science acquisition):

- From `experiments/st-johns-weather-map/web`: `npm test -- --project unit`: 676 passed, 53 files. This supersedes earlier frontend-failure notes in precipitation/radar evidence.
- Same directory: `npm test -- --project gl`: 8 passed in Chromium, including shader pixel readback.
- Same directory: `npm run build`: passed, existing large-bundle advisory.
- Same directory: `npm run check:source-types`: passed.
- From `experiments/st-johns-weather-map`: `uv run --project api pytest -o addopts='' -q api/tests/test_demand_clouds.py api/tests/test_forecast_comparison.py api/tests/test_ifs_selection.py api/tests/test_source_grid.py api/tests/test_source_times.py api/tests/test_weathernext_delivery.py api/tests/test_weathernext_gcs_bridge.py api/tests/test_weathernext_native.py api/tests/test_weathernext_surface.py api/tests/test_source_delivery.py api/tests/test_desktop_series.py api/tests/test_ecmwf_query.py api/tests/test_hrdps_query.py api/tests/test_rdps_query.py`: 438 passed, 18 skipped. Platform-bound decoder coverage is separately recorded in feature evidence; skips are not passes.
- Same directory: `uv run --project api python scripts/generate_source_contract.py --check`: passed.
- Same directory: `openspec validate --all --strict`: 93 passed.
- Repository root: `PYTHONPATH=tools/specs uv run --project tools/specs python -m unittest discover -s tools/specs/tests -q`: 17 passed.
- Repository root: `uv run --project tools/specs python tools/specs/specctl.py validate`: zero errors/warnings.
- Repository root: `git diff --check`: passed.

Missing/expired data remains unavailable; provider imagery retains its provider style when numeric precipitation is absent. Temperature source/palette changes consume existing data only. Browser proof, normal/200% zoom screenshots, limitations, and bounded live receipts remain in the feature evidence directories. Rollback is a revert of the integration commit and rebuild of the experimental services; no database migration is introduced.

Captured radar HTTP headers use normalized LF line endings in Git; header values are unchanged.
