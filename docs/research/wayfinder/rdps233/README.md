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
API gate is recorded separately when terminal. Independent review remains
pending because the runtime rejected a fresh reviewer with agent-thread-limit.
No merge or acceptance/status promotion is claimed.
