## ADDED Requirements

### Requirement: A derived artifact is not sampled onto a data path
Point and profile sampling SHALL read only artifacts that carry a retrieved
provider field. An artifact the deployment derived for display - the
interpolation motion the shader reads, the WEonG low-cloud repair, and any
derivation added later - SHALL be excluded before it is opened, and SHALL be
excluded on what its own provenance declares (`derived`, `generated`) rather
than on a match against its logical name. A name match is not a boundary: it
stops covering a derivation the moment one is renamed or added, and it fails
silently, in the direction of admitting a generated value rather than
withholding one.

An excluded derivation SHALL NOT be reported as a skipped artifact, because
a derivation that was never evidence is not evidence that was lost.

Every derived artifact SHALL record its QC in the vocabulary the evidence
contract defines. A response SHALL NOT be able to fail whole because one
artifact carries a status outside that set: the sampler holds many sources,
and one artifact's private vocabulary must not erase the others.

#### Scenario: A generated repair is published beside its base
- **WHEN** `/point` or `/profile` is read while a `low_cloud_weong` artifact
  is current
- **THEN** no field from it appears in the response, its provider's own
  surface artifact answers unchanged, and the skip list is empty

#### Scenario: The motion artifact's name carries its layer
- **WHEN** the interpolation motion for a derived layer is published as
  `cloud_motion_low_cloud_weong`
- **THEN** it is excluded from sampling because its provenance says derived,
  with no name list to update

#### Scenario: A derivation records a status the contract does not define
- **WHEN** a derived artifact's provenance carries a quality status outside
  the defined set
- **THEN** the derivation is at fault and is corrected at its source; the
  reader does not lose the retrieved evidence of every other source in the
  same response
