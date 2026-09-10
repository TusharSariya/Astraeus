# Reuse and exact product plan

Reuse `ingest/adapters/ecmwf_opendata.py`: bounded advertised listing discovery,
JSON-lines sidecar validation, strict206/Content-Range, per-member decoding and
coordinate equality. Reuse `ingest/experimental/native_deterministic.py` field
mappings and `api/weather_api/gfs_query.py` demand/cache orchestration. Fixtures
already cover refused IFS and ensemble assembly; replace only the authorized
refusal tests and extend production-path fixed-fixture coverage.

The official [ecmwf-opendata client](https://github.com/ecmwf/ecmwf-opendata)
supports model-specific requests and selected-field retrieval. It is not an
existing locked API dependency or imported client here. Evaluate its maintained
request selection within the bounded receipt/transport seam before adding a
dependency; reuse the tested local mechanism if it cannot expose required
range/final-byte hooks. Do not write another generic ECMWF downloader. Explicit
model, resolution, stream, type, date and time avoid SDK inference/implicit
latest; never use its whole-file download method for a point field request.

| Public identity | Producer request shape | Native ensemble identity |
|---|---|---|
| ecmwf-ifs | ifs / 0p25 / oper:fc | deterministic, no member |
| ecmwf-ens | ifs / 0p25 / enfo:ef plus approved control mapping | members1..50 and designated0 |
| ecmwf-aifs-single | aifs-single / 0p25 / oper:fc | deterministic, no member |
| ecmwf-aifs-ens | aifs-ens / 0p25 / enfo:pf and enfo:cf | members1..50 and control0 |

Verify actually advertised object names rather than synthesizing availability.
[ECMWF confirmed IFS50r1 and both AIFS v2 on12May2026](https://forum.ecmwf.int/t/confirmation-ifs-cycle-50r1-and-aifs-v2-joint-implementation-on-12-may-2026/14937).
A feed path alone does not prove model version: pin producer metadata/version
basis in provenance. Distributed0p25 is not native IFS9km or AIFS31km output.

First fields:2t/2d (K,2m),msl (Pa,mean sea level),tcc (fraction,entire atmosphere,
instantaneous). Reuse accepted catalogue normalization while preserving original
units. Do not relabel averages/accumulations as instantaneous cloud. Wind
components, pressure profiles, precipitation intervals and remaining fields stay
tracked and cannot be inferred from this first slice.

Latest means newest advertised run containing exact selected validtime/lead,
not nearest step. Pinnedrun failure does not choose another run. Do not assume
00/12-only or equal horizons for00/06/12/18; bounded discovery validates current
per-product cycle/lead coverage. No full-horizon prefetch.

Initial IFS ENS control mapping is restricted to the requested subset of the
six previously evidenced Cycle50r1 fields:tcc,2t,2d,10u,10v,msl. Retain original
oper:fc URL/stream/type plus explicit producer control mapping. Other deterministic
records cannot become members. Missing0 leaves the family partial.
