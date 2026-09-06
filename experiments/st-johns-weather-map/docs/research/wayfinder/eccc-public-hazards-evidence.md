# ECCC public hazards bounded evidence

Captured 2026-09-06 UTC from official ECCC HTTPS services. Raw responses were
kept only in `/tmp/eccc137-*` for review and are not committed.

| Request | Bytes | SHA-256 | Result |
| --- | ---: | --- | --- |
| OGC collections inventory | 321670 | `0cc5645f14fae4b87cfa2487b8855e3b887b889bdf05dea81dcab398cd302440` | Exact thunderstorm, weather-alert and four hurricane collection IDs present |
| `weather-alerts`, Avalon evidence box, limit 10 | 13801 | `dcd1a684068b9dbeff4616087a4cfefc14ceecdc749873373fc5ce72c7f5bdb7` | 4 matched/returned |
| `thunderstorm_outlook`, Avalon evidence box, limit 10 | 868 | `16b0306cf576eafb4111cfc7041f6dde7d699ba3acca0ee9d812f37edc94e6ca` | Valid observed-empty collection |
| hurricane cyclone/track/error-cone/wind-radii, Avalon evidence box | 887/877/902/902 | `0c4522cb...` / `aeff330b...` / `f401aaf8...` / `73ab2afa...` | Four valid observed-empty collections |

The adapter live smoke at 2026-09-06T03:59:49Z reopened one 892-byte
thunderstorm artifact and four 901-926-byte hurricane artifacts. All five were
complete, QC-passed, `observed-empty`, and had locally recomputed SHA-256
digests. Fixture-backed live-store HTTP readback preserved the feature
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
