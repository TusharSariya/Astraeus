# ECCC analysis experimental integration

## ADDED Requirements

### Requirement: Native air-quality fields remain isolated until semantically catalogued

The experimental WCS path SHALL enumerate and retain every selected RAQDPS and RDAQA field with its provider coverage id, published units, vertical level, product phase, valid time, reference time when published, response headers, and actual HTTP completion time. A field whose unit, attribution, averaging interval, or analysis phase has no canonical catalogue key SHALL remain source-scoped and nonpublishable; it SHALL NOT be converted to a differently dimensioned catalogue key or omitted from the acquisition receipt.

#### Scenario: GeoMet gas is published as mole fraction

- **WHEN** a selected RAQDPS or RDAQA gas coverage publishes `mol/mol` and the catalogue maps that species only as mass concentration
- **THEN** the experimental reader preserves the raw mole-fraction units and source identity
- **AND** the complete product remains nonpublishable pending an accepted canonical contract
