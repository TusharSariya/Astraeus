# GeoMet advertised-field accounting

**Non-normative research, dated 2026-09-06.** This note answers issue
[#145](https://github.com/TusharSariya/Astraeus/issues/145). It does not admit a
source, establish a canonical field, change `operational: false`, or claim that
metadata is ingestion evidence.

## Result

The reviewed 2026-09-05 ledger contains 1,289 deterministic-family coverage
IDs: 245 selected by issue #79 and 1,044 deferred. A bounded fresh WCS
capabilities request on 2026-09-06 still advertises every one of those IDs.
Within the same seven producer-product prefixes there are zero removed IDs and
zero new IDs. This comparison says nothing about the other 4,300 WCS
coverages or the other GeoMet families.

The [machine-readable manifest](geomet-field-accounting-2026-09-06.json) links
seven product files that preserve all 1,289 historical IDs. Every row records
the exact current WMS title, the semantic quantity separated from a final
bracketed unit without expanding provider abbreviations, the WGS84 extent,
valid and reference-time dimensions, parsed level where the title states one,
producer identifier, access/licence facts, representation, linked owner issues,
and one exact next disposition. Missing metadata is represented as missing; it
is not filled from identifier spelling.

| Disposition | IDs | Next action |
|---|---:|---|
| Already acquired experimentally by #79 | 245 | #141 owns source identity, field window and semantic admission; #97 owns final integration proof. |
| Unit/class semantics absent from WMS title | 86 | Resolve in #141. Preserve the title and raw value; do not infer a unit from the ID. |
| GDPS-GEML 25 km product disposition | 54 | Owner decides whether this distinct product adds relevant evidence beside current GDPS before implementation. |
| HRDPS vertical thermodynamics and dynamics | 195 | Candidate focused child: 123 thermodynamic plus 72 wind/dynamics IDs. |
| RDPS vertical thermodynamics and dynamics | 214 | Candidate focused child: 137 thermodynamic plus 77 wind/dynamics IDs. |
| GDPS vertical thermodynamics and dynamics | 221 | Candidate focused child: 136 thermodynamic plus 85 wind/dynamics IDs. |
| Convective diagnostics | 36 | Candidate focused child; keep provider diagnostics as issued and do not invent ranking thresholds. |
| Precipitation and hydrology | 99 | Candidate focused child; preserve stated amount/window semantics and do not infer rates. |
| Surface energy, land and ocean | 56 | Candidate focused child; preserve exact quantities and compare native producer paths. |
| Surface state and visibility | 83 | Candidate focused child; preserve exact quantities and compare native producer paths. |

The 1,044 deferred IDs equal the eight non-acquired rows above. The candidate
counts mean eligible for bounded follow-up investigation under the existing
experimental constraints. They do not mean production-admitted or already
retrieved.

## Current source receipts

The earlier capture recorded the server's `Date` header (`06:54:59 UTC`) but
did not record when the client received its final byte. Its client completion
is therefore explicitly unknown. A replacement capture used the repository's
`PoliteClient.get_bytes_with_headers_completed` path and records the actual
final-byte completion separately from the server `Date` header. The exact URLs,
ordered query parameters, request and response headers, byte ceilings, decoded
byte counts and digests are preserved in the compact JSON receipt. Raw bodies
and the full scratch receipt remain outside Git.

| Request | Exact URL | Final byte received (UTC) | Bytes | Service update sequence | SHA-256 |
|---|---|---|---:|---|---|
| WCS 2.0.1 `GetCapabilities` | `https://geo.weather.gc.ca/geomet?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCapabilities` | `2026-09-06T12:26:37.502141Z` | 1,090,094 | `2026-09-06T12:00:01Z` | `3c56b615f15b35913773d683b5caac596eb757b56880f5c8f937b6d9a53456c2` |
| WMS 1.3.0 `GetCapabilities` | `https://geo.weather.gc.ca/geomet?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities` | `2026-09-06T12:26:38.021203Z` | 37,108,386 | `2026-09-06T12:00:01Z` | `a1dbb4f985403167ce2bbe76b0a87649072b27148eff832714d981039149bfdd` |

The two reads consumed 38,198,480 decoded bytes under a 54,525,952-byte
operation bound. Scratch free space measured 38,479,654,912 bytes before and
38,451,228,672 bytes after the operation. Neither request retried. Regeneration
against this replacement snapshot still finds all 1,289 historical IDs and no
new or removed ID within the same seven historical producer families. Field
titles, units, levels, geography, identifiers and dispositions are unchanged;
only provider-advertised time and reference-time dimensions advanced.

WCS advertises 5,589 coverages and WMS advertises 7,071 named layers. The WMS
service identifies itself as `GeoMet-Weather 2.40.3`. ECCC's official
[GeoMet documentation](https://eccc-msc.github.io/open-data/msc-geomet/readme_en/)
describes public, free access and says GeoMet performs on-demand clipping,
reprojection, format conversion and visualization. It defines WCS as returning
coverages or grids. The page returned HTTP 200, 17,421 bytes, with SHA-256
`cccd1ff8584e6098f0cc3978d7b17aac1b98b60994933848750585ac7e4d0a18`.

The official [ECCC Data Servers End-use Licence, version 2.1](https://eccc-msc.github.io/open-data/licence/readme_en/)
grants worldwide, royalty-free use subject to its conditions, including source
acknowledgement. That page returned HTTP 200, 17,352 bytes, with SHA-256
`8dc38d32872a836ea93fb9771ba182dc14f41198fbcd17f83178e7b76e205b48`.
The accounting records the licence path rather than interpreting eligibility as
permission to change production status.

GeoMet WCS output is numeric coverage data, not a rendered image. It is also
not the model-native grid: the service advertises clipping/reprojection and the
reviewed issue-79 evidence records a rectified `PixelIsArea` TIFF plus
`server_resampled_method_unknown` when `SCALESIZE` is used. Every row therefore
states `model_native_grid: false`, `server_rectified_or_resampled: true`, and
`rendered_image: false`. A child must compare the producer's native public path
before selecting WCS.

No actual-value request was added for this research. The stable-ID and metadata
questions were resolved by capabilities, while issue #79 already provides real
bounded TIFF/artifact/reader/API evidence for 245 representative and selected
fields. Another sample would duplicate that proof. Future children must still
prove their selected values end to end; an HTTP 200 metadata response is not
ingestion.

## Existing owner boundaries

- [#79](https://github.com/TusharSariya/Astraeus/issues/79) owns the 245
  acquired fields and reusable server-rectified geometry/acquisition evidence.
- [#141](https://github.com/TusharSariya/Astraeus/issues/141) owns GeoMet source
  identity, field/lead windows, unit/class semantics and admission decisions.
- [#97](https://github.com/TusharSariya/Astraeus/issues/97) is the final native
  and integrated source-coverage blocker.
- [#133](https://github.com/TusharSariya/Astraeus/issues/133),
  [#134](https://github.com/TusharSariya/Astraeus/issues/134),
  [#135](https://github.com/TusharSariya/Astraeus/issues/135), and
  [#136](https://github.com/TusharSariya/Astraeus/issues/136) own RAQDPS/RDAQA,
  HRDPA/HREPA, HRDLPS/CaLDAS, and RDPA respectively. None owns these
  HRDPS/RDPS/GDPS coverage IDs.
- [#147](https://github.com/TusharSariya/Astraeus/issues/147) and
  [#148](https://github.com/TusharSariya/Astraeus/issues/148) own REPS members
  and GEPS producer reductions. Those ensemble families are excluded here.

## Created follow-up issues

Every focused deferred family is now an open child of map #70 and a native blocker of #97. Each implementation issue is also blocked by #141 for source identity, field-window, semantic, and admission decisions. This preserves all eligible catalogued source fields in scope independently of the current UI field set.

- [#187](https://github.com/TusharSariya/Astraeus/issues/187): 195 HRDPS vertical fields.
- [#188](https://github.com/TusharSariya/Astraeus/issues/188): 214 RDPS vertical fields.
- [#189](https://github.com/TusharSariya/Astraeus/issues/189): 221 GDPS vertical fields.
- [#190](https://github.com/TusharSariya/Astraeus/issues/190): 36 convective diagnostics.
- [#191](https://github.com/TusharSariya/Astraeus/issues/191): 99 precipitation and hydrology fields.
- [#192](https://github.com/TusharSariya/Astraeus/issues/192): 56 surface-energy, land, and ocean fields.
- [#193](https://github.com/TusharSariya/Astraeus/issues/193): 83 surface-state and visibility fields.
- [#194](https://github.com/TusharSariya/Astraeus/issues/194): the distinct-product decision for all 54 GDPS-GEML fields.

The 86 rows with unstated unit or class semantics remain directly owned by #141. The 245 selected rows remain owned by #79. Together these paths account for all 1,289 IDs and all 1,044 deferred IDs.

## Reproduction

The committed generator consumes the scratch historical ledger plus bounded
WCS/WMS capability snapshots:

```text
python3 scripts/account-geomet-fields.py \
  --historical /private/tmp/geomet-wcs-historical-2026-09-05.json \
  --wcs /private/tmp/geomet-wcs-completion-aware-2026-09-06.xml \
  --wms /private/tmp/geomet-wms-completion-aware-2026-09-06.xml \
  --capture-receipt /private/tmp/geomet-completion-aware-receipt-2026-09-06.json \
  --output docs/research/wayfinder/geomet-field-accounting-2026-09-06.json
```

The source files are deliberately omitted from Git. The manifest retains their
byte counts, update sequences and digests so an independent reviewer can bind
the derived catalogue to the exact scratch inputs.

Spec-Impact: none. This is provider research and issue decomposition only.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005,
GOV-SPEC-006.
