# Native RDPS demand experiment

Owner-directed timestamp delivery under #70 replaces the retained-run RDPS
read. This operational-false experiment preserves the existing native RDPS
science, sampling, units, and declared derivations. It introduces no normative
status promotion. #188 retains the 214 additional vertical catalogue IDs.

Scope: six existing surface inputs, the 19 existing profile inputs exposed at
1000/850/700/500 hPa, and metadata-only native hourly availability through f084.
Other mapped levels, surface pressure, additional catalogue IDs and native
rasters remain outside this slice and are explicitly deferred under #188/#70.
Existing GeoMet proxies retain their own source identity.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
Owning contracts: timestamp-demand-query-cache/demand-query-cache;
point-evidence-sampling (native nearest cell, missingness, product isolation,
profiles and declared RH/wind derivations); grib-decoding (WMO cloud identity);
field-catalogue (opacity cloud and liquid-water RH semantics).

The demand-only wind selectors use the provider-native WindSpeed/WindDir
objects at the existing levels. Actual component metadata is grid-relative;
native direction is coded in Degree true and is returned numerically unchanged
with the canonical degree label. No vector transformation is introduced.
