# OVATION selected-time demand DQC - Issue #236

Status: implementation evidence, non-normative.  This document does not mark
any specification, source, or product operational, accepted, verified, or
superseded.

## Scope and governing contracts

The owner-selected delivery architecture is selected timestamp -> finite
source-local cache -> one canonical current request on miss -> native
normalization -> API/map response. The slice is limited to the existing
`noaa-swpc-ovation` raster. It replaces its application delivery path; it does
not schedule ingestion, retain an archive, prefetch a horizon, or add a run
identity. Governing references: GOV-SPEC-004, GOV-SPEC-006,
`timestamp-demand-query-cache`, and the existing experimental
`space-weather-aurora-evidence` meaning contract. Implementation delta:
`experiments/st-johns-weather-map/openspec/changes/ovation-demand-query`.

## Source and native interpretation

Official public endpoint: `https://services.swpc.noaa.gov/json/ovation_aurora_latest.json`.
The current document has `Observation Time`, `Forecast Time`, and native
`[longitude, latitude, probability]` coordinates. The implementation preserves
the existing Atlantic context crop (40..55 N, -70..-40 W), longitude wrap,
percent units, zero cells, missing cells, nearest-neighbour rendering, and
model-nowcast disclosure. It preserves the existing one-native-interval
selection helper semantics: only a selected instant within 600 seconds of
payload Forecast Time is answerable. It makes no claim about producer run,
forecast skill, or a changed observation-to-forecast horizon.

A direct public eligibility response observed on 2026-09-07 was HTTP 200,
921,547 bytes, SHA-256
`8fa5aaf7071791af82177149b9f2609874387ad70f4067ed5fa5d4e07239a96d`, with
`Cache-Control: max-age=60`. Its raw body was deliberately not retained and is
not used as an oracle. Any final production capture must be made through the
production service once, with final-byte receipt and body retained outside Git.

## Bounded behavior and verification

One canonical request has a 1 MiB streamed body cap. The subprocess decoder
has explicit process/output limits and rejects unexpected shape, ambiguous
cells, invalid ranges, or an empty crop. The response retains no raw
body. It retains one normalized entry under 256 KiB and no more than 8 KiB of
selected freshness/identity headers. Completion time is sampled immediately
after the final byte. Cache freshness requires provider finite `max-age`; after
expiry a failed refresh drops cells, returns unavailable, and exposes only the
expired digest/expiry plus `values_withheld`. Successful raster responses carry a
bounded JSON `X-Weather-Acquisition` receipt containing canonical/effective URL,
safe request and retained response headers, final-byte completion, body byte
count/digest, and expiry.

Deterministic fixed fixtures cover crop equivalence, zero/missing values,
shape rejection, exact 600-second selection, coalescing, body/metadata caps,
final-byte receipt, expiry failure, cache receipt disclosure, layer-list
no-fetch, API failure status, headers, and native-cell map rendering. No raw
provider response is committed.
