## Why

The September 9 owner implementation request authorizes the supplied IFS
forecasts, ensembles and Atlantic map layers plan as an isolated experiment.
The existing deterministic demand reader acquires four fields together and
cannot deliver selected profiles, members or native maps.

Classification: Experiment.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

## What Changes

Extend experimental source-delivery, comparison, grid and ensemble contracts
with a versioned IFS catalogue and finite selected-record acquisition. Reuse
ECMWF indexed transport, isolation, scientific methods and native rendering.
Keep AIFS, scheduled ingestion, paid archives and operational admission outside
this change. No normative status is promoted.

## Impact

The existing WeatherNext interfaces remain compatible. Source product, run,
field, level, temporal definition and variant remain explicit. All input bytes
are bounded; incomplete selection results retain their reasons and receipts.
