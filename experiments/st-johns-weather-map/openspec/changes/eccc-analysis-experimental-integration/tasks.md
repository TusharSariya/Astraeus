# Tasks

## 1. Contracts

- [x] 1.1 Declare one selected field/time/quality contract for each numeric WCS
      product, with exact coverage ids and `operational: false`.
- [x] 1.2 Preserve unresolved and superseded public paths as explicit absence,
      without registering or scheduling them.

## 2. Retrieval and artifacts

- [x] 2.1 Extend WCS grid routing with product-specific source identities.
- [x] 2.2 Provide raw-response artifacts and raw/normalized hashes and counts
      in the experimental transport, with fixture integrity checks.
- [ ] 2.3 Retain reproducible live raw and normalized artifacts plus actual
      reader/HTTP proofs; the existing two JSON summaries are insufficient.

## 3. Verification

- [x] 3.1 Test field selection, cadence, product grid identity, standalone
      FireWork exclusion, and unknown-product failure.
- [x] 3.2 Run focused tests, strict changed OpenSpec, specification validation,
      and whitespace validation.
- [ ] 3.3 Complete all selected product/field evidence in the five linked
      acquisition children; metadata and declarations do not count as data.

## 4. Owner gates

- [ ] 4.1 Obtain owner acceptance of each source contract before production
      registry, scheduler, API capability, or normative status changes.

## Issue #133 native RAQDPS/RDAQA acquisition

- [x] Enumerate all selected live RAQDPS and RDAQA WCS fields, units, levels, phases, run/valid-time identity, and unsupported catalogue mappings.
- [x] Preserve actual HTTP completion time, response headers, raw hashes, geometry, and units in each isolated artifact.
- [x] Prove every selected raw grid against normalized storage and test-harness HTTP serialization; prove source-scoped raw fields remain absent from the normal point route.
- [ ] Owner accepts canonical PM10-column, gas mole-fraction, smoke-attribution, time-average, and RDAQA analysis-phase field contracts before a full RunManifest can publish.
- [ ] Only after acceptance: add the canonical mappings, validate the complete product with `validate_run`, and consider registration separately.

## Issue #134 HRDPA/HREPA precipitation analyses

- [x] Reuse the exact GeoMet WCS coverage ids, grid contracts, bounded numeric
      transport and retained HRDPA receipt already present in this change.
- [x] Define the proposed exact-time HRDPA six-hour accumulation behavior,
      including no rate conversion, neighbour substitution, run or lead.
- [x] Record PCT25/PCT75 as unproven HREPA candidate identifiers, require a
      bounded provider receipt before serving them, and prohibit inferred
      distribution/member/probability claims.
- [x] Specify the finite canonical demand cache, zero-request fresh hit,
      coalescing, expiry withholding and bounded metadata-only failure state.
- [ ] Retain one bounded HREPA provider receipt and fixed fixture that prove the
      two advertised identities, percentile ranks, literal intervals, units,
      geometry, masks and shared selected time; metadata declarations alone are
      insufficient.
- [ ] Identify exact provider contracts for HREPA precipitation analysis,
      uncertainty, confidence, probabilities, and 24 perturbed members plus
      control; keep each residual explicit until then.
- [ ] Owner accepts the #134 source/time/field/cache requirements before any
      public API mapping, production registration or implementation begins.
