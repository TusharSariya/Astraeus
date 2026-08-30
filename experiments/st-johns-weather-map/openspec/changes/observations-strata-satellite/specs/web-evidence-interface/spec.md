## ADDED Requirements

### Requirement: The cloud band filter is a view filter that never computes a value
The point panel SHALL offer three toggles, Low, Middle and High, above the Cloud layers metric, each labelled with its band in feet (low: base below 6,500 ft; middle: 6,500 to 20,000 ft; high: 20,000 ft and above), all on by default. A toggle that is off SHALL hide reported layers whose base in metres falls in that band and nothing else. A layer with no base in metres SHALL never be hidden and SHALL be labelled "base Unknown — not filterable". When any band is off, the metric detail SHALL read "N of M reported layers shown · view filter, not a classification". The filter SHALL NOT compute, count per band, sort, merge or send anything to the API, and the `Cloud L / M / H` readouts SHALL stay Unknown because no low, middle or high value was retrieved.

#### Scenario: All bands on
- **WHEN** every toggle is on
- **THEN** the metric reads the full as-reported list in provider order with the existing detail, exactly as before the filter existed

#### Scenario: Low is turned off
- **WHEN** the layers are `FEW` at 609.6 m and `BKN` at 3962.4 m and Low is off
- **THEN** only `BKN · 3962 m` is shown and the detail reads "1 of 2 reported layers shown · view filter, not a classification"

#### Scenario: A layer without a base survives every filter
- **WHEN** a layer has no base in metres, such as `SKC`, `CLR`, `CAVOK` or a base in another unit, and any combination of bands is off
- **THEN** it is still listed as "<code> · base Unknown — not filterable"

#### Scenario: No layer is returned
- **WHEN** no `cloud_layer_*` field is present
- **THEN** the metric reads Unknown as today and the toggles hide nothing, because there is nothing to filter

#### Scenario: Strata stay unknown
- **WHEN** any band toggle is changed
- **THEN** `Cloud L / M / H` still read Unknown, the API request is unchanged, and no percentage or count per band is displayed

#### Scenario: The toggles are real controls
- **WHEN** the band group is rendered
- **THEN** it is a `role="group"` labelled "Cloud layer bands" of three `button`s carrying `aria-pressed`, and the text alternative restates which bands are off

### Requirement: Model buttons are grouped by producer
The forecast-model row SHALL group model buttons by the catalogue `producer`, with a visible label before each producer's buttons, BLEND first and ungrouped. The row SHALL remain one horizontally scrolling strip. Grouping SHALL NOT change which buttons are enabled, what token they send, or their coverage readouts.

#### Scenario: Two producers
- **WHEN** the catalogue lists ECCC and NOAA sources that `/point` accepts as products
- **THEN** the row shows BLEND, then an ECCC label with its buttons, then a NOAA label with its buttons, and each button still sends the endpoint's own product token

#### Scenario: A producer with nothing selectable
- **WHEN** a producer's sources all map to no `/point` product token
- **THEN** no label is rendered for it, rather than a heading over an empty group

#### Scenario: The catalogue could not be read
- **WHEN** `/catalog` failed
- **THEN** the row is disabled with the catalogue error stated, as today, and no group labels are shown

## MODIFIED Requirements

### Requirement: The coverage ribbon shows where frames actually exist
For each published layer the interface SHALL show one row marking every published frame's position across the window, together with a count and the current resolution state. Rows SHALL be grouped under headings by the shared layer grouping, in the order satellite, observation, alert, forecast proxy, published model, each heading carrying the group's layer count; a group with no layers SHALL NOT be rendered. The satellite heading SHALL carry the line "observed imagery: frames exist only for the past". Each row SHALL carry a text alternative naming the layer, its frame count, and whether the selected time resolves to a frame or falls outside the layer's tolerance. A layer with no recognised group SHALL fall into the same fallback group the drawer uses, never be dropped.

#### Scenario: Grouped rows
- **WHEN** satellite, observation and proxied forecast layers are published
- **THEN** the ribbon shows a "Satellite · N layers" section first, then the other non-empty groups in order, and every layer appears in exactly one section

#### Scenario: A satellite row at a forward hour
- **WHEN** the selected time is after the last satellite frame
- **THEN** that row reads "no frame here" under the heading line that frames exist only for the past, and nothing is drawn or extrapolated

#### Scenario: A layer with gaps
- **WHEN** a layer published frames only over part of the window
- **THEN** the ribbon shows marks only where frames exist, so a gap reads as a gap

#### Scenario: A layer with no frames
- **WHEN** a layer published no frames
- **THEN** the row reads "no frames" and its text alternative says the layer published no frames in this window

#### Scenario: A layer with no group
- **WHEN** a layer omits `group` or declares an unrecognised value
- **THEN** it is listed under the fallback group, not hidden

#### Scenario: No layers at all
- **WHEN** nothing is published
- **THEN** the ribbon states that no layer is published so there are no frames to show, and no group heading is rendered

### Requirement: A station marker is a location picker, not a coverage claim
Station markers SHALL distinguish, by glyph and in words, four states: a live ingested source stands behind the station; a source is declared but has recorded no live retrieval; no source declares coverage of the place; and the status endpoint could not be read. The distinction SHALL NOT rest on colour alone and SHALL be repeated verbatim in the on-canvas label, the picker option and the text alternative. The station picker SHALL group its options with `<optgroup>` labels "Live ingested source" and "No ingested source (place to query)" from the same coverage state, and SHALL keep its disabled and empty behaviour when there is nothing to list.

#### Scenario: A station with a live source
- **WHEN** `/sources/status` reports a live retrieval for a source the station declares
- **THEN** the marker is a filled disc labelled "live source", the text alternative names the source and its last retrieval, and the picker lists it under "Live ingested source"

#### Scenario: A declared source that has retrieved nothing
- **WHEN** the declared source is catalogued but reports no live retrieval
- **THEN** the marker is an open ring labelled "no live retrieval" and the text says nothing has been ingested for the station

#### Scenario: A place no source claims
- **WHEN** a station declares no source ids — a headland inside a bounding box is not evidence that a station there reports
- **THEN** it is labelled "no ingested source", described as a location to query, and listed in the picker under "No ingested source (place to query)"

#### Scenario: The status endpoint could not be read
- **WHEN** `/sources/status` failed
- **THEN** every station reads "coverage unknown", none is shown as live, and the picker does not present any station as live

#### Scenario: Nothing to pick
- **WHEN** no station is available
- **THEN** the picker is disabled with the reason stated and no empty `<optgroup>` is rendered
