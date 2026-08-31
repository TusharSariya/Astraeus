# Design

## Decisions taken by the owner (2026-08-31)

1. **Total cloud units are declared from the message's own WMO keys.** The
   pending decision recorded in `eccc_datamart.py` offered two routes:
   publish from the coded WMO 0/6/1 keys, or carry a local ecCodes
   definitions overlay. The owner chose the WMO-key mapping. Rationale: the
   keys (discipline 0, parameterCategory 6, parameterNumber 1,
   typeOfFirstFixedSurface 1) are retrieved facts inside the message, and
   WMO code table 4.2 - the standard governing those keys - names them
   "Total cloud cover" in percent. This is a declaration from the message's
   identity, not a guess from its value range; the range-guess remains
   forbidden and tested. The basis is recorded on the variable
   (`units_basis`) and `original_units: "unknown"` preserves what ecCodes
   said.
2. **The `geomet-live-hrdps-nt` proxy is kept** alongside the rendered
   layers, as provider-truth reference imagery in its own style.

## Why not restyle or recolour the proxy

Probed live 2026-08-31: ECCC advertises no transparency style for the NT
layers (`CLOUD`, `CLOUD-50`, `CloudCover_50-100Pct_Dis` only, all opaque
where they paint). Recolouring ECCC-rendered pixels client-side would invent
a colour ramp over provider imagery, which geomet-wms-access forbids, and
would rest on an assumed luminance-to-percent mapping nobody published.
Rendering the stored grid here keeps every pixel a stored value under a
declared colormap.

## The curvilinear renderer

The rotated HRDPS/RDPS grids have no 1-D axes, so "the cell containing the
pixel" has no cheap exact form. The chosen rule is the one `/point` already
discloses for these grids: nearest published cell centre, equirectangular
distance with cos(latitude) longitude scaling. Bounded honesty: a pixel is
accepted only within half a cell diagonal (median adjacent-centre spacing
per axis, plus 5 percent for corner-pixel float noise) - beyond that it is
outside the grid and stays transparent. The method is disclosed end to end:
`X-Weather-Sample-Method: curvilinear_nearest_cell`, its own render
semantics sentence, and its own derivation version
(`rendered-grid-nearest-cell-v1`); the rectilinear path keeps
`rendered-grid-nearest-v1` unchanged. scipy's cKDTree does the neighbour
lookup; scipy moves from transitive (via metpy) to a direct pinned
dependency because the renderer now imports it.

## Semantics from provenance, not assertion

`grid_semantics` previously asserted "NOAA GFS GRIB2, 0.25 deg" for every
spec. With ECCC sources in the table, product and native resolution are now
read from the artifact's own provenance (`product`, `native_resolution`) -
retrieved facts - with an honest "an undeclared native resolution" fallback.

## Legend backdrop

`grid-cloud-alpha-v1` is a transparency ramp, so the served legend PNG was
itself transparent and read as a blank box. It is now composited over mid
grey (196), exactly the way the aurora and GOES cloud-mask legends already
composite theirs. The mapping is untouched; the legend headers disclose the
backdrop.

## Failure modes (fail closed)

- A `TCDC`/`TotalCloudCover` message without the matching WMO identity keys
  is refused with an `undeclared_units` decode error; a single-field run
  then fails loudly (`AdapterUnavailable`), never publishing unknown units.
- Until a worker run completes under the new maps, the stored artifacts
  carry no `total_cloud`: the layers are absent from `/layers` with a
  notice, the raster answers 404, and nothing is substituted.
- A curvilinear grid too small to establish a pitch, or with mismatched
  coordinate shapes, refuses to render (`GridUnavailable`).
