## ADDED Requirements

### Requirement: Status surfaces never reflow the workspace
In the full-viewport shell, the data-mode status banner (loading, fixture,
mixed, unavailable) SHALL overlay the shell rather than participate in its
layout, and the timeline dock's snap note SHALL occupy a reserved line, so
that no scrub-driven state change moves the map, the dock or the
conditions strip. The banner's visibility rules are unchanged: it appears
exactly when the data mode is not live, and fixture/mixed watermarking
stays on screen.

#### Scenario: Scrubbing while the point refreshes
- **WHEN** a scrub tick sets the point data mode to loading and back to
  live
- **THEN** the banner appears and disappears as an overlay and no element
  of the workspace changes size or position

#### Scenario: Fixture mode still watermarks
- **WHEN** the app runs on fixtures
- **THEN** the watermark banner is visible over the shell exactly as
  before, only without occupying a layout row
