## ADDED Requirements

### Requirement: METAR and TAF cloud layers and present-weather groups are published as retrieved
The AWC adapters SHALL publish every reported cloud layer as its own set of variables in provider order (`cloud_layer_{n}_cover_code` as a CF flag-coded integer with `flag_values` and `flag_meanings`, `cloud_layer_{n}_cover` in percent, `cloud_layer_{n}_base` in metres with `ft` recorded as the original unit), for n = 1 to 6, and SHALL publish the present-weather group as `weather_fog_code`, `weather_fog_vicinity_code` and `weather_mist_code` (0 or 1) with the raw group text kept in `present_weather_strings`. The fog vocabulary SHALL follow WMO No. 306 FM 15 table 4678: `FG` including `FZFG`, `MIFG`, `BCFG` and `PRFG` is fog, `VCFG` is vicinity fog, `BR` is mist and not fog, and nothing else in the group is interpreted. Layers SHALL NOT be bucketed into low, middle or high strata, and the existing single `total_cloud` percent SHALL be unchanged.

#### Scenario: A layer is published with its original unit
- **WHEN** a METAR record carries `clouds: [{cover: "OVC", base: 800}]`
- **THEN** `cloud_layer_1_cover_code` is 6, `cloud_layer_1_base` is `800 * 0.3048` metres with `original_units: "ft"` in provenance, `cloud_layer_2_*` carries no value, and `total_cloud` is what it was before

#### Scenario: Unknown vocabulary is a decode error
- **WHEN** a cover code outside `SKC CLR NSC FEW SCT BKN OVC VV OVX CAVOK` is encountered
- **THEN** the adapter records `cloud_cover_code:<code>@<stamp>` as a decode error, the verdict carries `decode_error:...` and the run is refused, rather than the code being mapped to a guessed flag or dropped

#### Scenario: More than six layers is reported, not dropped
- **WHEN** a record carries a seventh cloud layer
- **THEN** the adapter records `cloud_layers_truncated:<n>@<stamp>` as a decode error and the run fails QC, so a silently thinner sky is never published

#### Scenario: A null present-weather string is retrieved absence
- **WHEN** a record's `wxString` is null or empty
- **THEN** all three weather codes are 0 and `present_weather_strings` holds an empty string for that step, distinct from a step that was never retrieved, which carries NaN

#### Scenario: Mist is not fog
- **WHEN** `wxString` is `"-SHRA BR"`
- **THEN** `weather_mist_code` is 1 and both fog codes are 0

#### Scenario: A base that cannot be read
- **WHEN** a layer's `base` is absent or not numeric
- **THEN** the cover code is still published, the base stays NaN, and a non-numeric base is recorded as `cloud_base:<value>@<stamp>`

#### Scenario: Only the first slot is declared to the manifest
- **WHEN** `validate_run` judges a METAR or TAF run
- **THEN** `cloud_layer_1_cover_code`, `cloud_layer_1_base` and `weather_fog_code` are optional manifest fields with their normalized units, slots 2 to 6 are undeclared, and a clear-sky run with no layers is still complete

#### Scenario: TAF periods carry the same shape
- **WHEN** a TAF forecast period carries `clouds` and `wxString`
- **THEN** the same per-layer and weather-code variables are published per period under `adapter_version: "awc-taf-v2"`, and the existing duplicate TEMPO/BECMG valid-time stamps are left as they are
