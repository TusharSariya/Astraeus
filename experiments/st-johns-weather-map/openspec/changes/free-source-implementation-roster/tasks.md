# Tasks

## 1. Exhaustive roster

- [x] 1.1 Import and retain all 118 audited registry IDs exactly once.
  Verify: `python3 tools/specs/build_free_source_roster.py` reports 118.
- [x] 1.2 Retain all 136 appendix table rows and 34 narrative/bullet groups,
  including rejected, dead, out-of-box, tool/method and paid-deferred paths.
  Verify: the roster validator reports 170 research rows and 288 total rows.
- [x] 1.3 Attach implementation state, exact registry field declarations,
  free-access disposition, prior decision, account/permission, geography,
  target ticket, contract status and five-part completion evidence to every row.
  Verify: the roster validator rejects a missing required column or a true
  `operational` value.
- [x] 1.4 Route IERS/time, supplementary kernels, native per-site radar,
  radiosonde archives, MET Norway products, optical aurora archives and Globe
  at Night/SQM explicitly.
  Verify: targeted JSON queries return a named task for every item.

## 2. Owner/specification gates

- [ ] 2.1 Obtain owner decisions for each selected source-specific
  product/access/field contract before implementation. Research and this roster
  do not authorize behavior.
- [ ] 2.2 Reconcile any selected contract with accepted V1 requirements and
  keep registry/API state below operational until the full evidence gate passes.
- [ ] 2.3 Preserve the root readiness-image clarification and reconcile the
  optional-model rented-GPU task as deferred under the free-only boundary.

## 3. Execution-map structure

- [ ] 3.1 Create the bounded family children listed in
  `docs/research/free-source-implementation-roster.md` and connect their native
  blockers to the final coverage ticket.
- [ ] 3.2 Execute only eligible rows after contract approval. A completion must
  link fixture, upstream retrieval, artifact validation, Astraeus API readback,
  and failure/provenance evidence for every relevant field.
- [ ] 3.3 Resolve blocked/excluded rows with their recorded disposition rather
  than a fabricated live check; keep them visible in final reconciliation.

## 4. Gate

- [x] 4.1 Run roster coverage validation, strict validation for this OpenSpec
  change, repository specification validation and `git diff --check`.

