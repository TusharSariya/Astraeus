## MODIFIED Requirements

### Requirement: Product selection may never borrow another source's values
When a specific product is requested, the response SHALL return the fields whose provenance names that product's registry source, plus every retrieved field whose source is not the product's and whose registry `category` is one of `surface_observation`, `marine_observation`, `optional_observation`, `aviation`, `radar` or `satellite`, except a source the API names as a forecast filed under an observation category (`awc-taf`: a TAF is an aerodrome forecast, not a report). Every retained field SHALL keep its own `source_id`; no observation SHALL be relabelled under the product, and no field from a source of any other category SHALL be returned. The selection header, badge and reason SHALL describe the product only. A product with nothing published for the coordinate and time SHALL return `unavailable` naming that source, even when observations were retrieved, because the reader asked about the product. An unknown product name SHALL be a 422. Retaining an observation SHALL NOT derive any value from it: `cloud_low`, `cloud_middle` and `cloud_high` remain among the unavailable point fields.

#### Scenario: Observations are kept alongside the product with their own source
- **WHEN** `product=HRDPS` is requested and `eccc-hrdps` and `awc-metar-speci` both published for the coordinate and time
- **THEN** the HRDPS fields are returned with their own values unchanged, the METAR fields are returned with `source_id: awc-metar-speci`, and a notice states that observations from `awc-metar-speci` are shown alongside HRDPS and each carries its own source

#### Scenario: Another model is still excluded
- **WHEN** `product=HRDPS` is requested and `eccc-rdps`, a `deterministic_forecast` source, also published
- **THEN** no `eccc-rdps` field is returned, so the product header still means this model's numbers

#### Scenario: A source whose category cannot be read
- **WHEN** a retrieved field names a `source_id` with no registry record or no `category`
- **THEN** it is not retained under the product selection, because an unknown category is not an observation

#### Scenario: A product with no published artifact
- **WHEN** `product=HRDPS` is requested, `eccc-hrdps` published nothing covering the request, and a METAR observation was retrieved
- **THEN** the response is `unavailable` with a `no_published_artifact:eccc-hrdps` flag and a notice naming the product and source, and the observation is not offered as an answer to a question about HRDPS

#### Scenario: An unknown product
- **WHEN** a product name outside the known mapping is requested
- **THEN** the request is refused with 422

#### Scenario: Retained cloud layers do not become strata
- **WHEN** METAR `cloud_layer_{n}_cover` and `cloud_layer_{n}_base` fields are retained under a product selection
- **THEN** `cloud_low`, `cloud_middle` and `cloud_high` are still `null` with `data_mode: "unavailable"` provenance, and `UNAVAILABLE_POINT_FIELDS` is unchanged

#### Scenario: The fixture path is unchanged
- **WHEN** `WEATHER_DATA_MODE=fixture` and a product is requested
- **THEN** the fixture response keeps its existing shape, which already carries observations beside the product, and is not altered by this rule
