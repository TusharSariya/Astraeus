# Experimental Holyrood CASHR radar acquisition

## Scope

Acquire only the official MSC Datamart per-site CASHR DPQPE Rain and Snow GIF
products through the documented HTTPS directory. Preserve the images and their
retrieval receipts as nonpublishable experimental artifacts.

The adapter does not map GIF palette indices to precipitation values, treat
DPQPE as a raw radar moment, publish a layer or catalogue field, register a
source, or change `operational: false`.

The official path describes DPQPE as a lowest-sweep dual-polarization-processed
precipitation estimate. It does not expose independent dual-polarization
moments/classes or raw volumes. Those remain unsupported. The separately named
`-Contingency` products are composites and are excluded.

Spec-Impact: experiment; no normative status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
