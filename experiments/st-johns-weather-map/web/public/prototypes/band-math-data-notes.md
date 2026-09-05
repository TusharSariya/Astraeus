# Band math input readiness audit

Read-only investigation for [Prototype OpenLayers WebGLTile band math against a deck.gl two-texture shader](https://github.com/TusharSariya/Astraeus/issues/57). Spec-Impact: none: read-only evidence audit; no product behavior or normative status changes. No derived-here difference was registered. No renderer benchmark ran.

The requested HRDPS/GFS retrieved low-cloud numeric COG pair is **not ready**. Do not substitute the available HRDPS total cloud into a same-field comparison.

## Reproducible local evidence

`band-math-inputs.json` records full HTTP response bodies (PNG bytes as base64), headers, URLs, status, UTC request start times and individual elapsed milliseconds. These request durations describe diagnostic HTTP calls, not renderer frame times. Calls used localhost only; no credentials, AWS or secret stores were accessed. Snapshot captured 2026-09-05 around 01:36–01:37 UTC, as confirmed by server Date headers.

The live `/layers` response reports `data_mode=live`, `operational=false`. Relevant advertised layers:

| Layer | Field | Advertised stored instants |
| --- | --- | --- |
| eccc-hrdps-surface-total-cloud | total_cloud_opacity | 2026-09-02 23:00 through 2026-09-03 18:00 UTC |
| eccc-hrdps-low-cloud-weong | total_cloud_weong | Same HRDPS interval |
| noaa-gfs-surface-cloud-low | cloud_low | 2026-09-02 23:00 through 2026-09-04 01:00 UTC |

Shared advertised times between HRDPS total and GFS low exist hourly through September 3 at 18:00 UTC, but these are not a comparable field pair. Requests for both at the exact shared instant September 3 at 12:00 UTC return HTTP 422: the API now permits September 4 at 01:00 UTC onward. At that allowed boundary GFS low returns PNG successfully; HRDPS total returns 422 (nearest stored frame seven hours earlier). `eccc-hrdps-surface-cloud-low` at the allowed boundary returns 404: no such layer is published. Thus there is no demonstrated usable common instant even for the noncomparable rendered pair.

## Semantics, geometry and missing values

`registry/fields.py:624` declares HRDPS total cloud as opacity-weighted whole-column cover. `:654` declares GFS low cloud as a producer-declared low-layer fraction and explicitly states ECCC GeoMet publishes no layer cloud. `:648` identifies WEonG as a computed-here repair of total cover; it is not a second retrieved low-cloud input.

GFS successful PNG at September 4 01:00 UTC declares percent units, EPSG:4326, nearest native rectilinear sampling, and reference time September 2 18:00 UTC. The requested viewport is west -54, south 46.5, east -52, north 48.5; image size is 128 by 128. The layer describes a native 0.25-degree grid. Native numeric dimensions, transform, COG no-data value and independent numeric validity mask were not exposed by these responses and remain unverified. HRDPS source code handles a rotated curvilinear grid with two-dimensional latitude/longitude; its geometry at a permitted live instant could not be verified because no frame is available.

PNG headers explicitly describe white RGB with alpha `round(percent * 2.55)`. A transparent pixel can mean either stored zero cover **or missing/outside-grid data**. This PNG cannot be inverted into an honest numeric field with a no-data mask. Difference math on its alpha would conflate absent evidence and clear sky, and quantize the source values.

## COG delivery and provenance limits

TiTiler `/healthz` returns 200, but `/cog/info` without a supplied URL returns the expected 422 missing-URL response. A healthy TiTiler does not establish any COG exists. The audited API layer records contain no numeric COG URLs. `api/weather_api/app.py:1321` routes rendered grids into `grids.render_grid`; `grids.py:757` emits presentation PNG directly. Searching the ingestion source found a COG media-type constant, but no evidence that these two fields were published as COG inputs. The backing object store was not enumerated; this audit does not claim exhaustive absence of all COG files.

For the three audited source files (`app.py`, `grids.py`, `fields.py`), worktree and main workspace byte hashes match; hashes are retained in JSON. Running process/container source identity was not attested. The live API is a separately running service and its observed responses take precedence over assumptions from the local code checkout. For example the GFS index carries null run attribution while its raster supplies a reference time; preserve that distinction.

## Gate before a numeric benchmark

An honest benchmark needs two explicitly comparable retrieved numeric fields at an available exact instant; immutable COG URLs with source revision/run attribution; declared native grids, output sampling/alignment and CRS; numeric units, no-data and independent masks. Replacing HRDPS low cloud with total opacity or a generated repair changes the experiment question and cannot be done silently. No library performance recommendation can follow from this readiness audit.
