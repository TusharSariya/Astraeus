## ADDED Requirements

### Requirement: The ensemble member coordinate is preserved, never stripped
Where a decoded message carries an ensemble member coordinate, that
coordinate SHALL be preserved as the member's identity. It SHALL NOT be
discarded as an anonymous message scalar in the way that time, step and valid
time are, because those are recoverable from the artifact's own axes and a
member identity is not: once dropped, nothing downstream can say which member
a value came from. A decode that would collapse two or more members onto one
field SHALL fail with the member values it saw, rather than publishing a
field whose provenance cannot name what it holds.

#### Scenario: A member-bearing message is decoded
- **WHEN** a GRIB message carries a member number
- **THEN** the decoded field carries that member identity, and it survives
  into the artifact's provenance

#### Scenario: Two members would collapse onto one field
- **WHEN** messages for more than one member would be assembled into a single
  field with no member axis to separate them
- **THEN** the decode fails naming the member values it saw, and nothing is
  published, because a silently collapsed ensemble is indistinguishable from a
  deterministic field

#### Scenario: A deterministic message
- **WHEN** a message carries no member coordinate
- **THEN** decoding is unchanged and no member identity is invented for it
