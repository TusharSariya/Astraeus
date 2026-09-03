# One registered verdict entry with profile-declared grading curves, cached in the store

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
flagged on the row, never averaged. Verdicts are computed on request and persisted in a Postgres
cache table keyed by profile, focus, instant and override record, each row naming the artifact
revisions it read and served only while all of them are current; they are not artifacts (no
manifest, not listed under `/layers`) because they have no layer, run or legend, and they purge
with the retention window. An in-memory-only cache was rejected because the owner refreshes the
app by rebooting and wants site verdicts to survive it.
