## ADDED Requirements

### Requirement: Geographic reference remains legible above weather imagery
The map SHALL draw a themed land-and-water base below meteorological rasters and
a transparent geographic reference stack above them. The reference stack SHALL
include coast and lake outlines, selected roads, boundaries and place labels,
with detail increasing by zoom. Every meteorological raster SHALL be inserted
below that reference stack, and observation markers SHALL remain above it. The
reference line styling SHALL identify geography only and SHALL NOT resemble or
claim to encode a meteorological value.

#### Scenario: Opaque cloud covers the island
- **WHEN** a weather raster is visually opaque over land and water
- **THEN** coast and lake outlines, selected roads and labels remain visible
- **AND** their continued visibility does not alter the raster pixels

#### Scenario: Several weather layers are enabled
- **WHEN** two or more weather rasters draw in their published z-order
- **THEN** every raster remains below the same reference stack
- **AND** observation markers remain above both raster and reference layers

### Requirement: The map and desk offer truthful light and dark themes
The first visit SHALL follow the operating-system colour preference. A reader
SHALL be able to choose light or dark explicitly, and that explicit choice SHALL
be retained locally for later visits. Both themes SHALL use distinct land and
water colours, legible reference casings and cores, and semantic page colours;
changing theme SHALL NOT change weather raster pixels or provider legends.

#### Scenario: First visit
- **WHEN** no explicit theme choice has been stored
- **THEN** the rendered theme matches `prefers-color-scheme` before the app is
  shown

#### Scenario: Manual choice
- **WHEN** the reader chooses the other theme
- **THEN** page and map tokens update together, the choice is stored locally,
  and the weather imagery and provider legend remain byte-for-byte unchanged

### Requirement: Dense map controls use progressive disclosure
The layer drawer SHALL begin closed and SHALL expose its state through a real
button. It SHALL close with Escape while open. On narrow screens it SHALL occupy
the bottom of the map rather than a permanent side column. Exact provider
legends for active raster layers SHALL remain adjacent to the map; layers whose
provider supplies no legend SHALL say so and SHALL NOT receive a client-authored
scale.

#### Scenario: Map first opens
- **WHEN** the workbench loads
- **THEN** the geographic field receives the available map area and the layer
  drawer is closed

#### Scenario: Narrow screen
- **WHEN** the drawer is opened on a narrow viewport
- **THEN** it is presented as a scrollable bottom sheet and the page does not
  overflow horizontally

### Requirement: Reference-map failure does not erase weather evidence
Reference-vector, glyph or sprite failure SHALL be reported as "Reference map
unavailable" in a visible live status. Retrieved weather imagery, observation
markers, controls and the textual map alternative SHALL remain available. The
failure SHALL NOT be described as a weather-data outage.

#### Scenario: Vector tiles cannot be loaded
- **WHEN** the reference source reports a network or decoding error
- **THEN** the map announces "Reference map unavailable"
- **AND** active weather imagery and its textual state remain present
