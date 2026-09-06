# Reference-input manifest and publication contract

## Why

`RunManifest` is intentionally defined for spatial evidence inside the sliding weather window. Earth-orientation tables, leap-second tables, and versioned kernels instead carry global reference epochs, coverage or expiry intervals, and scientific-use constraints. Treating them as weather runs either invents geography and window semantics or bypasses the accepted validator.

## Proposed behavior

Introduce a separate `ReferenceInputManifest` and validation result for retrieved, non-display reference resources. A structurally valid resource with scientific status `unknown` may publish only as an experimental immutable artifact on the dedicated reference route. Every operational or scientific consumer remains blocked until an accepted consumer profile names its required version, time coverage, frame, accuracy, and prediction eligibility.

Publish required companions as one atomic revision group through the existing immutable storage transaction. Route exactly one current revision through a dedicated reference-input resource endpoint; exclude these artifacts from `/point`, `/layers`, `/timeline`, consensus, nearest-time sampling, and every science path. Reserve each source-specific measured acquisition bound before retrieval and keep all retained reference inputs within one 64 MiB aggregate sub-budget, while retaining at most eight revisions per source under the supersession and expiry rules in the design.

Spec-Impact: draft requirement change. No implementation or normative status transition is included.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
