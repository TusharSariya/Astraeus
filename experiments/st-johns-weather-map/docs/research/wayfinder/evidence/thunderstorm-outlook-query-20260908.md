# Issue #137 thunderstorm outlook native snapshot delivery checkpoint

Experiment; Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004,
GOV-SPEC-005, GOV-SPEC-006. Owning experiment:
`experimental-eccc-public-hazards`, structured hazard content preservation.
Root assigned current API-first source-local delivery; shared public routes and
registry changes remain root-owned. No canonical manifest or operational
promotion is implied.

## Selected ready increment

`ThunderstormOutlookQuery` uses the existing `ECCCThunderstormOutlookAdapter`
and its documented collection URL:
`https://api.weather.gc.ca/collections/thunderstorm_outlook/items?bbox=-58.0,45.0,-46.0,50.5&limit=1000&f=json`.
No guessed product, SCRIBE field interpretation, lightning or radar path is used.

It retains at most one immutable normalized native FeatureCollection and
original upstream digest/URL/completion/headers. Maximum response and combined
normalized cache are each 8MiB. Default HTTP acquisition has one attempt;
requests use the existing bounded/paced transport. Retention expires after
60 seconds fixed before acquisition, using both UTC and monotonic clocks.
This is retention, not scientific freshness. Shared misses coalesce; explicit
refresh replaces only successful complete snapshots and leaves an unexpired
previous revision after failure. The collection identity hashes canonical
native JSON; source byte SHA remains separate in the receipt.

The source-local metadata lists native feature IDs, file IDs, amendments,
publication time, validity time and expiration time without changing their
semantics. It records all 24 advertised field dispositions and uncontracted
properties. `report(revision, feature_id, publication_time)` requires an exact
retained revision and native publication instant and returns the full native
feature, including polygon and properties. It never acquires or substitutes
another report. Missing/duplicate IDs, pagination and incomplete matched counts
are refused. Empty observations have no invented report/time and are explicitly
not a safety all-clear. Operational and primary are false; scientific freshness
and source quality unknown. No point classification or derived warning score.

## Current public proof

One anonymous bounded GET completed at **2026-09-08 00:17:47.398392 UTC**.
The response was a valid observed-empty FeatureCollection: 892 bytes, upstream
SHA-256 `ae47697e8bb535ac4dfa14eba235b9d5b15857d53e64ef379c3124932ccbbd20`.
Canonical retained revision:
`652dd3b99754a9c21654dbafea2965566593ff55ebb9507e889d00124cc889cb`.
Repeat snapshot read made zero additional requests. This proves actual empty
collection acquisition/cache readback, not a live active report, native interval
filtering, geographic inclusion, or mounted public API route.

Raw upstream bytes, canonical immutable snapshot, metadata, receipt and harness
are outside Git at `/private/tmp/astraeus-thunderstorm-outlook-live-proof/`.
The actual source ran in locked Linux image `astraeus-lightning-proof:c88ff83`
with a read-only experiment mount, 1GiB memory, and no credentials. JSON handling
reuses the existing bounded adapter; this path adds no scientific pixel decoder.

## Tests and issue residual

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-eccc-outlook/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work \
  astraeus-lightning-proof:c88ff83 python -m pytest -q -p no:cacheprovider \
  api/tests/test_thunderstorm_outlook_query.py api/tests/test_adapter_eccc_hazards.py
uv run --project tools/specs python tools/specs/specctl.py validate
```

23 offline Linux tests passed; specctl 0 errors, 0 warnings. Nonempty fixtures
verify exact native publication/report/amendment/interval/geometry/unit
preservation, immutable caller isolation, empty state, pagination/truncation,
missing/duplicate IDs, revision replacement, failed refresh and UTC/monotonic
expiry. Existing adapter tests preserve unresolved canonical manifest behavior.

Issue #137 remains incomplete: root must decide/mount a native vector response
surface and verify actual API consumption; no shared route is added here.
CAP already has a separate query path. Four hurricane native collections remain
adapter-only and require a complete-family read/cache surface. SCRIBE/integrated
nowcasting remains unsupported pending the existing published matrix schema
pin. No live active thunderstorm report occurred in this proof. Do not close
#137 or claim the entire public-hazard family is delivered from this increment.
