## ADDED Requirements

### Requirement: The interpolation method is chosen from the server's own registry and named on the map
The client SHALL offer only the interpolation methods the server publishes,
with each method's measured skill shown beside it, and SHALL draw one method
at a time. Whenever the drawn method is not the default, the on-map
disclosure SHALL name it, so what produced the picture is never ambiguous. A
method that has not been scored SHALL be shown as unscored rather than as a
zero score, and a registry that could not be read SHALL leave the map on the
default construction and say so.

#### Scenario: Choosing a method
- **WHEN** the reader selects a published method
- **THEN** the map draws that method's fields and the disclosure names it

#### Scenario: A method that has never met a real frame
- **WHEN** a registered method has no held-out score
- **THEN** the menu says it has not been scored, rather than showing zero
  skill

#### Scenario: The registry cannot be read
- **WHEN** the method list request fails
- **THEN** the map draws the default construction and the failure is stated
  rather than a method list being invented

#### Scenario: A remembered choice the server dropped
- **WHEN** a stored method is absent from the registry the server now
  publishes
- **THEN** the client returns to the default rather than requesting fields
  no cycle produces
