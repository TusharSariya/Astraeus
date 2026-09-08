# RRFSv1.0 parallel native temperature experiment

Classification: isolated owner-requested API-first experiment for #260; proposed
source contract, no operational registration, shared point delivery or acceptance.

The official parallel NOMADS feed now exposes `2dfld.13km.na` RRFSv1.0 output.
Retain a bounded source-local native temperature reader for an explicitly pinned
run/validity while the operational and full-field admission gates remain open.
This is separate from RRFS3km regional outputs, retired prototypes and REFS.

Scope: exactly one indexed instantaneous two-metre temperature message, rotated
1127x683 native grid, K units, original bitmap, unknown producer QC; bounded
Linux decoding and source-local cache. No completeness claim for the model.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006.
