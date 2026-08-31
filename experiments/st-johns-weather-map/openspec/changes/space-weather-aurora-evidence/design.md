## Design

### D1 - One module, three adapters, three sources

`ingest/adapters/swpc.py` follows awc.py: injectable PoliteClient and URLs,
JSON parsed in `discover`, records carried through `RunCandidate.detail`,
xarray -> `write_zarr` -> `Artifact`, `register(...)` at module import. Three
adapters rather than one because the feeds have different cadences (10 min /
1 min / 3 h), different staleness meanings and independent failure modes: Kp
still serves when the aurora grid is late. `run_time` is the newest record
each feed itself carries, never the wall clock.

### D2 - Kp honesty: observed and forecast never mix

`noaa-swpc-kp` publishes two artifacts. `kp_observed` carries the 3-hourly
observed series (`kp_index`, `a_running`). `kp_forecast` carries the forecast
file's series with `kp_status` flag-coded to the provider's own
`observed|estimated|predicted` per value - served through the existing
flag-meaning path exactly as retrieved. The `space_weather` category stays
out of FORECAST_CATEGORIES, so no `lead_hours` is ever synthesized for a
3-day outlook that the provider does not lead-index.

### D3 - Planetary quantities carry no coordinates

The Kp and solar-wind series are written on a bare time axis with no
latitude/longitude dimensions. `sample_point` skips datasets without
horizontal coordinates, so these numbers can never appear in `/point` wearing
a `sample_distance_km`. They are served only by `/space-weather`, which reads
them through a new `LiveStore.read_series` (same integrity checks and cache
as `sample_point`, no spatial claims). The OVATION grid is the one genuinely
gridded product: it keeps lat/lon, is cropped to the Atlantic context box,
and `aurora_probability` joins `FIELD_BY_VARIABLE` for honest point sampling.

### D4 - OVATION times come from the file

The OVATION JSON carries its own `Observation Time` and `Forecast Time`. The
artifact's valid time is the Forecast Time; the run time is the Observation
Time; a payload missing either is refused (`AdapterUnavailable`), because a
nowcast without its own timestamps is not evidence. Grid values are the
file's 0-100 probabilities stored as retrieved (percent).

### D5 - The aurora layer over-claims nothing

`api/weather_api/aurora.py` clones the satellite.py shape: `claims()` keeps
the generic loop from double-listing, rendering reuses `grids.sample_field` +
`encode_png`, headers carry `X-Weather-Image-Basis: rendered_grid` and
`X-Weather-Source-Id: noaa-swpc-ovation` (passing the web provenance gate
unchanged), staleness past tolerance fails closed with a notice, and 422/
404/502 semantics are identical. Colormap: fully transparent below 2 percent
(disclosed in the legend), then a green-to-red ramp with alpha scaled by
probability, identical day and night. The legend caption states: OVATION
model nowcast (~30-40 min horizon), probability of visible aurora per cell,
and NOAA's guidance that at St. John's geomagnetic latitude (~53-54 N)
aurora is typically photographable from about Kp 4-5.

### D6 - Web: readouts and one toggle

Metric cards show the latest observed Kp, the maximum forecast Kp in the
window with its provider status, and the latest Bz with its age (southward
negative Bz is the aurora tripwire; the caption says that and no more). The
aurora layer files under the existing `rendered_grid` group - no new group
machinery. Failures render as unavailable text, never as a quiet zero.
