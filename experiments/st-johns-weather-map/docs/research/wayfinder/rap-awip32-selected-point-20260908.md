# RAP awip32 selected-point checkpoint

Owner-authorized, unregistered experiment for #271. Spec-Refs: GOV-SPEC-004,
GOV-SPEC-006. No accepted/verified/superseded status or admission changes.
Owning proposed source contract remains on `proposal/rap-demand-271` at
`openspec/changes/rap-timestamp-demand/specs/rap-timestamp-demand/spec.md`.
Root must reconcile/import that experiment contract before public registration.

NOAA's [RAP inventory](https://www.nco.ncep.noaa.gov/pmb/products/rap/) identifies
`awip32` as the North American 32-km product, distinct from excluded `awp130`
and `awp236`. The [native grid catalogue](https://www.emc.ncep.noaa.gov/mmb/namgrids/)
identifies it as grid221. Neither model nor grid is substituted for GFS.

Three anonymous public requests captured run2026090723/f00: index26,797B,
VIS range479649–552719 (73,071B), and TCDC entire-atmosphere
range15173489–15237041 (63,553B), total163,421B. Exact receipts and raw data
are outside Git in `/private/tmp/rap271-awip32-proof`. Linux ecCodes verifies
Lambert349×277, spacing32,463m, native instantaneous VIS metres and TCDC percent,
with516 cells inside the evidence box. The bounded worker pins grid/projection,
source run/valid time, step, level and units, checks projected boundary samples,
preserves native bitmap nulls, and crops without interpolation.

Actual default bounded-worker replay and the shared nearest-cell picker return
14,600m visibility and94% cloud at47.55657103159626,-52.92946069125662 for
requested47.56,-52.71. The second read is identical and adds zero requests.
`point-proof.json` preserves both source receipts and the exact cell. Replay
adds zero provider requests; this is not an HTTP API or browser proof.

## Delivered seam and remaining work

`RAPQueryCoordinator.point_native()` returns source-local native values, exact
run/time/cell, native units and transport receipts. Root owns its EvidenceField
adapter, source registration, catalogue field mappings, generated API and UI.
The result deliberately retains `operational:false` and unknown overall QC;
structural/native checks alone do not promote scientific QC.

One acquisition at a time has at most two512KiB indices and two2MiB ranges.
The decoder has1GiB address-space,2MiB output, bounded stdin/stdout/stderr and
60-second deadline; HTTPS has its existing120-second aggregate deadline.
Only cropped JSON is cached, four entries with fixed600-second expiry and
60-second failure backoff. Concurrent misses/refreshes share acquisition;
failed refresh preserves an unexpired entry but never serves it after expiry.
Exact hourly times only; two-cycle discovery does not claim every available
extended-cycle forecast. Aerosol/species/wavelength, wind orientation, profile
fields, full run inventory and source-to-app acceptance remain open.

Verification: offline Linux `python -m pytest api/tests/test_rap_query.py
-o addopts= -q -p no:cacheprovider` passed6 tests. Captured-byte replay used
`python /proof/replay.py` in the same locked image
`astraeus-lightning-proof:c88ff83`, with network disabled and actual bounded
child decoding. `specctl validate` and `git diff --check` passed.

## Boundary-cell review correction

Independent review found that masking provider cells outside the requested box
changed nearest-cell selection at the southeast corner. The crop now retains
one native-cell halo and all original values/bitmap masks; requested coordinates
remain restricted to the evidence box separately. For query45,-46, the actual
bounded decoder now selects44.95328150414761,-46.012876176115185, matching a
fresh nearest-cell calculation over the entire retained native GRIB grid.
The retained native values are100m visibility and100% cloud. No new provider
request was made; `/private/tmp/rap271-awip32-proof/corner-proof.json` records
the check. Seven focused Linux tests pass, including the boundary regression,
null preservation and refusal of an out-of-box query. Specctl and diff checks pass.
