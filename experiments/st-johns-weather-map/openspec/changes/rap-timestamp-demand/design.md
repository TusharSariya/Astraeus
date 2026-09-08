# Native request and reuse plan

Reuse `ingest/experimental/native_deterministic.py` indexed object discovery,
`_product_url`, range/GRIB identity validation and retained footprint evidence;
reuse `gfs_query.py` bounded demand coordination and existing fixed-clock tests.
Do not import experimental artifact publication into the demand path or assume
its raw-only aerosol inventory defines weather quantities.

The known product `awp130pgrb` is CONUS and failed the actual Avalon cell test.
NOAA's [product inventory](https://www.nco.ncep.noaa.gov/pmb/products/rap/)
distinguishes multiple distributed grids. The [current official directory](https://nomads.ncep.noaa.gov/pub/data/nccf/com/rap/prod/rap.20260906/)
also advertises `awp236pgrb`. A bounded native VIS message probe now disproves its Avalon coverage too.
The 2026090700 lead-zero object returned the requested bytes 13763–29334
(15,572 bytes; SHA256 `d592c1fb37c5f3f1337642683ad60bbe0e9efa7aef4bb4ce93393c035745b1b8`).
ecCodes decoded instantaneous VIS in metres on a 151 by 113 Lambert grid with
40,635 m spacing. The native evidence-box mask contains zero cells; the nearest
cell to 47.56 N, -52.71 W is 48.9822168 N, -60.2860900 W. No values are
eligible. Raw message and index stay outside Git in `/private/tmp/rap271-*`.
This exclusion remains product-specific. `awip32` now supplies the measured
covering product; do not call it 13 km merely because RAP's model is 13 km.

## Covering awip32 evidence and reusable implementation

The September 7 23Z/f00 acquisition used three requests: 26,797-byte index,
73,071-byte VIS range and 63,553-byte TCDC range (163,421 bytes total). Native
Lambert grid 221 is 349 by 277 with 32,463 m spacing. It has 516 cells in the
evidence box. St. John's request 47.56,-52.71 samples 47.55657103159626,
-52.92946069125662 with VIS 14,600 m and TCDC 94 percent. The corrected
southeast-boundary request 45,-46 samples 44.95328150414761,-46.012876176115185,
matching selection over the full native grid. A one-cell halo preserves native
boundary sampling; eligibility of the request remains separate from crop masks.

Durable evidence and reproduction are recorded in
[the merged native checkpoint](../../../docs/research/wayfinder/rap-awip32-selected-point-20260908.md).
Raw bytes and replay outputs remain `/private/tmp/rap271-awip32-proof/`; no new
capture was performed for this proposal update. The evidence establishes these
fields/cells for the captured run, not forecast skill, continuity, latency or
an observed full lead inventory.

Reuse the merged `api/weather_api/rap_query.py` and `rap_query_worker.py`.
The exact field/range selectors, native metadata guards, masks, crop halo and
bounded Linux decoder already exist. Their unregistered point_native result
is not a public EvidenceField mapping. The separate source-local expiry fix
54b90ef anchors lifetime before decode and must accompany public delivery.
Root owns shared EvidenceField/descriptor wiring after contract reconciliation.

First implementation chooses only TCDC entire atmosphere and VIS surface whose
native metadata matches instantaneous percent and metres. No aerosol wavelength,
species or unknown units are inferred. No wind direction is derived from
unverified grid-relative U/V. Pressure/profile fields remain explicit residuals.

Canonical request key includes product/grid, run, native lead, requested field
set and native spatial window. Pinning a run cannot silently choose another.
Latest selection uses bounded discovery of actually published runs containing
the exact lead, with selected run disclosed. Provider time-step inventories
win over assumptions about hourly cycles or extended forecast horizons.

Use bounded index/range receive sizes and a bounded Linux decoder, finite LRU
cache, same-key coalescing and failure backoff as the existing demand seam.
Record exact chosen numeric limits in the implementation and test at each
limit; no unbounded listings or retries. Receipt includes canonical/effective
URL, safe headers, received bytes, digest, final-byte retrieval time and expiry.


## Fixed demand limits proposed for shared mapping

Retain the source-local exact-hour selector and two candidate cycles, not
unbounded archive search. The selector accepts instants from 24 hours before
its current clock through 51 hours after; candidates are only the selected or
current hour (whichever is earlier) and its preceding hour. Existing 21/51-hour
lead eligibility is a search ceiling, not a claim that every eligible lead is
currently published. Actual eligible index content must exist.

One acquisition at a time uses at most two 512-KiB indices and two 2-MiB field
ranges. HTTPS retains its 120-second aggregate deadline. The Linux decoder has
1-GiB address space, 2-MiB output and a 60-second deadline. Cache at most four
cropped entries with fixed 600-second final-receipt expiry; back off failed
selections for 60 seconds. Expired values are withheld, including when decode
or validation consumes the lifetime. A failed refresh cannot extend an old
entry. No separate long-lived artifact or scientific QC certification follows.

## Full #271 residual field ownership

Temperature/dew point/humidity need exact field and unit mappings; winds need
native orientation and any separately approved rotation; pressure/profile
families need vertical identity and completeness. Smoke MASSDEN and aerosol
AOTK retain their unresolved species/wavelength/units and are not inferred from
VIS or TCDC. Other requested native fields, complete run inventories, latency
and continuity verification remain #271 work. RRFS is a separate source and
never a RAP fallback. None of these residuals is silently closed by this slice.
