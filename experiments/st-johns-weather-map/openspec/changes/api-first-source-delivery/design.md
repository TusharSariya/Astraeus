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
Legacy Series selectors omit product/variant/level; explicit selectors are
validated against declared implemented paths before provider work. Actual
reading identity remains alongside unchanged EvidenceField provenance.

`scripts/generate_source_contract.py` emits the affected OpenAPI routes and
fixed fixture responses from the actual Pydantic/API models. A pinned
openapi-typescript development dependency generates the client definitions.
Backend and frontend tests consume the same fixture JSON. Generated material is
checked for drift; live captures remain outside Git.
