## ADDED Requirements

### Requirement: A message whose parameter concept does not match is withheld and the cause recorded
A GRIB message that the decoder cannot resolve to a named parameter concept SHALL NOT be published under a canonical variable name the adapter assumes it deserves. The adapter SHALL leave the variable out of its declared maps, SHALL record the cause in code and in the live-stack report with the discipline, category, number and fixed-surface keys read from the message, and SHALL name the decision as one held for the owner. A version number is not a cause; only the message keys and the concept definition are.

#### Scenario: ECCC total cloud cover
- **WHEN** an HRDPS `TCDC_Sfc` or RDPS `TotalCloudCover_Sfc` message is decoded carrying WMO discipline 0, category 6, number 1 with `typeOfSecondFixedSurface=255`
- **THEN** the decoder resolves `paramId=0` with units `unknown`, because the `tcc` concept requires second fixed surface 8 and no CWAO local concept exists
- **AND** `total_cloud` is absent from `HRDPS_VARS`, `RDPS_VARS` and `GDPS_VARS`, so nothing is published for it

#### Scenario: A withheld variable declared anyway fails QC
- **WHEN** a decode yields a variable whose units are `unknown` and it is nevertheless declared as a mandatory canonical field
- **THEN** `validate_run` fails QC with `bad_units:<field>:unknown` and the run is not publishable, rather than a field of unknown meaning being served as percent cloud

#### Scenario: The decoder is upgraded
- **WHEN** the ecCodes library is replaced by a newer build
- **THEN** the outcome is re-established by a live smoke that prints the message keys and the decoded units verbatim, and the variable maps change only if the decoder itself states the units

#### Scenario: Nothing is retrieved for total cloud
- **WHEN** `/point` is asked for a coordinate covered by an HRDPS or RDPS artifact
- **THEN** `total_cloud` from that source is absent from the live fields, and the unavailable-field set still enumerates it as `null` with provenance, so the reader sees an honest gap rather than a value the decoder could not name
