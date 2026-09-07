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

## HRDPA and HREPA demand boundary

The existing WCS client is the transport and numeric-grid seam. A future #134
demand reader reuses its exact coverage ids, bounded receive/decode limits,
advertised-time checks, EPSG:4326 geometry validation, native unit metadata,
nodata mask, response headers, and final-byte completion time. It does not use
the scheduled artifact store and does not retain a provider-response archive.

The canonical cache key contains the source id, coverage id, selected analysis
time, requested WCS subset, and requested shape. The cache has explicit entry
and aggregate byte ceilings, a finite response-freshness TTL, coalesced
identical misses, and a bounded failure backoff. An expired entry may retain
bounded identity and expiry metadata, but its values are withheld. A cache hit
makes no WCS request and does not extend expiry.

The normal point route can include a field only when the selected timestamp is
an exact advertised coverage time and the returned normalized grid contains an
applicable published cell. Provenance discloses the requested and sampled
coordinate, sample distance, WCS coverage id, requested subset and shape,
published units, accumulation/statistic interval, nodata handling, geometry,
source id, final-byte time, digest, and cache expiry. The existing WCS path
records provider resampling as unknown; the response must preserve that fact
and must not describe the cell as a native-resolution point.

| Source | Initial public field | Meaning | Time/run rule | Unresolved source scope |
| --- | --- | --- | --- | --- |
| `eccc-hrdpa` | `precipitation_accumulation` from `HRDPA_2.5km_Precip-Accum6h` | Final six-hour accumulated precipitation, provider values unchanged | Exact advertised end time; no forecast lead; no invented run | Other accumulation intervals need exact coverage and interval evidence |
| `eccc-hrepa` | Candidate source-scoped fields named `HREPA.6P_2.5km_PCT25` and `HREPA.6P_2.5km_PCT75` in the scaffold | Unavailable until provider evidence proves their percentile ranks and literal interval | Exact advertised analysis time only after proof; no forecast lead or invented run | Coverage advertisement, units, interval, geometry, masks, shared time, analysis, uncertainty, confidence, probabilities, members/control and quality mappings |

The HREPA candidates remain unavailable until a retained fixed fixture and one
bounded provider receipt prove their advertised identities, percentile ranks,
literal interval, units, geometry, masks, and shared time. The reader never
manufactures an ensemble distribution from those candidates or claims that
they prove the registry's wider HREPA field inventory.
