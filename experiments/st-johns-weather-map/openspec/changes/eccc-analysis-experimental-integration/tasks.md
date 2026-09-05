# Tasks

## 1. Contracts

- [x] 1.1 Declare one selected field/time/quality contract for each numeric WCS
      product, with exact coverage ids and `operational: false`.
- [x] 1.2 Preserve unresolved and superseded public paths as explicit absence,
      without registering or scheduling them.

## 2. Retrieval and artifacts

- [x] 2.1 Extend WCS grid routing with product-specific source identities.
- [x] 2.2 Retain raw response bytes and record raw and normalized SHA-256,
      byte counts, finite cells, null cells, CRS, time, units, and quality.
- [x] 2.3 Retrieve bounded live RAQDPS and HRDPA examples and record evidence in
      `docs/evidence/eccc-analysis-wcs-2026-09-05.json`.

## 3. Verification

- [x] 3.1 Test field selection, cadence, product grid identity, standalone
      FireWork exclusion, and unknown-product failure.
- [x] 3.2 Run focused tests, strict changed OpenSpec, specification validation,
      and whitespace validation.

## 4. Owner gates

- [ ] 4.1 Obtain owner acceptance of each source contract before production
      registry, scheduler, API capability, or normative status changes.
