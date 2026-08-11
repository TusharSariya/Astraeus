# Astraeus agent instructions

Follow the `collaboration-principles` skill for all implementation work.

For any planning, design, implementation, fix, review, API/schema, scientific,
safety, provider, UX, infrastructure, documentation, commit, or pull-request
task, use the repository skill at
`.agents/skills/manage-astraeus-specs/SKILL.md`.

Before changing behavior:

1. Read `docs/specv1/README.md` and `docs/specv1/GOVERNANCE.md`.
2. Identify accepted requirement IDs and owning executable contracts.
3. Stop for human resolution if behavior is missing, draft, or conflicting.
4. Add mapped verification and traceable `Spec-Refs`.
5. Run `uv run --project tools/specs python tools/specs/specctl.py validate`
   before handoff.

Research under `docs/research/` is non-normative. Only `@TusharSariya` may
authorize accepted, verified, or superseded specification status.
