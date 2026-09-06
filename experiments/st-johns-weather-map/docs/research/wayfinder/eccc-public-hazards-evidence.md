# ECCC public hazards bounded evidence

Captured 2026-09-06T01:25:34Z through 2026-09-06T01:30:02Z from official ECCC HTTPS services. Raw responses were
kept only in `/tmp/eccc137-*` for review and are not committed.

| Request | Bytes | SHA-256 | Result |
| --- | ---: | --- | --- |
| OGC collections inventory | 321670 | `0cc5645f14fae4b87cfa2487b8855e3b887b889bdf05dea81dcab398cd302440` | Exact thunderstorm, weather-alert and four hurricane collection IDs present |
| `weather-alerts`, Avalon evidence box, limit 10 | 13801 | `dcd1a684068b9dbeff4616087a4cfefc14ceecdc749873373fc5ce72c7f5bdb7` | 4 matched/returned |
| `thunderstorm_outlook`, Avalon evidence box, limit 10 | 868 | `16b0306cf576eafb4111cfc7041f6dde7d699ba3acca0ee9d812f37edc94e6ca` | Valid observed-empty collection |
| hurricane cyclone/track/error-cone/wind-radii, Avalon evidence box | 887/877/902/902 | `0c4522cb0d7bd0ddfd59c909a9d5f269aca2f4b1d4556b45432e3ec03579963f` / `aeff330b9a820ccb1c3108ca9a098fc79a2b59595f59702e7e7e6ef678b8befd` / `f401aaf851e0bf5b42c28b824479596de7ab67b6a465239060aa7d75865891b0` / `73ab2afa2ea13299e2e8395f963a0f9afb86086a6583ed6f81b2c13e84f1e4b5` | Four valid observed-empty collections |

The corrected local replay at 2026-09-06T04:17:17Z reopened the retained raw
responses without another network capture. It wrote an 868-byte thunderstorm
artifact (`5996a7d57febce62b2699e991d41fa12d13afa7e453916c6f677b60ee56e7288`)
and four hurricane artifacts: cyclone 887 bytes
(`4bbf7224063a1ac3e876f61e371a1bccbc34c09a0c4e39d2bdc2fbfe806436fe`),
track 877 bytes
(`77e9d341022e4197427d1b083366fd089c3908c330cfaf7866d597fcc111fc9b`),
error cone 902 bytes
(`9d601059632d3bbf28b44478b46b5171123d673655aab446a869dbfc5fb6c035`),
and wind radii 902 bytes
(`bdf24355679a3c0f0f66f343aec76d48e0f640d886a958978a08a18cba26a347`).
All five were structurally valid and `observed-empty`, and had locally
recomputed SHA-256 digests. The corrected replay retains `run_time: null`, no
valid times, the exact requested window, and its actual retrieval timestamp.
Because no owner-approved canonical hazard manifest exists, the manifest-owned
verdict is `complete: false` with `manifest_unresolved`; the API has no
published frame and invents no source time.

After review identified that the original scratch capture had not retained
response headers or per-request completion times, a new bounded capture ran
from 2026-09-06T04:23:00.035156Z through 2026-09-06T04:23:02.115415Z. It made
exactly five requests, each capped at 8,388,608 bytes (41,943,040-byte declared
aggregate ceiling). The full raw bodies, selected headers, artifacts and JSON
receipt remain together in `/tmp/eccc137-review-dc78dd9/`.

| Collection | Body bytes | Body SHA-256 | Completed UTC | Response headers |
| --- | ---: | --- | --- | --- |
| `thunderstorm_outlook` | 892 | `6a125e265984bc2916d30d48c721bb2ed621adec86868118f02e59fec2c8dc6a` | `2026-09-06T04:23:00.277549Z` | `content-type: application/json`; `date: Sun, 06 Sep 2026 04:23:00 GMT` |
| `hurricanes-cyclone-realtime` | 911 | `56e80a0cd0ffe9303ec9713115373aae6a98b1d548b9710512734f70e95bd178` | `2026-09-06T04:23:00.609152Z` | `content-type: application/json`; `date: Sun, 06 Sep 2026 04:23:00 GMT` |
| `hurricanes-track-realtime` | 901 | `40941ee27cafef7aa6530b6261a5cbc6cc90602f80be2370a8ccfe3ff39b5fbe` | `2026-09-06T04:23:01.106504Z` | `content-type: application/json`; `date: Sun, 06 Sep 2026 04:23:01 GMT` |
| `hurricanes-error_cone-realtime` | 926 | `a4b374b9b71342bb921d858d4277494a5fcbcc563254fe9558bca3d3445b0f42` | `2026-09-06T04:23:01.611670Z` | `content-type: application/json`; `date: Sun, 06 Sep 2026 04:23:01 GMT` |
| `hurricanes-wind_radii-realtime` | 926 | `f32aeba2faeecc526e2baf18a61b6ce24833fc54824d515f07eb421e51e8566c` | `2026-09-06T04:23:02.115415Z` | `content-type: application/json`; `date: Sun, 06 Sep 2026 04:23:02 GMT` |

Each receipt carries the full request URL, including the evidence-box `bbox`,
`limit=1000`, and `f=json` query. The candidate retains the receipt unchanged;
artifact provenance copies its collection's receipt, and the run retrieval time
is the latest completion time across its required collection set.

The existing CAP adapter live smoke resolved provider run
`eccc-cap-alerts-20260906T033001Z`, queried its single bounded Avalon box, and
retrieved one distinct alert in force. Validation passed all declared fields.
The normalized count artifact was 4,297 bytes with SHA-256
`2673f51ffcc0f4a99d7b570acb40c02f72c452825cc1a7fb76dbc6f9b39ada2d`;
the verbatim feature artifact was 3,287 bytes with SHA-256
`21168e2fe369fa8db47323f1563c210b4c708a36da5c998127913b09ddf4ad11`.

Official documentation identifies thunderstorm outlook GeoJSON as experimental
and amendment-bearing, hurricane prediction as four active structured layers
plus the response zone, and SCRIBE as hourly 12-hour integrated-nowcasting
matrices. The current SCRIBE directory contains 224-225 KiB `.Z` files, but no
matrix field schema was pinned in this task, so no values are decoded or served.

No registry status, scheduling, science mapping, or operational claim changes.
