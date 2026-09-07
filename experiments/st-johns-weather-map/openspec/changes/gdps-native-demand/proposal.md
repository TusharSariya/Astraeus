# Native GDPS demand experiment

Owner-directed timestamp delivery under #70/#237 adds a bounded native GDPS
point read to the existing application. This operational-false experiment
preserves provider-native science, units, masks, geometry, times and provenance.
It introduces no normative status promotion.

Scope: five existing point values (2 m air temperature, 2 m dew point, native
10 m wind speed and true-north direction, and mean sea-level pressure) plus
metadata-only hourly availability through f240. GDPS pressure profiles remain
explicitly unavailable without a provider request; #189 retains 221 vertical
fields and #194 retains the distinct GDPS-GEML product.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Owning contracts: timestamp-demand-query-cache/demand-query-cache;
evidence-truth-boundary; point-evidence-sampling; source-registry-catalogue;
field-catalogue.

The native atmospheric forecast is the dated 15 km `LatLon0.15` product. The
10 km tree carries a separate sea-ice analysis NetCDF and is not a forecast
fallback. Demand wind uses provider-published `WindSpeed` and `WindDir`; it does
not rotate or derive from the separately published U/V objects.
