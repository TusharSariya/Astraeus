# Design: product-specific manifests over shared bounded transport

## Boundary

The shared WCS client owns HTTP limits, advertised-time selection, TIFF
validation, EPSG:4326 geometry checks, numeric decode, deterministic Zarr
round-trip, and immutable digests. Product contracts own source/product
identity, exact selected coverage ids, time meaning, cadence, and quality
semantics. Sharing transport does not imply that analysis grids are forecast
grids.

Unknown source semantics stay under `raw__` names with upstream units retained.
Only already-catalogued PM2.5 and precipitation quantities use canonical names.
No unit conversion, quality class, forecast lead, or missing-data meaning is
inferred.

The current selected set is deliberately small: four RAQDPS PM2.5/smoke
coverages, two RDAQA PM2.5 coverages, one final six-hour accumulation from each
of HRDPA and RDPA, HREPA's 25th and 75th percentile coverages, and two fields
each from HRDLPS and CaLDAS. Catalogue breadth is not an implementation claim.
RDPA advertises its selected layer in EPSG:102978 with unlabelled units, so its
field is metadata-only and retrieval fails closed until that CRS and unit
contract is resolved; it is not treated as the superficially similar RDPS grid.

Non-raster hazards, hotspot features, and nowcasting matrices fail closed with
a named reason. Standalone RAQDPS-FireWork remains superseded; current smoke is
represented only by RAQDPS wildfire-plume and RDAQA-FW analysis coverages.
