# IFS Atlantic experiment evidence, 2026-09-09

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

This records experimental implementation and verification, not source admission
or a transition to accepted/verified specification status. Existing unrelated
WeatherNext, demand-cloud and comparison workspace changes were retained.

## Delivered paths

The versioned `registry/ifs_manifest.json` contains 87 field/level definitions
and 11 products. Catalogue entries describe supported identities, not evidence
that every field is published in every run. Product-specific advertised runs,
indexed exact GRIB ranges, native Atlantic cells, shared native caches, finite
selection pages and paginated receipts are in `api/weather_api/ifs_*`.
The selection budget is 2 GiB / 4,096 records / two concurrent acquisitions,
with a fixed 15-minute job lifetime and the existing bounded decoder limits.

Series defaults to five models including control IFS. Native quantities,
levels, advertised runs, optional ensemble summaries and acquired-member
inspection are available. IFS map products use independent native-cell or
member-aware track layers. Opacity and loaded-member changes reuse data.
The canonical precipitation alias uses the existing registered
`precipitation_accumulation` field; cumulative predecessors are identity-checked.

Registered methods calculate wind and liquid-water humidity per member before
ensemble reduction. Reduction digests, minimum input expiry, member counts,
missing-member identities, dependency receipts and derivation steps remain
explicit. Temperature spread uses scale-only conversion; counts and probabilities
retain their own units. Provider reductions are labelled as provider statistics.

## Fixture verification

`api/tests/test_ifs_selection.py` passes **118 tests on Linux**, with Docker
networking disabled and the configured bounded subprocess implementation.
This includes exact indexed transport, every manifest entry's index identity,
pressure and soil levels, categories, static fields, wave missing/zero masks,
probability and maximum-interval records, and recorded BUFR control/ensemble
files. The BUFR fixtures include source URLs, hashes and retrieval receipts;
no synthetic storm coordinates replace native observations.

The affected API/registry suite passed on macOS; Linux-only kernel-limit cases
are skipped there and executed separately above. WeatherNext delivery/bridge
regressions passed (36 passed, four Linux-only skips), including unchanged
WeatherNext point wire values and omission of empty IFS-only metadata.
The focused frontend suite passed 24 tests covering fifth-model defaults,
pagination, shared time, independent layers, geometry and loaded-member reuse.
Generated OpenAPI and TypeScript checks, production build, strict validation of
four affected OpenSpec changes and `specctl validate` passed. Vite reports the
existing large-bundle advisory; the build succeeds.

## Separate live verification

- `live.json`: 112 decoded records, with cache reuse reducing acquisitions to
  111 and 111,804,245 input bytes. Eight control temperature frames across a
  24-hour window, 850 hPa temperature, first-layer soil temperature, a complete
  51-member atmospheric temperature set and a complete 51-member wave-height
  set were decoded.
- `products.json`: a daily probability field decoded after discovery was fixed
  to expand the native timestamps bundled inside probability index objects.
- `tracks-final.json`: successful bounded decoding of both selected cyclone
  products. Control native member 51 had zero tracks intersecting the Atlantic;
  the ensemble file decoded members 1–51 and one track intersected the region.
  No-track output is distinct from decoding failure.
- `track-job.json`: the rebuilt HTTP API returned an incomplete, cancellable
  selection immediately, then completed through polling with one Atlantic track
  and 5,121,717 total input bytes including discovery metadata.
- Earlier track evidence files retain failed attempts that exposed descriptor
  differences; `tracks-final.json` is the successful follow-up, not those files.

The representative checks do not establish retrieval success for all 87
catalogue entries. Publication and retention remain product-specific and can
change after this dated probe. No paid archive, scheduled ingestion, Aurora
execution or production-status change was introduced.

## Browser verification and practical limits

The local API/web services were rebuilt using the existing compose files.
Chrome inspection loaded native IFS temperature cells, run/time/value legends
and receipt links, and displayed IFS temperature, humidity, cloud and wind in
Series on native timestamps. The check caught and fixed the precipitation
catalogue key and the compact-layout rule that hid IFS legend details.

Normal 1728×872 layout and an emulated 200% equivalent layout (864×436 CSS pixels
at doubled device scale) were inspected. The temporary browser emulation was
reset. This is reflow/device-metrics verification, not an assertion that Chrome's
own zoom-menu state was changed. The single bottom timeline remains visible;
long chart content scrolls within the Series view. A final map click returned
284.9989776611328 K at native cell 47.5 N, 52.75 W, valid 2026-09-09 15:00 UTC,
from the displayed control run. Independent final review found no fatal
regressions in the scoped scientific, capability and lifecycle fixes.

The general legacy point endpoint retains its canonical-field contract; native
IFS quantities/levels are sampled through comparison and native-cell inspection.
The dedicated `/ifs` APIs are the typed native-grid/track interface. Grid and BUFR selections expose a cancellable identity before waiting for
science acquisition, then resume through bounded pages. An independently active
coalesced waiter can recover once after its original acquisition owner is
cancelled; the cancelled selection itself never restarts. The legacy small
`/ifs/tracks` read remains available alongside the track selection protocol.
