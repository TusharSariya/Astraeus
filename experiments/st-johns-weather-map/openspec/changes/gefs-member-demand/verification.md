# GEFS demand verification (operational false)

Owner-authorized experiment; no normative status promotion. Spec-Refs: GOV-SPEC-004, GOV-SPEC-006. Owning experiment contracts: point-evidence-sampling, ensemble/member, evidence-class and scoped demand-query-cache delta.

- Bounds: 704 MiB cache/output, 4 GiB cgroup, 3 GiB tmpfs, plus 2 MiB discovery indices. Structural evidence: `/private/tmp/gefs-local-harness-evidence-20260906T1929-704`. Partial admission closes and deletes the original ZIP before replacing the same output path; it releases decoded arrays before its sole payload read. The production-shaped mandatory decode failure test asserts this allocation ordering.
- Native capture: `/private/tmp/gefs-live-f006-a7f130f-20260906T2006`, run 2026090612/f006, 31 indices plus 186 ranges, 217 bodies, 39,571,186 bytes. No further provider acquisition.
- Native oracle: `/private/tmp/gefs-replay-oracle-f006-20260906T2032/native-oracle.json`, 186 records, six fields, 31 identities, zero value/mask mismatches, TCDC 0–6 h interval.
- Final backend head `8e197a6`: retained native replay at 8002/5174 uses the actual bounded child, adapter, source cache, API and existing client. Discovery injects the retained successful canonical control index receipt; its original body digest/completion remain intact. The acquisition is the original capture, not this replay. Repeat counters: one family load, one successful retained discovery, zero provider requests. Original full transport receipts, responses and counters are retained in `/private/tmp/gefs-api-ui-replay`.
- Final normalized output is identical to the approved oracle for values, masks, coordinates, units and attributes after selecting the sole native valid-time axis (the oracle represents that time as a scalar). `successor-oracle-comparison.json` records zero mismatches. No payload-hash equality is claimed across these different ZIP layouts.
- Native DPT is absent for all 31 members. Temperature completeness is true; existing scope QC remains suspect (`scope_incomplete:dew_point_2m`). Browser readback shows `HRDPS PRIMARY - CONSENSUS UNAVAILABLE`, 9°C synthetic fallback input, all 31 GEFS member/control identities with native 12Z run, distinct difference-selector labels, and six-hour cloud interval. No QC override was made.
- A separate entirely synthetic contract fixture at 8003/5175 supplies HRDPS 9°C, GFS 11°C and an eligible GEFS mean of 100°C. Actual browser readback shows 10°C, `Experimental consensus`, `derived here`, and the explicit contributor/witness notice: HRDPS and GFS enter the mean; GEFS supplies ensemble evidence only. API input fields are fixture-labelled; the page prominently displays `SYNTHETIC CONTRACT FIXTURE ONLY`. This verifies mapping, not provider acquisition or a native positive Consensus result. Evidence and external harness: `/private/tmp/gefs-consensus-ui-fixture`, `/private/tmp/gefs-consensus-fixture.py`.
- API verification includes historical/current/future discovery, available cycles before estimated latency, two-probe/no-run/backoff, repeat zero I/O, successful and failed receipt binding, missing control, malformed index content, mandatory/optional decode failures, stable source ordering despite reversed concurrent completion, and authoritative summary/input/witness invariants.
- Client verification includes malformed, unavailable and unbound summaries, member/run/control labels, distinct selectors, and visible point evidence notices in both Brief and Workbench.
- Full API at `8e197a6`: `uv run --project api pytest -q` → 2,324 passed, 50 skipped, 80 warnings. Focused GEFS/API review suite: 46 passed. Full web before the final notice rendering: 450 passed; final notice rendering: 451 tests pass across 22 files. The last bound-input detail mapping passes all 91 API-normalization tests, including opening the detail and seeing each deterministic input’s source, valid time and QC. Browser expansion confirms the same two inputs; GEFS is absent from the numeric input list. `npm run build` passes (existing bundle-size advisory). `specctl validate`: zero errors, zero warnings.

Independent exact-head review is required before merge. This verification changes no accepted/verified/superseded status and activates no operational profile.

## API-first source-local refresh, September 7, 2026

Classification: owner-authorized experiment. Spec-Refs: GOV-SPEC-004,
GOV-SPEC-006; owning delta: `specs/demand-query-cache/spec.md`, requirements
“GEFS demand retrieves one bounded native member family” and “GEFS availability
uses a bounded exact control index”. The resumed API-first task explicitly
requires source-local refresh and preservation of unexpired entries after a
failed refresh. No normative status or source admission changes.

`GEFSQueryCoordinator.query` and `point_fields` now accept explicit `refresh`.
It reacquires the bounded control-index discovery and selected family, retaining
the existing preflight, validation, native member/control identities, intervals,
QC and 60-second failure backoff. Concurrent identical refreshes share one
complete acquisition; different selections wait behind that one acquisition.
Ordinary hits never move the 600-second discovery or payload deadline. A failed
refresh retains the old unexpired family and discovery receipt, including when
the new index changed digest; expiry never serves that old family as fresh.

Mapped fixture verification in `api/tests/test_gefs_query.py`:

- `test_refresh_reacquires_discovery_and_family_without_renewing_hits`: refresh,
  unchanged hit deadlines and reacquisition at the exact expiry boundary.
- `test_failed_family_refresh_preserves_unexpired_entry_and_original_deadline`:
  cached recovery after payload failure and refusal at expiry during backoff.
- `test_failed_discovery_refresh_preserves_unexpired_discovery`: the two-index
  failure bound, cached recovery, and refusal after expiry.
- `test_concurrent_refreshes_share_one_complete_acquisition`: event-coordinated
  callers share one discovery and one family load without timing sleeps.
- `test_point_fields_forwards_explicit_refresh_before_sampling`: source-local
  point-read refresh propagation before sampling.
- `test_failed_refresh_with_changed_index_keeps_previous_family_reachable`:
  failed new-digest acquisition cannot hide the prior unexpired cached family.

Exact verification:

```sh
docker run --rm --network none --memory 1g -v /private/tmp/astraeus-api-first-ensembles/experiments/st-johns-weather-map:/work:ro -e PYTHONPATH=/work/api:/work -w /work astraeus-lightning-proof:c88ff83 python -m pytest api/tests/test_gefs_query.py -q -p no:cacheprovider
uv run --project tools/specs python tools/specs/specctl.py validate
git diff --check
```

Result: 37 fixture tests pass; specification validation has zero errors and
warnings; diff check passes. This offline 1 GiB test container exercises injected
loaders, not the actual GEFS decoder, whose unchanged preflight requires a
measured 4 GiB cgroup and 3 GiB temporary filesystem. No provider requests,
credentials, deployment, browser verification or new native acquisition occur.

Residual: GEFS native run inventory/nativeSeries planning and shared delivery
registration are not implemented by this change. Its settled discovery remains
one selected lead in at most two eligible cycles; a latest/previous complete
run-time inventory would need a separately bounded native availability design.
REPS/GEPS delivery is unchanged. Member/statistic/quantile/threshold/comparison
semantics continue through the existing point sampler without new reductions.
