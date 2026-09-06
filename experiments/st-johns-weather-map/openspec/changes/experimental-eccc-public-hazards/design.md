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
provider run listing exists. The content digest and latest provider timestamp,
when one exists in a feature, form the experimental snapshot identity. Empty
collections have no producer run or valid time; their identity uses the content
digest, while provenance retains the exact query interval and retrieval time.
They remain explicit `observed-empty`; transport, size and schema errors are
unavailable instead.

No canonical registry field currently represents these native vector products.
The manifest-owned one-way verdict therefore records `manifest_unresolved` and
`complete: false`. The artifacts support acquisition inspection but cannot pass
the worker publication gate or appear as an API frame until an owner-approved
canonical GeoJSON validation contract exists.
