# Tasks

- [x] Measure the complete AWC response and enumerate native keys.
- [x] Enforce received, decoded-process, artifact, and physical allocation caps.
- [x] Prove strict whole-response refusal and cleanup failure paths.
- [x] Prove raw-to-artifact-to-store-to-HTTP-to-existing-UI values and metadata.
- [x] Run full API, registry, SQL, strict OpenSpec, and specctl gates.

Verification is retained outside Git under `/private/tmp/awc-taf201-capture/`:
the 3,086-byte response and headers, the published 45,794-byte immutable
artifact, all seven half-open boundary responses, ordinary and cache-satisfied
job receipts, two-revision readability, and pinned local image digests. The
2026-09-06 final gates passed 1,887 API tests (49 platform/dependency skips),
411 web tests, 236 registry tests plus 354 subtests and four strict profiles,
all disposable-PostgreSQL invariants, strict OpenSpec validation, and specctl
with zero errors and warnings.
