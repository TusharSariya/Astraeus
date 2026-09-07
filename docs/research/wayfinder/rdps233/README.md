# RDPS selected-time native proof (#233)

Non-normative evidence for the operational-false experiment under #70.
Current native capture: September 6, 2026, RDPS run 18Z, lead f005, valid 23Z.

Primary documentation: https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps-datamart_en/
Dated source directory: https://dd.weather.gc.ca/20260906/WXO-DD/model_rdps/10km/18/005/

The documentation lists hourly f000-f084 at four daily cycles and rotated
0.09-degree coordinates. Its 1102 × 1076 geometry is stale: actual messages
have 1140 × 1045 cells. The runtime validates actual grid type, dimensions,
point count, coded parameter and vertical identity, run/valid time and one
instantaneous message before accepting a field.

The independent ecCodes oracle matched all 25 selected field values, unit
conversions, receipt SHA-256, and nearest native cell against the normalized
cache. Total native GRIB bytes: 17,348,567. Native cell [507,880] is
47.556348,-52.652600, 4.326 km from the requested 47.56,-52.71 point. The crop
is 35 × 36. No interpolation or regridding occurs.

Six point objects produced 47,149 normalized bytes; 19 profile objects
produced 113,877 bytes on the first complete pass. The real API cache proof
records 6 GRIB/16 total RDPS requests after point, unchanged after a different
selection in the same native hour; 25 GRIB/36 total RDPS after profile,
unchanged after profile repeat and both timeline calls. Timeline reads
provider-advertised metadata, not evidence values. Request-count `all` also
includes TestClient requests and independent METAR traffic; `rdps`/`grib`
are the source-specific counts.

The aggregate cgroup peak was 757,927,936 bytes (723 MiB), including parent,
child, cache and tmpfs. Enforced ceilings: 4 GiB aggregate cgroup, 2 GiB child
address space, 3 GiB tmpfs, 10 MiB per GRIB, 2 MiB per directory listing,
16 MiB child output, 32 MiB/4 cache entries, 600-second TTL, 60-second bounded
failure backoff. Selected operations serialize within the source coordinator.
The original 1 GiB child cap failed during native-library import; it produced
no accepted result. The measured replacement completed under the stated 2 GiB
child and 4 GiB aggregate ceilings.

Native U/V are grid-relative (`uvRelativeToGrid=1`). This demand path retrieves
the producer's `WindSpeed` and `WindDir` instead, preserving the latter's
native `Degree true` as original units and normalizing only its unit label to
`degree`. No wind component derivation or rotation is applied. At the example
cell the direct native direction is 85.3 degrees; treating native U/V as east/
north would incorrectly yield 52.47 degrees. This identifies a separate legacy
component-basis issue; it is not imported into this demand path.

Scope dispositions: six selected point inputs and 19 existing profile inputs
at 1000/850/700/500 hPa are retrieved. Missing profile level/field combinations
stay missing. Additional mapped lower levels, surface pressure and generated
WEonG/native raster products are not acquired or served by this slice; the
214 additional vertical catalogue IDs remain explicitly open in #188. #70/#97
retain all-source completion. GeoMet products remain independent evidence.

Retained raw bytes, completed transport receipts, normalized ZIPs, API bodies,
network journal, native wind check and browser screenshots are outside Git at
`/private/tmp/rdps233-live`. These are finite audit evidence, not application
retention or a cache fallback. Application cache entries expire; no background
acquisition or ArtifactStore publication serves this path.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
OpenSpec: rdps-native-demand and timestamp-demand-query-cache, with existing
point-evidence-sampling, grib-decoding and field-catalogue science unchanged.

Existing-client proof: retained real API responses were replayed without value
edits into the current Vite application. The browser selected RDPS at the exact
47.56,-52.71 request coordinate and issued RDPS point, timeline and profile
requests. Brief's source-family section displayed native opacity cloud; the
Workbench profile table displayed 1000/850/700/500 hPa. The generic legacy total
cloud card has no canonical-opacity slot and remains unknown; this is not a
claim that the native opacity field is absent. No UI redesign was included.

Verification at handoff: 16 focused RDPS tests; 10 isolated legacy no-fallback
cases; 237 registry tests and four strict profile audits; 452 web tests and
production build; 75 strict OpenSpec items; specctl 0 errors/0 warnings. The full
API suite passed 2,088 tests with 50 skips; the 46-case cutover group passed.
The first independent review found the two correction items documented below;
a fresh targeted re-review of their remediation later passed with no remaining
Standards or Spec blocker. No acceptance/status promotion is claimed.

## PR234 independent-review corrections

The independent review of `644ff2fc083d418a5a6731f9aefcb2c5a6cdc73b`
identified dropped transport/request provenance and lost expired identity on
failed refresh. Both are corrected without changing native values, science,
provider selection, units, times, cells, or operational status.

Each point/profile RDPS field now carries optional typed `demand_acquisition`:
canonical cycle/run/lead, requested fields and crop; normalized ZIP SHA-256;
actual run/native-valid/retrieval timestamps; every field's final effective URL,
request/response headers, body SHA-256, byte count and final-byte completion;
and UTC cache admission/expiry paired with the monotonic freshness deadline.
Metadata is capped at 64 KiB, 64 receipts, 16 headers per map and bounded strings.
The existing web parsers accept additive fields: point provenance is a record,
and profile explicitly reads valid_time/levels/fields. No client edit is needed.

After expiry, native ZIP/value entries are removed on lookup. At most four
metadata-only acquisitions remain for one further TTL (600 seconds maximum),
with lazy pruning. Failure backoff stores typed data, not exception tracebacks
that could retain native payload locals. Both point/profile responses carry
`demand_unavailable.expired_acquisition` on failed refresh, including directory
refresh failure, and return only null unavailable fields. No stored fallback.

Offline replay reused retained normalized ZIPs and all 25 native GRIBs, with
upstream access prohibited. All receipt hashes/bytes, values, units, times and
sampled cells matched the original capture. Point acquisition was 4,596 JSON
bytes; profile was 13,515 bytes. Fresh repeat preserved identity; simulated
expired refresh left zero native cache entries and two metadata-only records.
See [compact results](review-fix-summary.json). Full response bodies and script
are `/private/tmp/rdps233-live/review-fix-*-api.json`,
`review-fix-*-expired.json`, and `review_fix_replay.py`. This is offline audit
replay, not a new provider acquisition or application fallback.

Verification: 21 focused RDPS tests; strict OpenSpec 75/75; specctl 0 errors and
0 warnings. The broader API run had 2,090 passes, 44 skips and two pre-existing
GFS fixture-clock failures, reproduced against the unmodified reviewed head.
Per owner correction, those two tests now hardcode their fixture clock and
explicitly stub independent METAR acquisition; their focused rerun passes 2/2.
No production freshness behavior changed and no full suite was rerun solely
because the fixture aged. Earlier uninstrumented broad runs cannot establish
zero unrelated-provider attempts; the RDPS replay explicitly enforces zero
upstream requests. No RDPS provider bytes were reacquired for this correction.
Fresh independent targeted re-review passed the exact correction with zero
remaining Standards or Spec blockers. The review reran only the 21 RDPS and two
fixed-clock GFS tests plus OpenSpec/specctl validation; it did not reacquire
provider data or rerun the full suite. No status promotion.
