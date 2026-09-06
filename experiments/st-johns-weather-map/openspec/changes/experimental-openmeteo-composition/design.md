# Design

One experimental adapter handles three explicitly named product/access pairs.
It requests one St. John's point, streams each response under a 4 MiB JSON
ceiling, requires UTC, finite returned coordinates, exact selected fields,
full-length aligned arrays and native units, and writes a zipped Zarr artifact
only after all selected arrays validate. Returned full-day arrays are sliced
to the requested window before storage. The LSA SAF archive end is clamped to
the request's actual now, so future observation hours never enter an artifact.
Nulls remain NaN masks. Every CAMS mass concentration is converted from
micrograms per cubic metre to kilograms per cubic metre; AOD is dimensionless
and radiation remains watts per square metre.

CAMS `meta.json` is read beside the rolling series and retained as latest-model
context. It does not identify the run that produced an individual returned
value, so artifact `run_time` remains null and run certainty remains unknown.
LSA SAF is observation evidence and has no forecast run identity. Each product
lists only the intermediary transformations that apply to that access path;
forecast elevation downscaling and accumulation redistribution are not copied
onto composition or satellite provenance. Producer,
intermediary, product, response checksum, valid times, retrieval time, native
resolution, transformations, units, masks and field dispositions remain in
provenance.

The adapter stays under `ingest.experimental`; it is absent from the registered
adapter map and scheduler. API proof injects only the captured immutable
artifact into `LiveStore`, keeps `operational: false`, and performs no upstream
request during readback. Missing fields, wrong units, malformed metadata and
partial required arrays fail closed; the previous visible revision remains the
only publishable revision.
