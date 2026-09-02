## ADDED Requirements

### Requirement: The timeline shows the tier boundary and the step change beyond it
The timeline SHALL mark the 24 h boundary between the core and planning tiers,
and SHALL make the step change across it visible: the change in step spacing
(hourly to three-hourly or six-hourly) and the change in which sources cover the
instants. The boundary SHALL be a marked position on the axis, not a colour
alone, and SHALL carry a text alternative naming both tier ranges. Where the
step change cannot be determined because nothing is published beyond the
boundary, the timeline SHALL say the planning tier holds no published frames
rather than drawing a continuous axis that implies coverage.

#### Scenario: The boundary is marked
- **WHEN** the timeline is rendered with frames on both sides of 24 h ahead
- **THEN** the 24 h position is marked, the spacing change is visible, and the text alternative names the core and planning ranges

#### Scenario: Nothing published beyond the boundary
- **WHEN** no retrieved run covers any instant past 24 h ahead
- **THEN** the planning side reads that it holds no published frames, and the axis does not continue as though it did

#### Scenario: The boundary is not colour alone
- **WHEN** the reader cannot distinguish the boundary colour
- **THEN** the marked position and its label still identify the boundary

### Requirement: Each instant shows the sources covering it with their run times
For the selected instant the interface SHALL list every source the API reports
as covering it, each with its run time, its frame offset and its `run_stale`
flag where one applies. A source covering the instant SHALL never be hidden for
belonging to one tier or another, and no source in the list SHALL be presented
as the primary or as a check on another. An instant no source covers SHALL read
that nothing covers it, distinctly from a failed request and from a source that
covered it and published no value. A `run_stale` source SHALL be shown with its
flag and its run age, never withheld and never shown unmarked.

#### Scenario: Several sources at one instant
- **WHEN** three retrieved runs cover the selected instant
- **THEN** all three are listed with their own run times and offsets, in a stable order, with none marked primary

#### Scenario: A stale run at the selected instant
- **WHEN** a covering run is older than twice its producer cadence
- **THEN** it is listed with a `run_stale` badge and its run age, and its frame is still drawn

#### Scenario: Nothing covers the instant
- **WHEN** the API reports no source covering the selected instant
- **THEN** the list reads that nothing covers this instant, distinct from a request that failed and from a source that published no value

#### Scenario: The coverage request failed
- **WHEN** the coverage request errors or returns an unrecognised shape
- **THEN** the list reports an error naming the reason and claims no coverage either way

### Requirement: A run change within one source is labelled, never smoothed
Where two runs of one source serve one series, because a short cycle left the
previous run covering the far leads, the interface SHALL label each segment with
its run time and SHALL mark the instant at which the run changes. It SHALL NOT
draw the join as one continuous series, SHALL NOT interpolate across it and
SHALL NOT relabel either segment with the other's run time. Where the run time
of a segment is unknown, that segment SHALL be shown as unlabelled with the
reason rather than adopting the neighbouring run's time.

#### Scenario: The 06z short cycle
- **WHEN** the 06z IFS run covers to 144 h and the retained 00z run covers beyond it
- **THEN** both segments are labelled with their run times and the change point is marked

#### Scenario: No smoothing across the join
- **WHEN** a series crosses the run change
- **THEN** no value is drawn between the last frame of one run and the first of the other beyond the layer's own disclosed frame-fallback rules

#### Scenario: A segment with no run time
- **WHEN** a segment's run time is null
- **THEN** it is labelled unknown with the reason, and does not inherit the other segment's run time
