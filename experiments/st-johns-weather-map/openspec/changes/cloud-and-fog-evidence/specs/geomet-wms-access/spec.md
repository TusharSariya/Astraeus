## ADDED Requirements

### Requirement: A provider experimental flag is disclosed, not read as a unit
A capabilities title ending in `[experimental]` SHALL have that suffix stripped before the unit is parsed, SHALL set `experimental` on the layer's coverage, SHALL prefix the offered title with `[experimental]`, and SHALL add an index notice naming the layer and quoting that ECCC marks it experimental. The word `experimental` SHALL NOT be published as a unit. Offering such a layer at all is an owner decision; the default is shown and labelled.

#### Scenario: An experimental title with a unit
- **WHEN** the title is `RDPS-WEonG - Visibility through liquid fog [m] [experimental]`
- **THEN** the parsed units are `m`, canonical `m`, and the layer is flagged experimental with a notice

#### Scenario: An experimental title without a unit
- **WHEN** the title is `Current-Alerts [experimental]`
- **THEN** no unit is parsed and the layer is not flagged, so a bracket that is not a unit is never promoted to one

#### Scenario: The flag cannot be read
- **WHEN** `GetCapabilities` does not answer for a proxied layer
- **THEN** the layer is offered with no frames and a notice, as today, and is not described as experimental or not, because nothing was read

### Requirement: WEonG fog diagnostics are proxied as display evidence only
The four `HRDPS-WEonG_2.5km_{Liquid,Ice}FogVisibility` and `RDPS-WEonG_10km_{Liquid,Ice}FogVisibility` layers SHALL be offered as proxied forecast layers with products `HRDPS-WEonG` and `RDPS-WEonG`, units `m`, `evidence_basis: live_proxy`, and semantics stating that they are an ECCC Weather Elements on Grid post-processed fog diagnostic, not a raw model field, display evidence only, not sampled by `/point`, and not an input to `fog_state`. HRDPS-WEonG SHALL name registry record `eccc-hrdps-weg-prognos`; RDPS-WEonG SHALL state it has no registry record. The layer's upstream name SHALL equal its declared spec's WMS layer, and no proxied layer SHALL be assumed to be `HRDPS.CONTINENTAL_`.

#### Scenario: The layers appear in the index
- **WHEN** `/layers` is read with capabilities available
- **THEN** thirteen `geomet-live-*` layers are listed, the RDPS pair with units `m`, each WEonG layer carrying its product, its diagnostic semantics and a legend from `GetLegendGraphic`

#### Scenario: A near-empty tile at a clear hour
- **WHEN** a WEonG fog layer renders a fully transparent image
- **THEN** it is served `X-Weather-Retrieval-Status: retrieved` as a reading of no fog forecast, under the existing transparent-image rule

#### Scenario: The point sampler ignores imagery
- **WHEN** `/point` is sampled while WEonG layers are offered
- **THEN** no field from any WEonG layer appears and `fog_state` is unaffected; using WEonG as a `provider_diagnostic` is an owner decision not taken here

#### Scenario: Capabilities cannot be read for a WEonG layer
- **WHEN** `GetCapabilities` fails for one of the four layers
- **THEN** that layer is offered with no frames plus a notice and the others are unaffected, and the request stays inside the 16-call per-request budget

#### Scenario: The budget is nearly full
- **WHEN** all thirteen proxied layers are resolved on a cold cache
- **THEN** thirteen capability fetches are charged against the ceiling of sixteen, and a fourteenth proxied layer would need the ceiling revisited rather than assumed
