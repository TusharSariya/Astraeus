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
