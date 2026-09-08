# RRFSv1.0 parallel 13-km North America native temperature checkpoint

Isolated experiment for #260. No registry or shared API edits; operational is
false. This improves the earlier access prerequisite without claiming completed
RRFS or REFS source-to-app integration.

## Exact published path and native evidence

[NWS SCN26-48, July 6 update](https://www.weather.gov/media/notification/pdf_2026/scn26-048_RRFS_and_REFS_Implementation.aab.pdf)
identifies the version-1.0 parallel feed, its August 11 start and planned October
6 operational transition. It documents `rrfs.tCCz.2dfld.13km.fFFF.na.grib2` in
addition to regional outputs. REFS combined products remain separate and are
not North America output. This is a concrete additional path absent from the
previous issue comment's retired-prototype assessment.

The [NCEP RRFS inventory](https://www.nco.ncep.noaa.gov/pmb/products/rrfs/)
labels its North America product 13 km but also lists 4881 by 2961 dimensions.
The actual selected native GRIB contradicts those dimensions: it is rotated
latitude/longitude, template 1, **1127 by 683**, 769741 points, with increments
0.1083 degrees in the rotated grid. The reader pins the observed native geometry
and refuses changes rather than inheriting the inventory's contradictory size.

The [current official parallel directory](https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/para/rrfs.20260907/12/)
listed 12Z September 7 `2dfld.13km.f006.na` and its index. A bounded directory
GET, a 64-KiB-capped index GET, a 1024-byte GRIB-header range and a single
737370-byte temperature-message range were made. No full 143-MB forecast
object, model run, ensemble member or prototype archive was acquired. Raw
bodies and HTTP headers remain outside Git in
`/private/tmp/astraeus-rrfs-access-proof/`.

The native decoder found NOAA/NCEP `kwbc`, generating-process identifier 134,
deterministic product template 0, 12Z run / 18Z validity, instantaneous
`TMP` at two metres, units **K**. Its bitmap has 115720 missing cells, which
remain masks. The St. John's sample is 293.49 K at 47.531256,-52.735352,
3.7198 km from the requested point. All four evidence-box corners had finite
samples at distances 2.28 through 5.98 km. This proves those cells for one
run/message, not continuity, latency, forecast skill or complete product coverage.

[NODD's RRFS registry](https://registry.opendata.aws/noaa-rrfs/)
identifies anonymous public distribution and CC0 for its NODD data. The selected
NOMADS path is also anonymously retrievable; no account or paid service was
used. No broader terms or operational availability promise is inferred.

## Implemented source-local seam

`RRFSRequest` pins an aware exact-hour run and validity plus one evidence-box
coordinate. `temperature_range` reuses the existing NOAA index parser, selects
exactly one instantaneous two-metre TMP record, verifies run/lead and refuses
open-ended or over-2-MiB messages. The URL explicitly names the versioned
parallel 13-km North America product rather than a generic NOAA forecast.

`RRFSQueryService` requests only the at-most-64-KiB index and exact indexed
range, refuses redirects/full-file 200 responses/nonmatching Content-Range,
retains byte counts/digests/completion times, and passes the selected message
through the real bounded Linux child. Its cache retains one at-most-8-KiB point
for a fixed 300 seconds; identical in-flight requests share success/failure;
failed refresh does not invalidate an unexpired point. Native masks remain
nulls, values stay K, and producer QC stays unknown.

The decoder checks the exact observed rotated grid, run/validity, field/level,
instantaneous time semantics and deterministic generating-process identity.
It neither relabels a REFS statistic nor invents member/control identities.

## Verification and remaining gate

Offline Linux: 21 focused tests passed, including the real bounded child,
wrong process/level/time/grid rejection, bitmap nulls, exact range refusal,
concurrent refresh outcomes, expiry and mutation isolation. The fixture is
synthetically encoded from observed metadata and tests plumbing; it is not a
producer sample. A separate offline replay of the retained real 737370-byte
message passed the default reader/child, returned 293.49 K and repeated with
zero additional transport calls. Compact metadata receipt accompanies this note;
its query transport timestamps belong to the **offline replay**, while original
live response headers are retained outside Git.

```text
docker run --rm --network none --memory 2g \
  -v /private/tmp/astraeus-api-first-rrfs-prerequisite/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work astraeus-lightning-proof:c88ff83 \
  python -m pytest api/tests/test_rrfs_native.py -q -o addopts= -p no:cacheprovider
uv run --project tools/specs python tools/specs/specctl.py validate
```

Remaining: source-specific accepted field roster/manifest and demand rules;
full-field/lead availability and native QC assessment; operational transition
and cadence/latency verification; explicit shared point/status/Series and UI
integration; producer attribution/serving review. Existing optional-source
contract still requires stable operational distribution before admission.
Only this named temperature experiment is implemented. REFS remains separate
with no current North America combined-product/native-member contract selected.
Neither #260 nor RRFS/REFS integration is complete.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
