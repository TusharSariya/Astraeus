# Design

## Evidence boundary

| Product / field | Public evidence | Disposition |
| --- | --- | --- |
| CASHR DPQPE Rain GIF | Datamart `today/radar/DPQPE/GIF/CASHR/` | Retain immutable encoded image only |
| CASHR DPQPE Snow GIF | same | Retain immutable encoded image only |
| Numeric rain/snow rate per pixel | no published palette/georeferencing/canonical field contract in this experiment | Deferred |
| Independent dual-polarization moments or hydrometeor classes | not in the selected Datamart bytes | Unsupported |
| Raw volume scans | no verified public path | Unsupported |
| `-Contingency` GIF | producer describes it as a neighbouring-radar composite | Excluded |
| GeoMet WMS/WCS DPQPE | WMS capability describes a North American composite; WCS advertises no radar coverage | Excluded from native CASHR scope |

Each request has a finite streaming ceiling. Discovery accepts only exact,
non-contingency `Rain.gif` and `Snow.gif` names at one common UTC timestamp.
It rejects malformed listings, a missing paired product, GIF signature errors,
and incomplete receipts. The artifact carries source filename, parsed valid
UTC time, upstream and artifact SHA-256, HTTP headers, and actual completion
time.

There is no owner-approved canonical `RunManifest` or API representation for a
rendered native radar image. `unresolved_manifest_validation` makes every run
`complete: false`; worker publication and layer/API frames are therefore
refused. Its `qc_passed` value is a structural validation verdict only and is
not a provider-quality assertion. Each artifact separately records
`source_qc.status: unknown`, because the GIF exposes no provider quality flag.
The local artifact readback is verification of bytes and provenance, never a
data product claim.
