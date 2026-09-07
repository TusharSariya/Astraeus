# Holyrood native image readback receipt

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-002,
GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006. No normative status change,
registry activation, numerical field mapping, or public route is included.

## Delivered source-local seam

`weather_api.holyrood_presentation.image_metadata(evidence)` describes the
complete retained Rain/Snow pair with native valid time, source identity,
filenames, dimensions, listing/image receipts, original byte digests, retention
expiry, source quality unknown and operational false. Metadata does not embed
image bytes. Original producer rendering, including legend and map, remains
unchanged in the GIF. No CRS or geographic transform has been established;
`native_crs: null` and `georeferencing: not-established` avoid inventing one.
No palette-to-value, blank-image interpretation, unit or precipitation claim
is added.

`pair_revision(evidence)` hashes the source identity, valid time and both
phase-specific byte digests. A change to either phase invalidates the pair
identity, even if the other image's bytes stay identical.

`retained_image(query, revision=..., phase="Rain" | "Snow")` calls the new
cache-only `HolyroodQueryService.retained_images()`. It never acquires data,
refreshes or extends expiry. Unknown/expired revisions refuse readback; newer
pairs never substitute for requested older images. An explicit failed refresh
preserves an unexpired old pair. Both wall and monotonic deadlines are enforced.
Only one pair remains cached; no duplicate image cache was introduced.

## Minimal root-owned route proposal

This is a proposal, not activation authority. The existing source experiment
contract still explicitly leaves public image representation unapproved.
Root must reconcile that boundary with the current owner instructions before
mounting any routes or adding public response models.

1. `GET /sources/eccc-holyrood-cashr-dpqpe/images?refresh=false`: call the shared
   source service's `read_images(refresh=refresh)`, serialize
   `image_metadata(evidence)` through a closed response model, and attach
   per-phase byte URLs containing the full `pair_revision`. Return
   `Cache-Control: no-store` so HTTP caching does not silently extend local
   retention. Keep native valid time visibly separate from retrieval and
   expiry. The 60-second TTL is memory retention, not freshness.
2. `GET /sources/eccc-holyrood-cashr-dpqpe/images/{revision}/{phase}.gif`:
   validate a 64-character lowercase hexadecimal revision and phase enum;
   call `retained_image()` on that same shared service. Return its exact `body`
   as `image/gif`, `ETag` from the image SHA-256, `Cache-Control: no-store`,
   and `X-Content-Type-Options: nosniff`. Do not call `read_images()` here:
   that would acquire a replacement and break the metadata/byte boundary.
3. Map no retained exact pair to an unavailable response (suggested 404 for
   revision lookup; 503 for failed acquisition), without exposing raw exception
   chains. Do not add `/point`, raster/tile georeferencing, numeric units,
   rainfall assertions or operational activation.

This is a native producer image panel, not an overlay on a geographic map.
Reuse the exact CASHR Datamart endpoint selection and dated provider evidence
in `holyrood-api-first-20260907.md`; no provider rereads were needed.

## Verification

```sh
docker run --rm --network none --memory 1g \
  -v /private/tmp/astraeus-api-first-holyrood-delivery/experiments/st-johns-weather-map:/work:ro \
  -w /work -e PYTHONPATH=/work/api:/work \
  astraeus-lightning-proof:c88ff83 python -m pytest -q -p no:cacheprovider \
  api/tests/test_holyrood_presentation.py api/tests/test_holyrood_query.py \
  api/tests/test_experimental_holyrood_radar.py
uv run --project tools/specs python tools/specs/specctl.py validate
```

Result: 24 tests passed in the locked Linux image; specctl 0 errors, 0 warnings.
The metadata/readback test invokes the actual bounded structural GIF leaf with
three fixture transport reads (listing and pair), then zero additional reads
for both byte lookups. Other tests cover immutable pairing, wall/monotonic
expiry, explicit refresh/replacement, failed refresh, malformed identity and
cache-only absence. Provider requests: zero. These prove structural validation
and exact byte preservation, not pixel decoding or public route activation.
