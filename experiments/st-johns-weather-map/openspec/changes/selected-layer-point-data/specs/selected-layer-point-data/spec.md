## ADDED Requirements

### Requirement: Field selection separates map display from point data
Map-capable field rows SHALL cycle `○ Off → ● Map + data → ◐ Data only → ○ Off`.
Point-only fields SHALL alternate Off and Data only. Information-only sources
SHALL retain details actions. Shapes, tooltips, accessible state labels and
visible keyboard focus SHALL distinguish states without colour.

Main-row click and Enter/Space SHALL cycle selection. Right-click, Shift+F10,
Menu key and existing details actions SHALL NOT alter selection. Active SHALL
include Map + data and Data only entries, replace separate visibility with the
state control, and retain explicit Remove. Data only SHALL preserve order and
opacity for restoration. Additions SHALL preserve existing defaults and append
at the top of drawing order. Removal SHALL focus the next row, previous row or
list heading in that order.

Browse SHALL expose individual supported point fields. Map and point
capabilities SHALL combine only through explicit source/product/field mappings;
missing matches SHALL remain unsupported, without name-based inference.
Ambiguous member, statistic and level choices SHALL require explicit selection,
while existing declared defaults SHALL remain defaults.

#### Scenario: A map field cycles through data only
- **WHEN** a selected map field is cycled to Data only and later restored
- **THEN** numeric requests continue while imagery is hidden, and restoration
  preserves its drawing position and opacity
- **AND** all group appearances reflect the same selection identity

#### Scenario: A point field has ambiguous variants
- **WHEN** no declared default resolves its member, statistic or level
- **THEN** the reader must choose before a request is dispatched
- **AND** opening details or a context menu never cycles selection

### Requirement: Point data persists inside the map
The Map SHALL contain a persistent Point data panel at bottom left with a 12px
inset above timeline controls and attribution. It SHALL NOT resize the map.
Desktop width SHALL be 360px constrained to available map width. It SHALL start
expanded with an empty-state prompt when no selected fields contribute.

The panel SHALL grow naturally to at most 50% of available map height, then
scroll category contents internally with its header visible. The header SHALL
show Point data, selected location/time and Minimize. The minimized bar SHALL
show selected-field count and Expand. Browser storage SHALL remember minimized
state; adding selections SHALL NOT override it.

Layers and provenance opening SHALL NOT remove the panel. Timeline expansions
SHALL coordinate with it to avoid obstructed controls. At narrow effective
viewports, including 200% zoom, it SHALL reflow inside the available map area.
There SHALL be no dismiss or delete-panel action.

#### Scenario: The reader minimizes and adds a field
- **WHEN** another field is selected or the page reloads
- **THEN** the compact bar remains minimized, displays the updated count and
  continues refreshing evidence

#### Scenario: The contents exceed available height
- **WHEN** many fields and timeline details are open
- **THEN** the header stays visible, only category contents scroll, controls
  remain accessible and the map camera and map dimensions remain unchanged

### Requirement: Point readings preserve selected identity and return context
The panel SHALL include only selected fields, grouped by existing scientific
field-family metadata. Compact rows SHALL show source, value with units and relative native valid time
in three columns, targeting 28px for a single line. Percentages SHALL use `%`.
Field, level and member qualifiers SHALL distinguish ambiguous readings; sources
and members SHALL remain separate. Normal rows SHALL omit repeated product
titles, availability labels, ISO timestamps and evidence glyphs.

Loading readings SHALL remain in their scientific categories. Completed missing,
failed, unsupported or refused selected fields and image-only layers SHALL move
to an initially expanded, individually collapsible bottom section named
“Point data not available (N)”, once per selected identity. Empty sections SHALL
be omitted. Valid zero values SHALL remain in scientific categories. GOES-East
natural colour SHALL remain image-only. Radar echo zero SHALL read “0 · no echo”;
a missing numeric rate SHALL never be fabricated. Recovery SHALL restore the
reading to its scientific category. Relative labels SHALL use the real clock
(`12 min ago`, `in 2 h`, `now`) and update every minute without requests.

Row details SHALL expose supplied native time, offset from selected time, run,
level, member/statistic and provenance. Missing metadata SHALL remain explicitly
missing. Closing details SHALL restore row focus and preserve panel scroll.
Escape within the focused panel SHALL first close nested details, then minimize.

Each layer's Open point data action SHALL expand the panel, open the relevant
category or bottom section and focus its reading without hiding other selected readings.

#### Scenario: Two providers supply the same field family
- **WHEN** both fields are selected
- **THEN** both source-labelled readings appear in that family without blending
- **AND** unrelated fields returned in either response do not appear

#### Scenario: A layer opens its reading
- **WHEN** Open point data is activated while the panel is minimized
- **THEN** it expands and focuses that reading in its open category
- **AND** closing its provenance returns focus without changing panel scroll

### Requirement: Every active point selection owns exact-request results
The client SHALL maintain independent results for every active point selection
using existing endpoints and normalization. Requests sharing product and
selectors SHALL be deduplicated, with at most two concurrent requests.

Location, time and selection changes SHALL trigger refresh even while minimized.
Rapid changes SHALL debounce for 250ms and cancel obsolete work. During playback,
requests SHALL target settled timeline steps. Results SHALL remain bound to exact
location, selected time, product and selectors; late responses SHALL NOT replace
results for newer identities.

Previous-location/time values SHALL immediately cease appearing current. Each
field SHALL independently show loading, native-time gaps, unsupported readings,
credentials requirements or failure. Partial responses SHALL preserve available
selected fields while naming absent fields. An optional explicit `time_selection=directional` point request policy SHALL
select observations at or before selection and forecasts at or after selection,
with exact matches winning. A reader without declared directional discovery
SHALL report native time selection unavailable under this policy, retaining its
legacy exact-time interface without inventing a timestamp inventory.
Capability metadata SHALL explicitly distinguish
observation and forecast behavior. The backend SHALL resolve against declared
native availability and preserve source coverage and freshness limits. Missing
eligible times SHALL remain gaps; wrong-side or stale evidence SHALL NOT be
substituted. The selected instant SHALL remain separate from returned native
time. Policy SHALL participate in client request identity and any selection
cache keys; native artifact caches MAY remain keyed by resolved native identity.
Callers omitting the policy SHALL retain existing time semantics. Returned
timestamps SHALL be disclosed. Numerical values SHALL
NOT be extracted from raster colours.

#### Scenario: An obsolete response arrives after location changes
- **WHEN** the old request completes after a newer Focus is selected
- **THEN** its values never appear as current for that newer Focus
- **AND** the new identity shows loading or its own result independently

#### Scenario: A source requires credentials and another returns partial data
- **WHEN** both sources contribute selected fields, including WeatherNext
- **THEN** credentials failure does not hide the other source's returned values
- **AND** absent fields, unavailable times and actual timestamps remain explicit

### Requirement: Restored selections retain compatibility
Typed selections, saved stacks and URL restoration SHALL support point identities
and three-state selection. Existing visible entries SHALL become Map + data;
existing hidden entries SHALL become Data only. Order, opacity and unavailable
selections SHALL survive restoration. Explicit capability references SHALL be
added where existing mappings cannot establish a map-to-point match. Existing GeoMet radar native point sampling SHALL expose precipitation_rate,
snow_rate and radar_echo through explicit capabilities and the point response.
It SHALL reuse discovery caches, budgets, units, coverage and no-echo semantics.
No new provider integration, derivation or acquisition schedule SHALL be introduced.

#### Scenario: A legacy hidden layer is restored
- **WHEN** an existing URL or saved stack contains that layer
- **THEN** it restores as Data only at the original order and opacity
- **AND** unavailable capability or evidence remains visible as unavailable

#### Scenario: Desktop acceptance exercises overlapping controls
- **WHEN** the desktop is exercised at 1280×800, 1440×900 and 1920×1080
- **THEN** captures cover all themes, 200% zoom and simultaneous Layers,
  provenance and timeline overlays with the persistent panel accessible
- **AND** keyboard, URL, saved-stack and unchanged-camera regressions pass

#### Scenario: Compact unavailable rows recover
- **WHEN** a selected field fails or is missing and later returns a usable zero
- **THEN** it moves from its loading category to the bottom section and back
- **AND** the bottom section focus action and provenance return preserve context

#### Scenario: Relative ages do not reacquire
- **WHEN** the real clock advances one minute with selection unchanged
- **THEN** past and future native-time labels update without a new request

#### Scenario: Directional native boundaries
- **WHEN** a selected instant lies between published native readings
- **THEN** observations use the latest eligible before and forecasts the nearest eligible after
- **AND** exact matches win, unavailable and stale periods remain gaps, and legacy requests retain their matching rules

#### Scenario: Radar keeps numeric and echo semantics distinct
- **WHEN** GeoMet supplies rain, snow, explicit no echo, missing coverage or a failure
- **THEN** supplied rates retain their units, zero echo reads “0 · no echo”, and missing rates remain missing
- **AND** live evidence is recorded separately from fixture verification
