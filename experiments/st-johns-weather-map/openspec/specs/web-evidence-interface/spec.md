## Purpose
Define the browser workbench: a multi-layer map stack where each layer draws only its own published frames, a continuous scrubber across the 28-hour window, a coverage ribbon showing where frames actually exist, honest unavailable states for the panels that are not built, and a text alternative for everything the canvas shows.

## Requirements

### Requirement: Layers are an additive stack with per-layer opacity and published draw order
The map SHALL support several layers drawn at once, each toggleable and each with its own opacity control, ordered by the `z_index` the API published. The default stack SHALL be empty — basemap only — and that SHALL be stated as a deliberate choice rather than left ambiguous.

#### Scenario: Radar over a field
- **WHEN** two layers are enabled
- **THEN** both draw, in published z-order, each at its own opacity

#### Scenario: No layer selected
- **WHEN** no layer is enabled
- **THEN** the text alternative states "Basemap only. No meteorological layer is requested."

#### Scenario: No layer published
- **WHEN** `/layers` returns nothing or could not be read
- **THEN** the selector shows a status message naming the reason — loading, the error, or that the API published no layers — and no layer is invented

### Requirement: Each layer answers the requested instant from its own frames or declines
For each active layer the client SHALL resolve the requested instant against that layer's own declared times, accept only the nearest frame inside the layer's declared staleness tolerance, and otherwise record `no-frame` with a reason and neither fetch nor draw. Every drawn layer SHALL display the resolved frame's timestamp and its signed offset from the requested time.

#### Scenario: A frame resolves
- **WHEN** the nearest frame is inside tolerance
- **THEN** that frame's features are fetched and drawn, and the frame time plus a human offset such as "4 min earlier" is shown beside the layer

#### Scenario: No frame within tolerance
- **WHEN** the nearest frame is outside the declared tolerance
- **THEN** the layer is not requested and not drawn, and the reason names the tolerance in minutes

#### Scenario: The frame returned nothing
- **WHEN** a resolved frame's feature request succeeds but returns zero features
- **THEN** the layer reports that the frame published no values and that nothing has been drawn in their place — distinct from an error and from no frame at all

#### Scenario: The frame could not be read
- **WHEN** the feature request fails or returns an incompatible schema
- **THEN** the layer reports an error state naming the reason, and draws nothing

### Requirement: Colour identifies a layer and never encodes a value
Layer colours SHALL identify a layer within the stack only. The interface SHALL NOT draw a colour ramp, dBZ scale or any other value-encoding legend of its own; a colour ramp may only be the provider's own legend graphic.

#### Scenario: A layer swatch
- **WHEN** an active layer is listed in the stack
- **THEN** its swatch is marked decorative and carries no value meaning

### Requirement: The scrubber is continuous at a resolution finer than the fastest layer
The timeline control SHALL span `-3h` to `+24h` in five-minute steps, finer than the six-minute radar cadence so no layer's frames are unreachable between steps. The session reference instant SHALL be fixed once, so resolved frames do not slide under the reader between renders. Quick jumps SHALL be offered for the standard offsets.

#### Scenario: Scrubbing to a radar frame
- **WHEN** the reader drags the scrubber
- **THEN** the requested instant moves in five-minute steps and every layer re-resolves against its own frames at that instant

#### Scenario: The reference does not drift
- **WHEN** the component re-renders
- **THEN** the window and every resolved frame are computed from the same session reference instant, not from a fresh clock read

### Requirement: The coverage ribbon shows where frames actually exist
For each published layer the interface SHALL show one row marking every published frame's position across the window, together with a count and the current resolution state. Each row SHALL carry a text alternative naming the layer, its frame count, and whether the selected time resolves to a frame or falls outside the layer's tolerance.

#### Scenario: A layer with gaps
- **WHEN** a layer published frames only over part of the window
- **THEN** the ribbon shows marks only where frames exist, so a gap reads as a gap

#### Scenario: A layer with no frames
- **WHEN** a layer published no frames
- **THEN** the row reads "no frames" and its text alternative says the layer published no frames in this window

#### Scenario: No layers at all
- **WHEN** nothing is published
- **THEN** the ribbon states that no layer is published so there are no frames to show

### Requirement: The story is assembled only from hours the API actually served
The narrative strip SHALL request one real `/point` response per candidate hour, only for hours the timeline reports as publishing a product, and SHALL drop any card whose response was unavailable or carried no value. Nothing SHALL be interpolated between cards, and no card SHALL be generated from a model of the weather.

#### Scenario: An hour with no published product
- **WHEN** the timeline lists no product for a candidate hour
- **THEN** that hour is not requested and no card appears for it

#### Scenario: No card survives
- **WHEN** every candidate hour returns unavailable or valueless
- **THEN** the interface states that the 24-hour narrative is unavailable from this point response and that no forecast story has been inferred

### Requirement: A control that cannot change the request is disabled and says why
A selector SHALL only offer options the API actually returned; an empty option list SHALL leave the control disabled with the reason stated. A field the API reports in provenance but has no request parameter for SHALL be presented read-only with an explanation, because a control that accepts a choice and then discards it misstates what was requested. Model and product controls SHALL be offered only for catalogue sources that `/point` accepts as a `product` value; registry `state` is a ceiling that never reads `active` and SHALL NOT gate them.

#### Scenario: Run, member and level
- **WHEN** the expert controls are shown
- **THEN** run, member and level are read-only readouts of what the response reported, explaining that the point request has no parameter for them

#### Scenario: A catalogue that could not be read
- **WHEN** `/catalog` failed
- **THEN** the provider and product selectors are disabled with the catalogue error stated, rather than showing an empty but operable control

#### Scenario: A product whose source is not selectable
- **WHEN** a catalogue source maps to no `/point` `product` token
- **THEN** no model button or product option is rendered for it, rather than a control that no response could ever enable

#### Scenario: A model offered while no source is active
- **WHEN** the catalogue lists a source `/point` accepts as a product and its registry state is anything other than `active`
- **THEN** its model button is enabled and selecting it sends the endpoint's own product token, not the catalogue's prose product name

### Requirement: A station marker is a location picker, not a coverage claim
Station markers SHALL distinguish, by glyph and in words, four states: a live ingested source stands behind the station; a source is declared but has recorded no live retrieval; no source declares coverage of the place; and the status endpoint could not be read. The distinction SHALL NOT rest on colour alone and SHALL be repeated verbatim in the on-canvas label, the picker option and the text alternative.

#### Scenario: A station with a live source
- **WHEN** `/sources/status` reports a live retrieval for a source the station declares
- **THEN** the marker is a filled disc labelled "live source" and the text alternative names the source and its last retrieval

#### Scenario: A declared source that has retrieved nothing
- **WHEN** the declared source is catalogued but reports no live retrieval
- **THEN** the marker is an open ring labelled "no live retrieval" and the text says nothing has been ingested for the station

#### Scenario: A place no source claims
- **WHEN** a station declares no source ids — a headland inside a bounding box is not evidence that a station there reports
- **THEN** it is labelled "no ingested source" and described as a location to query, not an observing station

#### Scenario: The status endpoint could not be read
- **WHEN** `/sources/status` failed
- **THEN** every station reads "coverage unknown" and none is shown as live

### Requirement: Everything on the canvas has a text alternative
The interface SHALL provide a textual map alternative naming each active layer's state and the evidence at the selected point, SHALL name absent values explicitly as unknown with the reason, SHALL use real buttons and form controls with pressed/checked state rather than clickable divs, and SHALL restate a card's readings — including every unknown — in its accessible name.

#### Scenario: An absent reading
- **WHEN** a field has no value
- **THEN** it reads "Unknown — no <field> value was returned" rather than being omitted or shown blank

#### Scenario: A story card by ear
- **WHEN** a story card is focused
- **THEN** its accessible name restates temperature, dew point, precipitation probability and wind with their units, speaking each absent one as "unknown"

#### Scenario: Interactive elements
- **WHEN** a layer toggle, model choice or story card is rendered
- **THEN** it is a real `button` or input carrying `aria-pressed`, `aria-checked` or `aria-disabled`, so focus order and keyboard activation cannot drift from its role

#### Scenario: The map scale
- **WHEN** the map is zoomed
- **THEN** the scale bar is recomputed by the map from its real zoom and centre, never printed as a fixed distance

### Requirement: Location is never taken without permission and a refusal keeps the previous place
Browser geolocation SHALL be off until the reader asks for it, SHALL state that the position was used for the session only and was not sent until approved, and on denial, unavailability or timeout SHALL keep the currently selected place and name the alternatives.

#### Scenario: Permission denied
- **WHEN** the reader denies the location prompt
- **THEN** the notice says permission was denied, that the current place remains selected, and that coordinates, a station or the map may be used instead

#### Scenario: Geolocation unsupported
- **WHEN** the browser offers no geolocation
- **THEN** the same retention and alternatives are stated without a prompt

### Requirement: Unbuilt panels declare themselves unavailable rather than appearing to work
Panels with no evidence behind them SHALL say so plainly and SHALL NOT render a placeholder that could read as a result. This is the current specified behaviour for the comparison pane, the Skew-T panel and the drawn cross-section.

#### Scenario: The comparison pane
- **WHEN** the expert layout is shown
- **THEN** only one map pane is rendered and the second reads "Pane B unavailable — no second response-backed field is loaded. Comparison is not inferred."

#### Scenario: Skew-T
- **WHEN** the Skew-T panel is opened
- **THEN** it states that it is unavailable until a validated numeric profile response is loaded, and draws no diagram

#### Scenario: Drawn cross-section
- **WHEN** the cross-section panel is opened
- **THEN** it states that drawing and cross-section requests are not wired in this slice, and offers no drawing tool

#### Scenario: A profile with no levels
- **WHEN** `/profile` returns no usable levels
- **THEN** the panel states that profile visualization is not wired and that no vertical values are synthesized

### Requirement: Absent hazard evidence is not an all-clear
Alert text SHALL be taken verbatim from returned alert evidence fields. When no alert evidence was returned, the interface SHALL say that absence here is not an all-clear and direct the reader to the issuing authority, and SHALL NOT display a default or example hazard as though it were current.

#### Scenario: No alert evidence
- **WHEN** the point response carries no alert field
- **THEN** the hazard block reads "Hazard feed unavailable" with the note that absence is not an all-clear and the issuing authority should be checked

### Requirement: The interface SHALL disclose each layer's evidence basis

The interface SHALL state each layer's `evidence_basis` in words. Layers now reach the map by two different routes. A published artifact passed
ingestion, QC, manifest validation and atomic publication. A live-proxied layer
did not: it is fetched from the provider at request time and bypasses that spine
entirely. Both are genuinely retrieved, but they do not carry the same assurance,
and a reader cannot weigh what they are shown without being told which is which.
This disclosure is the condition under which the proxied route was permitted.

#### Scenario: A proxied forecast layer is labelled
- **WHEN** a layer reports `evidence_basis: "live_proxy"`
- **THEN** the interface states that it is live-proxied imagery and not a
  published artifact, in words, wherever that layer's state is shown
- **AND** the statement appears in the text alternative as well as the visual panel

#### Scenario: A published layer is not overclaimed
- **WHEN** a layer reports `evidence_basis: "published_artifact"` but its imagery
  is live-rendered
- **THEN** the interface does not describe the drawn image as a published artifact

#### Scenario: An absent or unrecognised basis fails closed
- **WHEN** a layer omits `evidence_basis` or declares an unrecognised value
- **THEN** the interface treats its basis as unknown and says so
- **AND** it does not assume the stronger of the two

### Requirement: A control SHALL NOT be permanently unreachable

The interface SHALL NOT render a control whose enabling condition the API can never satisfy. An affordance that can never be enabled is indistinguishable to the reader from
one that is merely disabled right now, and it misrepresents what the system can
do. Forecast model and product controls are gated on a source state the API
never emits by design, so every such control is permanently dead while
`/point?product=` is fully implemented.

#### Scenario: Product selection is reachable or absent
- **WHEN** the catalogue contains sources the API will accept as a product
- **THEN** those products are selectable
- **AND** no control remains rendered whose enabling condition the API cannot
  ever satisfy

#### Scenario: A genuinely unavailable option explains itself
- **WHEN** a product cannot be selected because of its own declared state
- **THEN** it is disabled with the reason drawn from the response, not from a
  predicate the API never satisfies
