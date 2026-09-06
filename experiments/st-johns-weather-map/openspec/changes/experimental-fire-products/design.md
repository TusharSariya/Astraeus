# Design

| Access path | Native fields / disposition |
| --- | --- |
| CWFIS `hotspots_last24hrs` WFS | GeoJSON geometry and all producer properties retained verbatim; empty Avalon result is observed-empty |
| CWFIS dated hotspot CSV | Header inventory retained; values are untyped source strings pending unit/mask contract |
| CFFEPS dated CSV | Header inventory retained; values are untyped source strings pending emissions contract |
| NASA FIRMS MODIS / VIIRS | Permission-gated: official API requires MAP_KEY; no credential retrieval or request |
| RAQDPS FireWork | Superseded, excluded |
| BlueSky | Unverified machine feed/licence, excluded |

Each listing, WFS document, and CSV response has a finite streaming ceiling,
records URL, headers, byte count, SHA-256 and actual completion time, and is
stored as immutable source bytes. No decoder constructs a numeric field,
quality value, fire perimeter, emission rate, or API response. Every result is
made nonpublishable by the unresolved manifest owner gate; it remains
unregistered and `operational: false`.
