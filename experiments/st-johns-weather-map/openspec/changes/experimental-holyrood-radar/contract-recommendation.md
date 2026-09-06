# Proposed CASHR rendered-image contract

> Draft recommendation only. It does not authorize a registry field, API route,
> publication, freshness claim, or `operational: true` status.

## Product identity and immutable artifact

A future accepted contract should name exactly one product identity per image:

```text
producer: Environment and Climate Change Canada
station_id: CASHR
product: DPQPE
phase: Rain | Snow
encoding: image/gif
valid_time: UTC instant parsed from YYYYMMDDTHHmmZ filename
```

The artifact must retain original GIF bytes unchanged. Its revision identity
must include the SHA-256 of those bytes, URL, source filename, HTTP completion
time, `Content-Type`, `Content-Length`, `ETag`, `Last-Modified`, and provider
`Date` where supplied. A parser must require one complete GIF frame, positive
logical dimensions, and a bounded pixel count before any display decoder sees
it. This is structural validation only: a palette entry is not a precipitation
value.

## Data semantics

The only retrieved datum is an opaque rendered image. The contract must not
assign `precipitation_rate`, reflectivity, hydrometeor class, quality mask,
radial velocity, or a dual-polarization moment to a GIF pixel without a
producer-published palette, georeferencing, calibration/version information,
and an accepted canonical field mapping.

`DPQPE` may state producer provenance as a lowest-sweep,
dual-polarization-processed estimate. That statement does not create an
independently observed dual-polarization field. Raw volumes and independent
moments remain unavailable until a verified public product path and field
schema are accepted. `-Contingency` filenames are a distinct composite product
and must never satisfy the native CASHR identity.

## Bounds, freshness and retention

Before activation, retain measured evidence for separate finite ceilings for:

- directory listing bytes;
- each Rain and Snow GIF byte stream;
- GIF dimensions and frame count;
- local artifact bytes and filesystem block allocation; and
- complete paired-operation parent/child and temporary-file overlap.

The current experiment uses 128 KiB for listings and 512 KiB for each image as
hard refusal ceilings only. They are not a future capacity declaration. A
future owner decision must pin the provider cadence and define staleness from
`valid_time` versus retrieval time. It must also define how many complete,
immutable paired revisions remain visible. Until then, no image is “current”.

## API and absence

A future API should expose image metadata separately from numeric point/grid
read APIs: source identity, phase, valid time, retrieval time, digest,
structural image dimensions/frame count, and declared rendered-image-only
semantics. The byte route must return precisely the immutable artifact selected
by that metadata, with its media type. It must not offer image pixels through
`/point`, synthesize a raster grid, or label a palette-derived value with a
unit.

A missing paired Rain/Snow timestamp, invalid image, oversize response, absent
receipt, or transport failure is unavailable and publishes nothing. A producer
may later define an explicit no-precipitation image state, but no blank or
transparent image may be interpreted as such until that producer rule and the
API response semantics are accepted.
