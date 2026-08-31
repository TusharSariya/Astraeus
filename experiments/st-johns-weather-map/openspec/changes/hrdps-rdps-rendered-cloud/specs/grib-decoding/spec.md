## MODIFIED Requirements

### Requirement: A message whose parameter concept does not match is withheld and the cause recorded
A GRIB message that the decoder cannot resolve to a named parameter concept
SHALL NOT be published under a canonical variable name on the strength of its
value range or the adapter's assumption. Where the message's own coded
identity keys - discipline, parameterCategory, parameterNumber and the fixed
surfaces, read from the message via the decoder - exactly match a WMO code
table 4.2 entry whose publication the owner has approved, the field MAY be
declared with that entry's name and units, recording the decoder's own units
as `original_units` and the declaration's basis in a `units_basis` attribute.
A message whose coded keys do not match SHALL be refused with a recorded
decode error, and the cause SHALL remain recorded in code with the keys read
from the message. The owner-approved entry is total cloud cover: WMO 0/6/1
with `typeOfFirstFixedSurface=1` declares `total_cloud` in percent (owner
decision 2026-08-31); no other unknown-units field is declared.

#### Scenario: ECCC total cloud cover is declared from its own keys
- **WHEN** an HRDPS `TCDC_Sfc` or RDPS `TotalCloudCover_Sfc` message is
  decoded carrying WMO discipline 0, category 6, number 1 with
  `typeOfFirstFixedSurface=1` and `typeOfSecondFixedSurface=255`, and ecCodes
  resolves `paramId=0` with units `unknown` (the `tcc` concept requires
  second fixed surface 8 and no CWAO local concept exists)
- **THEN** the field is published as `total_cloud` in `percent`, with
  `original_units: "unknown"` and a `units_basis` attribute naming WMO GRIB2
  code table 4.2 as the source of the declaration, and the stored values are
  untouched

#### Scenario: The wrong identity keys declare nothing
- **WHEN** a decode yields a variable whose units are `unknown` and whose
  coded keys are anything other than the approved 0/6/1 surface-based
  identity
- **THEN** no declaration is applied, the field is refused with an
  `undeclared_units` decode error, and a run consisting only of that field
  fails loudly rather than publishing units the decoder declined to declare

#### Scenario: A field the decoder does name is left alone
- **WHEN** ecCodes itself declares a name and units for the message
- **THEN** the WMO-key declaration does not run and normal unit
  normalization applies, so the day the decoder starts declaring `%` the
  pipeline simply uses it

#### Scenario: Total cloud is published for HRDPS and RDPS only
- **WHEN** the Datamart variable maps are read
- **THEN** `total_cloud` is present in `HRDPS_VARS` and `RDPS_VARS` and
  absent from `GDPS_VARS`, and `/point` serves the field from the stored
  grids once an ingest run under these maps completes
