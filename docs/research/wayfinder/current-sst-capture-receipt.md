# Current SST capture receipt — ticket 153

Captured 2026-09-06 UTC through the isolated, unregistered adapters. These are
acquisition facts, not production admission and not evidence that fog occurs.
Exact per-object URLs, byte counts and checksums are in
[`current-sst-capture-receipt.json`](current-sst-capture-receipt.json).

## Met Office OSTIA

- Product: `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2`, near-real-time Level 4 daily
  foundation SST analysis, valid `2026-09-04T00:00:00Z`.
- Request: anonymous HTTPS against the CloudFerro Copernicus Marine
  `timeChunked.zarr`: consolidated metadata, time chunk `1`, full single
  latitude/longitude chunks, and `analysed_sst`, `analysis_error`, `mask`
  chunks `7186.2.2`. Upstream bytes: 1,471,758.
- Bounds: 45.0–50.5 N, 58.0–46.0 W; native output 110 × 240 cells at 0.05°.
- Capture time: `2026-09-06T00:15:17.751851Z`.
- Artifact: 65,695 bytes; SHA-256
  `0330fdaa1bd4c67db0869c6f70083eeeabb35e4d528aa2b91a9d1a3f4a61f6b9`;
  revision `ostia-20260904-0330fdaa1bd4c67d`.

## NOAA OISST v2.1

- URL: `https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr/202609/oisst-avhrr-v02r01.20260904_preliminary.nc`.
- Product identity: NOAA AVHRR-only OISST v2.1 preliminary Level 4 daily
  analysis, valid `2026-09-04T12:00:00Z`. The `_preliminary` identity is
  retained.
- Upstream bytes: 1,554,546. Bounds: 45.0–50.5 N, 58.0–46.0 W; native output
  22 × 48 cells at 0.25°.
- Capture time: `2026-09-06T00:15:20.011383Z`.
- Artifact: 11,561 bytes; SHA-256
  `536d1ecdbb3b522ca73c373af7e11d094fec9e5ac4e9f9b9e7a5c2b739a8cffd`;
  revision `oisst-20260904-preliminary-536d1ecdbb3b522c`.
- `anom` and `ice` arrived inside the non-subsettable daily NetCDF container,
  but were marked available-not-stored and were not normalized into the
  artifact. Ice evidence remains ticket 111 and archive acquisition remains
  ticket 94.

## Astraeus HTTP replay proof

The retained live artifacts were read through the real `/point` handler at
47.424999 N, -52.025002 W. The reference clock was injected only to put each
captured analysis inside the unchanged evidence window; the response remained
`data_mode: live`, `operational: false`.

| Source | Injected reference | Valid time | SST | Uncertainty | API revision |
| --- | --- | --- | ---: | ---: | --- |
| OSTIA | `2026-09-04T12:00:00Z` | `2026-09-04T00:00:00Z` | 15.700012 °C (native K) | 0.48999998 °C (native K) | `ostia-20260904-0330fdaa1bd4c67d` |
| OISST | `2026-09-05T00:00:00Z` | `2026-09-04T12:00:00Z` | 15.5099997 °C (native Celsius) | 0.129999997 °C | `oisst-20260904-preliminary-536d1ecdbb3b522c` |

At the actual reference clock `2026-09-06T00:15:40.126794Z`, both latest
analyses are outside the unchanged 24-hour observation window. Discovery
therefore returned `AdapterUnavailable` for both sources. This is a timely-data
gap, not a successful live-now claim; the adapters do not widen or relabel the
window. OSTIA also returns null SST at native land-mask cells, including the
default St. John's point, rather than substituting a nearby ocean value.

Raw captures and normalized artifacts remain under `/tmp/astraeus-sst-153`
for root review and are not tracked by Git. Repeat the HTTP proof with
`PYTHONPATH=api:. WEATHER_DATA_MODE=live api/.venv/bin/python scripts/replay_sst_capture.py`
from `experiments/st-johns-weather-map`.
