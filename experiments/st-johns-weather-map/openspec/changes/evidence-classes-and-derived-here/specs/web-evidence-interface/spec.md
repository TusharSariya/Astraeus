## ADDED Requirements

### Requirement: Every value and layer shows its evidence class
The interface SHALL show the evidence class of every value and every layer it
renders, retrieved included, as a badge with a colour that is consistent
across the map, readings and stories, and SHALL provide a legend naming all
six classes. The absence of a badge SHALL never carry meaning. A value of
class `derived_here` SHALL expose its inputs and method on demand. A value
whose class the client does not recognise SHALL be shown as unavailable with
the reason, never as retrieved.

#### Scenario: A retrieved value
- **WHEN** a retrieved value is rendered
- **THEN** it carries the `retrieved` badge, not an empty space

#### Scenario: A derived value's inputs
- **WHEN** the reader opens a `derived_here` value
- **THEN** the interface lists each input with its source, valid time and quality, and the method name, version and citation

#### Scenario: An unknown class
- **WHEN** a response carries an `evidence_class` the client does not know
- **THEN** the value is rendered as unavailable with "unrecognised evidence class" and no number is shown
