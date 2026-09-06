## Design

### D1 - One seam, three adapter modules

`ingest/space_weather.py` holds what every coordinate-free series has in
common so that ten adapters written in parallel produce artifacts one reader
serves. Retrieval is `fetch_json`: it streams through
`PoliteClient.download_with_headers` under a byte ceiling (512 KiB for the
small products feeds, 8 MiB for the 24-hour RTSW and GOES feeds, measured
2026-09-05 at 1.5 MB, 2.7 MB, 245 KB and 643 KB), refuses a body past the
ceiling mid-stream, hashes what arrived and returns a `FeedReceipt`. The
receipt, never the body, goes into provenance under `retrieval`.

### D2 - Interleaved feeds get a platform axis, not a bare time axis

The RTSW magnetometer and plasma feeds interleave SOLAR1, ACE and IMAP rows at
the same minute. A bare `valid_time` axis cannot hold that without either
dropping two spacecraft or lying about duplicate instants, so these series are
`valid_time x spacecraft`, labels verbatim from the feed's `source` field and
sorted, a spacecraft with no row at a minute holding NaN. The `active` flag
and every `max_*_flag` / `overall_quality` column are stored as variables,
verbatim, including the feed's own `-9999` sentinel, which is recorded as a
sentinel in the variable attributes rather than converted. GOES feeds use the
same shape on a `satellite` axis; the NOAA scales file, whose "0" and "1" keys
share one instant, uses one issue instant times a `day_offset` axis.
`LiveStore.read_series` serves such a series per label as `name@label`, or one
label under its plain name when the caller selects it, and reports the labels
in `SeriesData.dimensions`; a dataset with two such axes is refused.

### D3 - Scopes are declared, never inferred

Every artifact's provenance carries `measurement_scope`: `planetary` (Kp, Hp30,
Dst, scales), `l1` (RTSW), `propagated` (SWPC Geospace propagated wind),
`geosynchronous` (GOES), `station` (reserved for STJ, which is not retrieved)
and `issued` (alerts). The propagated product keeps both instants the feed
gives - the L1 measurement minute as `valid_time` and the bow-shock arrival as
`propagated_time_unix` - and derives no lag. Kyoto Dst via SWPC is
`reprocessed`; `series_provenance` refuses that class without an intermediary
and refuses an intermediary on any other class, so a relay cannot be declared
retrieved by omission. Where a feed declares no provisional/final status (Hp30
serves none; the Dst relay interleaves without the WDC final flag) provenance
says `status_declared: false` and nothing is invented.

### D4 - Stale behind HTTP 200 is unavailable

Every adapter's `discover` refuses a feed whose newest instant is older than
the window start, naming the instant; the alerts feed alone is exempt, because
a quiet week is not a stale feed, and its provenance carries the newest issue
instant and the feed's Last-Modified instead. The two registry tombstones
(STEREO-A relay, hourly Kp prediction) keep their `unavailable` state; the
re-probe facts are appended to their reasons so the next reader has the
evidence, and the decision stays with the owner.

### D5 - The registry schedules only what an adapter claims

Records gain reach and native cadence only because an adapter now exists to be
measured against them (source-admissions-ledger deviation 2). The RTSW
condition block is kept and marked satisfied with the adapter version, the
fixture and the receipt that satisfy it. The plasma record's endpoint is
corrected, not swapped in silence: the reason states the 404 and the date.
Polling stays inside the scheduler's 300 s floor and the freshness half-life,
so the RTSW pair costs about 4.2 MB per poll; the per-operation byte ceilings
and the polite per-host interval are the safeguards the capacity decision
(issue 74) retained.

### D6 - Readback is one endpoint over one reader

`GET /space-weather/products` lists every published `space_weather` series
artifact through `read_series`: source, product, scope, evidence classes,
producer and intermediary, receipts, the stored dimensions, each variable's
units and latest finite value (per label on a platform axis), the newest
instant and freshness against the registry threshold. An artifact that cannot
be read is reported as skipped with the reason; fixture mode answers
unavailable; nothing is substituted.
