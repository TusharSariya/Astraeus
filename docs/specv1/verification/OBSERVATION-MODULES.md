---
id: SYS-MODULE-VERIFICATION
title: Observation Module Verification Matrix
type: verification
status: proposed
owners:
  - "@TusharSariya"
profiles:
  - event_day_preview
  - v1_web
  - v1_native
created: 2026-08-11
updated: 2026-08-11
depends_on:
  - RFC-005
  - RFC-001
supersedes: []
---

# Observation module verification matrix

| Case | Requirements | Evidence and pass condition |
|---|---|---|
| SYS-SUBJ-001-T01 | SYS-SUBJ-001 | Persistent-target request fixture omits occurrence ID and normalizes it to null; scheduled-occurrence fixture requires one; class and identity survive revision, result, layers, and snapshot |
| SYS-MOD-001-T01 | SYS-MOD-001 | Every active registry entry has one unique module ID/major owner and resolvable science, safety, score, request, result, and verification references |
| SYS-MOD-002-T01 | SYS-MOD-002 | Registry schema accepts every declared geometry/mode/objective and rejects unknown capabilities, duplicate identities, and malformed versions |
| SYS-MOD-003-T01 | SYS-MOD-003 | Contract fixture proves common optimizer fields remain common while eclipse circumstances stay inside the typed solar-eclipse result |
| SYS-MOD-004-T01 | SYS-MOD-004 | Unknown, planned, proposed, version-mismatched, unsupported-region, and schema-mismatched requests fail before provider, route, score, or recommendation work |
| SYS-SCORE-001-T01 | SYS-SCORE-001 | Applicable missing evidence remains null/insufficient; not-applicable is explicit; comparison keys differ across module, subject, occurrence, objective, profile, or score version |
| SYS-SAFE-001-T01 | SYS-SAFE-001, PRD-SAFE-002 | Missing/incompatible module safety blocks activation; utility cannot offset a module or common safety failure; solar protection survives generic transport |
| SYS-EXT-001-T01 | SYS-EXT-001 | A synthetic new module cannot activate without accepted ownership, closed contract variants, rules, provenance, approval, and mapped verification |
| EVD-API-001-T01 | EVD-API-001 | OpenAPI exposes generic `/v1/plans`, contains no eclipse creation path or arbitrary payload, and retains capability/idempotency/error lifecycle behavior |
| EVD-REV-001-T01 | EVD-REV-001 | Revision hash changes for module, registry, subject, occurrence, profile, comparison key, or score-version change and remains stable for identical frozen inputs |

The eclipse golden tests remain mandatory. Passing this matrix establishes
protocol conformance only; it does not validate a non-eclipse module's physics.
