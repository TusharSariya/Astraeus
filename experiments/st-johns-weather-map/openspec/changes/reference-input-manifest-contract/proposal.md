# Reference-input manifest and publication contract

## Why

`RunManifest` is intentionally defined for spatial evidence inside the sliding weather window. Earth-orientation tables, leap-second tables, and versioned kernels instead carry global reference epochs, coverage or expiry intervals, and scientific-use constraints. Treating them as weather runs either invents geography and window semantics or bypasses the accepted validator.

## Proposed behavior

Introduce a separate `ReferenceInputManifest` and validation result for retrieved, non-display reference resources. Structural validation may make a resource publishable while scientific suitability remains `unknown` until an accepted consumer profile names its required version, time coverage, frame, and accuracy.

Publish a declared resource group atomically through the existing immutable storage transaction. Route reads through a dedicated reference-input resource endpoint; exclude these artifacts from `/point`, `/layers`, `/timeline`, consensus, and nearest-time sampling.

Spec-Impact: draft requirement change. No implementation or normative status transition is included.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
