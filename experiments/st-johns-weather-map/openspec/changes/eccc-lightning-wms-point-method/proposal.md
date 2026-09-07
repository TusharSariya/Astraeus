# Decide how a GeoMet WMS lightning pixel is identified on point evidence

## Decision requested

May an exact-frame `Lightning_2.5km_Density` GeoMet `GetFeatureInfo` response use a source-specific `wms_getfeatureinfo_pixel` sampling method, preserving the provider-returned point geometry when a numeric feature is present and explicitly leaving sampled coordinates and distance unknown when the provider's accepted bare `{}` no-density response supplies no geometry?

The accepted GeoMet contract defines `GetFeatureInfo` as one pixel at one time. The accepted point-evidence contract currently names only `rectilinear` coordinate-label selection and `curvilinear_nearest_cell` 2-D index selection. GeoMet performs neither operation in this deployment, so relabelling its returned pixel as either method would invent a selection mechanism. The accepted lightning truth boundary separately requires a bare `{}` response to publish `lightning_observed = 0` with density absent, but that native response has no coordinate to report.

The proposed delta adds only this source-specific WMS pixel vocabulary and the honest no-coordinate case. It does not weaken distance checks when the provider returns geometry, infer a cell coordinate from the request, permit temporal snapping, change zero/no-retrieval semantics, or promote source status.

No implementation or status transition is authorized by this draft. Owner acceptance is required before the demand point path may merge.
