# Experimental IERS time inputs

## Purpose

This draft contract governs only the isolated issue #123 evidence path. It is not accepted production behavior.

## ADDED Requirements

### Requirement: Bounded exact-source retrieval

The experiment SHALL retrieve only the pinned IERS finals2000A, IERS leap table and NAIF0012 URLs under their declared byte ceilings and SHALL bind provider revision and `retrieved_at` to the response digest and actual completed HTTP capture time.

#### Scenario: provider data is invalid

- **WHEN** a response exceeds its ceiling or carries malformed identity, selected content, timestamps, flags, values, monotonic sequence, or expiry
- **THEN** retrieval fails before artifact publication

### Requirement: Lossless published semantics

The experiment SHALL preserve every selected product field, published unit, UTC identity, date/MJD agreement, observed/predicted status, missing value, version and expiry without deriving Earth orientation, time conversions, frames or ephemerides.

#### Scenario: immutable artifact is read through HTTP

- **WHEN** a validated but nonpublishable staged artifact is injected into the test store
- **THEN** the experimental endpoint reads its exact stored values and provenance through the production `LiveStore` path
- **AND** reports `operational: false`

### Requirement: No scientific promotion

The readers SHALL remain unregistered and unscheduled. No Earth PCK SHALL be chosen without owner-approved frame, interval, accuracy and use requirements.

#### Scenario: experiment is present

- **WHEN** the experimental readers and endpoint are installed
- **THEN** no worker schedule or production source registration references them
- **AND** their artifacts and HTTP response report `operational: false`
- **AND** each run reports incomplete, QC-failed and nonpublishable until an accepted reference-input manifest contract exists
