# WeatherNext native statistics decoder receipt

Classification: experiment. Spec-Refs: GOV-SPEC-001, GOV-SPEC-004,
GOV-SPEC-006; `weathernext3-statistics-experiment/specs/artifact-ingestion/spec.md`
remains draft and isolated.

The new `api/weather_api/weathernext_native.py` reads actual Zarr v3 bytes through
an injected object transport. It does not reuse the retained manifest as its
input. It plans scalar initialization, hourly lead and selected grid coordinates,
then selects the exact native field chunk for the point and lead. Generation,
ETag, object path, received bytes, native unit, statistic, coordinates and exact
timestamps survive the read. Nulls survive; missing objects fail rather than
letting Zarr synthesize fill. Pressure level and member remain absent.

The [official GCS guide](https://developers.google.com/weathernext/guides/gcs),
checked September 7, confirms the statistics bucket has Requester Pays off,
hourly flattened leads, two surface grids, and no pressure levels. Raw members
remain excluded. The existing strict greater-than-48-hour historical gate is
unchanged. Current one-hour terms do not authorize expanding this implementation.

The physical layout is grounded in the existing September 5 collector:
consolidated v3 metadata, scalar init_time, single-chunk coordinates and default
slash chunk keys. This reader handles metadata-declared field chunk shapes,
including the observed whole-grid time slices. It reads the initialization epoch
from CF units rather than hardcoding the August 1 sample epoch. Unknown codecs,
time units and axis layouts fail closed. Supported codecs are bytes, zstd and
blosc. Small deterministic Zarr fixtures exercise actual zstd decoding, descending
latitude, 0–360 longitude, exact lead selection, finite fill and NaN, missing
chunks, identity failures, wrong native units, forbidden member axes and budgets.

Defaults bound consolidated metadata to 4 MiB, received bytes to 512 MiB,
decoded declared chunk bytes to 128 MiB, operations to 270 and elapsed work to
60 seconds. Object transports must enforce generation-qualified reads, streaming
receive caps and per-call timeouts. The callback API cannot enforce a dishonest
transport's allocation or timeout. Decoding is in-process; metadata-based chunk
bounds are not an OS memory or decompression-bomb sandbox. A bounded child
process is required before enabling a live/default acquisition path.

No transport implementation, SDK authentication, credentials, remote acquisition,
registration, public API mapping, manifest conversion, cache wiring or serving
permission was added. There is no full-box/all-field current proof. Root can
integrate the isolated module and tests without activating it. Remaining work:
approved credential workflow and identity entitlement; bounded child decoder;
default transport with streaming and generation verification; actual entitled
metadata/codec replay and current payload proof; consumer mapping acceptance.
The source remains operational false and is not complete.

Verification: 15 deterministic native tests plus retained query/adapter suites
run in the locked Linux image with networking disabled. Specification validation
is run separately at handoff. No provider requests occurred.
