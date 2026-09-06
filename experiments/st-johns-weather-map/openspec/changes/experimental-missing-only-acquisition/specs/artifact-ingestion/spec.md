## ADDED Requirements

### Requirement: Partial cache acquisition fails closed without a safe publication representation
When the restart cache reports only some declared valid times for a provider
run, the worker SHALL pass the exact missing valid times to an adapter that
explicitly declares partial-fetch support. An adapter without that declaration
SHALL receive no payload fetch, and the outcome SHALL preserve the retained
revision while naming partial repair as unsupported. The declaration SHALL NOT
permit replacement of an already-published `(source_id, provider_run_id,
valid_time)` with different bytes.

#### Scenario: Selectable indexed request
- **WHEN** the cache holds one of several declared times and the adapter declares a safe partial representation
- **THEN** the adapter's request-construction window covers only missing times while the provider run id remains unchanged

#### Scenario: Aggregate artifact has no verified merge representation
- **WHEN** the cache is partial and the adapter has not declared partial-fetch support
- **THEN** the source fails before `fetch`, reports that retained frames remain visible, and publishes nothing

#### Scenario: Cache state is unknown
- **WHEN** the store cannot answer which run times are present
- **THEN** the source fails before `fetch` and does not interpret the unknown state as an empty cache
