# ECCC analysis experimental integration

## ADDED Requirements

### Requirement: Native air-quality fields remain isolated until semantically catalogued

The experimental WCS path SHALL enumerate and retain every selected RAQDPS and RDAQA field with its provider coverage id, published units, vertical level, product phase, valid time, reference time when published, response headers, and actual HTTP completion time. A field whose unit, attribution, averaging interval, or analysis phase has no canonical catalogue key SHALL remain source-scoped and nonpublishable; it SHALL NOT be converted to a differently dimensioned catalogue key or omitted from the acquisition receipt. Product phase, vertical scope, and any statistic window SHALL be explicit in the selected field contract, normalized variable attributes, artifact provenance, and retained receipt; they SHALL NOT be inferred later from a coverage identifier or variable spelling.

#### Scenario: GeoMet gas is published as mole fraction

- **WHEN** a selected RAQDPS or RDAQA gas coverage publishes `mol/mol` and the catalogue maps that species only as mass concentration
- **THEN** the experimental reader preserves the raw mole-fraction units and source identity
- **AND** the complete product remains nonpublishable pending an accepted canonical contract

#### Scenario: Source-scoped field reaches the normal point route

- **WHEN** a staged source-scoped raw field has no accepted catalogue and manifest mapping
- **THEN** the normal point route omits it
- **AND** test-only injected mappings are described as serialization evidence rather than admission
