# Design

| Product | Experimental disposition |
| --- | --- |
| AWC SIGMET/AIRMET | Official API/schema and bounded native artifact required; hazards, geometry, altitude and validity remain uncontracted. |
| AWC PIREP/AIREP | Official API/schema and bounded native artifact required; report fields retain source semantics only. |
| ECCC IWXXM | Official XML delivery path, product-specific schema/version and field inventory required. |
| WMO bulletins | Only selected official, public bulletins with product identity and parseable source encoding qualify. |
| ADSB.lol Mode-S weather | Blocked until physical weather fields, message semantics, permission, geography and separation from position tracking are verified. |
| AWC METAR/TAF JSON; raw tracking | Excluded. |

All network responses must have a finite streaming ceiling, retained bytes,
headers, URL, digest and transport completion. Unknown schema, term, geography,
quality, missing receipt, malformed input or resource ceiling fails closed.

## Completed bounded slice: AWC current caches

The official `aircraftreports.cache.csv.gz` and `airsigmets.cache.csv.gz` paths are retained as encoded immutable artifacts only. Encoded responses are capped at 2 MiB and streamed gzip decoding at 16 MiB. CSV headers remain ordered lists so duplicate PIREP labels cannot overwrite values. A fresh live capture with original response headers and transport-completion times lives locally at `/private/tmp/astraeus-awc-pr178-20260906T0630Z`; raw artifacts and its receipt remain uncommitted. The PIREP/AIREP capture has 2,162 rows, 44 positional columns, 121,712 encoded bytes, and SHA-256 `85da3370ba67cd604af2572241e8a271dff882ee75fae9b47d5f4b982a5243a5`, completed at `2026-09-06T05:59:25.844446+00:00`. The SIGMET capture has 9 rows, 11 columns, 1,256 encoded bytes, and SHA-256 `f994f476b89e81d393bc0d9fa1cb8641d2db6414858c67d4784d3ad0e950b8f1`, completed at `2026-09-06T05:59:25.931115+00:00`. Source QC remains unknown and the run remains incomplete. No API, field mapping, safety use or source admission is claimed.
