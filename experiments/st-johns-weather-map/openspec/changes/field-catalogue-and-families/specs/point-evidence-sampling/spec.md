## ADDED Requirements

### Requirement: Every served field carries its family, comparability and phase
Every field on `/point`, `/profile` and `/timeline` SHALL carry its catalogue
key, family, and, where more than one member of the family is present, the
comparability between them with the reason where false. Humidity fields SHALL
carry their phase. A field whose key is not in the catalogue SHALL NOT be
served.

#### Scenario: A family with mixed members
- **WHEN** `/point` serves three cloud-cover members from HRDPS, GFS and GOES
- **THEN** each carries its key and family, and the pairwise comparability says which pairs are comparable and why the others are not

#### Scenario: A field with no catalogue key
- **WHEN** an artifact carries a variable whose name is not a catalogue key
- **THEN** the variable is not served, and a notice names it as uncatalogued
