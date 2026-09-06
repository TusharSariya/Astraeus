# Open-Meteo composition acquisition evidence

Non-normative experimental evidence for issue #100 and PR #156. Captured
2026-09-06 at the representative St. John's point (47.5615, -52.7126).
This is point acquisition, not proof of full Avalon grid coverage or admission.

[Compact receipt](openmeteo-composition-receipt.json) records five anonymous
HTTPS responses, exact parameters, individual retrieval timestamps, bytes and
SHA-256 checksums, plus three artifact hashes and revisions. The eight objects
totalled 44,376 bytes; artifacts were 4,319, 13,000 and 18,339 bytes.
Raw responses and rebuilt artifacts were temporary review material outside Git.
Only this receipt and small hand-trimmed test fixtures are retained in Git.

Root independently verified all eight object hashes and byte counts and all
21 provider-to-artifact-to-API field comparisons: values, unit conversions,
actual valid times, source IDs and artifact revisions. The capture script uses
actual HTTP `/point` routing with LiveStore and test backing storage; it does
not establish a public deployment. All responses remained `operational: false`,
reprocessed and non-primary. CAMS run identity remains unknown; latest model
metadata does not identify the run of each rolling value. Particulate data
remains secondary to RAQDPS, and LSA SAF limb-geometry admission is unresolved.
No production admission, scheduler activation, scoring or viewer change follows
from this evidence.

Verification on implementation commit 0040f179ad2582ca454c903eb5fc43ff85983174:

- Full API suite: 1,431 passed, 36 skipped.
- Registry suite: 235 passed.
- Root rerun of Open-Meteo adapter tests: 34 passed.
- Strict OpenSpec validation: experimental-openmeteo-composition and
  shared-source-integration-contract passed.
- Repository specctl: zero errors and zero warnings.
- Live capture: five requests, 21 of 21 API comparisons passed; independent
  root checks also compared retained normalized artifact cells.

The capture script is
`experiments/st-johns-weather-map/scripts/openmeteo_composition_evidence.py`.
Running it makes new upstream requests; the receipt describes the dated capture,
not a promise of future provider availability.
