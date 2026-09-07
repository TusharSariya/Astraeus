# SWPC plasma selected-time demand query

Issue #242 replaces scheduled artifact delivery for the already admitted
`noaa-swpc-plasma` source with the selected-time demand/cache architecture.
It preserves the provider's 29 native plasma fields, time/source row identity,
spacecraft flag and quality values while exposing the existing density, speed
and temperature readings in the Space Weather card.

The implementation is experimental and `operational: false`. It does not add
bow-shock propagation, combine magnetic and plasma spacecraft rows, derive a
coupling value, create an archive, or promote any specification status.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Owning contracts: timestamp-demand-query-cache/demand-query-cache;
free-space-weather-products/space-weather-evidence;
source-registry-catalogue; field-catalogue.
