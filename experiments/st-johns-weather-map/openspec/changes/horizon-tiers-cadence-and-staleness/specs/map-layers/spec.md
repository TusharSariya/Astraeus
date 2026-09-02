## MODIFIED Requirements

### Requirement: A layer declares a staleness tolerance and renders nothing beyond it
Every layer SHALL publish `staleness_tolerance_seconds`. It SHALL be one native
interval of that layer, the layer's own derived cadence: 6 minutes for radar,
10 minutes for lightning and GOES, 1 hour for hourly observations and hourly
model frames, and 3 or 6 hours for the coarser planning steps (wayfinder
ticket 23; this replaces the half-cadence rule of
`frame-fallback-and-viewport-layout`, on which this change is applied). A
layer whose cadence cannot be derived SHALL receive a bounded unknown-cadence
tolerance of 900 seconds rather than none, so a lone frame cannot answer for
the whole window. The tolerance SHALL separate quiet display from disclosed
fallback. When the requested time is within the tolerance of the nearest
published frame, that frame is drawn with its signed offset displayed. Beyond
the tolerance the client MAY draw a neighbouring published frame instead of
nothing, but only with a mandatory, visible on-map disclosure naming that
frame's real time and its offset from the requested time, because an
undisclosed older frame would misdate the evidence. Fallback SHALL be
constrained by group: observed groups (`satellite`, `observation`, `alert`,
and any layer whose group is undeclared) SHALL fall back only to an earlier
frame, and SHALL NOT be drawn by fallback for a requested instant after the
session reference; forecast groups (`forecast_proxy`, `published_model`,
`rendered_grid`) MAY fall back to the nearest frame in either direction. When
nothing may be drawn, the same disclosure surface SHALL state the reason. A
layer that declared no numeric tolerance still resolves no quiet frame, and
its every drawn frame is a disclosed fallback.

#### Scenario: Within tolerance
- **WHEN** the requested time is nearer the resolved frame than to any other, within one native interval
- **THEN** the frame is drawn, and its signed offset from the requested time is displayed beside it, with no fallback note

#### Scenario: Beyond tolerance
- **WHEN** the nearest frame of an hourly forecast layer is 83 minutes from the requested time
- **THEN** that frame is drawn, and a visible on-map note names the layer, the frame's real time and "83 min later" (or earlier), so the reader can see the evidence is not the instant they asked for

#### Scenario: Beyond tolerance, an observed layer
- **WHEN** the nearest frame of a six-minute radar layer is an hour before the requested past instant
- **THEN** the previous frame is drawn with the same visible disclosure, and a later frame is never chosen for it

#### Scenario: A layer that declared no tolerance
- **WHEN** a layer item carries no numeric `staleness_tolerance_seconds`
- **THEN** no frame is drawn quietly for it: any frame shown is a disclosed fallback under the group rules, never an adopted default tolerance

#### Scenario: An observed layer at a future instant
- **WHEN** an observed layer is requested for an instant after the session reference, beyond its tolerance
- **THEN** nothing is drawn for it, and the disclosure states that observed imagery has no frames for future instants

#### Scenario: A layer with no frames
- **WHEN** a layer published no times
- **THEN** no frame resolves and the disclosure states that the layer published no frames

#### Scenario: A three-hourly planning layer
- **WHEN** a planning layer publishes three-hourly steps
- **THEN** its tolerance is three hours, one native interval, rather than the ninety minutes a half-cadence rule would give, and a frame 100 minutes away is drawn quietly

## ADDED Requirements

### Requirement: Every frame carries its run time and its run staleness
Every layer frame SHALL carry the run time of the run that produced it and a
`run_stale` flag computed as more than twice that source's declared producer run
cadence. Frame staleness and run staleness SHALL be reported as two separate
facts, so a frame inside its own tolerance can still be known to come from a
superseded run. `run_stale` SHALL NOT withhold a frame. A frame whose run time
is unknown SHALL be served with `run_time: null` and `run_stale: null` and SHALL
NOT be reported as current; an observation layer with no run concept SHALL carry
both as null with that reason, which is not a staleness claim.

#### Scenario: A fresh frame from a stale run
- **WHEN** a day-ten frame from a thirty-hour-old six-hourly run is requested
- **THEN** it resolves inside its six-hour tolerance and is served with `run_stale: true` and its run time

#### Scenario: A frame with no run time
- **WHEN** an artifact declares no run reference time
- **THEN** `run_time` and `run_stale` are null with the reason, and the frame is not presented as current

#### Scenario: Two runs of one source in one layer index
- **WHEN** a short cycle leaves the previous run serving the far leads
- **THEN** each frame carries its own run time, and the layer index shows both runs rather than one merged time axis
