# ECCC AQHI selected-time demand observation

## Why

Issue #241 migrates the admitted `eccc-aqhi` observation from scheduled artifact ingestion to the selected-time demand architecture. The existing adapter's sparse outer-product grid can place NaN cells at station-coordinate combinations that ECCC never published; this path retains and selects actual native point features instead.

## What changes

- Query the accepted `AQHI-OBS` WMS vector layer over the declared Avalon box with one bounded canonical request.
- Cache one normalized station document under finite freshness, coalesce misses, and withhold all values after expiry when refresh fails while retaining only typed bounded acquisition metadata.
- For the default unselected point response, consider only native observations at or before the selected instant with age strictly less than one hour, then choose the nearest actual station by the accepted latitude-corrected distance.
- Preserve native station identity, coordinate, observation time, AQHI index units, provider QC token, response digest, final-byte time, request identity, and bounded transport metadata.
- Advertise the observation layer from source-local cache metadata without an upstream catalogue request and disable scheduled AQHI ingestion.

The existing product-selection contract does not permit `air_quality` sources as companion observations. This change therefore does not append AQHI to an explicitly selected product. The separate `aqhi-selected-product-companion` proposal records that owner decision without implementing it.

The experiment remains `operational: false`; no AQHI interpretation, health advice, concentration conversion, forecast region, archive, interpolation, stale fallback, or source-status promotion is introduced.
