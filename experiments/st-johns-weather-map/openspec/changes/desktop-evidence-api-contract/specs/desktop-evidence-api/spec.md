## ADDED Requirements

### Requirement: Desktop evidence Series preserves a bounded native selection
The desktop API SHALL provide a bounded read of explicitly selected source and
catalogue-field evidence across a UTC window. It SHALL preserve each source's
actual published timestamps, per-reading identity and provenance, and explicit
checked absences. It SHALL NOT synthesize a shared cadence, interpolate,
substitute sources, or serve archived retained values as current evidence.

The read SHALL have finite selector, window, sample, byte, duration and cache
bounds. Pagination SHALL bind a canonical immutable selection and SHALL reject an
altered continuation. Expiry SHALL require a new initial read;
no read or continuation silently renews it. Exact wire shape and measured numeric
bounds are delegated implementation choices under the September 7 owner
decision recorded in proposal.md; they require mapped verification.

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

### Requirement: Series uses selected cursor pagination and fixed expiry
The desktop Series initial read SHALL use the proposed explicit selection
request. It SHALL return an opaque cursor when another bounded page remains.
A continuation SHALL contain that cursor only and SHALL bind the original
selection, relevant finite cache identity and fixed nonrenewing expiry. The API
SHALL reject a changed continuation. At expiry it SHALL return a
restart-required proposed `snapshot_expired` error; it SHALL NOT renew the
selection or treat a stale page as current.

#### Scenario: A client alters a cursor request
- **WHEN** a continuation supplies a cursor and a different selector or coordinate
- **THEN** the API rejects it as `invalid_cursor` and does not merge selections

### Requirement: Series run choices retain actual source scope and limits
Where a source/run-family delivery path supports run inventory and reads, the
desktop API SHALL expose Latest available, named Previous, and temporary
same-source two-run Compare according to the owner-selected run policy. Latest
available MAY segment across actual runs only with every segment disclosed.
Previous SHALL name and pin one actual retained run before frame matching.
Removed runs SHALL remain visibly selected with an explicit Latest available
alternative. Run identity SHALL live beside Focus in the URL and apply only to
its source/run family; Activity SHALL retain its own server-side evaluation.

Ordinary new-read inventory SHALL expose only latest and previous. An existing
unexpired finite selection MAY retain a displaced revision until its fixed
advertised expiry within the existing quota. It SHALL NOT renew by paging or
change checking, make displaced revisions newly selectable, add warehouse
retention, or silently evict a live pin.

#### Scenario: A latest run lacks a requested valid time
- **WHEN** Latest available has no frame for one valid time and a prior actual
  run covers it
- **THEN** the response may use that prior run only for that segment and names
  the actual run identity; it does not relabel the segment as the latest run

#### Scenario: A pinned run is removed
- **WHEN** a pinned run is no longer readable
- **THEN** it remains identified as unavailable, preserves Focus and time, and
  offers Latest available without substituting values
