## Shared foundation and source delivery
- [x] Generate and verify Pydantic/OpenAPI/TypeScript contract and shared fixture.
- [x] Prove GFS and AQHI descriptor/point seam and native GFS Series consumption.
- [x] Integrate strict selected-model AQHI companions with typed failures.
- [x] Integrate generic frontend selectors and safe configuration presentation.
- [x] Review and integrate completed source worker commits serially.
- [x] Record live, fixture, configuration, compute and terms states in handoff.
- [ ] Run focused source/contract/API/web checks, generated drift check, strict
      OpenSpec validation and `uv run --project tools/specs python tools/specs/specctl.py validate`.

Ownership: root owns shared source models, dispatch, routes, generated contracts
and integration documentation. Source workers own source-specific modules and
tests. The frontend worker owns UI and client normalization/tests. No worker
edits another's paths; the root performs a separate review before integration.

September 7 second restart: focused assembled checkpoint checks passed; full
assembled regression, latest CAMS browser proof and broader source completion
remain. See `docs/handoffs/api-first-restart-20260907.md` at repository root.
