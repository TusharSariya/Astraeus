# Design

## Exact source

The adapter accepts only Google DeepMind WeatherNext 3 product version `3.0.0`
from `gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/`.
WeatherNext 2 and Open-Meteo's WeatherNext 2 diagnostic remain separate. The
requester-paid 64-member bucket is excluded. Provider statistics carry
`member_id: null`, statistic identity, and the documented ensemble size 64;
they are never reconstructed as members.

## Field matrix

The acquisition and adapter scope contains all 126 arrays: 21 provider base
fields by `mean`, `p10`, `p25`, `p50`, `p75`, and `p90`. A bounded point read
retrieved every lead-6 array at its native 0.1 or 0.05 degree cell and preserved
six SST null masks over the selected land cell. The product-facing cloud
candidate is all 24 native total, low, medium and high cloud statistics in
fraction `[0,1]` units. The other 102 arrays are retrieved capability with no
accepted consumer mapping; production storage and API exposure remain
deferred rather than silently omitted or promoted.

The complete bounded spatial proof retains all 126 fields at lead 6 over the
declared evidence box, 45.0–50.5 N and 58.0–46.0 W: 56 by 121 cells for 114
fields on the 0.1-degree grid and 111 by 241 cells for 12 station-head fields
on the 0.05-degree grid. It preserves every cell, provider null, native unit,
statistic, time and raw object identity. Six sea-surface-temperature statistics
retain both finite ocean values and 1,587 null land cells each. This proves one
historical lead's spatial extraction and does not prove forecast cadence or a
complete operational time window. Fog, visibility, ceiling, cloud base and cloud top are unsupported because the
product does not publish them. Pressure levels and raw members exist only on
the excluded full-ensemble surface and are not fabricated here.

## Retrieval and identity

The bounded acquisition reads one object at a time, calculates sizes before
download, decodes at most one global chunk, deletes it after extraction, and
enforces a 4 GiB received-byte bound, 128 MiB decoded bound, 64 MiB serialized
output bound, 30-minute deadline, and 4 GiB local reservation in addition to
the next chunk and working allowances. The
Avalon proof rechecks generation, ETag and size after reads; the all-field proof
downloads generation-qualified objects and verifies their described byte sizes.
The adapter requires an explicit verified-read mechanism: either the box
collector's post-read metadata/ETag/size recheck or the all-field collector's
generation-qualified read with size check. It validates exact run
paths, object identities, field/lead bindings, and box metadata/coordinate
objects. This establishes internal record consistency; it does not
cryptographically authenticate arbitrary manifest JSON. Initialization,
lead, valid time, retrieval time, unknown publication time, native cell and
grid identity, native units, fill masks, product version, ECMWF initializer lineage, terms
identity and counters enter artifact provenance.

## Failure and activation boundary

Wrong version/surface/member identity, incomplete inventory, invalid statistic,
time mismatch, out-of-range value, missing payload, identity drift, cost gate,
storage gate or blocked acquisition fails closed before publication. The module
has no registry side effect and no scheduler or production configuration entry.
Point and bounded-box acquisitions are explicitly partial experiments. Their
run results remain incomplete and QC-failed, so the artifact store may stage
them for local inspection but cannot advance a current revision. Publication
requires a later accepted contract defining complete temporal and cadence
bounds.
