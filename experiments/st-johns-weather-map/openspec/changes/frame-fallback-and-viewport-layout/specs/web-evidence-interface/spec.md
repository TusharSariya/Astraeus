## MODIFIED Requirements

### Requirement: Each layer answers the requested instant from its own frames or declines
For each active layer the client SHALL resolve the requested instant against
that layer's own declared times. The nearest frame inside the layer's declared
staleness tolerance is drawn quietly with its signed offset, as before. Outside
the tolerance the layer SHALL fall back to a neighbouring published frame —
previous-only for observed groups (`satellite`, `observation`, `alert`,
undeclared), and never for an observed instant after the session reference;
nearest in either direction for forecast groups — and every fallback SHALL be
disclosed in a visible on-map note naming the layer, the drawn frame's real
time and its offset, with the same sentence carried in the text alternative and
the layer's drawer row. A layer with nothing drawable SHALL appear in the same
note surface with the reason. Stored features are still fetched only for a
frame the layer declared; no feature request is invented for an instant the
layer did not publish.

#### Scenario: A frame resolves
- **WHEN** the nearest frame is inside tolerance
- **THEN** that frame is fetched and drawn, the frame time plus a human offset such as "4 min earlier" is shown beside the layer, and no fallback note appears for it

#### Scenario: No frame within tolerance
- **WHEN** the requested instant falls between an hourly forecast layer's frames, beyond its tolerance
- **THEN** the nearest frame is drawn and the on-map note reads like "showing 14:00 NDT (23 min later than the selected time)", repeated in the text alternative and the drawer row

#### Scenario: An observed layer scrubbed into the future
- **WHEN** an observed layer is active and the scrubbed instant is after the session reference, beyond tolerance
- **THEN** nothing is drawn for that layer and the note states that observed imagery has no frames for future instants

#### Scenario: The frame returned nothing
- **WHEN** a resolved frame's feature request succeeds but returns zero features
- **THEN** the layer reports that the frame published no values and that nothing has been drawn in their place — distinct from an error and from no frame at all

#### Scenario: The frame could not be read
- **WHEN** the feature request fails or returns an incompatible schema
- **THEN** the layer reports an error state naming the reason, and draws nothing

### Requirement: The scrubber is continuous at a resolution finer than the fastest layer
The timeline control SHALL span `-3h` to `+24h` and SHALL be visible together
with the map, docked along its bottom edge, so scrubbing never requires
scrolling away from the canvas. The selected time SHALL be an exact instant.
When display interpolation is off and at least one active visible layer holds
frames in the window, a scrub action SHALL snap the selected instant to the
closest member of the union of the active layers' published frame instants
(ties resolving earlier), so the selected time is always a real frame instant
of at least one drawn layer; keyboard arrows SHALL move between those
instants, and the control's spoken value SHALL name the real instant and state
that it snapped. With interpolation on, or with no active layer holding
frames, the scrub SHALL move freely in five-minute steps, finer than the
six-minute radar cadence. Toggling a layer SHALL NOT move the selected
instant; only a scrub action snaps. The session reference instant SHALL be
fixed once, so resolved frames do not slide under the reader between renders.
Quick jumps SHALL be offered for the standard offsets and SHALL snap by the
same rule.

#### Scenario: Scrubbing to a radar frame
- **WHEN** interpolation is off, radar is the only active layer, and the reader drags the scrubber between two radar frames
- **THEN** the selected instant lands exactly on the closer frame's own timestamp, and the control's value text names that instant and says it snapped

#### Scenario: Keyboard movement between frames
- **WHEN** interpolation is off and the reader presses an arrow key on the scrubber
- **THEN** the selection moves to the adjacent frame instant in the union, not by a fixed step

#### Scenario: Free scrubbing
- **WHEN** interpolation is on, or no active layer holds a frame in the window
- **THEN** the scrubber moves in five-minute steps exactly as before

#### Scenario: A layer toggle does not move the clock
- **WHEN** the reader toggles a layer on or off while snapping is active
- **THEN** the selected instant stays where it is, even if it is no longer a member of the new union, until the next scrub action

#### Scenario: The reference does not drift
- **WHEN** the component re-renders
- **THEN** the window and every resolved frame are computed from the same session reference instant, not from a fresh clock read

## ADDED Requirements

### Requirement: Forecast display interpolation is opt-in, off by default, and disclosed as compositing
The interface MAY offer a display-interpolation setting for forecast imagery.
It SHALL default off and persist per browser only. When on, a forecast layer
whose requested instant lies strictly between two published frames SHALL be
drawn as both real retrieved frames composited at fractional opacities
weighted by the time fraction, and the on-map note SHALL name both frame times
and call the result display compositing — never evidence, and never a claim
that intermediate values exist. The setting SHALL never apply to observed
groups, to stored features, or to any data path: `/point` readings, stories
and feature requests remain frame-exact. The toggle's own wording SHALL state
that it is display-only.

#### Scenario: Default off
- **WHEN** the interface loads with no stored preference
- **THEN** interpolation is off and every layer resolves by the snap rules alone

#### Scenario: A blended forecast layer is disclosed
- **WHEN** interpolation is on and the selected instant sits 20 minutes past an hourly forecast frame
- **THEN** the previous and next frames are both drawn at fractional opacities and the note names both frame times as a display composite

#### Scenario: Observed layers are untouched
- **WHEN** interpolation is on and an observed layer is active
- **THEN** that layer resolves exactly as it does with interpolation off

### Requirement: The workbench fills the viewport with a docked timeline and a right evidence strip
In the default mode the map SHALL fill the remaining viewport, the conditions
panel SHALL be a scrollable strip on the right, and the timeline dock SHALL
stay visible along the bottom. The weather story and coverage ribbon SHALL be
reachable from the dock as an expandable panel over the map, opened and closed
by a real button whose state is exposed, with Escape closing it and returning
focus. Every text alternative, status region and keyboard behaviour that
existed in the scrolling layout SHALL survive the restructure, and the shell
SHALL keep the map on screen in the loading, unavailable, fixture and live
states alike.

#### Scenario: Map and timeline visible together
- **WHEN** the default mode is shown at desktop size
- **THEN** the map fills the space beside the conditions strip and the scrubber dock is visible without scrolling

#### Scenario: The story panel expands from the dock
- **WHEN** the reader activates the story toggle
- **THEN** the story and coverage ribbon slide up over the map, the toggle exposes its expanded state, and Escape closes the panel and returns focus to the toggle

#### Scenario: A status banner does not displace the map
- **WHEN** the API is still being checked, or no live evidence was retrieved
- **THEN** the banner is shown and the map stage remains on screen at viewport height
