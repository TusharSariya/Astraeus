# Change: Reconcile the free-source implementation roster

## Why

The implementation map currently has family tickets, while the audit contains
118 exact registry IDs plus finer product/access candidates outside the
registry. Without one checked roster, catalogue entries, research mentions,
dead paths and existing partial adapters can be lost or incorrectly counted as
implemented.

## What changes

- Add a machine-readable planning roster that assigns every audited row to an
  exact implementation or disposition ticket.
- Carry source state, access, field scope, account/permission, geography,
  contract status and required end-to-end proof without promoting a source.
- Record the bounded child splits required before broad family execution.
- Validate coverage against the 118-row audit and every appendix/narrative
  research group.

## Impact

Planning and traceability documentation only. Runtime behavior, registry state,
API shape, source schedulability and normative status do not change.

Spec-Impact: none. The roster exposes missing source-specific authority instead
of supplying it.

