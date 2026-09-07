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
This does not prove all RAP products fail: other advertised native grids remain
an explicit access/coverage prerequisite under #271. Do not call another grid 13 km just because RAP's model is 13 km.

Metadata investigation may precede acceptance. One bounded native-message
probe, outside Git, must prove geometry and native field/run/level/step identity;
no bulk retrieval. If no free distributed RAP grid covers the declared box,
record that concrete prerequisite on #271 while retaining RAP in overall scope.
Supporting source: `docs/research/wayfinder/native-deterministic-integration.md`.

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
