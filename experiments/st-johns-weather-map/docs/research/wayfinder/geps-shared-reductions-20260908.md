# GEPS shared point delivery: four mapped reductions, five acquired coverages

Experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005,
GOV-SPEC-006. Existing ensemble provider-reduction, field-catalogue and
API-first source identity contracts own this source-local addition. The owner
requested delivery over the five existing verified coverages; four have
accepted catalogue mappings. This does not close #148 or #70.

`GEPSReductionSource(geps_point_service)` implements the shared reader seam.
Its source is `eccc-geps`, product `geomet-provider-reductions`, point selector
`GEPS reductions`. It advertises exactly these four identities:

| Catalogue field | Provider-statistic variant | Parameter |
|---|---|---|
| temperature_2m | ensemble_mean | none |
| temperature_2m | ensemble_spread | none |
| temperature_2m | ensemble_quantile | quantile 0.5 |
| total_cloud_opacity | ensemble_quantile | quantile 0.5 |

These are retrieved provider statistics, never derived-here calculations or
members. `GEPS.DIAG.12_GUST-15MS.PROB` remains in the all-five normalized
artifact as the existing raw gust-threshold field. There is no accepted
catalogue/vertical/window mapping for serving that field as a scalar through
EvidenceField. No `wind_gust_10m` mapping is invented. The other 527 advertised
reductions remain unresolved. No native Series or selectable-run inventory is
claimed.

The selected valid time must be exact and advertised. One bounded capability
read chooses the latest advertised reference no later than the selected valid
time from the first supported coverage. Existing geps_query then revalidates
that exact reference/valid pair for all five coverages. There is no fallback to
an earlier reference if another coverage refuses it. A requested WCS reference
is not independent proof of producer-run identity: both returned `run_time`
and source-acquisition `provider_run_id` remain null. Actual request URLs keep
the reference parameter. Run staleness, scientific freshness and QC stay
unknown; native temporal windows remain explicitly unresolved.

The existing all-five query/strict GeoTIFF decoder preserves source masks,
units, requested 24-by-11 output geometry and server-resampling uncertainty.
Point reads sample that actual output cell, preserve its coordinates, and are
`reprocessed`, non-primary and `available-not-stored`. Full normalized bytes
and all 11 capability/coverage receipts share one finite cache entry. Expiry
is fixed at final-byte completion plus 300 seconds; decode and repeated reads
cannot renew it. Concurrent same-time refreshes coalesce. Failed refresh
retains an older crop only until its original deadline.

One discovery body is capped at 2 MiB, then existing acquisition has five
2 MiB capability ceilings and five 4 MiB TIFF ceilings: 32 MiB total decoded
provider input. The child uses the existing 2 GiB address-space and 4 MiB
output bounds with a 180-second deadline. Parent crop/cache is capped at
4 MiB; all scratch is temporary and no ArtifactStore or scheduler is added.

## Root-owned registration

This commit intentionally does not edit `app.py` or `source_delivery.py`.

1. In `source_delivery.source_readers`, import
   `GEPSReductionSource, geps_point_service` from `.geps_delivery` and add
   `GEPSReductionSource(geps_point_service)` to the reader list.
2. Add `GEPS reductions: eccc-geps` to the point-product/source mapping and
   route its selected point through that reader, preserving all four returned
   variants until explicit shared identity filtering is applied.
3. Require an explicit matching statistic/quantile where the shared selector
   selects one field. Temperature mean, spread and median are separate
   identities; a missing variant cannot silently select the first one.
4. Regenerate the source fixture/OpenAPI/TypeScript contract and add root HTTP
   evidence for exact identities, null run, native masks and no implicit
   statistic. Safe source-status mapping must not expose raw exceptions.

## Verification

Offline Linux source tests use anonymous generated XML/GeoTIFF fixtures,
including the actual bounded child worker. They cover four descriptors with no
I/O, eleven accounted requests/all five acquired reductions, exact variant
identity, original units, native nulls and sampled cells, unknown run/QC,
unsupported run/time/box before acquisition, fixed final-byte expiry,
coalescing and mutation isolation. No new live provider request was made;
existing five-coverage evidence remains acquisition evidence, not a new shared
HTTP proof.
