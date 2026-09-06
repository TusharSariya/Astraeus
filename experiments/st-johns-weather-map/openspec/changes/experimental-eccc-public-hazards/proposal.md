# Experimental ECCC public hazards acquisition

## Scope

Add isolated, unregistered adapters for the current ECCC OGC API structured
thunderstorm outlook and Canadian Hurricane Centre collections. Preserve every
GeoJSON geometry and property verbatim, enumerate every property in the live
collection schemas, bound each response to 8 MiB, and distinguish an active
empty collection from failed retrieval.

The existing `eccc-cap-alerts` adapter remains the selected CAP path. SCRIBE
nowcasting matrices remain unsupported: the hourly public compressed matrix is
live, but field interpretation waits for a pinned published matrix schema.

No adapter is registered or scheduled, no source ceiling changes, and every
artifact remains `operational: false`.

Spec-Impact: experiment; no normative status transition.
Spec-Refs: GOV-SPEC-001, GOV-SPEC-002, GOV-SPEC-004, GOV-SPEC-005, GOV-SPEC-006
