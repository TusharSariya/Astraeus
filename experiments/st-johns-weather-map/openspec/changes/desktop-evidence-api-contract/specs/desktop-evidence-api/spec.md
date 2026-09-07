## ADDED Requirements

### Requirement: Desktop evidence Series preserves a bounded native selection
The desktop API SHALL provide a bounded read of explicitly selected source and
catalogue-field evidence across a UTC window. It SHALL preserve each source's
actual published timestamps, per-reading identity and provenance, and explicit
checked absences. It SHALL NOT synthesize a shared cadence, interpolate,
substitute sources, or serve archived retained values as current evidence.

The read SHALL have finite selector, window, sample, byte, duration and cache
bounds. Pagination, if exposed, SHALL bind a canonical immutable selection and
shall reject an altered continuation. Expiry SHALL require a new initial read;
no read or continuation silently renews it. Exact wire shape and numeric bounds
are proposed rather than accepted by this change.

#### Scenario: Sparse native sources share a window
- **WHEN** two selected sources publish at different native timestamps
- **THEN** each source returns only its own samples and explicitly checked
  absences, without manufactured rows at the other source's times

#### Scenario: A bounded selection expires
- **WHEN** a continuation arrives after the proposed finite selection lifetime
- **THEN** it requires a fresh initial read and does not return cached values as
  current evidence

### Requirement: Desktop change checks are selection-specific and non-mutating
A desktop change check SHALL compare the displayed selection against its
original relevant evidence baseline. It SHALL report `unchanged`, `changed`, or
`unknown` without mutating the displayed result, acknowledging a change, or
renewing the selection cache. An unrelated source update or elapsed clock time
SHALL NOT by itself report `changed`. A failed comparison SHALL report
`unknown`; an expired selection SHALL require restart.

#### Scenario: An unrelated source publishes
- **WHEN** a source outside the displayed selection changes
- **THEN** the selection check reports `unchanged`, not a deployment-wide update

#### Scenario: The comparison cannot run
- **WHEN** the current relevant comparison cannot be obtained
- **THEN** the check reports `unknown` and does not describe the displayed
  evidence as confirmed current
