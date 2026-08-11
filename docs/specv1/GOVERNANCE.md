---
id: GOV-001
title: Specification Governance
type: governance
status: accepted
owners:
  - "@TusharSariya"
profiles:
  - all
created: 2026-08-11
updated: 2026-08-11
depends_on: []
supersedes: []
---

# Specification governance

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT,
RECOMMENDED, MAY, and OPTIONAL are to be interpreted as described by BCP 14
when, and only when, they appear in all capitals.

## GOV-SPEC-001 — Specifications are authoritative

Accepted specifications define behavior. Issues and pull requests track work.
Research supports decisions but is non-normative. An implementation MUST NOT
invent, weaken, or silently reinterpret a requirement.

## GOV-SPEC-002 — Human approval controls normative status

Allowed document states are:

```text
draft -> proposed -> accepted -> implemented -> verified -> superseded
```

Only `@TusharSariya` may authorize `accepted`, `verified`, or `superseded`.
Agents MAY draft documents and evidence but MUST NOT approve their own status
transition. A transition pull request requires the `spec-status-approved`
label and an explicit owner statement.

## GOV-SPEC-003 — Requirements use stable identifiers

Prefixes are registered here:

| Prefix | Owner |
|---|---|
| `GOV` | Specification governance |
| `PRD` | Product outcomes |
| `SYS` | System architecture |
| `EVD` | Evidence, revisions, and provenance |
| `MAP` | Rendering and offline behavior |
| `OPS` | Platform and operations |
| `SITE` | Candidate generation and routing |
| `ECL26` | August 2026 eclipse feature |

Requirement headings use `PREFIX-AREA-NNN`. Verification cases append `-TNN`.
Identifiers MUST NOT be renamed, recycled, or reassigned. Superseded
requirements remain discoverable and name their replacements.

## GOV-SPEC-004 — Behavior changes are spec-traceable

A feature, fix, API change, scientific change, safety change, UX workflow
change, provider change, or deployment behavior change MUST cite accepted
requirements with `Spec-Refs` and MUST add or update mapped verification.

New features, safety/science/scoring changes, and breaking API changes require
an accepted specification pull request before implementation. A small
non-breaking clarification MAY accompany implementation when the pull request
is classified `spec-compatible-change`. A fix that restores accepted behavior
references the existing requirement without rewriting it.

Research, prose-only documentation, dependency maintenance, and chores MAY use
`Spec-Impact: none` with a concrete explanation.

## GOV-SPEC-005 — Conflicts fail closed

Safety invariants cannot be weakened. Feature specs conform to the PRD and
accepted RFCs. Executable contracts conform to their owning specification.
When sources disagree, work MUST stop for owner resolution; there is no silent
precedence rule. Draft or superseded requirements cannot authorize production
implementation.

## GOV-SPEC-006 — Verification is part of the requirement

Every accepted behavior requirement MUST map to at least one verification case
or an explicitly approved manual evidence procedure. `implemented` means code
and tests are linked. `verified` means the acceptance evidence has passed in
the declared environment; it is not inferred from code completion.

## GOV-SPEC-007 — Documents remain bounded

A feature has a small index plus only the product, science, data, safety, UX,
delivery, or verification sub-specs it needs. Cross-cutting behavior belongs in
an RFC. The validator warns above 500 lines and fails above 1,000 unless the
owner adds a documented `size_exemption` to frontmatter.

## Change workflow

1. Read the specification index and affected feature index.
2. Classify the change: conforming implementation, requirement change,
   experiment, or no-spec-impact.
3. Locate accepted requirement IDs and contracts.
4. Resolve missing or conflicting behavior before implementation.
5. Update specification first where required.
6. Implement with mapped tests and evidence.
7. Run the repository specification validator and relevant product tests.
8. Prepare a conventional commit and traceable pull request.

## Commit and pull-request format

Final squash commits use:

```text
<type>(<scope>): <imperative summary>

Spec-Refs: ECL26-GEO-001, EVD-REV-001
Verification: uv run pytest tests/geometry -q
```

Allowed types are `feat`, `fix`, `docs`, `spec`, `refactor`, `test`, `perf`,
`build`, `ci`, and `chore`. No-spec-impact work uses `Spec-Impact: none` in the
pull request. The pull request body supplies clickable spec links, release
profiles, evidence, risk, rollback, and status authorization.
