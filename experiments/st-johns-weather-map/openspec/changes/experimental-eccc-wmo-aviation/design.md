# Design

## Product dispositions

| Product | Experimental disposition |
| --- | --- |
| CYYT TAF | Retain the complete latest unambiguous CWAO `LTCN38` IWXXM bulletin and validate that it contains CYYT. Do not infer aerodrome identity from the filename. |
| CZQX SIGMET | Retain the latest unambiguous IWXXM document under the Gander FIR directory and validate its `CZQX` native identity. |
| IWXXM METAR/SPECI | Officially documented but absent from the live product root; defer without SWOB or bulletin substitution. |
| IWXXM AIRMET | Live directories expose `CZUL` and `CZWG`, not `CZQX`; geographically unavailable for this selection. |
| CWAO FDCN01/02/03 | Retain every available period in one bounded native family. Validate YYT and the full two-line `WPM 47N 49W` row, but do not decode compact TAC groups. |

## Bounds and identity

Directory reads are capped at 128 KiB, at 24 UTC-hour directories, and retain
their headers and exact transport completion. Each IWXXM document is capped at
1 MiB before the shared XML helper additionally refuses DTD/entity semantics,
malformed XML, more than 4,096 elements, or depth over 64. Each alphanumeric
bulletin is capped at 256 KiB, the family at three documents, 1,024 nonblank
lines, and 512 characters per line; non-ASCII and control characters fail
closed. Requests ask for identity transfer encoding so retained payload bytes
are not silently transport-decoded.

Duplicate files at the newest native timestamp are refused because amendment
and correction precedence is not contracted. Filename, issue, validity,
cancellation, forecast-basis, use-window, and transport-completion times remain
distinct. XML QName counts, attribute QName counts, native time positions, and
the complete native element inventory are retained without canonical mapping.
Every alphanumeric line is accounted for as `retrieved_uninterpreted`, with the
YYT and WPM row bytes preserved explicitly.

Any request, parse, identity, ambiguity, ceiling, or write failure removes all
tracked files. Artifacts state source QC unknown, `operational: false`, and an
unresolved manifest verdict with `complete: false`. Public HTTPS access is not
treated as accepted redistribution permission. No registry, scheduler, API,
science, safety, or admission path is added.

## Retained live evidence

The post-main capture under
`/private/tmp/astraeus-eccc-wmo-aviation-capture-20260906T0730Z` retains raw
artifacts, all response/listing headers, full inventories, and exact transport
completion. Its committed compact receipt records two IWXXM documents and the
complete three-period FDCN family. Raw payloads remain outside Git. This is
native acquisition evidence only; it does not satisfy the unresolved API,
field, rights, quality, or safety contracts.
