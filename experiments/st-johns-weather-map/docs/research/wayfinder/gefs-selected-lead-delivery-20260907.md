# GEFS selected-lead delivery integration

Classification: owner-authorized, operational-false experiment. No source
admission or normative status changes. Spec-Refs: GOV-SPEC-004, GOV-SPEC-006.
Owning experiment contracts: `gefs-member-demand` bounded family and exact
control-index availability; `api-first-source-delivery` capability/identity;
`ensemble-families-and-member-statistics` member and derived-statistic identity.

## Integration seam

`GEFSQueryCoordinator.selected_lead_run(selected_time, refresh=False)` returns
one provider `RunCandidate`. Its `detail.valid_times` contains exactly the
resolved run plus selected lead, with the successful availability receipt and
digest. It acquires no family payload and no additional lead. It delegates to
the existing two-attempt, preflight-bounded discovery and fixed 600-second cache.
Returned mutable metadata is detached from cached transport evidence.

Do not wire this into the generic `run_inventory()` seam. The first eligible
cycle can succeed without probing its predecessor; when it fails, only the
successfully probed predecessor is established. Neither case proves two
available runs, a complete timeline, optional-field availability or a complete
member family. The exact native timestamp can precede the requested instant
under the existing three-hour floor rule; it must not be relabelled as the
requested timestamp.

`weather_api.gefs_delivery.point_capabilities()` is a concrete source-local
descriptor proposal for shared registration. It declares native product
`pgrb2ap5`, legacy point token `GEFS`, the seven registered fields, provider
members `gec00` and `gep01` through `gep30`, and existing locally computed
`ensemble_mean`/`ensemble_spread`. It declares no provider reductions, no
parameter defaults for quantile/probability, no native Series and no pinned
previous-run selection. The shared route should refuse unsupported Series and
explicit run/variant/level combinations before acquisition. Root owns shared
registration, selector forwarding and generated wire changes.

Existing `point_fields` remains the numerical read operation. Forward its
explicit member/statistic parameters; a member axis must never be silently
treated as deterministic. Statistics keep the raw member readings beside
them. Temperature is mandatory per member, optional-field gaps stay explicit,
method-specific completeness/QC guards remain authoritative, and averaged cloud
retains the provider-labelled interval. No decoder, units, bounds, payload cache,
refresh or family-coalescing logic changed.

## Verification

Offline Linux, no network, retained decoder environment:

```text
docker run --rm --network none --memory 4g --cpus 2 \
  -v /private/tmp/astraeus-api-first-gefs-delivery/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_gefs_delivery.py api/tests/test_gefs_query.py -q -p no:cacheprovider
```

42 tests passed. New tests cover exact selected-lead timestamps, first-success
and predecessor-only proof, no family I/O during metadata discovery, unavailable
inventory/backoff, detached receipts, unchanged expiry and member-versus-derived
descriptor identities. Existing GEFS tests cover canonical bounds, normalized
units, mandatory/optional absence, native control/member identity, cloud
intervals, receipts and complete-family cache/refresh behavior. This is offline
contract verification, not new live acquisition or native Series evidence.

`uv run --project tools/specs python tools/specs/specctl.py validate` passed with
zero errors and zero warnings. `git diff --check` passed.
