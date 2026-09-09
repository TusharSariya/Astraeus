## Verification mapping

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.

- [x] Catalogue identity: api/tests/test_ifs_selection.py catalogue fixtures.
- [x] Native transport and discovery: api/tests/test_ifs_selection.py.
- [x] Incremental decoding and scientific identity: api/tests/test_ifs_selection.py.
- [x] Finite jobs, receipts, cancellation and expiry: api/tests/test_ifs_selection.py.
- [x] Comparison defaults and identity: api/tests/test_forecast_comparison.py.
- [x] Map and chart native rendering: web IFS and comparison tests.
- [x] Linux default decoder with fixture transport, network disabled.
- [x] Separately labelled bounded live control/profile/member/probability/track evidence.
- [x] Generated OpenAPI/TypeScript checks and affected API/client tests.
- [x] Production build, strict OpenSpec and specctl validation.
- [x] Rebuilt local app at normal and 200 percent zoom.

Evidence: `docs/evidence/ifs-atlantic-20260909/README.md` at repository root.
The checklist records executed gates, not exhaustive implementation of every
lifecycle scenario. Additional lifecycle gates:

- [x] Integrate bounded BUFR acquisition into cancellable selection jobs.
- [x] Return selection identity before waiting on science acquisition.
- [x] Prove cross-selection cancellation recovery for coalesced record waiters.

Native fields/levels use the additive typed IFS interfaces and comparison;
legacy canonical point and WeatherNext grid routes retain their contracts.
The 200 percent check uses reflow/device-metrics emulation, not a browser-menu assertion.
