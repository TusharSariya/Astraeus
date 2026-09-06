# Design

## Selected products

| Source | Exact public path | Selected fields | Disposition |
| --- | --- | --- | --- |
| `eccc-cap-alerts` | Existing GeoMet `ALERTS` adapter and official CAP documentation | Existing alert count plus verbatim feature properties | Already adapter-backed; verification only |
| `eccc-thunderstorm-outlooks` | OGC collection `thunderstorm_outlook` | Geometry and all 24 schema properties | Experimental adapter |
| `eccc-hurricane-products` | OGC collections `hurricanes-cyclone-realtime`, `hurricanes-track-realtime`, `hurricanes-error_cone-realtime`, `hurricanes-wind_radii-realtime` | Geometry and all seven schema properties per collection | Experimental adapter; seasonal empty is an answer |
| `eccc-integrated-nowcasting` | Datamart `nowcasting/matrices/SCRIBE.NWCSTG.*.n.Z` | None | Unsupported pending published schema pin |

The OGC adapters do not translate category labels, infer hurricane wind
semantics, or turn human guidance into numeric weather fields. Schema-listed
properties receive a per-snapshot disposition. Extra properties are retained
and flagged as uncontracted rather than silently promoted.

Discovery retrieves the bounded OGC FeatureCollection because no separate
provider run listing exists. The content digest and latest provider timestamp
form the experimental snapshot identity. Empty collections use the observation
instant and remain explicit `observed-empty`; transport, size and schema errors
are unavailable instead.
