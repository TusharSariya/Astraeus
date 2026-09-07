# Decide whether AQHI may accompany a selected forecast product

## Decision requested

May the demand-query result from `eccc-aqhi` accompany an explicitly selected forecast product while retaining its own source, native observation time, station identity, and `air_quality_health_index` key?

The accepted product-selection rule currently permits companion fields only from `surface_observation`, `marine_observation`, `optional_observation`, `aviation`, `radar`, and `satellite`. The registry correctly files `eccc-aqhi` as `air_quality`, a category that mixes observations and forecasts. Adding the whole category would admit unintended forecast products. The proposed delta therefore names only a validated native `AQHI-OBS` station observation from `eccc-aqhi`; it does not promote the category or any AQHI forecast.

No implementation is included and no status is promoted. Owner acceptance is required before this behavior is implemented.
