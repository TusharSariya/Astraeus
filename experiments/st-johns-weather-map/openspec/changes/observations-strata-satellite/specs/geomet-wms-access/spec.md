## ADDED Requirements

### Requirement: GOES-East satellite imagery is proxied as observed, past-only evidence
The four GeoMet layers `GOES-East_1km_DayVis-NightIR`, `GOES-East_1km_SnowFog-NightMicrophysics`, `GOES-East_1km_NaturalColor` and `GOES-East_2km_NightIR` SHALL be offered as proxied layers with `product: GOES-East`, layer group `satellite`, `evidence_basis: live_proxy`, and semantics stating that they are observed imagery relayed by ECCC GeoMet from NOAA GOES-East, that frames exist only for the past, that the layer is never forecast, that it is display evidence only and not sampled by `/point`, and that the closest registry record is `noaa-goes-east`. Every offered frame SHALL be at or before the session reference instant; no frame SHALL be offered, generated or extrapolated for a future instant. A tile for such a layer SHALL carry `X-Weather-Time-Semantics` stating that the image was observed at the instant in `X-Weather-Valid-Time`. Frames, cadence and tolerance SHALL come from the advertised `TIME` extent as for every proxied layer. The thirteen previously offered proxied layers SHALL be unchanged.

#### Scenario: The layers appear in the index
- **WHEN** `/layers` is read with capabilities available
- **THEN** four `geomet-live-goes-east-*` layers are listed with `group: satellite`, `product: GOES-East`, `evidence_basis: live_proxy`, semantics containing the words "observed" and "never forecast", and `staleness_tolerance_seconds` of 300 from the advertised PT10M period

#### Scenario: Only past frames are offered
- **WHEN** the advertised extent is `<now-48h>/<now-15min>/PT10M` and it is intersected with the -3 h / +24 h window
- **THEN** only the instants inside the window are offered, every one is at or before the reference instant, and the window notice states how many of the advertised frames fall inside the window

#### Scenario: A forward instant is requested
- **WHEN** a render is asked for an instant after the last advertised frame
- **THEN** `TimeOutsideExtent` is raised client-side and the API answers 422 naming the layer, and no older frame is served as a forecast of that instant

#### Scenario: A tile is served
- **WHEN** `/layers/{id}/raster` succeeds for a satellite layer
- **THEN** the response is 200 image/png with `X-Weather-Retrieval-Status: retrieved`, `X-Weather-Evidence-Basis: live_proxy` and `X-Weather-Time-Semantics` reading "observed at the instant in X-Weather-Valid-Time"

#### Scenario: The point sampler ignores satellite imagery
- **WHEN** `/point` is sampled while satellite layers are offered
- **THEN** no `satellite_*` field appears and no cloud, fog or visibility value is affected

#### Scenario: Capabilities cannot be read for a satellite layer
- **WHEN** `GetCapabilities` fails for one of the four layers
- **THEN** that layer is offered with no frames plus a notice and the other layers, satellite or not, are unaffected

#### Scenario: The existing proxies are not disturbed
- **WHEN** the satellite specs are added
- **THEN** the thirteen existing `geomet-live-*` specs are byte-identical, with `group` unset and `legend` true by default

### Requirement: A resolution bracket is not a unit
A capabilities title whose trailing bracket matches a length such as `[1 km]` or `[2 km]` SHALL be read as a pixel resolution, not as a unit. No unit SHALL be parsed from it; the layer's coverage SHALL publish `units: unknown`, because the provider declared no unit, and the index SHALL carry a notice naming the layer and the advertised resolution. Titles whose bracket is a unit, such as `[m]`, SHALL keep their existing behaviour.

#### Scenario: A satellite title
- **WHEN** the title is `GOES-East Natural Color [1 km]`
- **THEN** no unit is parsed, `parse_title_resolution` returns `1 km`, the layer publishes `units: unknown`, and a notice reads that ECCC advertises 1 km pixel resolution for that layer

#### Scenario: A unit bracket
- **WHEN** the title is `HRDPS.CONTINENTAL - Visibility [m]`
- **THEN** the parsed units are `m`, canonical `m`, and no resolution is reported

#### Scenario: No bracket at all
- **WHEN** the title carries no trailing bracket
- **THEN** no unit and no resolution are parsed and the layer's units are `unknown`, as today

### Requirement: Legend availability reflects a probe, not an assumption
`legend_available` on a proxied layer SHALL be set from a per-spec `legend` flag rather than unconditionally true, and that flag SHALL be set only from an actual `GetLegendGraphic` probe recorded in `docs/geomet-layers.md`. A layer whose probe answered anything other than an image SHALL be offered with `legend_available: false`.

#### Scenario: A satellite layer with no legend
- **WHEN** `GetLegendGraphic` for a satellite layer answered 4xx or a non-image body during the probe
- **THEN** the layer is offered with `legend_available: false` and `/layers/{id}/legend` is not advertised as a working control

#### Scenario: A layer with a legend
- **WHEN** the probe answered 200 image/png
- **THEN** `legend_available` is true and the legend served is ECCC's own graphic, as for every other proxied layer

## MODIFIED Requirements

### Requirement: Upstream calls are budgeted per request and per process
Upstream calls SHALL be counted at the transport, so cache hits cost nothing, and SHALL be bounded both per incoming request and per process over a rolling window. The per-request ceiling SHALL be 32 upstream calls, raised from 16 so that seventeen proxied layers on a cold cache fit with headroom for roughly one more batch; the per-process window is unchanged. Exhaustion SHALL be reported as a 429 rather than fanned out. Raising the ceiling further SHALL be a deliberate decision recorded in a change, not a side effect of adding a layer.

#### Scenario: One request fans out
- **WHEN** a single API request would cause more than 32 upstream calls
- **THEN** the remainder is refused with `UpstreamBudgetExhausted`, surfaced as 429

#### Scenario: A cold index resolves every proxy
- **WHEN** `/layers` is read with every capability cache empty
- **THEN** seventeen capability fetches are charged against the ceiling of 32, and the index is returned with all seventeen proxied layers rather than none

#### Scenario: A scrub across the window
- **WHEN** the timeline is scrubbed repeatedly
- **THEN** capabilities and renders are answered from the shared TTL caches, so the same question is not re-asked upstream and the budget is not charged

#### Scenario: The proxy count is pinned against the ceiling
- **WHEN** the proxied layer specs are counted in test
- **THEN** the test asserts that the count, currently seventeen, is at or below the ceiling, so an eighteenth batch cannot silently return no proxies at all
