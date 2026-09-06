# ECCC public hazards bounded evidence

Captured 2026-09-06T01:25:34Z through 2026-09-06T01:30:02Z from official ECCC HTTPS services. Raw responses were
kept only in `/tmp/eccc137-*` for review and are not committed.

| Request | Bytes | SHA-256 | Result |
| --- | ---: | --- | --- |
| OGC collections inventory | 321670 | `0cc5645f14fae4b87cfa2487b8855e3b887b889bdf05dea81dcab398cd302440` | Exact thunderstorm, weather-alert and four hurricane collection IDs present |
| `weather-alerts`, Avalon evidence box, limit 10 | 13801 | `dcd1a684068b9dbeff4616087a4cfefc14ceecdc749873373fc5ce72c7f5bdb7` | 4 matched/returned |
| `thunderstorm_outlook`, Avalon evidence box, limit 10 | 868 | `16b0306cf576eafb4111cfc7041f6dde7d699ba3acca0ee9d812f37edc94e6ca` | Valid observed-empty collection |
| hurricane cyclone/track/error-cone/wind-radii, Avalon evidence box | 887/877/902/902 | `0c4522cb0d7bd0ddfd59c909a9d5f269aca2f4b1d4556b45432e3ec03579963f` / `aeff330b9a820ccb1c3108ca9a098fc79a2b59595f59702e7e7e6ef678b8befd` / `f401aaf851e0bf5b42c28b824479596de7ab67b6a465239060aa7d75865891b0` / `73ab2afa2ea13299e2e8395f963a0f9afb86086a6583ed6f81b2c13e84f1e4b5` | Four valid observed-empty collections |

The adapter live smoke at 2026-09-06T03:59:49Z reopened a 892-byte thunderstorm
artifact (`fa8f5790237a263dd6171a39edd05b0e947e5d4af2c02a15abb0e4d639897ad9`)
and four hurricane artifacts: cyclone 911 bytes
(`672e1dac26dc75845b95f27489c01600a3117646f783a297a465909d4999e78e`),
track 901 bytes
(`50631627b8e3f9f1753af6ca3d613e1c028ddeb3f6dc9a06af57cfefa98f2bbd`),
error cone 926 bytes
(`c47d6b08a29b3c6af88568b57fda70780e5c5169ed0c21cce3f58a1a91f45f14`),
and wind radii 926 bytes
(`2a51dbbd7d7447cb883bcafc2c3241e1cadea7a68f77f0b59e207ce7032cc122`).
All five were complete, QC-passed, `observed-empty`, and had locally recomputed
SHA-256 digests. Fixture-backed live-store HTTP readback preserved the feature
properties, named `eccc-thunderstorm-outlooks`, returned `data_mode: live`, and
kept `operational: false`.

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
