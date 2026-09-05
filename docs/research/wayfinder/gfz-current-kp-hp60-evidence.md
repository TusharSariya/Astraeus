# Current GFZ Kp and Hp60 disposition

Captured 2026-09-05 for issue 150. This is experimental evidence under issue
75, not normative authority and not a registry promotion.

| Source | Exact product and response fields | Time and units | Status semantics | Disposition |
|---|---|---|---|---|
| `gfz-kp-current` | GFZ current JSON selection, `Kp`, `datetime`, `status`, `meta` | producer instants at 3-hour cadence; Kp is dimensionless | producer tokens are retained verbatim per value; the adapter does not interpret `pre` or `def` | `catalogued`; experimental reader is not scheduler-registered |
| `gfz-hp60-current` | GFZ current JSON selection, `Hp60`, `datetime`, `meta` | producer instants at 1-hour cadence; Hp60 is dimensionless | the response declares no per-value status; provenance records `status_declared: false` | `catalogued`; experimental reader is not scheduler-registered |

Both anonymous HTTPS responses declared `meta.license: CC BY 4.0`. The readers
fail closed on another licence, missing or misaligned arrays, repeated or
unparseable instants, an empty selection, a stale newest instant, non-JSON,
HTTP failure, or the shared small-feed byte ceiling. Requests are clamped to
24 hours before retrieval. They store only a coordinate-free `valid_time`
series with planetary scope; retrieval time remains separate from producer
valid time and the newest producer instant is the provider run identifier.

The compact receipts are
[`gfz-kp-current.json`](space-weather-receipts/gfz-kp-current.json) and
[`gfz-hp60-current.json`](space-weather-receipts/gfz-hp60-current.json). Each
records the exact URL and parameters, response byte count and SHA-256, capture
time, generated artifact byte count/SHA/revision, source/run identity and the
actual HTTP API value/unit/time readback. Raw responses and generated artifacts
were held only in bounded temporary directories and were removed by the
capture path.

Historical Kp/Hp acquisition is outside this work and remains issue 94. The
existing Hp30 admission and adapter are unchanged in state. Promotion of Kp or
Hp60 requires a distinct owner admission decision; this evidence does not
provide it.
