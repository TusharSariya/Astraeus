## MODIFIED Requirements

### Requirement: Scheduling is derived from the registry and never spins
The scheduler SHALL run only registered adapters whose registry record permits
live ingestion and declares a reach. A forecast source's first attempt for a
run SHALL be scheduled at that run's nominal time plus the record's measured
publication latency, seeded from
`docs/research/wayfinder/planning-horizon-matrix.md`; where no latency has been
measured and no seed exists, the first attempt SHALL be at the run time itself
and SHALL NOT be offset by a guessed value. An observation or nowcast source
SHALL be scheduled at its native cadence: radar every 6 minutes, lightning
every 10, GOES every 10, METAR and SWOB hourly, SWPC every minute. A source
SHALL be rescheduled on its cadence regardless of outcome, so a failing source
neither spins nor drops out of the rotation.

#### Scenario: A failing source
- **WHEN** a source fails a cycle
- **THEN** it is rescheduled at its normal cadence rather than retried immediately or removed

#### Scenario: A non-schedulable source
- **WHEN** a registered adapter's registry record is not ingestible
- **THEN** the scheduler does not run it

#### Scenario: A forecast source with a measured latency
- **WHEN** GFS runs at 00z and its measured publication latency is about 5.3 h
- **THEN** the first attempt for that run is made at about 05:20Z rather than at 00:00Z, so a systematically early fetch does not manufacture cancellations

#### Scenario: A forecast source with no measured latency
- **WHEN** a record such as REPS carries neither a seed nor an observed latency
- **THEN** the first attempt is at the run time and the schedule records `latency_measured: false`, rather than adopting another source's offset

#### Scenario: An observation source
- **WHEN** radar declares a six-minute native cadence
- **THEN** it is scheduled every six minutes and not folded onto an hourly rotation

#### Scenario: A source with no declared reach
- **WHEN** a registered adapter's record declares no reach
- **THEN** the scheduler does not run it and names the missing reach, because an unbounded source cannot be said to cover any instant

### Requirement: Liveness distinguishes a live process from advancing ingestion
The heartbeat document SHALL carry a timestamp, per-source ingestion progress
and, for every forecast source, the observed publication instant of its most
recent run with the resulting re-measured latency estimate and its observation
count, written atomically, and SHALL be beaten before each source rather than
only between cycles, so a long serial cycle does not outlive the healthcheck
window. A re-measurement SHALL be written only from a publication this
deployment actually observed; a run that never appeared SHALL leave the previous
estimate and its observation count untouched. The healthcheck SHALL report
unhealthy for a missing, unparseable or stale heartbeat, and also when ingestion
has stalled.

#### Scenario: A long cycle
- **WHEN** a cycle walks many sources serially over minutes
- **THEN** the heartbeat is refreshed before each source and during a fetch, so the container is not killed mid-download leaving staging to clean up

#### Scenario: A source that used to work and stopped
- **WHEN** a source with a recorded past success has gone more than three nominal cadences without another
- **THEN** the healthcheck reports unhealthy naming the stalled sources, because a live process is not the same claim as advancing ingestion

#### Scenario: A source that never worked
- **WHEN** a source has never succeeded, a 404 endpoint, or a product this stack cannot yet decode
- **THEN** it is not counted as a stall; that is an ingestion fact to report through source status, not a reason to restart-loop the container

#### Scenario: A missing or unparseable heartbeat
- **WHEN** the heartbeat file is absent, malformed, or its timestamp is stale or in the future
- **THEN** the healthcheck reports unhealthy

#### Scenario: Latency is re-measured from an observed publication
- **WHEN** a run is first seen present at T+4 h 50 m against an estimate of T+5 h 18 m
- **THEN** the heartbeat records the observed instant, the estimate moves toward it, and the observation count increases

#### Scenario: A run that never appeared
- **WHEN** the poll window closes with the run still absent
- **THEN** no latency observation is written, the estimate and its count are unchanged, and the absence is reported as a cancelled attempt naming the run

## ADDED Requirements

### Requirement: A run is polled for, with a bounded poll and a declared fallback
After the first scheduled attempt for a forecast run, the worker SHALL poll
every ten minutes until that run appears. The poll SHALL be bounded: it SHALL
stop at the next scheduled run time for that source, at which point the missing
run SHALL be reported `cancelled` naming the run and the poll duration, and the
previous run SHALL stay visible and keep serving. For ECCC sources whose primary
path does not answer, the worker SHALL fall back to the dated WXO-DD Datamart
path declared on the record, and SHALL report which path answered. A fallback
path that is not declared on the record SHALL NOT be tried. No poll SHALL
substitute a neighbouring run, a fixture or any other value for the run it was
waiting for.

#### Scenario: A run that appears late
- **WHEN** a run appears at the fourth ten-minute poll
- **THEN** it is fetched, the observed publication instant is recorded, and no earlier poll's absence was reported as a failure

#### Scenario: A run that never appears
- **WHEN** a run is still absent when the next run of that source is due
- **THEN** polling stops, the attempt is `cancelled` naming the run and how long it was polled for, the previous run stays visible, and nothing is fetched in the missing run's place

#### Scenario: A latency estimate that is wrong in either direction
- **WHEN** the estimate is hours early or the run publishes hours before it
- **THEN** the early case is absorbed by polling with no cancellation until the bound, the late case fetches at the next poll after publication, and in neither case is an absence reported as an upstream failure or a stale run served as new

#### Scenario: The ECCC primary path is empty
- **WHEN** a `dd.weather.gc.ca` directory answers 200 with only `doc/`
- **THEN** the declared dated WXO-DD Datamart path is tried, the answering path is recorded on the artifact, and if neither answers the outcome is `cancelled` naming both

#### Scenario: A source with no declared fallback
- **WHEN** a source's primary path does not answer and its record declares no fallback
- **THEN** the outcome is `cancelled` naming the primary path, and no alternative path is inferred

### Requirement: A short cycle keeps the previous run serving the leads it lacks
When a source's newest retrieved run reaches less far than the previous
retrieved run of the same source (IFS and IFS ENS reach 144 h at 06z and 18z
against 360 h at 00z and 12z), the previous run SHALL be retained and SHALL keep
serving every instant the newer run does not reach. Both runs SHALL be labelled
with their own run time wherever they are served or drawn. The two runs SHALL
NOT be blended, averaged or joined into one series. Where neither run reaches an
instant, that instant SHALL be uncovered by that source and reported so, never
extrapolated from the last lead.

#### Scenario: A 06z IFS run
- **WHEN** the 06z run reaches 144 h and the retained 00z run reached 360 h
- **THEN** instants to 144 h are served from the 06z run and instants beyond it from the 00z run, each labelled with its run time

#### Scenario: The join is visible
- **WHEN** both runs of one source appear in one response or one series
- **THEN** they are two labelled pieces of evidence with the run change shown, and no value is interpolated across the join

#### Scenario: No previous run was retained
- **WHEN** a short-cycle run is the only run retained for that source
- **THEN** instants beyond its reach are uncovered by that source with the reason, and nothing is extrapolated from its final lead
