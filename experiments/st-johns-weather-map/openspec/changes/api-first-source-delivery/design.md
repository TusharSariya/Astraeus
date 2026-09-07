# Delivery seam

`SourceReader` has descriptors, point reads and optional native Series planning.
It adapts existing coordinators; those retain acquisition, authentication, native
timing, decoding, process limits and finite caches. The central Series reader
enforces its existing aggregate request/sample/byte/time/expiry bounds and never
constructs cadence. A missing planner is an explicit unsupported capability.

`source_contract.py` defines additive Pydantic identity, capability and safe
configuration models. `SourceRecord.capabilities` describes implemented read
paths independently from broader published-field inventory and actual coverage.
`SourceStatus.configuration` does not change source admission or freshness.
The optional `point_product` token connects a declared point capability to the
existing `/point?product=` selector. It is distinct from the provider product
identifier. The client uses an unambiguous declared token, with legacy mappings
retained for older catalogue responses. CAMS AOD declares point delivery only:
Open-Meteo hourly labels must never be exposed as native CAMS Series frames.

Observed read dispositions retain at most 128 source states for a fixed 300
seconds. Safe constant reasons distinguish denied access, unavailable native
runs and acquisition failures. Reading status performs no retry. Expiry falls
back to software readiness without claiming a successful acquisition. The
remaining configuration/compute states require source-specific assessment;
their presence in the schema alone is not implementation or entitlement proof.
Legacy Series selectors omit product/variant/level; explicit selectors are
validated against declared implemented paths before provider work. Actual
reading identity remains alongside unchanged EvidenceField provenance.
Selector levels use the canonical field catalogue. Reading identity additionally
keeps `native_level` from source provenance: a native artifact's grouping such
as surface or column is not silently rewritten as a physical height.

`scripts/generate_source_contract.py` emits the affected OpenAPI routes and
fixed fixture responses from the actual Pydantic/API models. A pinned
openapi-typescript development dependency generates the client definitions.
Backend and frontend tests consume the same fixture JSON. Generated material is
checked for drift; live captures remain outside Git.
