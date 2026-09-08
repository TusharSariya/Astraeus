# Current GEPS shared HTTP evidence, 2026-09-08

Non-normative experimental evidence for #148, scoped to four mapped producer
reductions. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

At 02:40:37–02:40:44 UTC the existing default bounded Linux worker acquired
all five selected GeoMet coverages. It validated the explicitly selected
2026-09-08T12:00Z frame against published capabilities and selected the
advertised 2026-09-07T12:00Z reference request parameter. That parameter is
not independently verified producer-run identity: public run fields remain null.

Exactly 11 HTTP 200 requests completed (six capabilities and five bounded
GeoTIFF outputs), under the existing 32 MiB aggregate ceiling. The existing
2 GiB child, 4 MiB output and 180-second deadline were unchanged. The attached
compact JSON retains exact byte counts, transport URLs, completion times and
hashes. Original worker receipt and normalized artifact remain unchanged outside
Git at `/private/tmp/astraeus-geps-current-proof/`.

FastAPI TestClient then exercised the actual shared `/point` route twice for
each supported statistic, using the acquired cache. Replacing the loader with
a refusal ensured zero additional provider requests across those six HTTP
reads. Both quantile fields retain q=0.5; mean/spread retain no quantile.

| Field | Provider statistic | Exact returned value | Units |
| --- | --- | --- | --- |
| temperature_2m | ensemble_mean | 15.507867813110352 | degC |
| temperature_2m | ensemble_spread | 0.15140482783317566 | degC |
| temperature_2m | ensemble_quantile, 0.5 | 15.470331192016602 | degC |
| total_cloud_opacity | ensemble_quantile, 0.5 | 91.125 | percent |

The requested point was 47.5N, 52W. Evidence stays reprocessed, nonprimary,
available-not-stored and QC unknown. This is current acquisition plus actual
HTTP replay, not an assertion that a live deployed public server was tested.
The live-backed frontend replay manifest is in the same outside-Git directory.

The fifth raw gust-threshold reduction remains acquired but unmapped because
its catalogue/vertical/window contract is unresolved. The remaining 527
reductions, native members and Series are not claimed complete.

Verification: default Linux worker acquisition and six actual HTTP reads
succeeded; no implementation changes or additional broad tests were needed.
