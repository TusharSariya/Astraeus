## Purpose
Define the single 28-hour evidence window — `now-3h` through `now+24h` — that bounds every request, ingestion and display in this experiment, and the hourly timeline index that reports which hours actually hold a published frame.

## Requirements

### Requirement: The window is exactly three hours back and twenty-four forward
The evidence window SHALL run from `now - 3h` to `now + 24h` inclusive, giving 28 hourly steps. Both boundaries SHALL be inclusive. The same window SHALL bound the API's accepted `valid_time`, the ingestion `FetchWindow`, and manifest out-of-window QC.

#### Scenario: The timeline reports the window
- **WHEN** `/timeline` is requested
- **THEN** it returns `start = now-3h`, `end = now+24h` and exactly 28 items, each carrying its UTC valid time and the same instant in `America/St_Johns`

#### Scenario: A time outside the window
- **WHEN** `/point`, `/profile` or `POST /cross-section` is given a `valid_time` before the start or after the end
- **THEN** the request is refused with 422 naming the available window, rather than answered with the nearest evidence

#### Scenario: The boundaries themselves
- **WHEN** exactly `now-3h` or exactly `now+24h` is requested
- **THEN** the request is accepted

#### Scenario: A naive timestamp
- **WHEN** a `valid_time` is supplied with no UTC offset
- **THEN** it is refused with 422, because an offsetless instant cannot be placed in the window

#### Scenario: Local time is zone-derived across DST
- **WHEN** timeline items are rendered in Newfoundland time
- **THEN** the offset comes from the `America/St_Johns` zone database rather than a fixed offset, so it is correct on either side of a DST transition

### Requirement: An hour is listed only when a published artifact actually covers it
The timeline SHALL list a source under an hour only when that source published a frame belonging to that hour. Frames landing off the hour SHALL be floored into the hour they belong to, so an hour that genuinely holds evidence is not reported empty; the frame's own exact time stays exact in `/layers`. An hour with no published frame SHALL carry an empty product list, never a generated one.

#### Scenario: A frame at six minutes past
- **WHEN** radar publishes a frame at 02:18Z
- **THEN** the 02:00Z hour lists `eccc-radar`, and the hourly bucket says only that the hour holds a published frame — not that the frame is at :00

#### Scenario: Nothing is published for an hour
- **WHEN** no source published a frame belonging to an hour
- **THEN** that item's `available_products` is empty

#### Scenario: Nothing is published at all
- **WHEN** the live store returns no coverage
- **THEN** the timeline is `data_mode: "unavailable"` with all 28 items present, empty product lists, and a notice saying no artifact is currently published for this window

#### Scenario: The store cannot be read
- **WHEN** the live store is unreachable or raises while resolving coverage
- **THEN** the timeline is `unavailable` with a notice naming that failure, and no hour is said to hold a product

### Requirement: Live readiness requires evidence inside the window
Live readiness SHALL require a configured data mode, a reachable live store, a registry catalogue, a job store, and published artifacts whose valid times fall inside the current window. Anything less SHALL report not ready, however healthy the process is.

#### Scenario: Store reachable but no current evidence
- **WHEN** the live store answers but no published frame falls inside `now-3h .. now+24h`
- **THEN** `/ready` reports `ready: false` with `evidence_boundary: false` and `data_mode: "unavailable"`

#### Scenario: A fixture deployment says so
- **WHEN** `/ready` is requested in fixture mode
- **THEN** it reports `ready: true` with `data_mode: "fixture"` and `live_store: false`, so readiness cannot be mistaken for live evidence

#### Scenario: An unconfigured deployment
- **WHEN** `/ready` is requested with no valid data mode
- **THEN** it reports `ready: false` with `data_mode_configured: false`

### Requirement: Coordinates outside the Avalon core are refused
`/point`, `/profile` and `POST /cross-section` SHALL refuse any coordinate outside the Avalon core box (46.5S, -55.0W, 48.5N, -51.0E) with 422, inclusive on the boundary, rather than answering from evidence about somewhere else.

#### Scenario: A coordinate outside coverage
- **WHEN** a request names a coordinate beyond the core box
- **THEN** it is refused with 422 stating the coordinate is outside the Avalon core coverage

#### Scenario: A coordinate exactly on the boundary
- **WHEN** a request names a coordinate on the box edge
- **THEN** it is accepted
