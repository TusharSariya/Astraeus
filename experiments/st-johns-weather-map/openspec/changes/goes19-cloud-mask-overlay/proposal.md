## Why

The four proxied GOES-East composites change character completely at the
day/night terminator: the visible component vanishes, the false-colour ramps
swap meaning, and the same sky reads differently at 20:00 and 22:00 local.
They are rendered RGB pictures, so clouds cannot be separated from land,
ocean, colour ramps and JPEG compression after the fact — a chroma key or
frame-differencing approach would fabricate clouds around snow, coastlines,
fog and the terminator (verified against the temporal-differencing
literature; even operational algorithms of that family need modelled
clear-sky backgrounds and spectral tests).

NOAA already solves the classification problem upstream. The GOES-19
Enterprise Cloud Mask (ABI-L2-ACMF, Full Disk) publishes per-pixel
`Cloud_Probabilities` (0-1), a four-class mask (`ACM`), a binary mask and
`DQF` quality flags, day and night, every 10 minutes, openly on
`https://noaa-goes19.s3.amazonaws.com/` — verified live 2026-08-30 (6
files/hour observed, ~25 MB each, arriving ~1 minute after scan end). The
matching Cloud Top Height product (ABI-L2-ACHAF, ~1.5 MB, same cadence)
permits per-pixel parallax correction, which matters here: St. John's sits at
~58.6 degrees viewing zenith, so an uncorrected cloud appears displaced by
roughly 1.6x its height (~16 km for a 10 km top). St. John's lies outside the
live CONUS sector by ~0.23 degrees, so Full Disk is required.

The owner wants this rendered as a new cloud-only satellite layer whose
palette and semantics do not change at sunset, offered ALONGSIDE the four
existing composites so the processed (cloud mask) and unprocessed (provider
RGB) views can be compared side by side. Nothing is retired.

Verified: bucket cadence/size/variables, projection recipe (geostationary
`geos` projection, x/y scan angles times perspective height), CONUS boundary,
parallax geometry. Unverified until live smoke: decode of a real granule
(scale/offset/_FillValue of `Cloud_Probabilities`); the ~90% day / ~88% night
detection accuracy is NOAA's published validation figure, not locally
measured, and is disclosed as such. GOES-19 cloud-top height carries NOAA
"Provisional" maturity, disclosed verbatim.

Classification: Experiment, Spec-Impact: none. `docs/specv1` is untouched.

## What Changes

- **Ingestion:** a new adapter under the already-catalogued `noaa-goes-east`
  registry id lists and fetches the newest ABI-L2-ACMF and ABI-L2-ACHAF Full
  Disk granules over anonymous HTTPS, crops to the Atlantic context bounds in
  fixed-grid index space, parallax-corrects cloudy pixels using cloud-top
  height (flagging cloudy pixels with no valid height as uncorrected),
  regrids by nearest neighbour to a regular lat/lon grid no finer than the
  local native footprint, and publishes one zipped-Zarr artifact per scan
  carrying probability, class, quality, correction flag and the disclosure
  strings. DQF-flagged pixels are preserved as an explicit invalid class,
  never dropped to transparent. A feed gap publishes nothing.
- **API:** a new `weather_api/satellite.py` lists one layer
  (`noaa-goes19-cloud-mask`, group `satellite`) and renders it from the
  published artifact with the existing nearest-neighbour rasteriser: clear
  fully transparent; probably-clear/probably-cloudy/cloudy as neutral white
  whose opacity encodes detection confidence (capped so the basemap stays
  readable); invalid as a distinct non-white state. Identical palette day and
  night. Frames are exactly the ingested scan times; beyond the staleness
  tolerance the layer declares itself unavailable rather than showing an old
  frame, and a gap is never rendered as clear sky. Responses carry
  rendered-grid provenance (`X-Weather-Image-Basis: rendered_grid`,
  `X-Weather-Source-Id`), which the browser already accepts.
- **Web:** the satellite group now lists five layers — the four provider
  composites unchanged plus the cloud mask — so they can be flipped or
  overlaid at the same instant; evidence-basis wording says the cloud-mask
  imagery is drawn by this experiment from stored NOAA cloud-mask values.
- **The four GeoMet proxies are untouched.**

## Capabilities

### New Capabilities

- `satellite-cloud-mask-imagery`: the honesty rules for a cloud-only
  satellite layer rendered from retrieved NOAA cloud-mask values — invariant
  day/night palette, opacity-as-confidence, invalid-distinct-from-clear,
  observed-frames-only, and the required disclosures.

### Modified Capabilities

- `artifact-ingestion`: gains the GOES ABI cloud-mask ingestion requirement
  (fetch, crop, parallax-correct, regrid, publish — with DQF preservation and
  honest gap behaviour).
