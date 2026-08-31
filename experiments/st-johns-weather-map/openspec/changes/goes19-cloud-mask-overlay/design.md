## Design

### D1 — Ingestion pipeline (`ingest/adapters/goes_abi.py`, registry id `noaa-goes-east`)

Anonymous HTTPS to `https://noaa-goes19.s3.amazonaws.com/` through
`PoliteClient` (house style; no boto3/s3fs at runtime). Discovery lists
`?list-type=2&prefix=ABI-L2-ACMF/YYYY/DDD/HH/`; the newest hour prefix being
empty is normal (a granule lands ~1 minute after scan end) and falls back to
the previous scan without being called a gap. The whole ~25 MB ACMF granule is
downloaded — HDF5 byte-range reading would require ROS3/h5py machinery foreign
to this codebase, and 25 MB per 10 minutes is trivially polite — plus the
matching ~1.5 MB ACHAF granule (paired by scan start timestamp in the key).

Processing per scan:
1. Open with xarray + netCDF4 engine (new dependency).
2. Compute the fixed-grid index window covering `ATLANTIC_CONTEXT_BOUNDS`
   from the file's own `goes_imager_projection` attributes and `x`/`y` scan
   angles (pyproj `geos`, `sweep='x'`, `lon_0` and `h` read from the file,
   never hard-coded), padded by ~30 km so parallax shifts cannot move pixels
   out of the window; slice lazily before loading data.
3. Parallax-correct: for pixels ACM calls cloudy/probably-cloudy with a valid
   ACHAF height, shift the pixel's lat/lon toward the sub-satellite point by
   height x tan(viewing zenith) along the satellite azimuth (the apparent
   position is displaced away from the sub-satellite point, so the
   correction moves it back). Cloudy pixels
   with no valid height keep their apparent position and are flagged
   `parallax_uncorrected`.
4. Regrid `Cloud_Probabilities`, `ACM`, `DQF` and the correction flag to a
   regular 1-D lat/lon grid by nearest neighbour. The target cell is chosen
   at runtime from the actual cropped pixel spacing and is never finer than
   the local native footprint (~2 km nadir stretches to ~4-6 km at 58.6
   degrees zenith) — no invented resolution. DQF != 0 becomes an explicit
   invalid class, never NaN.
5. Publish one zipped-Zarr artifact per scan. Scan time comes from the
   granule's `time_coverage_start`/`time_coverage_end`, not the S3 key
   timestamp. Attrs carry satellite longitude, product versions, DQF counts,
   and the regrid / parallax / Provisional-CTH disclosure strings.

The registry cadence string for `noaa-goes-east` ("full disk/product
dependent, typically minutes") does not parse, silently defaulting the worker
to 6 h; it is changed to a parseable "10 minutes" (and the freshness field
checked the same way). The status field is not touched.

### D2 — API module (`api/weather_api/satellite.py`)

A separate module, not an extension of `RENDERED_GRID_SPECS`: the group stays
`satellite`, the colormap is categorical-with-alpha rather than a scalar
ramp, time semantics are observed-at-scan, and staleness is wall-clock. It
reuses `grids.encode_png`, `grids.rasterize` and the 404/422/502 discipline
of `grids.render_grid` by call, not by copy. Responses carry
`X-Weather-Image-Basis: rendered_grid` + `X-Weather-Source-Id:
noaa-goes-east`, which the browser's provenance gate already accepts
unchanged. One layer: `noaa-goes19-cloud-mask`.

### D3 — Time, staleness, absence

Cadence 10 minutes; staleness tolerance 1800 s (three missed scans). The
layer's time axis is exactly the ingested scan times within the past window;
never a forward frame; a request resolves to the nearest stored frame within
half a cadence, else 422. Past the tolerance the layer declares itself
unavailable. A feed gap is never rendered as clear sky.

### D4 — Rendering and legend

Nearest neighbour only. Clear: fully transparent. Probably-clear: white,
alpha ~0.12. Probably-cloudy: white, alpha ~0.45. Cloudy: white, alpha scaled
by `Cloud_Probabilities` within ~0.55-0.85, capped so coastlines and roads
remain visible. Invalid (DQF-bad): a distinct dim non-white state, never
transparent. The same palette at noon and midnight. The legend draws the
transparent clear swatch over a labelled checker background (an invisible
swatch would lie), and its caption states: opacity encodes detection
confidence, not cloud thickness; NOAA-published accuracy ~90% day / ~88%
night (provider figure, not locally measured); values regridded nearest
neighbour from the fixed grid; parallax corrected from Provisional-maturity
cloud-top height, uncorrected cloudy pixels flagged.

### D5 — Coexistence

The four GeoMet composites, their JPEG branch and headers are untouched. The
cloud mask is a fifth member of the `satellite` group, per-frame
time-matched, a transparent PNG that can be flipped against or overlaid on
the opaque provider composites at the same valid time.
