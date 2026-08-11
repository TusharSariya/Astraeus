# Contributing to Astraeus

Read [the V1 specification index](docs/specv1/README.md) and
[governance](docs/specv1/GOVERNANCE.md) before changing behavior.

## Workflow

1. Open or select an Issue linked to accepted requirement IDs.
2. Use a `spec/`, `feat/`, `fix/`, or `chore/` branch.
3. Change specifications first when governance requires it.
4. Add tests/evidence mapped in the owning `VERIFICATION.md`.
5. Run `uv run --project tools/specs python tools/specs/specctl.py validate`
   and product tests.
6. Open a pull request using the template.
7. Squash merge with the validated conventional title and traceability body.

Only `@TusharSariya` may authorize accepted, verified, or superseded normative
status. GitHub Issues track work but do not override repository specifications.
