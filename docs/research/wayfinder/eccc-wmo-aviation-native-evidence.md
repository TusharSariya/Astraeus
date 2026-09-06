# ECCC IWXXM and WMO aviation native-source evidence

Non-normative research for issue #115, checked 2026-09-06. This note identifies acquisition candidates only. It does not define aviation safety meaning, canonical fields, quality, or publication rights.

## Authority and common constraints

ECCC's [IWXXM Datamart documentation](https://eccc-msc.github.io/open-data/msc-data/aviation/iwxxm/readme_aviation-iwxxm-datamart_en/) defines the HTTPS hierarchy as `aviation/iwxxm/{product}/{code_issuer}/{HH}`, the filename as `A_{TTAAiiCCCCYYGGggBBB}_C_{CCC}_{YYYYMMddhhmmss}.xml`, and Canada's encoding as WMO IWXXM 3.0.0 plus Canadian schemas and code lists. The live documents inspected used `http://icao.int/iwxxm/3.0`. Canadian extensions, schemas, code lists, and documentation are published beside the products under [`schema/`](https://dd.weather.gc.ca/today/aviation/iwxxm/schema/), [`code-ca/`](https://dd.weather.gc.ca/today/aviation/iwxxm/code-ca/), and [`doc/`](https://dd.weather.gc.ca/today/aviation/iwxxm/doc/).

The public hierarchy is governed by the [ECCC Data Servers End-use Licence](https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt). Any implementation should retain the exact licence URL and source URI without treating public access as science or safety acceptance.

A bounded reader needs separate caps for directory listings, encoded XML bytes, XML element count/depth/attributes/text, and schema/code-list references. It must forbid DTD/entity expansion, validate the root bulletin and IWXXM namespace/version, retain every native XML element and attribute, and avoid dereferencing `xlink` or schema URLs during parsing. Filename time, bulletin identifier, issue time, valid period, cancellation/amendment state, issuing unit, FIR/aerodrome identity, and retrieval completion are distinct fields and must not substitute for one another.

## Product dispositions

| Product | Current public path and observed shape | Newfoundland/Avalon disposition |
| --- | --- | --- |
| TAF | [`today/aviation/iwxxm/taf/cwao/{HH}/`](https://dd.weather.gc.ca/today/aviation/iwxxm/taf/cwao/) contains WMO `LTCN` bulletin XML. At 05 UTC, `A_LTCN38CWAO060500_C_CWAO_20260906050000.xml` was 32,662 bytes and contained CYYT among multiple aerodrome forecasts. | **Selected:** CYYT entries only, identified inside the bulletin. The filename does not identify CYYT, so whole-bulletin acquisition must preserve all members or a structurally verified extraction must retain bulletin/member identity. Amendments/corrections (`AAA`, `RRB`, and other `BBB`) cannot be ordered lexically as ordinary replacements. |
| SIGMET | [`today/aviation/iwxxm/sigmet/czqx/{HH}/`](https://dd.weather.gc.ca/today/aviation/iwxxm/sigmet/czqx/) directly exposes Gander FIR bulletins. `A_LSCN27CWAO060320_C_CWAO_20260906032055.xml` was 4,182 bytes and identified FIR `CZQX`. | **Selected:** CZQX only. Preserve phenomenon, geometry, vertical extent, movement, issue/valid period, sequence, cancellation/replacement, issuing unit, and nil reasons as native structure; infer none of their operational meaning. |
| AIRMET | The live root exposed only [`czul`](https://dd.weather.gc.ca/today/aviation/iwxxm/airmet/czul/) and [`czwg`](https://dd.weather.gc.ca/today/aviation/iwxxm/airmet/czwg/), while the official documentation lists AIRMET header families `LWCN`/`LWNT`. | **Geographically unavailable:** no CZQX directory was advertised. Do not relabel CZWG/CZUL as Gander coverage. Discovery may record an observed-absent CZQX disposition without fetching another FIR's payload. |
| METAR | Official documentation lists `metar` and header `LACN`, but the live product root did not advertise `metar/`. | **Deferred/observed absent:** no current public path was verified. Do not guess a replacement from SWOB or alphanumeric bulletins. |
| SPECI | Official documentation lists `speci` and header `LPCN`, but the live product root did not advertise `speci/`. | **Deferred/observed absent:** same constraint as METAR. |

The hierarchy's `{code_issuer}` is not consistently an aerodrome identifier: live TAF used `cwao` and carried multiple aerodromes, while SIGMET used FIR directory `czqx`. Selection must therefore validate native document identity rather than infer geography from the directory alone.

No stable cadence should be inferred from one listing. Discovery should inspect only the current and bounded prior UTC-hour directories required by a separately approved cadence contract, then select using native issue/amendment semantics. Empty current hours are a normal observed-empty state, distinct from transport failure.

## Selected alphanumeric WMO bulletin candidate

The current [alphanumeric hierarchy](https://dd.weather.gc.ca/today/bulletins/alphanumeric/) is organized as `{YYYYMMDD}/{TT}/{CCCC}/{HH}`. ECCC's official [bulletin search help](https://dd.weather.gc.ca/bulletins/doc/CMC_Bulletin_Search_Help_en.pdf) defines searchable product, issuer, date/hour/minute, and optional station properties; those query fields are discovery metadata, not a payload schema.

`FD/CWAO/02/` advertised four CWAO winds/temperatures-aloft bulletins: `FDCN01`, an amended `FDCN02`, a later `FDCN02`, and `FDCN03`. Their text contains explicit `FCST BASED ON`, `VALID`, and `FOR USE` groups. The current `FDCN01/02/03` bodies contained Newfoundland identifiers including YYT, YQX, YQY, YJT, and ocean point WPM. This makes the CWAO `FDCN01`, `FDCN02`, and `FDCN03` family a **selected bounded native-text candidate** for Newfoundland/Avalon winds and temperatures aloft.

The selection is the complete bulletin family for a native issue cycle, not an arbitrary YYT line: shared headers define levels and validity, and amended/corrected bulletins affect identity. The format is compact traditional alphanumeric code, not self-describing XML. Before implementation it needs a pinned owner contract for bulletin grammar, level columns, `9900`/missing encodings, amendment precedence, station/point authority, issue/valid/use times, and complete family membership. Until then it can only be retained as immutable native bytes with source QC unknown and `complete: false`; no numeric wind or temperature publication is justified.

Finite acquisition should cap the date/product/issuer/hour listings, number of family members, bytes per bulletin, aggregate bytes, line count, line length, and decoded character set. It should reject path escapes, unknown headers, duplicate/conflicting identities, partial family cycles, malformed control characters, and ceiling breaches with complete cleanup. The live 02 UTC listing is evidence of access, not an authoritative publication cadence.

## Exclusions and next gates

- Do not substitute existing normalized SWOB METAR-like observations for absent IWXXM METAR/SPECI.
- Do not acquire non-CZQX AIRMET as Newfoundland evidence.
- Do not map IWXXM hazards, TAF conditions, or FD groups to canonical values without product-specific field/time/QC contracts.
- Do not register, schedule, publish, or call issue #115 complete from these access findings. Each selected path still needs measured complete-operation bounds, immutable receipts with actual HTTP completion, a full native inventory, manifest validation, and independent artifact/API proof if an approved delivery route exists.

## Bounded capture result

The final post-main capture is summarized in
[`eccc-wmo-aviation-capture-receipt.json`](eccc-wmo-aviation-capture-receipt.json).
Raw artifacts, every response header, directory receipts, exact native
inventories, and exact transport-completion records remain outside Git at
`/private/tmp/astraeus-eccc-wmo-aviation-capture-20260906T0730Z`. The capture
retained 32,662-byte CYYT TAF and 4,182-byte CZQX SIGMET bulletin XML plus all
three 7,809-byte `FDCN01/02/03` documents. XML inventory accounts for every
element and attribute QName occurrence. Each FDCN inventory accounts for all
229 nonblank lines and preserves the native YYT and two-line `WPM 47N 49W`
selections. All five raw hashes match the retained artifacts. Both acquisition
runs state `complete: false`, source QC unknown, and `operational: false`.

There is deliberately no API readback claim: no approved delivery contract or
registered adapter exists for these native products. A test-only API route
would not prove an authorized product boundary.
