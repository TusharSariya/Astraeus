# Design: retrieved time authorities without scientific use

Three adapters each bind one exact public HTTPS product and source identity. Discovery performs one bounded download, records the actual post-response UTC time, validates schema and identity, and includes the response digest in the provider revision. Fetch revalidates candidate bytes and the current window before writing coordinate-free Zarr.

`finals2000A.all` uses the provider's fixed-width contract. MJD is UTC; rows represent daily 00:00 UTC epochs. The independent polar-motion, UT1 and nutation `I`/`P` flags survive as stored variables. All Bulletin A values/errors and optional Bulletin B values remain in published units. Blank optional LOD or Bulletin B fields remain missing.

`Leap_Second.dat` preserves its Bulletin/update and expiry identity, effective MJD/date, and TAI-UTC seconds. Expired or non-monotonic tables fail closed. `naif0012.tls` is pinned by versioned URL and KPL/LSK identity; its DELTET constants and effective DELTA_AT pairs are stored but never executed.

Malformed identity, schema, date/MJD agreement, flags, numbers, monotonicity, expiry, request failure and byte ceilings fail closed. The current accepted `RunManifest` has no reference-input contract for these uncatalogued products, so every result is explicitly incomplete, QC-failed and nonpublishable. The HTTP proof injects staged immutable artifacts into a test store and reads them through `LiveStore`; it does not demonstrate worker publication. The endpoint is always `operational: false` and substitutes nothing. The readers remain under `ingest/experimental` and are absent from worker registration.

Earth PCK selection is deferred because NAIF publishes several products with different frame, accuracy, coverage and prediction semantics. An accepted scientific use and accuracy policy must precede any selection.
