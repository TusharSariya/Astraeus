# Holyrood CASHR DPQPE capture

This is non-normative capture evidence for issue #105. Provider bodies, headers
and rebuilt image artifacts remain at `/tmp/holyrood105-capture/` for review;
they are not committed.

On 2026-09-06 the official MSC Datamart listing
`https://dd.weather.gc.ca/today/radar/DPQPE/GIF/CASHR/` advertised the paired,
non-contingency CASHR DPQPE images at 05:00Z. The actual adapter fetched and
structurally verified both as one-frame 580 by 480 GIFs:

| Product | Provider completion | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Rain | 2026-09-06T05:03:50.495439Z | 24,998 | `071cbba704819d99a13e32952923a5049bf868ece0119166981734b70ccb9e07` |
| Snow | 2026-09-06T05:03:51.050950Z | 35,569 | `2ff7a12da0a2f3e4cd1b92575496478d977f8dc2ee5c4c0b709c6a84daff9172` |

For each product the local artifact hash equals the received-body hash. The
receipt retained URL, `Content-Type`, `Content-Length`, `ETag`, `Last-Modified`
and provider `Date`. The returned run is deliberately `complete: false`; it
has no canonical numeric pixel, image API or manifest contract and cannot be
published.

GeoMet WMS capabilities were also retrieved at the same capture location. Its
DPQPE description is a North-American mosaic, not a native CASHR product. WCS
advertised no radar/CASHR coverage. The Datamart documentation identifies
DPQPE as lowest-sweep dual-polarization-processed precipitation estimation,
but does not supply independent dual-polarization moments/classes or raw
volumes on this selected path. Contingency-named GIFs are producer-labelled
composites and excluded.

Verification command:

```text
cd experiments/st-johns-weather-map/api
uv run pytest tests/test_experimental_holyrood_radar.py tests/test_adapter_eccc_hazards.py -q
# 15 passed
```
