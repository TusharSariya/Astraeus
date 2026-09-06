# ECCC local native-product bounded evidence

Non-normative evidence for issue #116. Full raw bodies, headers and receipts remain in `/tmp/eccc116-capture/`; no provider body is committed. The primary source paths inspected were the [partner SWOB hierarchy](https://dd.weather.gc.ca/today/observations/swob-ml/partners/), the [NL Citypage hierarchy](https://dd.weather.gc.ca/today/citypage_weather/NL/), and the [MetNotes hierarchy](https://dd.weather.gc.ca/today/metnotes/).

On 2026-09-06 the official partner hierarchy advertised 12 NL Water and 22 NL Fire Weather station directories. The six previously established Avalon stations were acquired through the experimental adapter: NL Water `NLENCL0001`, `NLENCL0013`, `NLENCL0015` and NL Fire Weather `011`, `014`, `015`. Their observation instants were 02:30Z and 05:00Z. Immutable XML sizes/digests were respectively 4,827 `b5ee66c...`, 5,330 `f7b9c42...`, 6,282 `854bb6c...`, 6,110 `17a247b...`, 6,113 `89f5b50...`, and 6,124 bytes `8ccdc67...`. Each artifact digest equals its HTTP body digest. Native inventories contain 50, 56, 72, 75, 75 and 75 named/leaf dispositions and retain missing-value presence plus native qualifiers. Embedded provincial attribution says all rights reserved, so no raw bytes are redistributed and publication remains prohibited.

The official Citypage hierarchy yielded St. John's English site `s0000280`, issue `2026-09-06T05:24:48.467Z`: 36,411 bytes, SHA-256 `5642cca91c04442612d79dc23ece818a97e94689a06e87186692c381574b7d98`. Its 562-row inventory records deterministic structural paths and preserves native units, periods, languages, condition/index codes, and other structural attributes without assigning scientific meaning. It maps no element to a canonical field without a contract.

The official MetNotes directory returned a valid empty listing at `2026-09-06T05:33:29.506617Z`. The experiment issued no payload request. Official documentation describes future GeoJSON filenames and temporal properties, but an absent body cannot establish complete payload bounds or a live schema.

The actual HTTP document receipts record completion through `2026-09-06T05:33:29.322413Z`; the MetNotes listing completed at `2026-09-06T05:33:29.506617Z`. After the inventory and transport-completion paths were refined, a labeled local fetch replay at `2026-09-06T05:51:35.296985Z` rebuilt artifacts from the retained immutable document bodies. It made no network request, did not replay discovery listings, and used explicitly reconstructed candidates. `/tmp/eccc116-capture/final-replay-proof.json` shows that all seven artifacts retain their original HTTP completion timestamps, byte counts, and body hashes and remain incomplete with source QC unknown.

The actual adapter run returned six partner artifacts and one Citypage artifact, all `complete: false`, structurally suspect only because `manifest_unresolved`, source QC unknown and `operational: false`. No normal Astraeus API route accepts these native XML artifacts; local raw-to-artifact readback is the truthful proof boundary. This is acquisition evidence only and neither accepts the provincial rights terms nor permits raw-body redistribution.

## Complete current NL partner station disposition

All 34 current NL Water/Fire Weather station directories were opened under bounded requests and one latest XML per directory supplied coordinates. Selection does not imply completion of the wider partner family.

| Partner directory | Provider station | Name | Latitude | Longitude | Disposition |
| --- | --- | --- | ---: | ---: | --- |
| nl-firewx-001 | 001 | Main Brook | 51.121364 | -56.36245 | geographically excluded from the six-station Avalon set |
| nl-firewx-002 | 002 | Spring Tilt Rd | 50.384233 | -57.315761 | geographically excluded from the six-station Avalon set |
| nl-firewx-003 | 003 | Jack Ladder | 49.348778 | -57.494278 | geographically excluded from the six-station Avalon set |
| nl-firewx-004 | 004 | Camp 185 | 48.637722 | -58.18625 | geographically excluded from the six-station Avalon set |
| nl-firewx-005 | 005 | Mountainview | 47.962528 | -58.957917 | geographically excluded from the six-station Avalon set |
| nl-firewx-006 | 006 | Sitting Horse | 49.646861 | -56.411139 | geographically excluded from the six-station Avalon set |
| nl-firewx-007 | 007 | Red Indian Lake | 48.836167 | -56.548639 | geographically excluded from the six-station Avalon set |
| nl-firewx-008 | 008 | Portage Lake | 48.444667 | -57.441806 | geographically excluded from the six-station Avalon set |
| nl-firewx-009 | 009 | Rattling Brook | 49.055167 | -55.311194 | geographically excluded from the six-station Avalon set |
| nl-firewx-010 | 010 | S of Berry Hill Pond | 48.292861 | -55.468667 | geographically excluded from the six-station Avalon set |
| nl-firewx-011 | 011 | Winterland | 47.131778 | -55.32875 | selected |
| nl-firewx-012 | 012 | Gander | 48.944111 | -54.557 | geographically excluded from the six-station Avalon set |
| nl-firewx-013 | 013 | Harcourt | 48.241972 | -53.876694 | geographically excluded from the six-station Avalon set |
| nl-firewx-014 | 014 | Salmonier | 47.234064 | -53.320153 | selected |
| nl-firewx-015 | 015 | New Harbour Barrens | 47.581528 | -53.335194 | selected |
| nl-firewx-016 | 016 | Moose Head Lake | 52.992889 | -66.704306 | geographically excluded from the six-station Avalon set |
| nl-firewx-017 | 017 | Cashe River | 53.261194 | -62.442639 | geographically excluded from the six-station Avalon set |
| nl-firewx-018 | 018 | Grand Lake | 53.600806 | -60.82725 | geographically excluded from the six-station Avalon set |
| nl-firewx-019 | 019 | Paradise River | 53.4255 | -57.2355 | geographically excluded from the six-station Avalon set |
| nl-firewx-020 | 020 | Port Hope Simpson | 52.614056 | -56.429556 | geographically excluded from the six-station Avalon set |
| nl-firewx-022 | 022 | Kenamu River | 52.86423 | -60.15837 | geographically excluded from the six-station Avalon set |
| nl-firewx-023 | 023 | Churchill Falls | 53.45214 | -63.53204 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0001 | NLENCL0001 | Pippy Park in St. Johns | 47.58036 | -52.73936 | selected |
| nl-water-nlencl0002 | NLENCL0002 | Exploits River at Badger east of Stadium | 48.975 | -56.03472 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0003 | NLENCL0003 | Humber River at Humber Village Bridge | 49.98277 | -57.76055 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0005 | NLENCL0005 | Sandy Lake near Birchy Narrows (Camp 55) | 49.27444 | -56.85166 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0006 | NLENCL0006 | Muskrat Falls MET | 53.24333 | -60.75833 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0008 | NLENCL0008 | TLH between Churchill Falls and Lab City | 53.35972 | -65.56138 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0009 | NLENCL0009 | Metchin River near TLH | 53.43611 | -62.23361 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0010 | NLENCL0010 | Exploits below Noel Paul's Brook MET | 48.84467 | -56.26941 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0011 | NLENCL0011 | Mud Lake Road MET | 53.33525 | -60.18986 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0013 | NLENCL0013 | Vale LH2 | 47.430339 | -53.820658 | selected |
| nl-water-nlencl0014 | NLENCL0014 | Marathon Gold | 48.346044 | -57.152025 | geographically excluded from the six-station Avalon set |
| nl-water-nlencl0015 | NLENCL0015 | Conception Bay South | 47.483928 | -53.016842 | selected |
