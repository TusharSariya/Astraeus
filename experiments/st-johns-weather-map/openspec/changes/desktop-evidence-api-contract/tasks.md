# Tasks

Accepted for implementation under the single owner authorization linked in
proposal.md. Tasks below are implementation obligations, not owner gates.

- [ ] 1. Implement the selected Series, cursor/change-check and finite
  selection-cache wire shapes, including limits, expiry and error semantics.
- [ ] 2. Define schema models that reuse `EvidenceField` and `Provenance`, and
  verify native timestamps, explicit absences, source/report identity and
  receipt/freshness remain visible.
- [ ] 3. Define the finite backing strategy without retained-artifact fallback
  or warehouse retention; #173 is not a prerequisite.
- [ ] 4. Specify source/field joins, imagery availability, and actual served
  raster time without changing existing layer `times` semantics.
- [ ] 5. Specify read-only site, horizon and camera records and their privacy,
  version and arbitrary-point refusal behavior.
- [ ] 6. Add mapped fixed-clock API and client contract tests; include paging, relevant/unrelated change, expiry, unreadable,
  zero, explicit absence, and no-stale-fallback cases.
- [ ] 7. Run focused API/web/OpenSpec/specctl gates and record results before
  any implementation or verified-status claim.
