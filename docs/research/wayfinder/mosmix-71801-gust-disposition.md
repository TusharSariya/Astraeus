# MOSMIX 71801 gust disposition

Date: 2026-09-06  
Tracking: [issue 144](https://github.com/TusharSariya/Astraeus/issues/144)  
Classification: research, `Spec-Impact: none`

## Finding

The all-null gusts are **producer-missing for WMO station 71801 in the sampled
MOSMIX_L cycles**. They are not an Astraeus selector, retrieval, conversion or
decode defect, and they are not an omission introduced only by Bright Sky.

Eight directly retrieved DWD station files, with issue times from
`2026-09-04T09:00:00Z` through `2026-09-06T03:00:00Z`, each contain 247
forecast positions for every one of the nine advertised gust fields. Every
position in every gust field is the DWD missing marker (`-`). The same files
contain 246 finite `FF` wind-speed positions, so the files and time axes are
populated. DWD defines `FX1` as the maximum wind gust within the last hour, in
`m/s`, in its
[meteorological-element definition](https://opendata.dwd.de/weather/lib/MetElementDefinition.xml).

Bright Sky maps MOSMIX `FX1` to `wind_gust_speed` in the pinned
[`dwdparse` parser](https://github.com/jdemaeyer/dwdparse/blob/e22a924a544dba7ce367b7044ed67c4f69ead681/dwdparse/parsers.py#L113).
Four current Bright Sky windows returned 80 forecast rows and 0/80 gust
values. No row named a fallback source for gust or any other
field. This matches the native producer masks exactly.

There is therefore no eligible code fix. Gusts must remain missing. Deriving a
gust from `wind_speed` would invent producer evidence and must remain forbidden.

## Selector and identity

The correct public selector is `wmo_station_id=71801`. Bright Sky's current
[OpenAPI description](https://api.brightsky.dev/openapi.json) defines the WMO
station selector as the stable station criterion and describes `source_id` as
an identifier obtained from `/sources`. Numeric source IDs must not be assumed
stable.

The sampled `/sources?wmo_station_id=71801` response identified exactly one
forecast source:

| Property | Returned value |
|---|---|
| Bright Sky source ID | `1228` |
| WMO station ID | `71801` |
| Observation type | `forecast` |
| Station name | `ST.JOHNS NEUFUNDL.` |
| Coordinate and height | `47.62, -52.73`, 134 m |
| Available record boundary | `2026-09-06T04:00:00Z` to `2026-09-16T10:00:00Z` |

The exact source query was
`https://api.brightsky.dev/sources?wmo_station_id=71801`. Its 263-byte JSON
body completed at the client after the final byte at
`2026-09-06T07:09:38.553416Z`, with SHA-256
`0aca97c87532717db4dbb14de50c00a56f5eb6655037c6728a0d8fc1d0a45e6e`.
The retained headers declare HTTP 200, `application/json` and
`Content-Length: 263`.

Each weather sample repeated that source object and every returned weather row
had `source_id=1228`. The identity was revalidated from each response rather
than inferred from the September 5 capture. Future retrieval should continue
selecting by WMO ID, then bind the returned forecast source ID for row
correlation within that response. A changed numeric ID alone is not evidence
of a different station; a WMO/name/type/coordinate mismatch must fail closed.

The current experimental adapter additionally requires literal source ID 1228.
That is conservative today but is a source-lifecycle contract gap: the draft
contract has not decided whether numeric-ID rotation with stable WMO identity
is acceptable. This research does not change that behavior.

## Current Bright Sky capture

All requests used `units=dwd`, so Bright Sky's declared gust unit is `km/h`.
The intended canonical conversion to `m s-1` is multiplication by `1/3.6`;
there were no finite values to convert. Valid timestamps are hourly. DWD's
native `FX1` interval is the preceding hour. Bright Sky exposes no MOSMIX issue
time, so the intermediary response's run identity remains unknown rather than
being inferred from the native directory.

Request shape for each row below:

```text
GET https://api.brightsky.dev/weather?date=<day>T04%3A00%3A00Z&last_date=<day>T23%3A00%3A00Z&wmo_station_id=71801&units=dwd
```

| Valid-date window | Client final-byte completion | HTTP result | Bytes | SHA-256 | Rows | Gust disposition |
|---|---|---|---:|---|---:|---|
| 2026-09-06 04:00–23:00Z | `2026-09-06T07:09:38.697930Z` | 200, JSON, length matched | 8,609 | `d13a242239bcf5e8a881dd77aa1c738438eb299863c41b2464d157c82349c9e2` | 20 | 0 finite / 20 null |
| 2026-09-07 04:00–23:00Z | `2026-09-06T07:09:39.211266Z` | 200, JSON, length matched | 8,614 | `d809d408f871909a04dacd85bb4741863585f248c9ff600d4d29276d7f5e44bd` | 20 | 0 finite / 20 null |
| 2026-09-08 04:00–23:00Z | `2026-09-06T07:09:39.717207Z` | 200, JSON, length matched | 8,647 | `94129bc408a09d964462503635899bafc5afe9a15f49106dddeb39e36fdc30a0` | 20 | 0 finite / 20 null |
| 2026-09-09 04:00–23:00Z | `2026-09-06T07:09:40.211569Z` | 200, JSON, length matched | 8,612 | `70917fdff0e9385bc33defc706e029726c08a1590adf93a3479e0e98bf6edc4a` | 20 | 0 finite / 20 null |

Across all 80 rows, temperature, dew point, cloud cover, visibility, mean-sea-
level pressure, wind speed, wind direction, precipitation, condition and icon
were retrieved in all 80. Six-hour precipitation probability was retrieved in
12. Gust speed, relative humidity, gust direction, hourly precipitation
probability, sunshine and solar were null throughout. This is field-level
missingness, not HTTP or response failure.

## Native DWD cycle capture

The files came from DWD's public
[MOSMIX_L single-station directory](https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/71801/kml/).
DWD describes MOSMIX_L as a four-times-daily, up-to-240-hour product in its
[availability description](https://www.dwd.de/EN/ourservices/met_application_mosmix/mosmix_application_description.pdf?__blob=publicationFile&v=2).
Each response completed with HTTP 200 and
`application/vnd.google-earth.kmz`; compressed files were bounded below 17 KiB.

| DWD issue | Client final-byte completion | Bytes | KMZ SHA-256 | Decoded KML SHA-256 | All 9 gust fields | FF |
|---|---|---:|---|---|---:|---:|
| 2026-09-04 09Z | `2026-09-06T07:09:41.264076Z` | 16,723 | `4bfa3b826748f07649bc175c840c04061d381a46aa7d5094a41c244a09a100e8` | `b90fb7dd4249c4c8d8d18622a3b624b561390b516b501eca692dab451212bb25` | each 0 / 247 | 246 / 247 |
| 2026-09-04 15Z | `2026-09-06T07:09:41.427465Z` | 16,581 | `09e376a5b67b3463f730f35bca3236568e4d9977ffa54a62de29324ffebe7967` | `60d90f7c459c6b36792707bd75464cbe4f33ae43264a37849bea2ca0f22ec257` | each 0 / 247 | 246 / 247 |
| 2026-09-04 21Z | `2026-09-06T07:09:41.938546Z` | 16,726 | `071bb10e2eb5250202f63f1f253e64dcb45e90d66313d4df8e404607ee02ff47` | `b9d33eb50b6fb174a7909bda324c9da657bff2f671df9554ca658465da893842` | each 0 / 247 | 246 / 247 |
| 2026-09-05 03Z | `2026-09-06T07:09:42.428915Z` | 16,670 | `b4e1b010882956287eb98193ad488c70ddab2ef2c2be34694314a0ab7422d005` | `2af087ff79bae49fa114435e358a288b847a2994376bcff7245734789b19a771` | each 0 / 247 | 246 / 247 |
| 2026-09-05 09Z | `2026-09-06T07:09:42.942962Z` | 16,723 | `7c31fb485796a01dd7f60da7455ce50d8a8c2233aab63144d5d56f9a47310ee0` | `33f1c0224d0a94fd8ad32ebfbd8acb017bf827eda9cbff28c07c9100820729f8` | each 0 / 247 | 246 / 247 |
| 2026-09-05 15Z | `2026-09-06T07:09:43.437508Z` | 16,546 | `92cd08fe4f7f4a8d9094133db8befe92ecb4f3be07d01f0443bd1cf5cab2f397` | `5cffa875e45887add5caec87140597feedf8bf49a501788f4b77682e8324296b` | each 0 / 247 | 246 / 247 |
| 2026-09-05 21Z | `2026-09-06T07:09:43.937860Z` | 16,502 | `0ff50f4c0e3db8aaecaacefeaec17f96758aa23b90f7cce68bcc42daebab6dfe` | `fd7ae24a56d5703ce190b728db3cc5d38beb818946fbcf6dc2147e5ae5262ee9` | each 0 / 247 | 246 / 247 |
| 2026-09-06 03Z | `2026-09-06T07:09:44.439355Z` | 16,322 | `53c951d2725f1e27bd6e5312dafb16429979229818d1fb1b8d78adcdb6b5bfbb` | `422b66ebe5c074aabc504fe044707c6ee66bf8f7a29b7831966bd97007cbff25` | each 0 / 247 | 246 / 247 |

The complete advertised gust inventory has distinct quantities and must not be
collapsed into `FX1`:

| Field | Native unit | Native meaning | Result in every cycle |
|---|---|---|---|
| `FX1` | m/s | Maximum wind gust within the last hour | 0 finite / 247 missing |
| `FX3` | m/s | Maximum wind gust within the last 3 hours | 0 finite / 247 missing |
| `FXh` | m/s | Maximum wind gust within the last 12 hours | 0 finite / 247 missing |
| `FX625` | % | Probability of gusts at least 25 kn within the last 6 hours | 0 finite / 247 missing |
| `FX640` | % | Probability of gusts at least 40 kn within the last 6 hours | 0 finite / 247 missing |
| `FX655` | % | Probability of gusts at least 55 kn within the last 6 hours | 0 finite / 247 missing |
| `FXh25` | % | Probability of gusts at least 25 kn within the last 12 hours | 0 finite / 247 missing |
| `FXh40` | % | Probability of gusts at least 40 kn within the last 12 hours | 0 finite / 247 missing |
| `FXh55` | % | Probability of gusts at least 55 kn within the last 12 hours | 0 finite / 247 missing |

Every KML identifies station `71801`, description `ST.JOHNS NEUFUNDL.`, and
coordinate `-52.73,47.62,134.0`. Its `IssueTime` matches the filename cycle.
The KML time axes and missing masks were read directly; no interpolation or
replacement was applied.

## Disposition and owner decision proposal

Keep `wind_gust_10m` represented as missing with its native preceding-hour
interval and mask. Keep the incomplete, QC-passed artifact publication refusal
already proven by the experimental adapter. No mean-wind substitution and no
silent removal of gust from the mandatory set are justified by this evidence.

For the future source contract, decide explicitly between these two behaviors:

1. **Strict-source completeness:** gust remains mandatory, so an all-null
   producer gust mask makes the whole station artifact incomplete and preserves
   the prior visible revision. This is the current experimental behavior.
2. **Field-independent availability:** preserve and publish the other retrieved
   station fields while `wind_gust_10m` remains null/missing, with field-level
   completeness and no favorable treatment of the missing gust. This would be
   a requirement and API/completeness change and needs owner acceptance before
   implementation.

Separately, the source contract should state whether the adapter may bind a new
Bright Sky numeric source ID when WMO `71801`, forecast type, name and location
remain consistent. Until that decision, the adapter's literal-ID refusal stays
fail-closed.

## Retention and bounds

Raw responses, response headers, DWD KMZ/KML files, the fetched OpenAPI schema,
and the pinned `dwdparse` checkout remain outside Git at
`/private/tmp/astraeus-issue144-evidence` for independent review. The original
curl captures are preserved, but they did not record a client final-byte time;
their server `Date` headers are not represented as completion evidence. The
fresh raw bundle and machine receipt at `fresh-completed-20260906/` were read
through `PoliteClient.get_bytes_with_headers_completed`, whose recorded UTC
timestamp is taken only after the final response byte. No time was derived from
server `Date`, `Last-Modified`, replay time or file metadata.

Git contains only this compact receipt. The fresh capture used four Bright Sky
weather requests, one Bright Sky source request and eight native station-file
requests. The native path avoided the roughly 80 MiB all-station files.
Individual HTTP bodies were capped at 4 MiB for JSON and 1 MiB for each station
KMZ. The prior and fresh evidence bundles together remain small against 36 GiB
free disk.

Verification completed on the isolated branch:

```text
uv run --project tools/specs python tools/specs/specctl.py validate
# specctl: 0 error(s), 0 warning(s)

cd experiments/st-johns-weather-map
npx --yes @fission-ai/openspec@latest validate experimental-openmeteo-brightsky --strict
# Change 'experimental-openmeteo-brightsky' is valid

uv run --project api pytest api/tests/test_adapter_openmeteo.py -q
# 34 passed
```

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005,
GOV-SPEC-006.
