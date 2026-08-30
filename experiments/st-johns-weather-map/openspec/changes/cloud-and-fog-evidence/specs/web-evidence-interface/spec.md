## ADDED Requirements

### Requirement: Cloud layers are listed as reported, never bucketed
The point panel SHALL list each returned cloud layer in provider order as the retrieved cover code and its base above ground level in metres, SHALL state in words that layers are shown as reported and not bucketed into strata, and SHALL NOT sort, merge or assign layers to low, middle or high. A base SHALL be shown only when its unit is metres; any other unit is shown as unknown. The existing `Cloud L / M / H` readouts SHALL stay as they are, reading unknown when nothing was retrieved for them.

#### Scenario: Two layers are returned
- **WHEN** `/point` returns `cloud_layer_1_cover_code: "BKN"` with `cloud_layer_1_base` 4267 m and `cloud_layer_2_cover_code: "OVC"` with no base
- **THEN** the Cloud layers metric reads `BKN · 4267 m  |  OVC · base Unknown`, in that order, with the source and mode of `cloud_layer_1_cover_code`

#### Scenario: No layer is returned
- **WHEN** no `cloud_layer_*` field is present or every one is `null`
- **THEN** the metric reads Unknown and the text alternative says no cloud layer value was returned

#### Scenario: A base in an unexpected unit
- **WHEN** a `cloud_layer_{n}_base` field arrives with a unit other than metres
- **THEN** the base is shown as unknown for that layer and the cover code is still listed

#### Scenario: Strata stay unknown
- **WHEN** layers are listed
- **THEN** `Cloud L / M / H` still read Unknown, because no low, middle or high value was retrieved and none is inferred from the layers

### Requirement: Fog carries its own attribution
The point panel SHALL show fog as its own metric with the mode and source of the `fog_state` field, SHALL restate it in the text alternative, and SHALL NOT present fog under another field's attribution or infer it from visibility, cloud or imagery.

#### Scenario: Fog evidence is present
- **WHEN** `fog_state` is `evidence_present`
- **THEN** the Fog metric shows the existing evidence-present wording with the source tag of the METAR or TAF step it was derived from

#### Scenario: Fog is unknown
- **WHEN** `fog_state` is `unknown` or absent
- **THEN** the Fog metric reads unknown with the existing wording that no fog determination was returned, not an all-clear

#### Scenario: Imagery does not become a reading
- **WHEN** a WEonG fog-visibility layer is drawn on the map
- **THEN** the Fog metric is unchanged, because proxied imagery is display evidence and is not sampled
