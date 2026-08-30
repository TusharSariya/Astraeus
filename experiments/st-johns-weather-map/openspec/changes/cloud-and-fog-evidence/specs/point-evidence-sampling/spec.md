## ADDED Requirements

### Requirement: Flag-coded categorical evidence is served as its retrieved meaning
When a sampled variable carries CF `flag_values` and `flag_meanings`, the point sampler SHALL serve the meaning string that the retrieved integer maps to, not the integer, and SHALL serve `null` for an integer outside the table. The value is the provider's own vocabulary carried through the artifact; the sampler SHALL NOT keep a parallel lookup table of its own.

#### Scenario: A cover code becomes its meaning
- **WHEN** `cloud_layer_1_cover_code` samples as 6 from an artifact whose attrs map 6 to `OVC`
- **THEN** the field value is the string `"OVC"` with units `code` and the provenance of the cell actually read

#### Scenario: A value outside the table
- **WHEN** the sampled integer has no entry in `flag_meanings`
- **THEN** the field value is `null` with full provenance, rather than a guessed label or the bare integer

#### Scenario: A NaN code is absence
- **WHEN** the sampled cell is NaN
- **THEN** the field value is `null`, as for any other variable

#### Scenario: A base is served in metres with its original unit
- **WHEN** `cloud_layer_1_base` is sampled
- **THEN** the value is in metres and provenance records `original_units: "ft"` for that variable

### Requirement: Fog state is derived only from retrieved present-weather codes and says which
`fog_state` SHALL be derived per source from the sampled `weather_fog_code` and `weather_fog_vicinity_code` only, with `fog_code = fog OR fog_vicinity` and no provider diagnostic, and the derived field SHALL carry `derivation` text naming what counts as fog evidence (FG including FZFG, MIFG, BCFG, PRFG, and VCFG), what does not (BR is mist), and `derivation_version` `fog-state-present-weather-v1`. The raw `weather_*_code` inputs SHALL be sampled but never served as fields. Because no provider fog diagnostic is read, the derivation SHALL NOT produce `not_indicated`; absence of a fog group is `unknown` until a provider diagnostic is retrieved and approved.

#### Scenario: A fog group was reported
- **WHEN** the sampled `weather_fog_code` is 1
- **THEN** `fog_state` is `evidence_present` with units `category`, the derivation text and version in provenance, and the source of the METAR or TAF step it came from

#### Scenario: Only vicinity fog was reported
- **WHEN** `weather_fog_code` is 0 and `weather_fog_vicinity_code` is 1
- **THEN** `fog_state` is `evidence_present`, and the derivation text states that VCFG counts

#### Scenario: No fog group was reported
- **WHEN** both fog codes sample as 0
- **THEN** `fog_state` is `unknown`, never `not_indicated`, because the observer reporting no fog group is not a provider diagnostic that fog is absent

#### Scenario: The step was never retrieved
- **WHEN** the fog codes sample as NaN
- **THEN** `fog_state` is `unknown` with provenance, and no value is borrowed from another step or source

#### Scenario: Raw codes are never a field
- **WHEN** a point response is assembled
- **THEN** `weather_fog_code`, `weather_fog_vicinity_code` and `weather_mist_code` do not appear as fields, only `fog_state` does

#### Scenario: Nothing was retrieved at all
- **WHEN** no artifact answers the coordinate
- **THEN** `fog_state` remains one of the twelve unavailable point fields, `null` with `data_mode: "unavailable"` provenance, and `UNAVAILABLE_POINT_FIELDS` is unchanged
