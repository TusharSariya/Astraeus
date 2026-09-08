# HRRR selected native point delivery

Status: draft experiment proposal. No implementation or source admission.
Issue: #259. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.

The prior optional North Atlantic contract excludes HRRR for Avalon. Preserve
that exclusion. The owner's all-source scope includes supported Focus locations;
this separate proposal describes the missing contract without relaxing Avalon
coverage or declaring unverified meteorological fields implemented.

Split NOAA HRRR CONUS `wrfsfc` and Alaska `wrfsfc.ak` into separate product
identities. Reuse NOAA indexed HTTP ranges, bounded process isolation and
source-local finite demand caching, not the GFS model/field/grid assertions.

Retained native message replay establishes one supported Denver and Anchorage
cell and no Avalon cell. The captured messages are composite reflectivity used
only for geometry. They do not validate temperature or other field mapping,
current-cycle availability, live point sampling or model-version attribution.

Before implementation, reconcile the draft requirements and choose the first
native field contract, supported-Focus request rule and current run inventory
bound. Suggested smallest next evidence is one current CONUS `TMP:2 m above
ground` indexed message for Denver; neither numeric normalization nor HRRR
version may be inferred from the existing GFS adapter or a product filename.

Partner SWOB and Citypage gates from #116 are independent of this proposal.
