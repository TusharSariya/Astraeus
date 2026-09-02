## ADDED Requirements

### Requirement: An aged-out frame is a third absence state
A value absent because this deployment held the frame and purged it when its
valid time left the window SHALL be reported as `aged_out` carrying
`last_valid_time`, rendered to the reader as `aged out at <last valid time>`.
It SHALL be a third absence state beside `null` (never retrieved) and
`blocked` (licence, credential or partnership), and SHALL be distinct from
`retrieval failed` (an attempt was made and broke, which a retry may clear)
and from `available-not-stored` (the producer publishes the field and this
deployment does not fetch it, which no retry clears). `aged_out` SHALL NOT be
reported without a recorded last valid time, and an unreadable store SHALL
report `unavailable` rather than any absence state. The reader SHALL be shown
all of these states by name, with a legend, so the absence of a badge never
carries meaning.

#### Scenario: A purged forecast frame
- **WHEN** a request names an instant a source once covered and whose frames have been purged for leaving the window
- **THEN** the field reports `aged_out` with the last valid time the store held, naming the source

#### Scenario: Aged out is not retrieval failed
- **WHEN** one source's frame aged out and another source's fetch broke for the same instant
- **THEN** the two are reported as different states, and only the second is presented as a condition a retry may clear

#### Scenario: Aged out is not never retrieved
- **WHEN** a source has never published here
- **THEN** the field reports `null`, never `aged_out`, because there is no last valid time to state

#### Scenario: The last valid time cannot be read
- **WHEN** the store cannot answer for a stream's last valid time
- **THEN** the response reports `unavailable` naming that failure, rather than guessing between `aged_out` and `null`

#### Scenario: Every state has a badge
- **WHEN** the map or a reading shows an absent value
- **THEN** its state is named on screen as one of null, blocked, aged out, retrieval failed or available-not-stored, and the legend lists all five

## MODIFIED Requirements

### Requirement: The window is exactly three hours back and twenty-four forward
The evidence window SHALL be a sliding valid-time window running from `now - 24h` to `now + 14d` inclusive, giving 361 hourly steps. Both boundaries SHALL be inclusive. It SHALL slide continuously with the request clock rather than being pinned to a run or a cycle. The same window SHALL bound the API's accepted `valid_time`, the ingestion `FetchWindow`, manifest out-of-window QC and what the store retains, and SHALL be defined in exactly one place so those four cannot drift apart. A request for an instant inside the window that no retained frame covers SHALL be answered with an absence state naming why: `aged_out` where a frame was held and purged, `null` where none was ever held.

#### Scenario: The timeline reports the window
- **WHEN** `/timeline` is requested
- **THEN** it returns `start = now-24h`, `end = now+14d` and exactly 361 items, each carrying its UTC valid time and the same instant in `America/St_Johns`

#### Scenario: A time outside the window
- **WHEN** `/point`, `/profile` or `POST /cross-section` is given a `valid_time` before `now-24h` or after `now+14d`
- **THEN** the request is refused with 422 naming the available window, rather than answered with the nearest evidence and rather than answered with an aged-out state, because the instant is outside what this deployment ever serves

#### Scenario: The boundaries themselves
- **WHEN** exactly `now-24h` or exactly `now+14d` is requested
- **THEN** the request is accepted

#### Scenario: A naive timestamp
- **WHEN** a `valid_time` is supplied with no UTC offset
- **THEN** it is refused with 422, because an offsetless instant cannot be placed in the window

#### Scenario: Local time is zone-derived across DST
- **WHEN** timeline items are rendered in Newfoundland time
- **THEN** the offset comes from the `America/St_Johns` zone database rather than a fixed offset, so it is correct on either side of a DST transition

### Requirement: An hour is listed only when a published artifact actually covers it
The timeline SHALL list a source under an hour only when that source published a frame belonging to that hour and that frame is still retained. Frames landing off the hour SHALL be floored into the hour they belong to, so an hour that genuinely holds evidence is not reported empty; the frame's own exact time stays exact in `/layers`. An hour with no retained frame SHALL carry an empty product list, never a generated one, and SHALL state which of its sources are `aged_out` and which are `null`, so an emptied hour near the back edge is not read as an hour nothing ever covered.

#### Scenario: A frame at six minutes past
- **WHEN** radar publishes a frame at 02:18Z
- **THEN** the 02:00Z hour lists `eccc-radar`, and the hourly bucket says only that the hour holds a published frame, not that the frame is at :00

#### Scenario: Nothing is published for an hour
- **WHEN** no source published a frame belonging to an hour, or every frame that did has been purged
- **THEN** that item's `available_products` is empty and it names the aged-out sources with their last valid times

#### Scenario: Nothing is published at all
- **WHEN** the live store returns no coverage
- **THEN** the timeline is `data_mode: "unavailable"` with all 361 items present, empty product lists, and a notice saying no artifact is currently published for this window

#### Scenario: The store cannot be read
- **WHEN** the live store is unreachable or raises while resolving coverage
- **THEN** the timeline is `unavailable` with a notice naming that failure, and no hour is said to hold a product and no hour is said to have aged out

### Requirement: Live readiness requires evidence inside the window
Live readiness SHALL require a configured data mode, a reachable live store, a registry catalogue, a job store, and published artifacts whose valid times fall inside the current sliding window. Anything less SHALL report not ready, however healthy the process is. A store holding only frames that have aged out SHALL report not ready, and SHALL say so as aged out rather than as never retrieved.

#### Scenario: Store reachable but no current evidence
- **WHEN** the live store answers but no retained frame falls inside `now-24h .. now+14d`
- **THEN** `/ready` reports `ready: false` with `evidence_boundary: false` and `data_mode: "unavailable"`, naming aged out where a last valid time is recorded

#### Scenario: A fixture deployment says so
- **WHEN** `/ready` is requested in fixture mode
- **THEN** it reports `ready: true` with `data_mode: "fixture"` and `live_store: false`, so readiness cannot be mistaken for live evidence

#### Scenario: An unconfigured deployment
- **WHEN** `/ready` is requested with no valid data mode
- **THEN** it reports `ready: false` with `data_mode_configured: false`
