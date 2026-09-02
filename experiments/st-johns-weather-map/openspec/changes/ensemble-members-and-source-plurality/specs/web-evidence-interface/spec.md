## ADDED Requirements

### Requirement: Every contributing source is shown for a field, and none is blended
Where more than one source published a field for the selected point and
instant, the interface SHALL show each source's own value with the source
named beside it, and SHALL NOT display any number computed across sources. The
declared primary SHALL be identifiable as such, with the ordering that chose
it stated. No control, badge, label or text alternative SHALL use the word
consensus or imply that a displayed number was agreed between models. Where
only one source published, that SHALL read as one source having published,
never as agreement.

#### Scenario: Several sources published
- **WHEN** three models published the selected field
- **THEN** all three values are shown with their sources named, the declared
  primary is marked, and no fourth combined number appears

#### Scenario: One source published
- **WHEN** only HRDPS published the selected field
- **THEN** the single value is shown attributed to HRDPS, and nothing states
  or implies that models agree

#### Scenario: No source published
- **WHEN** no source published the selected field
- **THEN** the field reads as unavailable with the reason, and the absence is
  not filled from a neighbouring source or a previous instant

#### Scenario: The text alternative
- **WHEN** the map contents are read as text
- **THEN** each value is announced with its source, and no consensus wording
  appears anywhere in the alternative

### Requirement: A reprocessed value is labelled as reprocessed wherever it is shown
Where a displayed value came from a source declared `reprocessed`, the
interface SHALL name both the originating producer and the intermediary, and
SHALL state that the value was transformed before it arrived rather than
attributing it to the producer alone. The label SHALL be present wherever the
value is, including the text alternative. A reprocessed value SHALL NOT be
styled or positioned as the primary reading. Where the intermediary documents
no transformation for that field, the interface SHALL say the transformation
is undocumented rather than implying there was none.

#### Scenario: A reprocessed value is displayed
- **WHEN** a value from an aggregator-delivered global model is shown
- **THEN** both the producer and the intermediary are named beside it, the
  transformations are stated, and it does not occupy the primary slot

#### Scenario: The text alternative
- **WHEN** the map contents are read as text
- **THEN** a reprocessed value is announced with both parties named and with
  the fact that it was transformed, never as the producer's own reading

#### Scenario: Nothing is known about the transformation
- **WHEN** the intermediary documents no transformation for the field
- **THEN** the interface reads that the transformation is undocumented, and
  does not present the value as unmodified

#### Scenario: No reprocessed source is displayed
- **WHEN** every displayed value comes from a `published_cell` source
- **THEN** no reprocessing label appears anywhere, so the label always carries
  information rather than becoming decoration
