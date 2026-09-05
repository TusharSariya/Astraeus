# Design

Each gridded adapter retrieves one object through anonymous HTTPS with a 64 MiB
per-file ceiling. S3 discovery requests at most 1,000 keys per hour prefix and
looks back six hours. The NetCDF must identify the selected product and G19,
and its own scan time must agree with the object key within one second.

The fixed-grid crop retains native cells. Two-dimensional latitude and
longitude are computed from the file's geostationary projection; pixels outside
the evidence box are masked. The original pressure coordinate remains on
LVMPF/LVTPF. Native units are checked before the three explicit normalizations:
TCF fraction to percent, TPW millimetres to the dimensionally equivalent
kg m-2, and LVT kelvin to degC.

Every native DQF array and meaning table remains in the artifact. Scientific
values become readable only at product-declared good states. CODF, COD2KMF and
CPSF use DQF 1/2 for the valid day/night algorithm branches; the remaining
products use zero. A scan with no readable value fails completeness and QC.

DMW keeps every in-box vector with its DQF, band, pressure, tracer temperature
and geometry. GLM keeps events, groups and flashes with their identifiers,
parents, time, energy, area and quality. An empty in-box GLM or DMW collection
is an observed empty only after the file was read and its field of view was
proved to contain the box.

All adapters remain absent from scheduler registration. Artifacts and source
payloads are local evidence only; Git contains tests, the receipt and code.
