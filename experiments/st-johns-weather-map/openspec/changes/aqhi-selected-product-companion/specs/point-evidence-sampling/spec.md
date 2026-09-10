## MODIFIED Requirements

### Requirement: Product selection may never borrow another source's values
When a specific product is requested, the response SHALL return the fields whose provenance names that product's registry source, plus every retrieved field whose source is not the product's and whose registry `category` is one of `surface_observation`, `marine_observation`, `optional_observation`, `aviation`, `radar` or `satellite`, except a source the API names as a forecast filed under an observation category. A validated `eccc-aqhi` `AQHI-OBS` native station observation MAY also accompany the product under its own `source_id`, native observation time, station identity, and `air_quality_health_index` key; no other `air_quality` source or AQHI forecast is admitted by this exception. Every retained field SHALL keep its own `source_id`; no observation SHALL be relabelled under the product. The selection header, badge and reason SHALL describe the selected product only.

#### Scenario: Native AQHI observation accompanies a selected model
- **WHEN** a forecast product is selected and a validated `eccc-aqhi` `AQHI-OBS` station observation applies to the same point and selected instant
- **THEN** the model fields retain the selected product provenance and AQHI is shown separately with `source_id: eccc-aqhi`, its native station and observation time, and no health interpretation

#### Scenario: Another air-quality product is present
- **WHEN** a selected weather model response can access RAQDPS, RDAQA, an AQHI forecast region, or any other `air_quality` evidence
- **THEN** that evidence is excluded because the exception admits only the native `eccc-aqhi` `AQHI-OBS` station observation

#### Scenario: A product with no published artifact
- **WHEN** `product=HRDPS` is requested and `eccc-hrdps` published nothing covering the request
- **THEN** the response is `unavailable` with a `no_published_artifact:eccc-hrdps` flag and a notice naming that product and source, even when an AQHI observation exists

#### Scenario: An unknown product
- **WHEN** a product name outside the known mapping is requested
- **THEN** the request is refused with 422
