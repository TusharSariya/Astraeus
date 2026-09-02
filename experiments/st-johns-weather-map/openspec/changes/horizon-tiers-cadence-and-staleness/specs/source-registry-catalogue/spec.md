## ADDED Requirements

### Requirement: Every source declares its reach
Every registry record that can feed a forecast or observation frame SHALL
declare its reach as the earliest and latest valid time it can cover relative
to its run time, per run cycle where cycles differ (IFS and IFS ENS: 360 h at
00z and 12z, 144 h at 06z and 18z). Reach SHALL be a declared registry fact,
never inferred from what a fetch happened to return. A record with no declared
reach SHALL NOT be schedulable, SHALL cover no instant, and SHALL be reported
with the reason, because a source that will not say how far it reaches cannot
be shown to answer any instant.

#### Scenario: A source with no declared reach
- **WHEN** a schedulable record declares no reach
- **THEN** `registry/audit.py` fails naming the record, the scheduler does not run it, and it appears in no instant's coverage

#### Scenario: A cycle-dependent reach
- **WHEN** the IFS record declares 360 h at 00z and 12z and 144 h at 06z and 18z
- **THEN** each run's coverage is computed from its own cycle's reach, not from the record's longest reach

#### Scenario: A fetch that returned less than the declared reach
- **WHEN** a run publishes fewer leads than its declared reach promised
- **THEN** the instants beyond the leads actually retrieved are uncovered by that run and reported so, and the declared reach is not silently rewritten from the fetch

### Requirement: Run cadence and publication latency are declared and measured separately
Every forecast record SHALL declare its producer run cadence. Publication
latency SHALL be a measured quantity held beside it, carrying the estimate, the
number of observations behind it and the instant of the most recent
observation, seeded from
`docs/research/wayfinder/planning-horizon-matrix.md` (ICON about T+3.5 h, GFS
about T+5.3 h, ECMWF about T+7.6 h). A record this deployment has observed no
publication for SHALL report `latency_measured: false` (the registry block's
own flag is `measured`) and SHALL NOT have a default substituted, because an
unmeasured latency is not a producer promise. Its estimate SHALL be the
research seed where one exists and `null` where none does; a non-null estimate
SHALL name the basis it came from, and a basis of `"none"` SHALL be refused.

#### Scenario: A seeded but unobserved latency
- **WHEN** a record carries a research seed value and the deployment has observed no publication
- **THEN** the estimate is served as the seed with `latency_measured: false` and its observation count zero, and the reader is told the value is a research measurement rather than this deployment's

#### Scenario: A source with no latency at all
- **WHEN** a record such as GEPS or REPS has neither a seed nor an observation
- **THEN** the estimate is `null`, `latency_measured` is false, and scheduling falls back to the run time itself rather than to a guessed offset

#### Scenario: A cadence that cannot be resolved
- **WHEN** a record's prose states no resolvable run cadence
- **THEN** the record is not schedulable, as it is today for an unresolvable freshness threshold, and no cadence is defaulted into existence
