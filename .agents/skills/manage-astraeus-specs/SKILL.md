---
name: manage-astraeus-specs
description: Manage Astraeus specifications and traceable implementation work. Use whenever designing, planning, implementing, fixing, reviewing, or documenting behavior; changing APIs, schemas, science, safety, providers, UX, infrastructure, or release behavior; creating feature/RFC/ADR documents; or preparing Astraeus commits, issues, and pull requests.
---

# Manage Astraeus specifications

Treat `docs/specv1/README.md` as the entry point and
`docs/specv1/GOVERNANCE.md` as the normative workflow. Research is evidence,
not authority.

## Classify the work

Choose exactly one:

- **Conforming implementation:** accepted requirements already define it.
- **Requirement change:** behavior is missing, changed, contradictory, or not
  accepted.
- **Experiment:** exploratory work cannot enter a production path or claim
  conformance.
- **No spec impact:** research, prose-only docs, chores, or maintenance with no
  behavior change.

Do not use no-spec-impact to bypass an API, scientific, safety, UX, provider,
data, infrastructure, or failure-behavior change.

## Follow the workflow

1. Read the spec index and the affected feature index completely.
2. Read every owning accepted requirement, dependency, contract, rule, and
   mapped verification case needed for the task.
3. Record requirement IDs before editing code.
4. If behavior is absent, draft/conflicting, or requires an unapproved rule,
   stop implementation and request human resolution. Never choose silently.
5. For a requirement change, update and accept the specification first. New
   features, breaking APIs, science, scoring, and safety changes use a separate
   spec PR. Small non-breaking clarifications may accompany code only when the
   human marks `spec-compatible-change`.
6. Implement only the accepted behavior. Preserve units, time, provenance,
   masks, revisions, missing-data semantics, and fail-closed safety.
7. Add or update verification mapped to every affected requirement.
8. Run `uv run --project tools/specs python tools/specs/specctl.py validate`
   plus the exact product tests.
9. Prepare conventional commit and pull-request metadata with `Spec-Refs` and
   `Verification`.

## Preserve human authority

Only `@TusharSariya` can authorize `accepted`, `verified`, or `superseded`.
Never self-approve, add the approval label, invent evidence, or represent a
draft as production-ready. If a user explicitly requests a transition, record
that request and still produce the required verification/PR metadata.

## Create specifications

Use the repository templates and generator:

```text
uv run --project tools/specs python tools/specs/specctl.py new feature <slug> --prefix <PREFIX>
uv run --project tools/specs python tools/specs/specctl.py new rfc <title> --number <N>
uv run --project tools/specs python tools/specs/specctl.py new adr <title> --number <N>
```

Keep requirements atomic and testable. Use stable registered IDs. Split a
feature by product, science, data, safety, UX, delivery, or verification only
when those concerns exist. Put reusable cross-feature design in an RFC and one
architectural choice in an ADR. Do not recreate a monolith.

## Prepare Git history

Use `<type>(<scope>): <imperative summary>`. The pull request is squash-merged,
so its title/body define the final commit. Behavior changes include:

```text
Spec-Refs: ECL26-GEO-001, EVD-REV-001
Verification: <exact commands and outcomes>
```

No-spec-impact work declares `Spec-Impact: none` and explains why. Pull
requests link requirement headings, identify profiles, list evidence, describe
safety/data/API impact, and state rollback or failure behavior.

## Review another change

Reject or block when:

- a behavior-changing path lacks valid accepted references;
- code contradicts a requirement or executable contract;
- safety is treated as a score tradeoff;
- stale, missing, unknown, or failed-QC evidence becomes a favorable value;
- clients independently calculate authoritative science;
- verification is absent, mislabeled, or does not exercise the requirement;
- an agent changed normative status without explicit human authorization.
