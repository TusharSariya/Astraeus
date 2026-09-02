## ADDED Requirements

### Requirement: A derived rendered-grid layer discloses its derivation as generated
A rendered-grid layer whose values come from a derived artifact rather than
from a provider's own published field - the WEonG low-cloud repair on HRDPS,
and any layer like it - SHALL be a separate layer with its own identifier
and logical name, SHALL leave the provider's artifact untouched, SHALL carry
a title suffix and a `derived_disclosure` naming the construction and its
citation, SHALL say `generated` in every response's provenance beside the
base artifact's revision and the derivation version, SHALL be offered only
while the deployment kill switch permits generated display, and SHALL never
be read by any data path. A data path SHALL decide what to exclude from the
artifact's own provenance, never by matching a logical name, so that a
renamed or newly added derivation cannot re-enter sampling unnoticed; and a
derived artifact SHALL record its QC in the vocabulary the evidence contract
defines, so that a derivation's private status cannot fail a response that
does not otherwise concern it. Where the derived artifact is absent for a run the
layer SHALL be absent from `/layers` for that run rather than drawn from the
base field.

#### Scenario: The WEonG layer is served
- **WHEN** `eccc-hrdps-low-cloud-weong` is rendered
- **THEN** the title carries "(generated: WEonG low-cloud repair)", the
  response names the technote section and the base revision, provenance
  says `generated`, and the provider's `total_cloud` layer is unchanged

#### Scenario: The kill switch is off
- **WHEN** `WEATHER_GENERATED_DISPLAY=off` is set
- **THEN** the layer is absent from `/layers` and any request for it is a
  named absence, never the base field under the derived name

#### Scenario: The derived artifact is missing
- **WHEN** no `low_cloud_weong` artifact exists for the current run
- **THEN** the layer is not offered and no frame is drawn from the base
  field in its place

#### Scenario: A point reading
- **WHEN** `/point` or `/profile` is read over the Avalon
- **THEN** no field from the derived artifact appears in the response, and
  the artifact is not counted as a skipped one either: a derivation that was
  never evidence is not evidence that was lost

#### Scenario: The derivation is renamed
- **WHEN** a derived artifact's logical name changes to carry the layer it
  supports, or a new derivation is published
- **THEN** it stays off the data paths because its provenance declares it
  derived, with no list of names to update

#### Scenario: The derivation records its own QC
- **WHEN** a derived artifact's provenance carries a quality status
- **THEN** that status is one the evidence contract defines, with the
  derivation named in the flags, and a status outside that set is a defect
  in the derivation rather than a response the reader loses
