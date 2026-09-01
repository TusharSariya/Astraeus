## ADDED Requirements

### Requirement: The timeline offers a playback transport over the same clock the scrubber moves
The dock SHALL offer play/pause, faster, slower and reverse controls beside
the scrubber. Speed SHALL be one of 1, 2, 4, 8, 16 or 32 weather-minutes per
wall-clock second, starting at 1, doubling or halving one rung per press and
clamping at both ends with the unavailable control disabled. Direction SHALL
be independent of speed. Playback SHALL advance only the selected instant,
which every layer then resolves under the existing frame rules, so a played
instant is identical to the same instant reached by scrubbing. Playback
SHALL advance by elapsed wall-clock time between animation frames, SHALL
continue from the opposite edge on reaching either end of the window, and
SHALL NOT leave the window whatever the gap between frames. Any manual time
action - the scrubber, a quick jump, a keyboard step, a frame marker, a
story card or a jump from the map - SHALL stop playback. Playback SHALL NOT
change the display-interpolation setting and SHALL NOT snap to the frame
axis.

#### Scenario: Playing at a chosen speed
- **WHEN** the reader presses faster twice and then play
- **THEN** the selected instant advances by four weather-minutes per second
  of wall-clock time, and the readout names that speed

#### Scenario: Reaching the end of the window
- **WHEN** playback passes `now+24h` (or `now-3h` in reverse)
- **THEN** it continues from the opposite edge and the selected instant
  remains inside the window

#### Scenario: A hand on the timeline
- **WHEN** the reader scrubs, jumps or steps while playback is running
- **THEN** playback stops at the instant the reader chose and does not
  resume by itself

#### Scenario: Playback invents no imagery
- **WHEN** playback runs with display interpolation off
- **THEN** each layer shows its own retrieved frames as the clock passes
  them, with the same disclosures a scrub to those instants would carry, and
  the interpolation setting stays off

### Requirement: The timeline marks the instants the active layers actually published
Beneath the scrubber the interface SHALL mark every instant an active
visible layer published inside the window, positioned on the scrubber's own
scale, with a colour identifying the layer and no other meaning. A layer's
colour SHALL be stable when other layers are toggled. An instant published
by more than one layer SHALL be marked once, carrying every publishing
layer, so no marker is hidden beneath another. Each marker SHALL be
operable by keyboard and pointer, SHALL name the publishing layers and its
Newfoundland clock time to assistive technology, and SHALL move the
selected instant to exactly that published instant. Markers SHALL come only
from the frame times the API returned; no instant SHALL be marked that no
layer published.

#### Scenario: Jumping to a published frame
- **WHEN** the reader activates a marker
- **THEN** the selected instant becomes that published instant exactly, and
  the layer resolves to that frame with no fallback disclosure

#### Scenario: Two layers publishing the same instant
- **WHEN** two active layers both published a frame at the same instant
- **THEN** one marker is shown carrying both layers' colours, and activating
  it names both layers

#### Scenario: A layer with no time axis
- **WHEN** an active layer published no frame times
- **THEN** it contributes no markers and is named as having no published
  frame axis, rather than being silently absent from the rail

#### Scenario: Nothing published in the window
- **WHEN** no active layer published a frame inside the window
- **THEN** the rail states that in words rather than showing an empty strip
