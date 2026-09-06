# Change: Acquire the free space-weather products the roster admitted

## Why

The 2026-09-02 admissions (issue 25) admitted eleven space-weather products
beyond the three SWPC feeds already ingested, and the source audit at 333d5e2
lists them as absent adapters plus one disabled adapter: the real-time solar
wind adapter stores `bz_gsm` and `bt` on a bare time axis while the feed now
interleaves SOLAR1 (SWFO-L1), ACE and IMAP by the minute with an `active`
flag and a quality flag set per row, so which spacecraft measured a served Bz,
and whether the row was flagged usable, is unrecoverable from what is stored.
Issue 89 asks for that handling to be completed and for the admitted plasma,
propagated wind, one-minute Kp, alerts, NOAA scales, GFZ Hp30, GOES
magnetometer and X-ray and Kyoto Dst products to be acquired, with planetary,
L1, propagated, geosynchronous and station measurements kept apart, stale
HTTP-200 relays kept unavailable and the STJ/imagery permissions explicit.

Verified live on 2026-09-05 (receipts under
`docs/research/wayfinder/space-weather-receipts/`): every feed named below
answers with the pinned shape, except `products/solar-wind/plasma-7-day.json`,
the endpoint the plasma record carried, which is HTTP 404; the live SWPC plasma
product is the 1-minute `json/rtsw/rtsw_wind_1m.json` feed. The STEREO-A
relay, recorded `unavailable` as stale, was found current again on re-probe;
that state is not changed here (see owner decisions).

What is not verified: long-run schema stability (live-smoke tripwires pin the
shapes), the science value of any of these for Avalon visibility (research,
non-normative), and production admission, which stays with the owner.

Classification: Experiment, Spec-Impact: none for `docs/specv1`. Every source
stays `operational: false`; registry status stays a ceiling.

## What changes

- **`ingest/space_weather.py`** (new): the shared seam for coordinate-free
  series - bounded, receipted JSON retrieval (`fetch_json` streams under a
  byte ceiling and returns a `FeedReceipt`: URL, parameters, byte count,
  SHA-256, capture instant, provider Last-Modified); feed-own instants;
  1-D and platform-axis datasets; provenance with a `measurement_scope` and a
  mandatory intermediary for `reprocessed` relays.
- **`ingest/adapters/swpc.py`**: `noaa-swpc-rtsw` re-implemented
  (`swpc-rtsw-v2`) on a `valid_time x spacecraft` axis with the feed's
  `active` flag and every quality flag stored verbatim; `noaa-swpc-plasma`
  added on the same shape from the RTSW plasma feed.
- **`ingest/adapters/swpc_products.py`** (new): propagated solar wind
  (bow-shock arrival instant stored beside the L1 minute, no lag derived),
  one-minute Kp (with the SWPC thirds code flag-coded), alerts (issued text
  verbatim), NOAA scales (one issue instant times a `day_offset` axis), GOES
  magnetometer and X-ray (`valid_time x satellite`), and Kyoto Dst declared
  `reprocessed` with producer Kyoto WDC and intermediary NOAA SWPC.
- **`ingest/adapters/gfz.py`** (new): GFZ Hp30 over a bounded 24-hour
  selection, licence checked against the response's own `meta.license`.
  Follow-up issue 150 adds unregistered experimental readers for current GFZ
  Kp and Hp60 over the same bound. Kp's per-value `status` token is retained;
  Hp60 declares none. Both remain `catalogued` and cannot be scheduled.
- **Registry**: the ten records gain reach, native cadence and parseable
  freshness so they schedule; the RTSW admission condition is recorded as
  satisfied by the v2 adapter; the plasma access endpoint is corrected with
  the 404 receipt; the two stale-relay tombstones carry the re-probe facts and
  stay `unavailable`.
- **`LiveStore.read_series`**: serves a platform axis (`name@label`, or one
  selected label) and text values verbatim. **`GET /space-weather`** serves
  the latest Bz from the spacecraft the feed flagged active, naming it.
  **`GET /space-weather/products`** (new) reads every published space-weather
  series back with its scope, evidence class, receipts, freshness and latest
  values, failing closed in fixture mode.
- Fixtures are hand-trimmed samples under 20 KB; no provider payload enters
  Git.

## Capabilities

### Modified capabilities

- `space-weather-evidence`: per-spacecraft L1 series, scope separation,
  reprocessed relay declaration, stale-relay refusal, products readback.
- `artifact-ingestion`: bounded, receipted feed retrieval for series sources.
- `source-registry-catalogue`: the RTSW condition recorded satisfied; a dead
  access endpoint corrected with evidence rather than silently swapped.
