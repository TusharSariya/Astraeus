# One registered verdict entry with profile-declared grading curves and finite caching

Status: accepted (owner decision, wayfinder ticket #49, 2026-09-03)

The decision layer scores the four activity profiles with a single derivation-method registry
entry, `activity_verdict`, whose one input is the profile file itself. A per-profile entry would
give each activity a code path, which the activity-profile spec forbids, and declaring the
profile's fields as ordinary inputs would trip the registry's blending refusal (astronomy reads
two cloud-cover members from two sources) even though a verdict blends no values: the fields a
verdict read are disclosed on its criteria rows instead. Each graded criterion declares a grading
curve (step, linear, exponential or band in version 1) that maps its value to a share of its
weight lost, with every curve anchor a named threshold in the profile file, so reader overrides,
CI audit and provenance stay the mechanisms already built for thresholds; binary grading was
rejected because the owner wants each criterion tunable and researched per activity. One source
supplies each field, chosen by a per-tier source precedence in API config with any fallback
flagged on the row, never averaged. Verdicts are computed on request through existing selected-time queries with
bounded finite caching. The September 7 owner direction supersedes this ADR's
original Postgres table, persistence across reboots, poller precomputation and
warm-up requirements. The earlier persistence choice is historical; it is no
longer an implementation prerequisite. Profile anchors and staged budgets follow
#64, including band low_cap and explicit applicability; no new scientific rules
are inferred from the cache or the desktop layout.

The [accepted Activity contract](../../experiments/st-johns-weather-map/openspec/changes/desktop-evidence-api-contract/specs/activity-verdict/spec.md)
records #48/#49/#64 and references the existing single owner authorization.
