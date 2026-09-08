# GOES ACTPF shared point tasks

Status: draft. Checked items denote document preparation only.

- [x] Identify the existing categorical rule and missing shared satellite shape.
- [x] Propose an additive typed shape and exact scan-start selection for review.
- [ ] Owner decides whether to accept this proposed experiment contract.
- [ ] After approval, add typed Pydantic provenance and the source-local reader.
- [ ] Verify codes 0..5 with producer mappings, DQF/masks, exact scan boundaries,
  projection retention, real cell distance, unknown QC and zero substitution.
- [ ] Verify identity refusal before acquisition, cache expiry/refresh/coalescing,
  and all-null/unavailable cases using the existing retained capture offline.
- [ ] Root registers the shared point descriptor/dispatch and regenerates the
  OpenAPI, TypeScript and shared fixtures; verify actual API readback.
- [ ] Keep source/issue completion and production admission separately assessed.
