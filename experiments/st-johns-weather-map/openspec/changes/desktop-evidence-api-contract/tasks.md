# Tasks

The September 7 owner response approves the Series/refresh/run interactions and
delegates routine engineering choices as recorded in proposal.md. Remaining
capabilities retain their own acceptance boundaries under GOV-SPEC-002. This
task list does not claim the whole proposal is accepted or implemented.

- [x] 0. Record owner approval of the native Series, explicit refresh, finite
  expiry and supported run-comparison interactions, with routine implementation
  details delegated and camera visibility held separately.

- [ ] 1. Confirm the proposed Series, cursor/change-check and finite
  selection-cache wire shapes, including limits, expiry and error semantics.
- [ ] 2. Define schema models that reuse `EvidenceField` and `Provenance`, and
  verify native timestamps, explicit absences, source/report identity and
  receipt/freshness remain visible.
- [ ] 3. Define the finite backing strategy without retained-artifact fallback
  or warehouse retention; resolve any dependency on #173 separately.
- [ ] 4. Specify source/field joins, imagery availability, and actual served
  raster time without changing existing layer `times` semantics.
- [ ] 5. Specify read-only site, horizon and camera records and their privacy,
  version and arbitrary-point refusal behavior.
- [ ] 6. Add mapped fixed-clock API and client contract tests only after
  acceptance; include paging, relevant/unrelated change, expiry, unreadable,
  zero, explicit absence, and no-stale-fallback cases.
- [ ] 7. Run focused API/web/OpenSpec/specctl gates and record results before
  any implementation or verified-status claim.
