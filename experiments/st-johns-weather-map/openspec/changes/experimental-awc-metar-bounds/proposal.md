# Experimental AWC METAR allocation bounds

Add complete-operation admission and enforced decode/output limits to the registered CYYT AWC METAR/SPECI source. Preserve the accepted response fields, 24-hour evidence window, native report identity, manifest quality, units, provenance, and HTTP shape. This is experimental implementation and makes no normative transition.

Owning experiment contracts:

- `artifact-ingestion`: discovery remains separate from retrieval; completeness and QC are computed; every step is inside the evidence window; upstream access is bounded.
- `evidence-window-timeline`: the same inclusive `now-3h` through `now+24h` window bounds ingestion and HTTP requests.
- `cloud-and-fog-evidence` / `artifact-ingestion`: all six native cloud slots and the three present-weather flags preserve their accepted units, masks, order, and raw group provenance.
- `point-evidence-sampling`: stored cells remain unmodified, missing values remain null with provenance, and AWC observations retain their own source identity beside the selected model.
- `observations-strata-satellite` / `point-evidence-sampling`: the existing model-plus-observations HTTP boundary remains unchanged.

Mapped verification is `test_adapter_awc.py` for accepted field, unit, QC and provenance behavior; `test_awc_metar_bounds.py` for all-row/window/admission behavior; the retained raw-to-artifact proof for every value, mask and unit; and the real-store point-route replay for complete HTTP key and derivation coverage.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
