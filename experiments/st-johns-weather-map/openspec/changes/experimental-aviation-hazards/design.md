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

The official `aircraftreports.cache.csv.gz` and `airsigmets.cache.csv.gz` paths are retained as encoded immutable artifacts only. Encoded responses are capped at 2 MiB and streamed gzip decoding at 16 MiB. CSV headers remain ordered lists so duplicate PIREP labels cannot overwrite values. Retained capture/headers live at `/tmp/aviation115-capture`; the replay proof is explicitly no-network and does not substitute its clock for original completion. No API, field mapping, safety use or source admission is claimed.
