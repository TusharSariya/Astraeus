# WeatherNext 3 experimental integration evidence

Recorded 2026-09-05 for [Implement the verified WeatherNext forecast source](https://github.com/TusharSariya/Astraeus/issues/77).
This evidence is non-normative. The source contract remains draft and the
adapter remains absent from production registration and scheduling.

## Exact source and field scope

The implementation accepts only Google DeepMind WeatherNext 3.0.0 statistics
from `weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr`.
It preserves the Cartesian inventory of 21 base variables and six statistics
(`mean`, `p10`, `p25`, `p50`, `p75`, `p90`), 126 fields total. The selected
cloud candidate is four native cloud-cover variables by six statistics, 24
fields. All 126 are retrieved adapter capability; the other 102 have no
accepted consumer mapping and remain deferred for production exposure. Fog, visibility,
ceiling, cloud base and cloud top are unsupported. Raw members and pressure
levels belong to the excluded requester-paid full-ensemble product.

## Capture receipts

No provider payload is stored in Git (owner decision of 2026-09-05, issue #70).
Each live capture below is recorded by its receipt: dataset path, request
parameters, byte counts, SHA-256 of the capture, capture time and artifact
revision. Re-create any of them with the capture scripts under
`experiments/st-johns-weather-map/scripts/` and Google credentials.

Common source for every row: `gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/`,
initialization `2026-08-01T00:00:00Z`, artifact revision `20260801_00hr_01_preds`
(provider run id `2026080100`), no requester-billing identity.

| Capture | Request parameters | Objects | Received bytes | Capture bytes | Elapsed | SHA-256 | Captured at (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| All-field lead-6 object plan | 126 fields, lead 6 h, metadata only | 126 | 0 | 41,455 | 81.617 s | `17fff8135223e867693acb70c0de4635d22587a6d616d08184d501ee14990e46` | 2026-09-05 |
| Avalon point, six cloud statistics | 6 fields, leads 6/12/24 h, nearest native cell to 47.5 N, -52.7 E | 26 | 375,407,160 | 52,993 | 105 s | `cbb1dd55e31382e261fac090947a903f88395d734f1662d1c6f4e3565defc5e7` | 2026-09-05T14:06:45Z |
| All-field lead-6 point values | 126 fields, lead 6 h, nearest native cell to 47.5 N, -52.7 E | 126 | 3,150,943,978 | 132,878 | 432 s | `b9ed43359425550eeab98c6f639dcc67f347657ae8a25a081850bef337a1d122` | 2026-09-05T14:49:52Z |
| Avalon box, six cloud statistics | 6 fields, leads 6/12/24 h, box -54.0/46.5/-52.5/48.0, 16 x 16 native cells | 26 | 375,407,160 | 220,942 | 100 s | `d35a5bbb3b92deab515732ae88f92934e605a3697d4fe1aee90374c1c81e4d4c` | 2026-09-05T14:56:00Z |
| All-field lead-6 Avalon box | 126 fields, lead 6 h, box -58.0/45.0/-46.0/50.5, 56 x 121 (0.1 deg) and 111 x 241 (0.05 deg) | 133 | 3,150,943,978 | 37,503,385 | 433 s | `c46e4609cf8d2b9915c78ce65b1cbe4dde6603639899655b67831154bb605ca5` | 2026-09-05T15:41:33Z |

Test fixtures are hand-trimmed cuts of these captures, held next to the tests:

- `experiments/st-johns-weather-map/api/tests/fixtures/weathernext3/avalon-box-six-field-4x4.json`
  is the six-field Avalon box narrowed to a 4 x 4 native window around 47.5 N, -52.7 E.
- `experiments/st-johns-weather-map/api/tests/fixtures/weathernext3/all-fields-point-lead6.json`
  is the all-field lead-6 point capture, one native cell per grid.
- `experiments/st-johns-weather-map/scripts/tests/fixtures/weathernext3/all-fields-lead6-plan.json`
  is the object-identity plan: paths, generations, ETags and byte counts, no values.

The all-field Avalon box capture has no trimmed form: `validate_acquisition`
requires every native cell over the declared box on both grids, so a trimmed cut
would not validate. The two tests that read it skip unless a credentialed
re-capture is present.

## Live proofs

The all-field lead-6 object plan describes the exact
lead-6 chunk for every field. All 126 exist with positive size, generation and
ETag. The 127 metadata operations completed in 81.617 seconds and downloaded
zero forecast bytes. A value read would require 3,150,715,420 compressed bytes.
The owner then authorized the known operation with a 30-minute deadline and
4 GiB cap. The all-field lead-6 point capture
retrieved all 126 lead-6 point values sequentially: 3,150,943,978 bytes, 140
operations, 103,708,800 peak decoded bytes, 122,420 collector-output bytes and 432
seconds. Each generation-qualified download matched its described byte size;
the retained records name that pinned-read mechanism explicitly and do not
claim a later metadata or ETag recheck. The
adapter validates the exact run path, generation, ETag, size and one-to-one
field/lead binding before normalization. These are internal consistency checks
on the evidence record, not cryptographic proof that arbitrary JSON came from
GCS. It records 120 numeric values and six explicit unavailable masks, all
six being sea-surface-temperature statistics at the selected land cell. The
114 0.1-degree and 12 station-head 0.05-degree arrays retain distinct grid and
coordinate identity. This is all-field point evidence, not full spatial
coverage. Its annotated SHA-256 is
`b9ed43359425550eeab98c6f639dcc67f347657ae8a25a081850bef337a1d122`.
Roughly 50,067,508 KiB was physically free before the operation. The gate held
a 4 GiB team reservation plus the next compressed chunk, decoded allowance and
output allowance. Every raw chunk was deleted immediately after point
extraction. Only the receipt above and the hand-trimmed fixture are retained in
the repository; the 132,878-byte capture it records includes the explicit
identity-mechanism annotations added during adapter hardening.
the two normalized Zarr artifacts are created in temporary test directories
and are not installed in a shared store.

The Avalon box capture is the value proof for the six
previously sampled cloud statistics at leads 6, 12 and 24. It contains every
native cell centre within `[-54.0, 46.5, -52.5, 48.0]`: 16 latitudes by 16
longitudes, 256 cells per lead. The read received 375,407,160 bytes in 78
operations, decoded at most 25,934,400 bytes at once, emitted 220,942 bytes,
and completed in 100 seconds. Source object identity checks all passed. The
4 x 4 native window kept as a fixture reproduces the same validation and the same
normalized artifact shape on a payload readable in a diff.

The all-field lead-6 Avalon box capture is the
complete bounded spatial proof. It retains every lead-6 native cell whose
centre lies within 45.0–50.5 N, 58.0–46.0 W for all 126 fields: 56 by 121 cells
for 114 fields on the 0.1-degree grid and 111 by 241 cells for 12 fields on the
0.05-degree station-head grid. It received 3,150,943,978 bytes in 140
operations, decoded at most 103,708,800 bytes at once, emitted 37,503,385
bytes, and completed in 433 seconds. The collector held the 4 GiB received-byte
bound and local reservation, a 128 MiB decoded bound, a 64 MiB serialized-output
bound, and a 30-minute deadline. Every raw global chunk was deleted immediately
after extraction. The 133 retained identities cover all 126 field chunks, root
metadata, both latitude and longitude coordinate pairs, lead time, and
initialization. Its 37,503,385-byte payload is not stored in Git; the receipt
above and `scripts/weathernext_all_fields_sample.py` are its record.

Every field retains its native unit, provider statistic, valid time, finite
range, values and null count. Only the six sea-surface-temperature statistics
contain nulls: each has 1,587 provider-null land cells and finite ocean cells;
the mean spans 283.22454833984375–291.3005676269531 K. This is a spatial proof
at one historical lead, not a cadence or operational-window proof. Its two
temporary normalized Zarr artifacts are approximately 0.91 MiB and 2.26 MiB
and remain outside shared storage.

## Adapter, artifact, API and failures

The isolated adapter validates exact product/surface/member/statistic/time and
the complete disposition inventory, preserves nulls as masks, writes a
deterministic immutable Zarr artifacts split by native grid, and carries all
126 dispositions plus the validated source-object records in provenance.
Astraeus' real reader and HTTP point endpoint read both native-grid artifacts
in a local harness and compare all 126 response fields with the retained point
manifest: 120 numeric values and six explicit SST nulls. The same path compares
all six earlier box fields at a retained native cell. The comparison of all 126
complete-box fields at representative land and ocean cells, including SST null
and finite behavior, ran against the live capture and now skips unless that
capture is re-created with credentials. Every catalogue override is
test-local. No production catalogue, source registry, scheduler, shared store
or deployment configuration is changed.

The complete all-field box proves spatial extraction at one representative
historical lead. The earlier Avalon artifact proves six cloud statistics at
three leads. Neither establishes operational cadence or full-window
completeness. Both return `complete=false` and
`qc_passed=false`, with explicit `experimental_partial_sample` provenance, so
even manual passage to the actual artifact store stages without moving a
published revision. Operational publishability remains blocked until accepted
full temporal and cadence bounds exist.

Tests refuse WN2 identity, fabricated member identity, incomplete inventory,
statistic mismatch, invalid cloud fractions, mask-count mismatch, blocked
acquisition and requester-paid bucket state. Mutations of either retained
manifest's path, generation, ETag or verified-read mechanism fail closed; box
metadata and coordinate identities and every selected field/lead binding are
required. Invalid inputs create no partial artifact. Existing transport tests
prove request reservation, byte limits, redacted failures and empty
billing/project/auth override variables.
