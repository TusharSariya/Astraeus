# Design

The candidates live under `ingest/experimental/` and are absent from the
side-effect registration list. Existing `ecmwf-ifs` and `dwd-icon-global`
registered stubs remain byte-for-byte unchanged.

ECMWF is addressed as `{date}/{cycle}z/{model}/0p25/oper/{run}-{lead}h-oper-fc`
using the producer's JSON-lines index and exact `_offset`/`_length` ranges.
The evidence inventory selects eight IFS surface records and seven profile
families at every published 1000, 925, 850, 700, 600, 500, 400, 300, 250, 200,
150, 100, 50, and 10 hPa surface. AIFS Single selects its published surface
cloud strata and six profile families. Its absent profile RH, absent TCWV, and
absent q at 10 hPa stay explicit; RH is never derived from q.

ICON uses DWD's `icon_global_icosahedral_*` objects and the matching CLAT/CLON
messages. Values stay on the R03B07 cell centres. It selects ten surface
objects and RH/T/U/V on 850, 700, 500, and 300 hPa. QV and W exist on model
coordinates, not those pressure surfaces, and are unavailable rather than
vertically converted. A lead-0 precipitation initialization is retained raw
and replay-decoded, but has no canonical value because a nonzero interval is
not established.

NOAA uses public `noaa-rap-pds` grid 130 `awp130pgrb` and `noaa-nam-pds`
`awphys` parent-grid objects, each with its `.idx`. Grid 130 contains RAP
`MASSDEN` at 8 m and column `AOTK`, but ecCodes exposes neither stable semantics
nor units and the native footprint has no cell in the target box. NAM `awphys`
contains column `TCDC`, but its native footprint does not cover the east of the
box and its nearest cell to St. John's is beyond the reader's 0.75-degree
ceiling. Both fail closed as regional exclusions. No CONUS nest, alternate
grid, or product is silently substituted.

Every decoded artifact stores two-dimensional native cell coordinates. The
reader chooses one nearest published cell without interpolation and reports
that coordinate and distance. Pressure is an integer hPa coordinate. GRIB
`units`, `stepType`, `startStep`, and `endStep` are copied from the message.
ECMWF replay starts from the retained JSON-lines index and concatenated selected
GRIB messages. ICON replay validates and decompresses each retained field and
CLAT/CLON object from its manifest. The HTTP check mounts the real `LiveStore`
behind a test-only route, so it proves reader sampling rather than a production
response schema.
